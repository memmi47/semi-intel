from __future__ import annotations
"""
Advisory Engine
================
데이터 수집/분석 결과 + LLM API → 투자 조언 생성

지원 LLM: Anthropic Claude, OpenAI GPT, Google Gemini
.env의 LLM_PROVIDER 설정으로 선택 (기본: anthropic)

기능:
- 일일 브리핑 자동 생성
- 지표 심층 분석
- 시나리오 영향 분석
- 자유 질의 (What-if)
- Regime 전환 분석
- 대화형 인터랙션
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Generator

from loguru import logger

from advisory.llm_client import create_llm_client
from advisory.prompts import (
    SYSTEM_PROMPT_ADVISOR, SYSTEM_PROMPT_BRIEFING, SYSTEM_PROMPT_SCENARIO,
    build_score_context, build_signals_context, build_scenario_context,
    build_comparison_context, build_indicator_context,
    query_briefing, query_indicator_analysis, query_scenario_deep_dive,
    query_what_if, query_regime_transition,
)


class AdvisoryEngine:
    """
    반도체 투자 AI 조언 엔진

    사용법:
        engine = AdvisoryEngine(db)  # .env 설정 자동 감지
        engine = AdvisoryEngine(db, provider="openai")  # OpenAI 사용
        engine = AdvisoryEngine(db, provider="google")  # Gemini 사용

        # 일일 브리핑
        briefing = engine.daily_briefing()

        # 자유 질문
        answer = engine.ask("HBM 수요가 DRAM 가격에 미치는 영향은?")

        # 스트리밍
        for chunk in engine.ask_stream("분석해줘"):
            print(chunk, end="")

        # 시나리오 분석
        analysis = engine.analyze_scenario("ai_capex_surge")
    """

    def __init__(self, db, provider: str | None = None,
                 api_key: str | None = None, model: str | None = None):
        self.db = db
        self.client = create_llm_client(provider=provider, api_key=api_key, model=model)

        # 캐시: 반복 호출 방지
        self._score_cache = None
        self._score_cache_date = None
        self._signals_cache = None

    # ============================================================
    # 내부: 데이터 수집 + 컨텍스트 빌드
    # ============================================================

    def _get_score(self):
        """Composite Score (당일 캐시)"""
        today = date.today()
        if self._score_cache and self._score_cache_date == today:
            return self._score_cache

        from analysis.composite_score import CompositeScoreCalculator
        calc = CompositeScoreCalculator(self.db)
        self._score_cache = calc.calculate()
        self._score_cache_date = today
        return self._score_cache

    def _get_signals(self):
        """전체 시그널 (당일 캐시)"""
        today = date.today()
        if self._signals_cache and self._score_cache_date == today:
            return self._signals_cache

        from analysis.signal_generator import SignalGenerator
        gen = SignalGenerator(self.db)
        self._signals_cache = gen.generate_all()
        return self._signals_cache

    def _get_scenarios_comparison(self):
        """시나리오 비교"""
        from analysis.scenario_analyzer import ScenarioAnalyzer
        analyzer = ScenarioAnalyzer(self.db)
        return analyzer.compare_scenarios(base_result=self._get_score())

    def _build_full_context(self) -> tuple[str, str, str]:
        """Score + Signals + Scenarios 컨텍스트 일괄 생성"""
        score_ctx = build_score_context(self._get_score())
        signals_ctx = build_signals_context(self._get_signals())
        comparison_ctx = build_comparison_context(self._get_scenarios_comparison())
        return score_ctx, signals_ctx, comparison_ctx

    # ============================================================
    # Public API: 브리핑
    # ============================================================

    def daily_briefing(self) -> str:
        """일일 투자 브리핑 생성"""
        logger.info("Generating daily briefing...")
        score_ctx, signals_ctx, comparison_ctx = self._build_full_context()

        query = query_briefing(score_ctx, signals_ctx, comparison_ctx)
        response = self.client.chat(
            user_message=query,
            system=SYSTEM_PROMPT_BRIEFING,
            include_history=False,
            temperature=0.2,
        )

        logger.info(f"Briefing generated. {self.client.get_usage_summary()}")
        return response

    def daily_briefing_stream(self) -> Generator[str, None, None]:
        """일일 브리핑 (스트리밍)"""
        logger.info("Generating daily briefing (streaming)...")
        score_ctx, signals_ctx, comparison_ctx = self._build_full_context()

        query = query_briefing(score_ctx, signals_ctx, comparison_ctx)
        yield from self.client.stream(
            user_message=query,
            system=SYSTEM_PROMPT_BRIEFING,
            include_history=False,
            temperature=0.2,
        )

    # ============================================================
    # Public API: 자유 질의
    # ============================================================

    def ask(self, question: str) -> str:
        """자유 질문 — 현재 데이터 컨텍스트 포함하여 답변"""
        score_ctx = build_score_context(self._get_score())
        signals_ctx = build_signals_context(self._get_signals())

        query = query_what_if(question, score_ctx, signals_ctx)
        response = self.client.chat(
            user_message=query,
            system=SYSTEM_PROMPT_ADVISOR,
            include_history=True,
            temperature=0.3,
        )
        return response

    def ask_stream(self, question: str) -> Generator[str, None, None]:
        """자유 질문 (스트리밍)"""
        score_ctx = build_score_context(self._get_score())
        signals_ctx = build_signals_context(self._get_signals())

        query = query_what_if(question, score_ctx, signals_ctx)
        yield from self.client.stream(
            user_message=query,
            system=SYSTEM_PROMPT_ADVISOR,
            include_history=True,
            temperature=0.3,
        )

    # ============================================================
    # Public API: 지표 심층 분석
    # ============================================================

    def analyze_indicator(self, indicator_id: str) -> str:
        """개별 지표 심층 분석"""
        from config.indicators import get_indicator
        ind = get_indicator(indicator_id)
        if not ind:
            return f"Unknown indicator: {indicator_id}"

        # 지표 데이터 수집
        series_data = {}
        for s in ind.fred_series:
            data = self.db.get_series_data(s.code)
            if data:
                recent = data[-24:]
                series_data[s.code] = {
                    "name": s.name,
                    "latest_value": recent[-1]["value"],
                    "latest_date": str(recent[-1]["date"]),
                    "data_points": len(data),
                    "recent": [{"date": str(d["date"]), "value": d["value"]} for d in recent],
                }

        ind_ctx = build_indicator_context(indicator_id, series_data)
        score_ctx = build_score_context(self._get_score())

        query = query_indicator_analysis(indicator_id, ind_ctx, score_ctx)
        return self.client.chat(
            user_message=query,
            system=SYSTEM_PROMPT_ADVISOR,
            include_history=False,
            temperature=0.3,
        )

    # ============================================================
    # Public API: 시나리오 분석
    # ============================================================

    def analyze_scenario(self, scenario_id: str) -> str:
        """시나리오 심층 분석"""
        from analysis.scenario_analyzer import ScenarioAnalyzer
        analyzer = ScenarioAnalyzer(self.db)
        result = analyzer.analyze_scenario(scenario_id, base_result=self._get_score())

        if not result:
            return f"Unknown scenario: {scenario_id}"

        scenario_ctx = build_scenario_context(result)
        score_ctx = build_score_context(self._get_score())

        query = query_scenario_deep_dive(scenario_ctx, score_ctx)
        return self.client.chat(
            user_message=query,
            system=SYSTEM_PROMPT_SCENARIO,
            include_history=False,
            temperature=0.3,
        )

    # ============================================================
    # Public API: Regime 전환 분석
    # ============================================================

    def analyze_regime_transition(self) -> str:
        """Regime 전환 가능성 분석"""
        score_ctx = build_score_context(self._get_score())
        signals_ctx = build_signals_context(self._get_signals())

        query = query_regime_transition(score_ctx, signals_ctx)
        return self.client.chat(
            user_message=query,
            system=SYSTEM_PROMPT_ADVISOR,
            include_history=False,
            temperature=0.3,
        )

    # ============================================================
    # 유틸리티
    # ============================================================

    def new_conversation(self):
        """새 대화 시작 (히스토리 초기화)"""
        self.client.clear_history()
        self._score_cache = None
        self._signals_cache = None

    def save_briefing(self, content: str, output_dir: str = "./reports"):
        """브리핑을 파일로 저장"""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        filepath = Path(output_dir) / f"ai_briefing_{date.today()}.md"
        with open(filepath, "w") as f:
            f.write(f"# Semi-Intel AI Briefing — {date.today()}\n\n")
            f.write(content)
        logger.info(f"AI Briefing saved: {filepath}")
        return str(filepath)

    def get_usage(self) -> str:
        return self.client.get_usage_summary()
