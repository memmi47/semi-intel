from __future__ import annotations
"""
Scenario Analyzer
==================
What-if 분석 프레임워크
- 사전 정의된 시나리오 (Fed 금리, 중국 경기, AI 투자 등)
- 사용자 정의 시나리오
- 시나리오 간 비교

시나리오가 각 차원 스코어에 미치는 Delta를 계산하여
현재 Composite Score에 적용
"""

from dataclasses import dataclass, field
from datetime import date

from loguru import logger


@dataclass
class ScenarioAssumption:
    """시나리오 내 개별 가정"""
    indicator_id: str
    assumed_direction: str      # "improve", "deteriorate", "neutral"
    magnitude: str              # "mild", "moderate", "severe"
    description: str


@dataclass
class ScenarioImpact:
    """시나리오의 차원별 영향"""
    dimension: str
    delta: float                # -50 ~ +50 범위의 스코어 변화
    explanation: str


@dataclass
class Scenario:
    """분석 시나리오 정의"""
    id: str
    name: str
    description: str
    probability: float          # 발생 확률 추정 (0~1)
    time_horizon: str           # "3m", "6m", "12m"
    assumptions: list[ScenarioAssumption]
    impacts: list[ScenarioImpact] = field(default_factory=list)


@dataclass
class ScenarioComparison:
    """시나리오 비교 결과"""
    base_score: float
    scenarios: list[dict]       # [{scenario, adjusted_score, regime, delta, actions}]


# ============================================================
# 사전 정의 시나리오
# ============================================================

PREDEFINED_SCENARIOS = {
    # === 긍정 시나리오 ===
    "ai_capex_surge": Scenario(
        id="ai_capex_surge",
        name="AI CapEx 급증",
        description="Hyperscaler AI 투자 50%+ 증가, HBM/GPU 공급 부족 심화",
        probability=0.25,
        time_horizon="6m",
        assumptions=[
            ScenarioAssumption("HYPERSCALER_CAPEX", "improve", "severe",
                               "빅테크 CapEx YoY 50%+ 가이던스"),
            ScenarioAssumption("DRAM_SPOT", "improve", "moderate",
                               "HBM 수요 급증 → 범용 DRAM 공급 축소 → 가격 상승"),
            ScenarioAssumption("SEMI_BB", "improve", "moderate",
                               "장비 주문 급증, B/B > 1.2"),
            ScenarioAssumption("ISM_MFG", "improve", "mild",
                               "테크 섹터 주도 PMI 개선"),
        ],
        impacts=[
            ScenarioImpact("demand_cycle", +15, "AI 수요가 전체 반도체 수요 견인"),
            ScenarioImpact("supply_cycle", +10, "장비 투자 확대, 가동률 상승"),
            ScenarioImpact("price_cycle", +12, "메모리 가격 강세, ASP 상승"),
            ScenarioImpact("macro_regime", +3, "테크 투자가 GDP 성장 기여"),
            ScenarioImpact("global_demand", +5, "글로벌 AI 인프라 수요 확산"),
        ],
    ),

    "fed_pivot_dovish": Scenario(
        id="fed_pivot_dovish",
        name="Fed 비둘기파 전환",
        description="인플레이션 안정화로 금리 인하 사이클 개시",
        probability=0.30,
        time_horizon="6m",
        assumptions=[
            ScenarioAssumption("FOMC", "improve", "moderate",
                               "연내 3회 이상 금리 인하"),
            ScenarioAssumption("CPI", "improve", "moderate",
                               "Core CPI 2.5% 이하로 안정"),
            ScenarioAssumption("YIELD_CURVE", "improve", "mild",
                               "수익률곡선 정상화"),
        ],
        impacts=[
            ScenarioImpact("demand_cycle", +5, "금리 인하 → 소비/투자 심리 개선"),
            ScenarioImpact("price_cycle", +5, "인플레 안정 → 비용 부담 완화"),
            ScenarioImpact("macro_regime", +12, "유동성 환경 개선, 밸류에이션 멀티플 확장"),
            ScenarioImpact("global_demand", +3, "달러 약세 → 수출 여건 개선"),
        ],
    ),

    "china_recovery": Scenario(
        id="china_recovery",
        name="중국 경기 회복",
        description="중국 부양책 효과 발현, 제조업 PMI 52+ 지속",
        probability=0.20,
        time_horizon="6m",
        assumptions=[
            ScenarioAssumption("CHINA_PMI", "improve", "moderate",
                               "Caixin PMI 52+ 3개월 연속"),
            ScenarioAssumption("TRADE", "improve", "moderate",
                               "대중국 반도체 수출 회복"),
            ScenarioAssumption("DRAM_SPOT", "improve", "mild",
                               "중국 스마트폰/서버 수요 회복 → 메모리 수요 증가"),
        ],
        impacts=[
            ScenarioImpact("demand_cycle", +5, "레거시 반도체 수요 회복"),
            ScenarioImpact("price_cycle", +8, "범용 메모리 수요 증가 → 가격 지지"),
            ScenarioImpact("global_demand", +15, "최대 소비국 회복의 직접 효과"),
        ],
    ),

    # === 부정 시나리오 ===
    "recession_hard": Scenario(
        id="recession_hard",
        name="경기 침체 (Hard Landing)",
        description="Fed 긴축 과잉으로 경기침체 진입, 기업 투자 급감",
        probability=0.15,
        time_horizon="12m",
        assumptions=[
            ScenarioAssumption("GDP", "deteriorate", "severe",
                               "GDP 역성장 2분기 연속"),
            ScenarioAssumption("NFP", "deteriorate", "severe",
                               "실업률 5%+ 급등"),
            ScenarioAssumption("ISM_MFG", "deteriorate", "severe",
                               "PMI 45 이하 지속"),
            ScenarioAssumption("DGORDER", "deteriorate", "severe",
                               "비국방 자본재 주문 6개월 연속 감소"),
            ScenarioAssumption("DRAM_SPOT", "deteriorate", "severe",
                               "메모리 가격 40%+ 하락"),
            ScenarioAssumption("LEI", "deteriorate", "severe",
                               "선행지수 6개월+ 연속 하락"),
        ],
        impacts=[
            ScenarioImpact("demand_cycle", -25, "기업/소비자 지출 급감"),
            ScenarioImpact("supply_cycle", -15, "가동률 급락, 감산 돌입"),
            ScenarioImpact("price_cycle", -20, "메모리 가격 폭락, ASP 붕괴"),
            ScenarioImpact("macro_regime", -20, "전방위 매크로 악화"),
            ScenarioImpact("global_demand", -10, "글로벌 수요 동반 위축"),
        ],
    ),

    "trade_war_escalation": Scenario(
        id="trade_war_escalation",
        name="미중 기술전쟁 격화",
        description="대중국 반도체 수출 규제 확대, 보복 조치",
        probability=0.20,
        time_horizon="6m",
        assumptions=[
            ScenarioAssumption("TRADE", "deteriorate", "severe",
                               "반도체 수출 규제 확대 → 수출 급감"),
            ScenarioAssumption("CHINA_PMI", "deteriorate", "moderate",
                               "공급망 재편 혼란"),
            ScenarioAssumption("DRAM_SPOT", "deteriorate", "mild",
                               "중국 수요 감소 → 가격 하방 압력"),
        ],
        impacts=[
            ScenarioImpact("demand_cycle", -5, "중국향 수요 차질"),
            ScenarioImpact("supply_cycle", -3, "공급망 재편 비용"),
            ScenarioImpact("price_cycle", -8, "수요 감소 → 가격 약세"),
            ScenarioImpact("global_demand", -18, "최대 시장 접근 제한"),
        ],
    ),

    "ai_bubble_burst": Scenario(
        id="ai_bubble_burst",
        name="AI 투자 거품 붕괴",
        description="AI ROI 의문 → 빅테크 CapEx 급감, GPU/HBM 과잉재고",
        probability=0.10,
        time_horizon="12m",
        assumptions=[
            ScenarioAssumption("HYPERSCALER_CAPEX", "deteriorate", "severe",
                               "빅테크 CapEx 가이던스 30%+ 하향"),
            ScenarioAssumption("SEMI_BB", "deteriorate", "moderate",
                               "장비 주문 취소, B/B < 0.8"),
            ScenarioAssumption("SOX", "deteriorate", "severe",
                               "SOX 지수 30%+ 조정"),
            ScenarioAssumption("DRAM_SPOT", "deteriorate", "moderate",
                               "HBM 수요 급감 → 가격 하락"),
        ],
        impacts=[
            ScenarioImpact("demand_cycle", -20, "AI 수요 절벽"),
            ScenarioImpact("supply_cycle", -12, "장비 투자 급감, 과잉설비"),
            ScenarioImpact("price_cycle", -15, "메모리/GPU 가격 급락"),
            ScenarioImpact("macro_regime", -8, "테크 섹터 조정 → 시장 전반 영향"),
        ],
    ),
}


class ScenarioAnalyzer:
    """시나리오 분석기"""

    def __init__(self, db):
        self.db = db
        self.scenarios = dict(PREDEFINED_SCENARIOS)

    def add_custom_scenario(self, scenario: Scenario):
        """사용자 정의 시나리오 추가"""
        self.scenarios[scenario.id] = scenario
        logger.info(f"Added custom scenario: {scenario.name}")

    def analyze_scenario(self, scenario_id: str,
                         base_result=None) -> dict:
        """
        단일 시나리오 분석

        Args:
            scenario_id: 시나리오 ID
            base_result: 현재 CompositeResult (없으면 새로 계산)
        """
        scenario = self.scenarios.get(scenario_id)
        if not scenario:
            logger.error(f"Unknown scenario: {scenario_id}")
            return {}

        # 현재 스코어
        if base_result is None:
            from analysis.composite_score import CompositeScoreCalculator
            calc = CompositeScoreCalculator(self.db)
            base_result = calc.calculate()

        base_score = base_result.total_score

        # 시나리오 영향 적용
        dim_adjustments = {}
        for impact in scenario.impacts:
            dim_name = impact.dimension
            if dim_name in base_result.dimensions:
                original = base_result.dimensions[dim_name].score
                adjusted = max(0, min(100, original + impact.delta))
                dim_adjustments[dim_name] = {
                    "original": round(original, 1),
                    "delta": impact.delta,
                    "adjusted": round(adjusted, 1),
                    "explanation": impact.explanation,
                }

        # 조정된 총점 산출
        from analysis.composite_score import DIMENSION_CONFIG
        adjusted_total = 0.0
        total_weight = 0.0

        for dim_name, config in DIMENSION_CONFIG.items():
            if dim_name in dim_adjustments:
                score = dim_adjustments[dim_name]["adjusted"]
            elif dim_name in base_result.dimensions:
                score = base_result.dimensions[dim_name].score
            else:
                continue
            adjusted_total += score * config["weight"]
            total_weight += config["weight"]

        if total_weight > 0:
            adjusted_total = adjusted_total / total_weight
        adjusted_total = max(0, min(100, adjusted_total))

        # 조정된 regime
        adjusted_regime = self._score_to_regime(adjusted_total)

        return {
            "scenario": {
                "id": scenario.id,
                "name": scenario.name,
                "description": scenario.description,
                "probability": scenario.probability,
                "time_horizon": scenario.time_horizon,
            },
            "base_score": round(base_score, 1),
            "adjusted_score": round(adjusted_total, 1),
            "delta": round(adjusted_total - base_score, 1),
            "base_regime": base_result.regime,
            "adjusted_regime": adjusted_regime,
            "regime_changed": base_result.regime != adjusted_regime,
            "dimension_impacts": dim_adjustments,
            "assumptions": [
                {
                    "indicator": a.indicator_id,
                    "direction": a.assumed_direction,
                    "magnitude": a.magnitude,
                    "description": a.description,
                }
                for a in scenario.assumptions
            ],
        }

    def compare_scenarios(self, scenario_ids: list[str] = None,
                          base_result=None) -> ScenarioComparison:
        """
        복수 시나리오 비교

        Args:
            scenario_ids: 비교할 시나리오 ID 리스트 (None이면 전체)
        """
        if scenario_ids is None:
            scenario_ids = list(self.scenarios.keys())

        if base_result is None:
            from analysis.composite_score import CompositeScoreCalculator
            calc = CompositeScoreCalculator(self.db)
            base_result = calc.calculate()

        results = []
        for sid in scenario_ids:
            analysis = self.analyze_scenario(sid, base_result)
            if analysis:
                results.append(analysis)

        # 확률 가중 기대값 산출
        expected_score = base_result.total_score
        remaining_prob = 1.0

        for r in results:
            prob = r["scenario"]["probability"]
            expected_score += prob * r["delta"]
            remaining_prob -= prob

        # 남은 확률은 base 유지 (delta=0이므로 추가 안 해도 됨)

        comparison = ScenarioComparison(
            base_score=round(base_result.total_score, 1),
            scenarios=sorted(results, key=lambda x: x["adjusted_score"], reverse=True),
        )

        logger.info(f"Scenario comparison: {len(results)} scenarios analyzed")
        logger.info(f"  Base: {comparison.base_score:.1f}")
        logger.info(f"  Expected (prob-weighted): {expected_score:.1f}")

        return comparison

    def _score_to_regime(self, score: float) -> str:
        if score >= 65:
            return "expansion"
        elif score >= 50:
            return "late_cycle"
        elif score >= 35:
            return "contraction"
        else:
            return "recovery"

    def list_scenarios(self) -> list[dict]:
        """사용 가능한 시나리오 목록"""
        return [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "probability": s.probability,
                "time_horizon": s.time_horizon,
                "type": "positive" if any(i.delta > 0 for i in s.impacts) and
                        sum(i.delta for i in s.impacts) > 0 else "negative",
            }
            for s in self.scenarios.values()
        ]
