from __future__ import annotations
"""
Prompt Templates
=================
투자 조언 생성을 위한 프롬프트 템플릿
- System prompts: Claude의 역할/행동 정의
- Context builders: 데이터를 프롬프트 컨텍스트로 변환
- Query templates: 특정 분석 유형별 질의
"""

import json
from datetime import date


# ============================================================
# System Prompts
# ============================================================

SYSTEM_PROMPT_ADVISOR = """You are Semi-Intel, a semiconductor industry investment analyst AI.

ROLE:
- 반도체/AI 섹터 전문 투자 분석가
- 매크로 경제지표를 반도체 산업 사이클에 연결하여 해석
- 구조적 분석 + 전략적 시사점 도출

ANALYSIS FRAMEWORK:
- Bernard Baumohl의 "The Secrets of Economic Indicators" 기반 지표 해석
- 5차원 분석: Demand Cycle, Supply Cycle, Price Cycle, Macro Regime, Global Demand
- 4단계 사이클: Expansion → Late Cycle → Contraction → Recovery
- 시나리오 기반 의사결정 프레임워크

RESPONSE STYLE:
- 핵심 요약(2-3문장) → 논리 구조 → 근거/데이터 → 전략적 시사점
- 멀티레벨 불릿, 1-2문장/불릿
- 인과관계와 전달 경로(transmission mechanism) 명시
- 불확실성과 대안적 시나리오 함께 제시
- 숫자/데이터 기반 주장

CONSTRAINTS:
- 특정 종목 매수/매도 추천은 하지 않음 — 섹터/테마 수준의 방향성 제시
- 예측의 확률적 성격을 항상 명시
- 데이터가 불충분한 영역은 솔직하게 인정
- 과거 패턴이 미래를 보장하지 않음을 전제

LANGUAGE: 사용자의 언어에 맞춤 (한국어 우선)"""


SYSTEM_PROMPT_BRIEFING = """You are Semi-Intel, generating a concise investment briefing for a semiconductor sector investor.

FORMAT:
1. 핵심 판단 (1-2문장 — 현재 사이클 위치와 투자 방향)
2. 핵심 시그널 (bullish/bearish 각 2-3개, 데이터 수치 포함)
3. 차원별 진단 (5개 차원, 각 1-2문장)
4. 시나리오 리스크 (가장 주의할 시나리오 1-2개)
5. 행동 권고 (구체적 액션 2-3개)

STYLE: 간결, 숫자 중심, 모호한 표현 배제. "좋아 보인다" 대신 "ISM New Orders 54.2로 3개월 연속 확장 영역 — 반도체 수요 2-3개월 후행 반영 예상"

LANGUAGE: 한국어"""


SYSTEM_PROMPT_SCENARIO = """You are Semi-Intel, analyzing a specific scenario's impact on the semiconductor sector.

ANALYSIS STRUCTURE:
1. 시나리오 요약 및 발생 조건
2. 전달 경로 (Transmission Mechanism): 시나리오 → 각 차원 → 반도체 섹터
3. 시간축: 즉각적 영향 (1-3개월) vs 구조적 영향 (6-12개월)
4. 수혜/피해 세그먼트: Memory vs Logic vs Equipment vs Materials
5. 대응 전략: 포지션 조정 방안
6. 모니터링 포인트: 시나리오 실현 여부 확인 지표

LANGUAGE: 한국어"""


# ============================================================
# Context Builders — 분석 데이터를 프롬프트 컨텍스트로 변환
# ============================================================

def build_score_context(composite_result) -> str:
    """CompositeResult → 프롬프트 컨텍스트 문자열"""
    lines = []
    lines.append(f"=== SEMICONDUCTOR CYCLE SCORE: {composite_result.total_score:.1f}/100 ===")
    lines.append(f"Regime: {composite_result.regime.upper()}")
    lines.append(f"Description: {composite_result.regime_description}")
    lines.append(f"Confidence: {composite_result.confidence_level} (data coverage {composite_result.data_coverage:.0%})")
    lines.append("")

    lines.append("=== DIMENSION SCORES ===")
    for name, dim in composite_result.dimensions.items():
        lines.append(f"\n[{name.upper()}] Score: {dim.score:.1f}/100 (weight: {dim.weight:.0%})")
        for sig in dim.contributing_signals:
            arrow = "▲" if sig["signal_type"] == "bullish" else "▼" if sig["signal_type"] == "bearish" else "●"
            lines.append(f"  {arrow} {sig['indicator_id']}: {sig['description']} (strength: {sig['strength']:.2f})")

    lines.append(f"\n=== INVESTMENT ACTION ===")
    lines.append(composite_result.investment_action)

    return "\n".join(lines)


def build_signals_context(signals: dict) -> str:
    """Signal dict → 프롬프트 컨텍스트"""
    lines = ["=== CURRENT SIGNALS ==="]

    bullish = [(k, v) for k, v in signals.items() if v.signal_type == "bullish"]
    bearish = [(k, v) for k, v in signals.items() if v.signal_type == "bearish"]
    neutral = [(k, v) for k, v in signals.items() if v.signal_type == "neutral"]

    bullish.sort(key=lambda x: x[1].strength, reverse=True)
    bearish.sort(key=lambda x: x[1].strength, reverse=True)

    if bullish:
        lines.append("\nBULLISH:")
        for k, v in bullish:
            lines.append(f"  ▲ {k} (strength {v.strength:.2f}): {v.description}")
            if v.sub_signals:
                for sk, sv in v.sub_signals.items():
                    lines.append(f"    - {sk}: {sv}")

    if bearish:
        lines.append("\nBEARISH:")
        for k, v in bearish:
            lines.append(f"  ▼ {k} (strength {v.strength:.2f}): {v.description}")
            if v.sub_signals:
                for sk, sv in v.sub_signals.items():
                    lines.append(f"    - {sk}: {sv}")

    if neutral:
        lines.append(f"\nNEUTRAL: {', '.join(k for k, _ in neutral)}")

    return "\n".join(lines)


def build_scenario_context(scenario_result: dict) -> str:
    """시나리오 분석 결과 → 프롬프트 컨텍스트"""
    sc = scenario_result["scenario"]
    lines = [
        f"=== SCENARIO: {sc['name']} ===",
        f"Description: {sc['description']}",
        f"Probability: {sc['probability']*100:.0f}%",
        f"Time Horizon: {sc['time_horizon']}",
        f"",
        f"Base Score: {scenario_result['base_score']:.1f} → Adjusted: {scenario_result['adjusted_score']:.1f} (delta: {scenario_result['delta']:+.1f})",
        f"Regime: {scenario_result['base_regime']} → {scenario_result['adjusted_regime']}",
        f"Regime Changed: {'YES' if scenario_result['regime_changed'] else 'No'}",
        f"",
        "Dimension Impacts:"
    ]
    for dim, impact in scenario_result.get("dimension_impacts", {}).items():
        lines.append(f"  {dim}: {impact['original']:.1f} → {impact['adjusted']:.1f} ({impact['delta']:+.1f}) — {impact['explanation']}")

    lines.append("\nAssumptions:")
    for a in scenario_result.get("assumptions", []):
        lines.append(f"  {a['indicator']}: {a['description']}")

    return "\n".join(lines)


def build_comparison_context(comparison) -> str:
    """시나리오 비교 → 프롬프트 컨텍스트"""
    lines = [
        f"=== SCENARIO COMPARISON ===",
        f"Base Score: {comparison.base_score:.1f}",
        f""
    ]
    for sc in comparison.scenarios:
        s = sc["scenario"]
        delta_mark = "+" if sc["delta"] > 0 else ""
        lines.append(f"  {s['name']:<25} prob={s['probability']*100:.0f}%  delta={delta_mark}{sc['delta']:.1f}  score={sc['adjusted_score']:.1f}  regime={sc['adjusted_regime']}")

    return "\n".join(lines)


def build_indicator_context(indicator_id: str, series_data: dict) -> str:
    """개별 지표 데이터 → 프롬프트 컨텍스트"""
    lines = [f"=== INDICATOR: {indicator_id} ==="]
    for code, data in series_data.items():
        lines.append(f"\n[{code}] {data.get('name', code)}")
        lines.append(f"  Latest: {data['latest_value']} ({data['latest_date']})")
        lines.append(f"  Data points: {data['data_points']}")
        if "recent" in data and len(data["recent"]) >= 3:
            recent = data["recent"][-6:]
            recent_str = ", ".join(str(r["date"]) + ": " + str(r["value"]) for r in recent)
            lines.append(f"  Recent: {recent_str}")
    return "\n".join(lines)


# ============================================================
# Query Templates
# ============================================================

def query_briefing(score_context: str, signals_context: str, comparison_context: str) -> str:
    """투자 브리핑 생성 쿼리"""
    return f"""다음 데이터를 기반으로 오늘의 반도체 섹터 투자 브리핑을 생성해 주세요.

{score_context}

{signals_context}

{comparison_context}

오늘 날짜: {date.today()}"""


def query_indicator_analysis(indicator_id: str, indicator_context: str, score_context: str) -> str:
    """개별 지표 심층 분석 쿼리"""
    return f"""다음 지표를 반도체/AI 섹터 투자 관점에서 심층 분석해 주세요.

{indicator_context}

현재 반도체 사이클 위치:
{score_context}

분석 포인트:
1. 이 지표의 현재 수준이 반도체 섹터에 미치는 구체적 영향
2. 과거 사이클에서 유사 수준일 때 반도체 섹터 성과
3. 향후 3-6개월 전망 시사점
4. 모니터링할 임계값"""


def query_scenario_deep_dive(scenario_context: str, score_context: str) -> str:
    """시나리오 심층 분석 쿼리"""
    return f"""다음 시나리오가 반도체 섹터에 미치는 영향을 심층 분석해 주세요.

{scenario_context}

현재 사이클 위치:
{score_context}

분석 요구:
1. 전달 경로(transmission mechanism): 시나리오 → 수요/공급/가격 → 반도체 세그먼트별 영향
2. 시간축 분석: 즉각적(1-3개월) vs 구조적(6-12개월) 영향 구분
3. 세그먼트별 차등 영향: Memory(DRAM/NAND/HBM) / Logic / Equipment / Materials
4. 대응 전략: 포지션 조정 방안
5. 모니터링 지표: 시나리오 실현 확률을 조기에 감지할 선행 신호"""


def query_what_if(user_question: str, score_context: str, signals_context: str) -> str:
    """사용자 자유 질의 쿼리"""
    return f"""사용자 질문: {user_question}

현재 반도체 사이클 데이터:
{score_context}

현재 시그널:
{signals_context}

위 데이터를 참고하여 사용자 질문에 답변해 주세요. 반도체/AI 섹터 투자 관점에서 답변하되, 데이터에 근거한 구체적 분석을 제공하세요."""


def query_regime_transition(score_context: str, signals_context: str) -> str:
    """Regime 전환 가능성 분석"""
    return f"""현재 반도체 사이클 데이터를 기반으로 Regime 전환 가능성을 분석해 주세요.

{score_context}

{signals_context}

분석 요구:
1. 현재 Regime 유지 확률 vs 전환 확률
2. 가장 가능성 높은 전환 방향과 트리거
3. 전환 확인을 위한 선행 시그널 3-5개
4. 전환 시 포트폴리오 조정 타이밍"""
