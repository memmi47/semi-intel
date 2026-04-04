from __future__ import annotations
"""
Composite Score Calculator
============================
개별 지표 시그널 → 5개 차원 가중합산 → Semiconductor Cycle Score (0-100)

차원 구조:
  Demand Cycle   (30%) — 자본재 주문, PMI, 소매, 빅테크 CapEx
  Supply Cycle   (20%) — 산업생산/가동률, 장비 B/B, 생산성
  Price Cycle    (20%) — DRAM 가격, CPI, PPI
  Macro Regime   (20%) — GDP, 수익률곡선, Fed, LEI, 실업수당
  Global Demand  (10%) — 무역, 중국 PMI
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
from loguru import logger

from analysis.signal_generator import Signal, SignalGenerator


@dataclass
class DimensionScore:
    """개별 차원 스코어"""
    name: str
    weight: float              # 0~1 (e.g. 0.30 = 30%)
    score: float               # 0~100
    contributing_signals: list  # 해당 차원에 기여한 시그널 목록
    confidence: float          # 데이터 가용률 (0~1)


@dataclass
class CompositeResult:
    """복합 스코어 결과"""
    date: date
    total_score: float                        # 0~100
    regime: str                               # expansion, late_cycle, contraction, recovery
    regime_description: str
    investment_action: str
    dimensions: dict[str, DimensionScore]     # dimension_name → score
    signal_count: int                         # 산출에 사용된 시그널 수
    data_coverage: float                      # 전체 데이터 가용률 (0~1)
    confidence_level: str                     # high, medium, low
    trend_alert: Optional[str] = None         # Momentum/Divergence Alert


# 차원별 소속 지표 + 개별 가중치
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
            "HYPERSCALER_CAPEX": 1.5,  # AI 수요의 핵심 드라이버
            "HBM_PREMIUM": 1.2,        # HBM/AI 수요 프리미엄
            "WSTS": 0.5,               # 2개월 후행 확인 지표, 가중치 하향
        },
    },
    "supply_cycle": {
        "weight": 0.20,
        "indicators": {
            "INDPRO": 1.0,
            "EQUIP_PROXY": 1.3,        # SEMI B/B 대체 (장비주 basket)
            "PRODUCTIVITY": 0.8,
        },
    },
    "price_cycle": {
        "weight": 0.20,
        "indicators": {
            "DRAM_PROXY": 1.3,          # DRAM pure player basket
            "NAND_PROXY": 1.2,          # NAND pure player basket
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


class CompositeScoreCalculator:
    """
    Semiconductor Cycle Composite Score 산출

    사용법:
        calc = CompositeScoreCalculator(db)
        result = calc.calculate()
        print(f"Score: {result.total_score:.1f} | Regime: {result.regime}")
    """

    def __init__(self, db):
        self.db = db
        self.signal_gen = SignalGenerator(db)

    def calculate(self) -> CompositeResult:
        """전체 복합 스코어 산출"""

        # 1) 전체 시그널 생성
        all_signals = self.signal_gen.generate_all()
        logger.info(f"Generated {len(all_signals)} signals for composite score")

        # 2) 차원별 스코어 산출
        dimensions = {}
        for dim_name, config in DIMENSION_CONFIG.items():
            dim_score = self._calculate_dimension(dim_name, config, all_signals)
            dimensions[dim_name] = dim_score

        # 3) 가중합산 → 총점
        total_score = 0.0
        total_weight_used = 0.0

        for dim_name, dim in dimensions.items():
            config = DIMENSION_CONFIG[dim_name]
            if dim.confidence > 0:
                total_score += dim.score * config["weight"]
                total_weight_used += config["weight"]

        # 가용 데이터 기준으로 정규화
        if total_weight_used > 0:
            total_score = total_score / total_weight_used * 1.0
        else:
            total_score = 50.0  # 데이터 없으면 중립

        total_score = max(0, min(100, total_score))

        # 4) 과거 기록 조회 (약 1개월 전)
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

        # 5) 알람(Trend Alert) 및 Regime 판별
        trend_alert = self._detect_trend_alerts(total_score, dimensions, past_record)
        regime, regime_desc, action = self._detect_regime(total_score, dimensions, trend_alert)

        # 5) 신뢰도 판정
        data_coverage = len(all_signals) / len(self.signal_gen._generators)
        if data_coverage >= 0.7:
            confidence = "high"
        elif data_coverage >= 0.4:
            confidence = "medium"
        else:
            confidence = "low"

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
        )

        logger.info(f"Composite Score: {result.total_score:.1f} | Regime: {result.regime} | Alert: {result.trend_alert or 'None'}")
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

            # signal score: signal_type에 따라 0~1 → 0~100 변환
            if signal.signal_type == "bullish":
                sig_score = 50 + signal.strength * 50  # 50~100
            elif signal.signal_type == "bearish":
                sig_score = 50 - signal.strength * 50  # 0~50
            else:
                sig_score = 50  # neutral

            weighted_sum += sig_score * ind_weight
            weight_sum += ind_weight
            contributing.append({
                "indicator_id": ind_id,
                "signal_type": signal.signal_type,
                "strength": signal.strength,
                "score": round(sig_score, 1),
                "weight": ind_weight,
                "description": signal.description,
            })

        if weight_sum > 0:
            dim_score = weighted_sum / weight_sum
            confidence = len(contributing) / len(indicators)
        else:
            dim_score = 50.0
            confidence = 0.0

        return DimensionScore(
            name=dim_name,
            weight=config["weight"],
            score=round(dim_score, 1),
            contributing_signals=contributing,
            confidence=round(confidence, 2),
        )

    def _detect_trend_alerts(self, total_score: float,
                             dimensions: dict[str, DimensionScore],
                             past_record) -> Optional[str]:
        """
        Momentum(약 30일 변동폭) 및 Divergence(상충)를 기반으로 변곡점(Inflection) 포착
        """
        if not past_record:
            return None

        # 1M Delta 계산
        demand = dimensions.get("demand_cycle")
        supply = dimensions.get("supply_cycle")
        price = dimensions.get("price_cycle")
        macro = dimensions.get("macro_regime")

        demand_delta = demand.score - (past_record.demand_score or 50) if demand else 0
        total_delta = total_score - (past_record.total_score or 50)

        alerts = []

        # Divergence 1: Peak Warning (공급 과잉 징후)
        # 공급/가동률은 높은데, 수요 모멘텀이 꺾일 때
        if supply and supply.score > 65 and demand_delta < -5:
            alerts.append("⚠️ PEAK WARNING: 공급 과잉 진입 조짐 (가동률 높으나 수요 모멘텀 둔화)")

        # Divergence 2: Bottom Buy (조기 회복 징후)
        # 가격은 바닥권인데, 수요 모멘텀이 반등할 때
        elif price and price.score < 35 and demand_delta > 5:
            alerts.append("🚀 BOTTOM BUY: 조기 회복 신호 (가격은 바닥권이나 수요 반등 시작)")

        # Divergence 3: AI Decoupling
        # 매크로는 나쁜데, 수요(AI/빅테크 중심)가 견조할 때
        if demand and demand.score > 60 and macro and macro.score < 45:
            alerts.append("💡 AI DECOUPLING: 매크로 부진에도 AI/테크 주도 수요 구조적 강세")

        # General Momentum
        if not alerts:
            if total_score > 50 and total_delta > 10:
                alerts.append("⚡ ACCELERATING: 전방위적 확장세 가속 (MoM +10p)")
            elif total_score > 50 and total_delta < -5:
                alerts.append("⚠️ MOMENTUM SLOWING: 점진적 둔화 경고 (추세 반전 주의)")
            elif total_score < 50 and total_delta > 5:
                alerts.append("🌱 BOTTOMING OUT: 바닥 통과 / 상승 전환 모멘텀")

        return alerts[0] if alerts else None


    def _detect_regime(self, total_score: float,
                       dimensions: dict[str, DimensionScore],
                       trend_alert: Optional[str] = None
                       ) -> tuple[str, str, str]:
        """
        Regime Detection — 4단계 사이클 판별
        단순 점수 기반 + 차원 간 크로스체크로 보완
        """

        demand = dimensions.get("demand_cycle")
        supply = dimensions.get("supply_cycle")
        price = dimensions.get("price_cycle")
        macro = dimensions.get("macro_regime")

        # 기본 regime (점수 기반)
        if total_score >= 65:
            regime = "expansion"
            desc = "확장기 — 반도체 수요/공급/가격 대부분 우호적"
            action = self._expansion_action(dimensions)

        elif total_score >= 50:
            # Late cycle vs early expansion 구분
            if (macro and macro.score < 45) or (demand and demand.score > 60):
                regime = "late_cycle"
                desc = "후기 확장 — 수요는 견조하나 매크로 환경 악화 조짐"
                action = self._late_cycle_action(dimensions)
            else:
                regime = "expansion"
                desc = "초기 확장 — 회복 신호 나타나는 중"
                action = self._expansion_action(dimensions)

        elif total_score >= 35:
            # Contraction vs Recovery 구분
            if demand and demand.score > macro.score if macro else False:
                regime = "recovery"
                desc = "회복 초기 — 수요 바닥 통과 신호, 매크로는 아직 약세"
                action = self._recovery_action(dimensions)
            else:
                regime = "contraction"
                desc = "수축기 — 수요/가격 약세, 방어적 포지션 필요"
                action = self._contraction_action(dimensions)

        else:
            # Recovery 가능성 체크
            if price and price.score > 45:
                regime = "recovery"
                desc = "바닥권 — 가격 안정화/반등 조짐, 선별적 매수 검토"
                action = self._recovery_action(dimensions)
            else:
                regime = "contraction"
                desc = "깊은 수축기 — 전방위 약세, 현금 비중 극대화"
                action = self._contraction_action(dimensions)

        if trend_alert:
            desc = f"[{trend_alert}] {desc}"

        return regime, desc, action

    def _expansion_action(self, dims) -> str:
        parts = ["반도체 섹터 비중 확대 (Overweight)"]

        demand = dims.get("demand_cycle")
        price = dims.get("price_cycle")

        if demand and any(s["indicator_id"] == "HYPERSCALER_CAPEX"
                         for s in demand.contributing_signals
                         if s.get("signal_type") == "bullish"):
            parts.append("AI/HBM 테마 집중: SK하이닉스, 삼성전자, NVIDIA 밸류체인")

        if price and price.score > 65:
            parts.append("메모리 가격 상승 사이클 → 메모리 비중 확대")

        parts.append("사이클 피크 신호(가동률 85%+, B/B 하락 전환) 모니터링")
        return " | ".join(parts)

    def _late_cycle_action(self, dims) -> str:
        parts = ["선별적 포지션 유지 (Neutral → Underweight 준비)"]
        parts.append("밸류에이션 높은 종목 차익실현 검토")
        parts.append("방어적 전환: 장비/소재 → 팹리스, 서비스 쪽으로 이동")
        parts.append("수익률곡선 역전 심화 시 즉각 비중 축소")
        return " | ".join(parts)

    def _contraction_action(self, dims) -> str:
        parts = ["반도체 비중 축소 (Underweight)"]
        parts.append("현금 비중 확대, 방어주/배당주 비중 늘리기")
        parts.append("바닥 신호 모니터링: DRAM 가격 반등, ISM New Orders 반전, LEI 반등")
        parts.append("바닥 확인 시 장비/소재 섹터부터 선제 매수 준비")
        return " | ".join(parts)

    def _recovery_action(self, dims) -> str:
        parts = ["바닥 매수 개시 (Underweight → Neutral)"]
        parts.append("사이클 초기 수혜: 반도체 장비(ASML, 도쿄일렉트론), 소재(SK머티리얼즈)")
        parts.append("메모리 가격 계약가 상승 전환 확인 시 메모리 본격 매수")
        parts.append("점진적 비중 확대, 급격한 올인 지양")
        return " | ".join(parts)

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
