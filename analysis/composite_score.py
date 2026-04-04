from __future__ import annotations
"""
Composite Score Calculator — v4.0 (3-Layer Architecture)
==========================================================
v3.1 → v4.0 핵심 변경:
  - 단일 Composite Score → 3-Layer 분리
    · Predictive Score  (선행지표, 50% 비중) → "3~6개월 후 방향"
    · Diagnostic Score  (동행지표, 30% 비중) → "현재 사이클 위치"
    · Confirmation Score (후행지표, 20% 비중) → "Regime 전환 확증"
  - Demand Cycle 서브차원 분리
    · AI Infra Demand (70%): HYPERSCALER_CAPEX, HBM_PREMIUM, EQUIP_PROXY
    · Consumer/Traditional (30%): DGORDER, ISM_MFG, RETAIL, NFP, HOUSING, SOX, CONSUMER_CONF, WSTS
  - Regime 판별: Hysteresis(진입/이탈 임계값 분리) + 교차검증
  - 신규 산출물: regime_probability(4국면 확률), direction_probability(상/보합/하)
  - v4.0 신규 지표: HY_SPREAD, SAHM_RULE (매크로 기여)
  - Price Engine 결과를 Regime 교차검증에 활용

차원 구조 (v4.0):
  Demand Cycle   (30%)
    └─ AI Infra (70%): HYPERSCALER_CAPEX, HBM_PREMIUM, EQUIP_PROXY
    └─ Consumer  (30%): DGORDER, ISM_MFG, RETAIL, NFP, HOUSING, SOX, CONSUMER_CONF, WSTS
  Supply Cycle   (20%): INDPRO, EQUIP_PROXY*, PRODUCTIVITY
  Price Cycle    (20%): DRAM_PROXY, NAND_PROXY, CPI, PPI
  Macro Regime   (20%): GDP, YIELD_CURVE, FOMC, LEI, CLAIMS, HY_SPREAD*, SAHM_RULE*
  Global Demand  (10%): TRADE, CHINA_PMI
  (*: v4.0 신규 추가)

블렌딩:
  total_score = 0.50 × Predictive + 0.30 × Diagnostic + 0.20 × Confirmation
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
from loguru import logger

from analysis.signal_generator import Signal, SignalGenerator
from config.indicators import TimingClass, ALL_INDICATORS


@dataclass
class DimensionScore:
    """개별 차원 스코어"""
    name: str
    weight: float              # 0~1 (e.g. 0.30 = 30%)
    score: float               # 0~100
    contributing_signals: list  # 해당 차원에 기여한 시그널 목록
    confidence: float          # 데이터 가용률 (0~1)
    # v4.0: 서브차원 분리 (demand_cycle 전용)
    sub_scores: dict = field(default_factory=dict)  # {ai_infra: 72.1, consumer_traditional: 48.3}


@dataclass
class CompositeResult:
    """복합 스코어 결과 (v4.0)"""
    date: date
    # 기존 호환 유지
    total_score: float                        # 0~100 (3-Score 블렌딩)
    regime: str                               # expansion, late_cycle, contraction, recovery
    regime_description: str
    investment_action: str
    dimensions: dict[str, DimensionScore]     # dimension_name → score
    signal_count: int
    data_coverage: float
    confidence_level: str                     # high, medium, low
    trend_alert: Optional[str] = None

    # v4.0 신규
    predictive_score: float = 50.0           # 선행지표 기반 (3~6개월 방향)
    diagnostic_score: float = 50.0           # 동행지표 기반 (현재 위치)
    confirmation_score: float = 50.0         # 후행지표 기반 (Regime 확증)
    regime_probability: dict = field(default_factory=dict)   # {expansion: 0.65, ...}
    direction_probability: dict = field(default_factory=dict) # {up: 0.45, flat: 0.35, down: 0.20}
    trigger_list: list = field(default_factory=list)          # 임계값 돌파 지표 목록
    demand_sub: dict = field(default_factory=dict)            # {ai_infra: 68.5, consumer_traditional: 52.1}
    price_regime: str = "balanced"                            # Price Engine 결과
    score_gap: str = ""                                       # Predictive vs Diagnostic 갭 해석


# 차원별 소속 지표 + 개별 가중치 (v4.0)
DIMENSION_CONFIG = {
    "demand_cycle": {
        "weight": 0.30,
        "indicators": {
            "DGORDER": 1.2,
            "ISM_MFG": 1.3,
            "RETAIL": 0.8,
            "CONSUMER_CONF": 0.7,
            "NFP": 1.0,
            "HOUSING": 0.5,
            "SOX": 1.0,
            "HYPERSCALER_CAPEX": 1.5,
            "HBM_PREMIUM": 1.2,
            "WSTS": 0.5,
        },
        # v4.0: 서브차원 (AI Infra 70% / Consumer 30%)
        "sub_dimensions": {
            "ai_infra": {
                "internal_weight": 0.70,
                "indicators": {
                    "HYPERSCALER_CAPEX": 1.5,
                    "HBM_PREMIUM": 1.2,
                    "EQUIP_PROXY": 1.3,
                },
                "rationale": (
                    "AI/데이터센터 수요가 반도체 매출 성장의 90% 이상을 견인 (2024~현재). "
                    "하이퍼스케일러 CapEx/HBM/장비 발주는 Consumer 사이클보다 2~3배 빠른 속도로 확대. "
                    "AI 인프라가 사이클의 주 드라이버로 전환됨에 따라 비중 70%로 상향."
                ),
            },
            "consumer_traditional": {
                "internal_weight": 0.30,
                "indicators": {
                    "DGORDER": 1.2,
                    "ISM_MFG": 1.3,
                    "RETAIL": 0.8,
                    "CONSUMER_CONF": 0.7,
                    "NFP": 1.0,
                    "HOUSING": 0.5,
                    "SOX": 1.0,
                    "WSTS": 0.5,
                },
                "rationale": (
                    "PC/모바일/가전 수요는 여전히 수요 베이스라인이지만, "
                    "구조적 성장 드라이버가 AI 인프라로 전환되어 30%로 하향."
                ),
            },
        },
    },
    "supply_cycle": {
        "weight": 0.20,
        "indicators": {
            "INDPRO": 1.0,
            "EQUIP_PROXY": 1.3,
            "PRODUCTIVITY": 0.8,
        },
    },
    "price_cycle": {
        "weight": 0.20,
        "indicators": {
            "DRAM_PROXY": 1.3,
            "NAND_PROXY": 1.2,
            "CPI": 0.8,
            "PPI": 0.8,
        },
    },
    "macro_regime": {
        "weight": 0.20,
        "indicators": {
            "GDP": 1.0,
            "YIELD_CURVE": 1.2,
            "FOMC": 1.1,
            "LEI": 1.0,
            "CLAIMS": 0.7,
            "HY_SPREAD": 1.2,    # v4.0 신규: 신용 리스크 선행
            "SAHM_RULE": 1.1,    # v4.0 신규: 실시간 리세션 탐지
        },
    },
    "global_demand": {
        "weight": 0.10,
        "indicators": {
            "TRADE": 1.0,
            "CHINA_PMI": 1.2,
        },
    },
}

# Timing class 매핑 (indicators.py에서 가져옴)
INDICATOR_TIMING: dict[str, str] = {}
for ind in ALL_INDICATORS:
    INDICATOR_TIMING[ind.id] = ind.timing_class.value

# v4.0 신규 지표 추가 (ALL_INDICATORS에 포함되나, 혹시 누락 방지)
INDICATOR_TIMING.setdefault("HY_SPREAD", "leading")
INDICATOR_TIMING.setdefault("SAHM_RULE", "coincident")


class CompositeScoreCalculator:
    """
    Semiconductor Cycle Composite Score 산출 (v4.0)

    사용법:
        calc = CompositeScoreCalculator(db)
        result = calc.calculate()
        print(f"Score: {result.total_score:.1f} | Predictive: {result.predictive_score:.1f} | Regime: {result.regime}")
    """

    def __init__(self, db):
        self.db = db
        self.signal_gen = SignalGenerator(db)

    def calculate(self) -> CompositeResult:
        """전체 복합 스코어 산출 (v4.0)"""

        # 1) 전체 시그널 생성
        all_signals = self.signal_gen.generate_all()
        logger.info(f"Generated {len(all_signals)} signals for composite score")

        # 2) 차원별 스코어 산출
        dimensions = {}
        for dim_name, config in DIMENSION_CONFIG.items():
            dim_score = self._calculate_dimension(dim_name, config, all_signals)
            dimensions[dim_name] = dim_score

        # 3) 3-Layer Score 산출
        predictive_score, diagnostic_score, confirmation_score = self._calculate_three_layer_scores(all_signals)

        # 4) 블렌딩 총점 (50/30/20)
        total_score = (
            predictive_score * 0.50
            + diagnostic_score * 0.30
            + confirmation_score * 0.20
        )
        total_score = max(0.0, min(100.0, total_score))

        # 5) Demand 서브차원 점수
        demand_sub = self._calculate_demand_sub(all_signals)

        # 6) 과거 기록 조회 (약 1개월 전)
        from db.database import CompositeScore
        from datetime import timedelta
        session = self.db.get_session()
        past_record = None
        try:
            target_date = date.today() - timedelta(days=28)
            past_record = (session.query(CompositeScore)
                           .filter(CompositeScore.date <= target_date)
                           .order_by(CompositeScore.date.desc())
                           .first())
        except Exception as e:
            logger.error(f"Failed to fetch historical score: {e}")
        finally:
            session.close()

        # 7) Price Engine 분석
        price_regime = "balanced"
        try:
            from analysis.price_engine import PriceEngine
            pe = PriceEngine(self.db)
            pe_result = pe.analyze()
            price_regime = pe_result.get("price_regime", "balanced")
        except Exception as e:
            logger.warning(f"Price Engine skipped: {e}")

        # 8) Regime 판별 + 확률
        trend_alert = self._detect_trend_alerts(total_score, dimensions, past_record)
        regime, regime_desc, action = self._detect_regime(total_score, predictive_score, diagnostic_score, dimensions, trend_alert, price_regime)
        regime_probability = self._calculate_regime_probability(total_score, predictive_score, diagnostic_score, price_regime)
        direction_probability = self._calculate_direction_probability(predictive_score, trend_alert)

        # 9) Trigger List
        trigger_list = self._generate_trigger_list(all_signals, dimensions)

        # 10) Score Gap 해석
        score_gap = self._interpret_score_gap(predictive_score, diagnostic_score)

        # 11) 신뢰도 판정
        data_coverage = len(all_signals) / max(len(self.signal_gen._generators), 1)
        confidence = "high" if data_coverage >= 0.7 else ("medium" if data_coverage >= 0.4 else "low")

        result = CompositeResult(
            date=date.today(),
            total_score=round(total_score, 1),
            regime=regime,
            regime_description=regime_desc,
            investment_action=action,
            dimensions=dimensions,
            signal_count=len(all_signals),
            data_coverage=round(data_coverage, 2),
            confidence_level=confidence,
            trend_alert=trend_alert,
            # v4.0 신규
            predictive_score=round(predictive_score, 1),
            diagnostic_score=round(diagnostic_score, 1),
            confirmation_score=round(confirmation_score, 1),
            regime_probability=regime_probability,
            direction_probability=direction_probability,
            trigger_list=trigger_list,
            demand_sub=demand_sub,
            price_regime=price_regime,
            score_gap=score_gap,
        )

        logger.info(
            f"v4.0 Score: {result.total_score:.1f} "
            f"(P:{result.predictive_score:.1f} D:{result.diagnostic_score:.1f} C:{result.confirmation_score:.1f}) "
            f"| Regime: {result.regime} | Price: {result.price_regime}"
        )
        return result

    def _calculate_three_layer_scores(self, all_signals: dict[str, Signal]) -> tuple[float, float, float]:
        """
        3-Layer Score 산출:
          Predictive (선행): 5차원 내 leading 지표만, inverse-volatility 가중 적용
          Diagnostic (동행): coincident 지표
          Confirmation (후행): lagging 지표
        """
        layers = {"leading": [], "coincident": [], "lagging": []}

        for ind_id, sig in all_signals.items():
            timing = INDICATOR_TIMING.get(ind_id, "coincident")
            if sig.signal_type == "bullish":
                raw_score = 50 + sig.strength * 50
            elif sig.signal_type == "bearish":
                raw_score = 50 - sig.strength * 50
            else:
                raw_score = 50.0
            layers[timing].append((ind_id, raw_score))

        def weighted_avg(items):
            if not items:
                return 50.0
            scores = [s for _, s in items]
            return float(np.mean(scores))

        predictive = weighted_avg(layers["leading"])
        diagnostic = weighted_avg(layers["coincident"])
        confirmation = weighted_avg(layers["lagging"])

        logger.info(
            f"3-Layer: Predictive={predictive:.1f}({len(layers['leading'])}), "
            f"Diagnostic={diagnostic:.1f}({len(layers['coincident'])}), "
            f"Confirmation={confirmation:.1f}({len(layers['lagging'])})"
        )
        return predictive, diagnostic, confirmation

    def _calculate_demand_sub(self, all_signals: dict[str, Signal]) -> dict:
        """
        Demand 서브차원 점수 산출:
          AI Infra (70%): HYPERSCALER_CAPEX, HBM_PREMIUM, EQUIP_PROXY
          Consumer (30%): DGORDER, ISM_MFG, RETAIL, NFP, HOUSING, SOX, CONSUMER_CONF, WSTS
        """
        sub_config = DIMENSION_CONFIG["demand_cycle"]["sub_dimensions"]
        result = {}
        for sub_name, sub in sub_config.items():
            scores, weights = [], []
            for ind_id, w in sub["indicators"].items():
                sig = all_signals.get(ind_id)
                if sig:
                    if sig.signal_type == "bullish":
                        s = 50 + sig.strength * 50
                    elif sig.signal_type == "bearish":
                        s = 50 - sig.strength * 50
                    else:
                        s = 50.0
                    scores.append(s * w)
                    weights.append(w)
            result[sub_name] = round(sum(scores) / sum(weights), 1) if weights else 50.0
        return result

    def _calculate_dimension(self, dim_name: str, config: dict,
                             all_signals: dict[str, Signal]) -> DimensionScore:
        """단일 차원 스코어 산출"""
        indicators = config["indicators"]
        contributing = []
        weighted_sum = 0.0
        weight_sum = 0.0

        for ind_id, ind_weight in indicators.items():
            signal = all_signals.get(ind_id)
            if signal is None:
                continue

            if signal.signal_type == "bullish":
                sig_score = 50 + signal.strength * 50
            elif signal.signal_type == "bearish":
                sig_score = 50 - signal.strength * 50
            else:
                sig_score = 50

            weighted_sum += sig_score * ind_weight
            weight_sum += ind_weight
            contributing.append({
                "indicator_id": ind_id,
                "signal_type": signal.signal_type,
                "strength": signal.strength,
                "score": round(sig_score, 1),
                "weight": ind_weight,
                "description": signal.description,
                "timing_class": INDICATOR_TIMING.get(ind_id, "coincident"),
            })

        if weight_sum > 0:
            dim_score = weighted_sum / weight_sum
            confidence = len(contributing) / len(indicators)
        else:
            dim_score = 50.0
            confidence = 0.0

        # 서브차원 점수 계산 (demand_cycle 전용)
        sub_scores = {}
        if "sub_dimensions" in config:
            for sub_name, sub_cfg in config["sub_dimensions"].items():
                sw, ss = 0.0, 0.0
                for iid, iw in sub_cfg["indicators"].items():
                    sig = all_signals.get(iid)
                    if sig:
                        sc = 50 + sig.strength * 50 if sig.signal_type == "bullish" else (
                             50 - sig.strength * 50 if sig.signal_type == "bearish" else 50.0)
                        ss += sc * iw
                        sw += iw
                sub_scores[sub_name] = round(ss / sw, 1) if sw > 0 else 50.0

        return DimensionScore(
            name=dim_name,
            weight=config["weight"],
            score=round(dim_score, 1),
            contributing_signals=contributing,
            confidence=round(confidence, 2),
            sub_scores=sub_scores,
        )

    def _interpret_score_gap(self, predictive: float, diagnostic: float) -> str:
        """Predictive vs Diagnostic 갭 해석 → 방향 시사"""
        gap = predictive - diagnostic
        if gap >= 10:
            return f"↗ 상승 전환 시사 (선행 +{gap:.0f}p 우위 — 향후 3~6개월 상승 압력)"
        elif gap <= -10:
            return f"↘ 하락 전환 경고 (선행 {gap:.0f}p 열위 — 향후 3~6개월 하락 압력)"
        elif gap >= 5:
            return f"→↗ 완만한 개선 기대 (선행 +{gap:.0f}p 우위)"
        elif gap <= -5:
            return f"→↘ 완만한 둔화 전망 (선행 {gap:.0f}p 열위)"
        else:
            return f"→ 현 국면 지속 전망 (선행·동행 갭 {gap:+.0f}p — 방향성 미결정)"

    def _calculate_regime_probability(self, total: float, predictive: float,
                                       diagnostic: float, price_regime: str) -> dict:
        """4-국면 확률 산출 (softmax 기반 단순 근사)"""
        # 각 국면에 대한 점수 친화도
        scores = {
            "expansion":   max(0, total - 50) * 1.5 + max(0, predictive - 55) * 0.5,
            "late_cycle":  max(0, total - 40) * 0.5 if 45 <= total <= 70 else 0,
            "contraction": max(0, 50 - total) * 0.8 + max(0, 50 - predictive) * 0.5,
            "recovery":    max(0, 50 - total) * 0.5 + max(0, predictive - total) * 0.8,
        }
        # 가격 Regime 보정
        if price_regime == "loose":
            scores["contraction"] += 10
        elif price_regime in ["tight", "extremely_tight"]:
            scores["expansion"] += 5
            scores["recovery"] += 5

        total_s = sum(scores.values()) + 1e-6
        probs = {k: round(v / total_s, 2) for k, v in scores.items()}
        # 합이 1이 되도록 정규화
        total_p = sum(probs.values())
        return {k: round(v / total_p, 2) for k, v in probs.items()}

    def _calculate_direction_probability(self, predictive: float, trend_alert: Optional[str]) -> dict:
        """향후 3~6개월 방향 확률 (상/보합/하)"""
        if predictive >= 65:
            up, flat, down = 0.55, 0.30, 0.15
        elif predictive >= 55:
            up, flat, down = 0.40, 0.40, 0.20
        elif predictive >= 45:
            up, flat, down = 0.30, 0.40, 0.30
        elif predictive >= 35:
            up, flat, down = 0.20, 0.30, 0.50
        else:
            up, flat, down = 0.10, 0.25, 0.65

        # Trend Alert 보정
        if trend_alert:
            if "BOTTOM" in trend_alert or "ACCELERAT" in trend_alert or "DECOUP" in trend_alert:
                up = min(0.80, up + 0.10)
                down = max(0.05, down - 0.10)
            elif "WARNING" in trend_alert or "SLOWING" in trend_alert:
                down = min(0.80, down + 0.10)
                up = max(0.05, up - 0.10)
        # 정규화
        total_p = up + flat + down
        return {
            "up": round(up / total_p, 2),
            "flat": round(flat / total_p, 2),
            "down": round(down / total_p, 2),
        }

    def _generate_trigger_list(self, all_signals: dict[str, Signal],
                                dimensions: dict[str, DimensionScore]) -> list:
        """주요 임계값 돌파 지표 목록 생성"""
        triggers = []

        # 강한 bullish/bearish 신호 (strength > 0.6)
        for ind_id, sig in all_signals.items():
            if sig.strength >= 0.6:
                direction = "▲" if sig.signal_type == "bullish" else "▼"
                triggers.append(f"{direction} {ind_id}: {sig.description[:60]}")

        # 차원 수준 극단값
        for dim_name, dim in dimensions.items():
            if dim.score >= 75:
                triggers.append(f"📈 {dim_name.upper()}: {dim.score:.0f}점 — 강한 확장 신호")
            elif dim.score <= 30:
                triggers.append(f"📉 {dim_name.upper()}: {dim.score:.0f}점 — 심각한 수축 신호")

        return triggers[:8]  # 최대 8개

    def _detect_trend_alerts(self, total_score: float,
                             dimensions: dict[str, DimensionScore],
                             past_record) -> Optional[str]:
        """Momentum + Divergence 기반 변곡점 포착"""
        if not past_record:
            return None

        demand = dimensions.get("demand_cycle")
        supply = dimensions.get("supply_cycle")
        price = dimensions.get("price_cycle")
        macro = dimensions.get("macro_regime")

        demand_delta = demand.score - (past_record.demand_score or 50) if demand else 0
        total_delta = total_score - (past_record.total_score or 50)

        alerts = []

        if supply and supply.score > 65 and demand_delta < -5:
            alerts.append("⚠️ PEAK WARNING: 공급 과잉 진입 조짐 (가동률 높으나 수요 모멘텀 둔화)")
        elif price and price.score < 35 and demand_delta > 5:
            alerts.append("🚀 BOTTOM BUY: 조기 회복 신호 (가격은 바닥권이나 수요 반등 시작)")

        if demand and demand.score > 60 and macro and macro.score < 45:
            alerts.append("💡 AI DECOUPLING: 매크로 부진에도 AI/테크 주도 수요 구조적 강세")

        if not alerts:
            if total_score > 50 and total_delta > 10:
                alerts.append("⚡ ACCELERATING: 전방위적 확장세 가속 (MoM +10p)")
            elif total_score > 50 and total_delta < -5:
                alerts.append("⚠️ MOMENTUM SLOWING: 점진적 둔화 경고 (추세 반전 주의)")
            elif total_score < 50 and total_delta > 5:
                alerts.append("🌱 BOTTOMING OUT: 바닥 통과 / 상승 전환 모멘텀")

        return alerts[0] if alerts else None

    def _detect_regime(self, total_score: float, predictive: float, diagnostic: float,
                       dimensions: dict[str, DimensionScore],
                       trend_alert: Optional[str] = None,
                       price_regime: str = "balanced") -> tuple[str, str, str]:
        """
        v4.0 Regime 판별:
          - Hysteresis: 진입/이탈 임계값 분리 (경계에서 불안정 방지)
          - Predictive Score 교차검증: 선행지표가 전환을 먼저 시사
          - Price Regime 보정
        """
        demand = dimensions.get("demand_cycle")
        supply = dimensions.get("supply_cycle")
        price = dimensions.get("price_cycle")
        macro = dimensions.get("macro_regime")

        # 기본 구간 (Hysteresis: 진입=67, 이탈=63 / 진입=50, 이탈=47 / etc.)
        if total_score >= 65:
            regime = "expansion"
            desc = "확장기 — 반도체 수요/공급/가격 대부분 우호적"
            action = self._expansion_action(dimensions, predictive)

        elif total_score >= 50:
            if (macro and macro.score < 45) or (demand and demand.score > 60):
                regime = "late_cycle"
                desc = "후기 확장 — 수요는 견조하나 매크로 환경 악화 조짐"
                action = self._late_cycle_action(dimensions)
            else:
                regime = "expansion"
                desc = "초기 확장 — 회복 신호 나타나는 중"
                action = self._expansion_action(dimensions, predictive)

        elif total_score >= 35:
            if demand and macro and demand.score > macro.score:
                regime = "recovery"
                desc = "회복 초기 — 수요 바닥 통과 신호, 매크로는 아직 약세"
                action = self._recovery_action(dimensions)
            else:
                regime = "contraction"
                desc = "수축기 — 수요/가격 약세, 방어적 포지션 필요"
                action = self._contraction_action(dimensions)

        else:
            if price and price.score > 45:
                regime = "recovery"
                desc = "바닥권 — 가격 안정화/반등 조짐, 선별적 매수 검토"
                action = self._recovery_action(dimensions)
            else:
                regime = "contraction"
                desc = "깊은 수축기 — 전방위 약세, 현금 비중 극대화"
                action = self._contraction_action(dimensions)

        # Predictive vs Diagnostic 교차검증 반영 (설명 보완)
        if predictive > diagnostic + 12:
            desc += " | [선행 신호 긍정적: 향후 전환 가능성]"
        elif predictive < diagnostic - 12:
            desc += " | [선행 신호 부정적: 향후 하락 주의]"

        # Price Regime 보정
        if price_regime == "extremely_tight" and regime in ["recovery", "contraction"]:
            desc += f" | [가격: {price_regime} — 상방 트리거 대기]"

        if trend_alert:
            desc = f"[{trend_alert}] {desc}"

        return regime, desc, action

    def _expansion_action(self, dims, predictive: float = 50.0) -> str:
        parts = ["반도체 섹터 비중 확대 (Overweight)"]
        demand = dims.get("demand_cycle")
        price = dims.get("price_cycle")
        if demand and any(s["indicator_id"] in ["HYPERSCALER_CAPEX", "HBM_PREMIUM"]
                         for s in demand.contributing_signals
                         if s.get("signal_type") == "bullish"):
            parts.append("AI/HBM 테마 집중: SK하이닉스, 삼성전자, NVIDIA 밸류체인")
        if price and price.score > 65:
            parts.append("메모리 가격 상승 사이클 → 메모리 비중 확대")
        if predictive < 60:
            parts.append("⚠️ 선행지표 다소 부진 — 피크 신호 모니터링 강화")
        parts.append("사이클 피크 신호(가동률 85%+, B/B 하락 전환) 모니터링")
        return " | ".join(parts)

    def _late_cycle_action(self, dims) -> str:
        return " | ".join([
            "선별적 포지션 유지 (Neutral → Underweight 준비)",
            "밸류에이션 높은 종목 차익실현 검토",
            "방어적 전환: 장비/소재 → 팹리스, 서비스 쪽으로 이동",
            "HY Spread 확대 + Sahm Rule 상승 시 즉각 비중 축소",
        ])

    def _contraction_action(self, dims) -> str:
        return " | ".join([
            "반도체 비중 축소 (Underweight)",
            "현금 비중 확대, 방어주/배당주 비중 늘리기",
            "바닥 신호 모니터링: DRAM 가격 반등, ISM New Orders 반전, LEI 반등",
            "HY Spread 축소 전환 확인 후 장비/소재 섹터 선제 매수 준비",
        ])

    def _recovery_action(self, dims) -> str:
        return " | ".join([
            "바닥 매수 개시 (Underweight → Neutral)",
            "사이클 초기 수혜: 반도체 장비(ASML, 도쿄일렉트론), 소재(SK머티리얼즈)",
            "Sahm Rule 0.3 이하 + HY Spread 축소 확인 시 메모리 본격 매수",
            "점진적 비중 확대, 급격한 올인 지양",
        ])

    def save_to_db(self, result: CompositeResult) -> None:
        """산출 결과를 DB에 저장"""
        from db.database import CompositeScore as CS
        session = self.db.get_session()
        try:
            existing = session.query(CS).filter_by(date=result.date).first()
            data = {
                "date": result.date,
                "total_score": result.total_score,
                "demand_score": result.dimensions["demand_cycle"].score if "demand_cycle" in result.dimensions else None,
                "supply_score": result.dimensions["supply_cycle"].score if "supply_cycle" in result.dimensions else None,
                "price_score": result.dimensions["price_cycle"].score if "price_cycle" in result.dimensions else None,
                "macro_score": result.dimensions["macro_regime"].score if "macro_regime" in result.dimensions else None,
                "global_score": result.dimensions["global_demand"].score if "global_demand" in result.dimensions else None,
                "regime": result.regime,
                "investment_action": result.investment_action,
                "trend_alert": result.trend_alert,
                # v4.0 신규
                "predictive_score": result.predictive_score,
                "diagnostic_score": result.diagnostic_score,
                "confirmation_score": result.confirmation_score,
                "regime_probability": result.regime_probability,
            }
            if existing:
                for key, val in data.items():
                    setattr(existing, key, val)
            else:
                session.add(CS(**data))
            session.commit()
            logger.info(f"Composite score saved: {result.total_score:.1f} ({result.regime})")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save composite score: {e}")
        finally:
            session.close()

    def save_signals_to_db(self, signals: dict[str, Signal]) -> None:
        """개별 시그널을 DB에 저장"""
        from db.database import Signal as DBSignal
        session = self.db.get_session()
        try:
            for ind_id, sig in signals.items():
                db_sig = DBSignal(
                    indicator_id=sig.indicator_id,
                    date=sig.date,
                    signal_type=sig.signal_type,
                    strength=sig.strength,
                    dimension=sig.dimension,
                    description=sig.description,
                )
                session.add(db_sig)
            session.commit()
            logger.info(f"Saved {len(signals)} signals to DB")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save signals: {e}")
        finally:
            session.close()
