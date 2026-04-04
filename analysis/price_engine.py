from __future__ import annotations
"""
Price Engine — 메모리 가격 사이클 분석 (v4.0 신규)
====================================================
문서 3(가격 변곡점 로직)을 Semi-Intel에 이식.

핵심 로직:
  1. Inventory Proxy: 누적 수급 갭 기반 재고 상태 추정
  2. Momentum-Fundamental Divergence: 가격 모멘텀 vs 펀더멘털 괴리
  3. Price Regime Classification: 4-국면 (tight/balanced/loose) 분류
"""

import numpy as np
import pandas as pd
from loguru import logger


class PriceEngine:
    """
    메모리 가격 사이클 분석 엔진

    사용법:
        engine = PriceEngine(db)
        result = engine.analyze()
        print(result)  # {'regime': 'tight', 'inventory_proxy': 0.8, ...}
    """

    def __init__(self, db):
        self.db = db

    def _load_series(self, code: str, months: int = 36) -> pd.Series | None:
        """DB에서 시계열 로드"""
        from datetime import date, timedelta
        cutoff = date.today() - timedelta(days=months * 30)
        data = self.db.get_series_data(code, start_date=cutoff)
        if not data:
            return None
        s = pd.Series(
            [d["value"] for d in data],
            index=pd.DatetimeIndex([d["date"] for d in data]),
        )
        return s.sort_index().dropna()

    def compute_inventory_proxy(self) -> dict:
        """
        누적 수급 갭(Cumulative Supply-Demand Gap) 기반 재고 프록시 산출.

        아이디어 (문서 3):
          Gap(t) = Supply(t) - Demand(t)
          CumGap(t) = CumGap(t-1) + Gap(t)
          InventoryProxy(t) = clip(zscore(CumGap(t)), lower=-2, upper=+3)

        현재 구현에서는:
          - Supply proxy: INDPRO (산업생산) — 반도체 공급 증가율
          - Demand proxy: DRAM_PROXY + SOX 모멘텀 — 수요 강도
          - A=2 (바닥 민감도 높게), B=3 (상단 완충 더 크게)

        Returns:
            dict: {
              'inventory_proxy': float (-2 ~ +3),
              'interpretation': str,
              'cumulative_gap_zscore': float,
            }
        """
        supply = self._load_series("INDPRO", months=36)
        dram = self._load_series("MU", months=36)   # Micron — DRAM proxy
        if supply is None:
            return {"inventory_proxy": 0.0, "interpretation": "데이터 부족", "cumulative_gap_zscore": 0.0}

        # 월별 리샘플로 통일
        try:
            supply_m = supply.resample("ME").last().pct_change().dropna()
            if dram is not None:
                demand_m = dram.resample("ME").last().pct_change().dropna()
                # 공통 인덱스로 정렬
                common = supply_m.index.intersection(demand_m.index)
                gap = supply_m.loc[common] - demand_m.loc[common]
            else:
                gap = supply_m * 0  # 데이터 없으면 0 갭
        except Exception as e:
            logger.warning(f"PriceEngine inventory proxy error: {e}")
            return {"inventory_proxy": 0.0, "interpretation": "계산 오류", "cumulative_gap_zscore": 0.0}

        if len(gap) < 6:
            return {"inventory_proxy": 0.0, "interpretation": "데이터 부족 (6개월 미만)", "cumulative_gap_zscore": 0.0}

        # 누적 갭 + z-score + clip
        cum_gap = gap.cumsum()
        if cum_gap.std() > 0:
            z = (cum_gap - cum_gap.mean()) / cum_gap.std()
        else:
            z = cum_gap * 0
        proxy = float(np.clip(z.iloc[-1], -2, 3))

        if proxy > 1.5:
            interp = "공급 과잉 (재고 누적↑) — 가격 하방 압력"
        elif proxy > 0.5:
            interp = "공급 소폭 우위 — 가격 안정~약세 전망"
        elif proxy > -0.5:
            interp = "수급 균형 — 가격 중립"
        elif proxy > -1.5:
            interp = "공급 타이트 — 가격 상방 압력"
        else:
            interp = "극단적 공급 부족 — 가격 급등 가능"

        return {
            "inventory_proxy": round(proxy, 2),
            "interpretation": interp,
            "cumulative_gap_zscore": round(float(z.iloc[-1]), 2),
        }

    def detect_momentum_divergence(self) -> dict:
        """
        가격 모멘텀(ΔP) vs 펀더멘털(ΔTightness) 괴리 탐지.

        핵심 규칙 (문서 3의 Leading Indicator #1):
          - 수요는 강한데 가격이 더 안 오르는 시점 (Divergence < 0 연속 2분기)
            → 피크아웃(Peak) 신호
          - 공급은 타이트한데 가격이 반등하는 시점 (Divergence > 0 반전)
            → 바닥(Trough) 신호

        Returns:
            dict: {
              'divergence_signal': 'peak_warning' | 'trough_signal' | 'normal',
              'price_momentum': float,
              'fundamental_strength': float,
              'divergence': float,
            }
        """
        dram = self._load_series("MU", months=24)
        equip = self._load_series("AMAT", months=24)  # Equipment basket proxy

        if dram is None:
            return {
                "divergence_signal": "no_data",
                "price_momentum": 0.0,
                "fundamental_strength": 0.0,
                "divergence": 0.0,
            }

        try:
            dram_m = dram.resample("ME").last().pct_change()
            # 3개월 이동평균으로 스무딩
            price_mom = float(dram_m.rolling(3).mean().iloc[-1]) if len(dram_m) >= 3 else 0.0

            if equip is not None:
                equip_m = equip.resample("ME").last().pct_change()
                fund_str = float(equip_m.rolling(3).mean().iloc[-1]) if len(equip_m) >= 3 else 0.0
            else:
                fund_str = 0.0

            divergence = price_mom - fund_str

            # 피크/바닥 판정
            dram_accel = dram_m.diff()  # 가격 상승 속도의 변화 (감속=피크 접근)
            recent_accel = float(dram_accel.rolling(2).mean().iloc[-1]) if len(dram_accel) >= 2 else 0.0

            if fund_str > 0.02 and price_mom < fund_str * 0.5 and recent_accel < 0:
                signal = "peak_warning"
                interp = "수요 대비 가격 모멘텀 약화 (피크아웃 접근 신호)"
            elif fund_str < -0.01 and price_mom > 0 and divergence > 0:
                signal = "trough_signal"
                interp = "공급 타이트 + 가격 반등 시작 (바닥 통과 신호)"
            else:
                signal = "normal"
                interp = "가격 모멘텀-펀더멘털 괴리 없음 (정상 국면)"

        except Exception as e:
            logger.warning(f"PriceEngine divergence error: {e}")
            return {
                "divergence_signal": "error",
                "price_momentum": 0.0,
                "fundamental_strength": 0.0,
                "divergence": 0.0,
            }

        return {
            "divergence_signal": signal,
            "interpretation": interp,
            "price_momentum": round(price_mom, 4),
            "fundamental_strength": round(fund_str, 4),
            "divergence": round(divergence, 4),
        }

    def classify_price_regime(self, inventory_proxy: float,
                               divergence_signal: str) -> str:
        """
        4-국면 분류 (문서 3 기반):
          - extremely_tight: 재고 부족 + 피크 미접근
          - tight: 공급 타이트 (가격 상승 환경)
          - balanced: 수급 균형
          - loose: 공급 과잉 (가격 하방 압력)
        """
        if inventory_proxy < -1.5:
            return "extremely_tight"
        elif inventory_proxy < -0.5:
            if divergence_signal == "peak_warning":
                return "tight"  # 타이트하지만 피크 접근
            return "tight"
        elif inventory_proxy < 0.5:
            return "balanced"
        else:
            return "loose"

    def analyze(self) -> dict:
        """
        전체 Price Engine 분석 실행

        Returns:
            dict: {
              'price_regime': str,       # extremely_tight/tight/balanced/loose
              'inventory': dict,         # compute_inventory_proxy() 결과
              'divergence': dict,        # detect_momentum_divergence() 결과
              'summary': str,            # 한줄 요약
            }
        """
        inventory = self.compute_inventory_proxy()
        divergence = self.detect_momentum_divergence()
        regime = self.classify_price_regime(
            inventory["inventory_proxy"],
            divergence["divergence_signal"],
        )

        regime_labels = {
            "extremely_tight": "극단 타이트 (가격 급등 리스크)",
            "tight": "타이트 (상방 압력 우세)",
            "balanced": "균형 (중립)",
            "loose": "루즈 (하방 압력 우세)",
        }
        summary = regime_labels.get(regime, regime)

        if divergence["divergence_signal"] == "peak_warning":
            summary += " — ⚠️ 피크아웃 경고: 수요 대비 가격 상승 둔화"
        elif divergence["divergence_signal"] == "trough_signal":
            summary += " — 🚀 바닥 신호: 가격 반등 시작"

        logger.info(f"Price Engine: {regime} | Inventory: {inventory['inventory_proxy']} | {divergence['divergence_signal']}")
        return {
            "price_regime": regime,
            "inventory": inventory,
            "divergence": divergence,
            "summary": summary,
        }
