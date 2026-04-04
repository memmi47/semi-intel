#!/usr/bin/env python3
from __future__ import annotations
"""
Semi-Intel: Semiconductor Investment Intelligence
===================================================
Phase 1-4 Complete

사용법:
    # === Phase 1: 데이터 수집 ===
    python main.py setup / validate / collect / status / scheduler

    # === Phase 2: 분석 ===
    python main.py signals / score / briefing / scenarios / full

    # === Phase 4: AI 조언 ===
    python main.py ai-briefing        # AI 일일 브리핑 생성
    python main.py ai-ask "질문"      # 자유 질의
    python main.py ai-indicator ISM_MFG  # 지표 심층 분석
    python main.py ai-scenario ai_capex_surge  # 시나리오 심층 분석
    python main.py ai-regime          # Regime 전환 분석
    python main.py ai-chat            # 대화형 모드 (REPL)
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# ============================================================
# Logging 설정
# ============================================================

def setup_logging(log_dir: str = "./logs", level: str = "INFO"):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger.remove()  # 기본 핸들러 제거
    logger.add(sys.stderr, level=level, format="{time:HH:mm:ss} | {level:<7} | {message}")
    logger.add(
        f"{log_dir}/semi_intel_{{time:YYYY-MM-DD}}.log",
        level="DEBUG",
        rotation="1 day",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {module}:{function}:{line} | {message}",
    )


# ============================================================
# Commands
# ============================================================

def cmd_setup(db):
    """초기 설정: DB 테이블 생성 + 지표 메타데이터 동기화"""
    from config.indicators import ALL_INDICATORS

    logger.info("=== SETUP: Creating tables & syncing metadata ===")
    db.create_tables()
    db.sync_indicator_meta(ALL_INDICATORS)

    # 수동 입력 CSV 템플릿 생성
    from collectors.manual_collector import ManualCollector
    mc = ManualCollector(db)
    for ind_id in mc.MANUAL_SERIES:
        mc.create_csv_template(ind_id)

    logger.info("Setup complete!")
    logger.info("  → DB tables created")
    logger.info("  → Indicator metadata synced")
    logger.info("  → CSV templates created in ./data/manual/")
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. python main.py validate   # FRED 시리즈 유효성 검증")
    logger.info("  2. python main.py collect     # 데이터 수집 시작")


def cmd_validate(fred_api_key, db):
    """FRED 시리즈 코드 유효성 검증"""
    from collectors.fred_collector import FredCollector

    logger.info("=== VALIDATE: Checking all FRED series codes ===")
    collector = FredCollector(fred_api_key, db)
    result = collector.validate_all_series()

    print(f"\n{'='*60}")
    print(f"  Valid:   {len(result['valid'])} series")
    print(f"  Invalid: {len(result['invalid'])} series")

    if result["invalid"]:
        print(f"\n  ⚠ Invalid series (need fix in config/indicators.py):")
        for item in result["invalid"]:
            print(f"    {item['indicator']}: {item['code']} — expected: {item['expected']}")

    print(f"{'='*60}\n")


def cmd_collect_fred(fred_api_key, db):
    """FRED 데이터 수집"""
    from collectors.fred_collector import FredCollector

    collector = FredCollector(fred_api_key, db)
    results = collector.collect_all()
    return results


def cmd_collect_yahoo(db):
    """Yahoo Finance 데이터 수집"""
    from collectors.yahoo_collector import YahooCollector

    collector = YahooCollector(db)
    results = collector.collect_all()
    return results


def cmd_collect_capex(db):
    """Hyperscaler CapEx 수집"""
    from collectors.yahoo_collector import YahooCollector

    logger.info("=== Collecting Hyperscaler CapEx ===")
    collector = YahooCollector(db)
    results = collector.fetch_hyperscaler_financials()

    for symbol, data in results.items():
        if "error" in data:
            logger.warning(f"  {symbol}: {data['error']}")
        else:
            logger.info(f"  {symbol}: {len(data.get('capex', {}))} quarters")


def cmd_collect_all(fred_api_key, db):
    """전체 수집 (FRED + Yahoo + CapEx)"""
    logger.info("=== FULL COLLECTION START ===")
    start = datetime.now()

    cmd_collect_fred(fred_api_key, db)
    cmd_collect_yahoo(db)
    cmd_collect_capex(db)

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(f"=== FULL COLLECTION COMPLETE — {elapsed:.1f}s ===")


def cmd_status(db):
    """수집 현황 출력"""
    stats = db.get_collection_stats()

    print(f"\n{'='*60}")
    print(f"  Semi-Intel Data Status")
    print(f"{'='*60}")
    print(f"  Total records:     {stats['total_records']:,}")
    print(f"  Active series:     {stats['series_count']}")
    print(f"  Last collection:   {stats['latest_collection'] or 'Never'}")

    # 지표별 상세
    session = db.get_session()
    try:
        from sqlalchemy import func
        from db.database import TimeSeriesData, IndicatorMeta

        indicator_stats = (
            session.query(
                TimeSeriesData.indicator_id,
                func.count(TimeSeriesData.id),
                func.min(TimeSeriesData.date),
                func.max(TimeSeriesData.date),
            )
            .group_by(TimeSeriesData.indicator_id)
            .all()
        )

        if indicator_stats:
            print(f"\n  {'Indicator':<20} {'Records':>8} {'From':>12} {'To':>12}")
            print(f"  {'-'*55}")
            for ind_id, count, min_date, max_date in indicator_stats:
                print(f"  {ind_id:<20} {count:>8,} {str(min_date):>12} {str(max_date):>12}")

    finally:
        session.close()

    print(f"{'='*60}\n")


def cmd_scheduler(fred_api_key, db):
    """스케줄러: 자동 수집 데몬"""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BlockingScheduler()

    # FRED: 매일 오전 10시 (미국 동부 기준 데이터 발표 후)
    scheduler.add_job(
        cmd_collect_fred,
        CronTrigger(hour=10, minute=0),
        args=[fred_api_key, db],
        id="fred_daily",
        name="FRED Daily Collection",
    )

    # Yahoo: 매일 장 마감 후 (오후 5시)
    scheduler.add_job(
        cmd_collect_yahoo,
        CronTrigger(hour=17, minute=30),
        args=[db],
        id="yahoo_daily",
        name="Yahoo Daily Collection",
    )

    # Hyperscaler CapEx: 매주 월요일 (실적 시즌에 주 1회면 충분)
    scheduler.add_job(
        cmd_collect_capex,
        CronTrigger(day_of_week="mon", hour=8, minute=0),
        args=[db],
        id="capex_weekly",
        name="Hyperscaler CapEx Weekly",
    )

    logger.info("=== SCHEDULER STARTED ===")
    logger.info("  FRED:     Daily at 10:00")
    logger.info("  Yahoo:    Daily at 17:30")
    logger.info("  CapEx:    Weekly Monday 08:00")
    logger.info("  Press Ctrl+C to stop")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")


# ============================================================
# Phase 2 Commands: Analysis Engine
# ============================================================

def cmd_signals(db):
    """전체 지표 시그널 생성"""
    from analysis.signal_generator import SignalGenerator

    logger.info("=== SIGNAL GENERATION ===")
    gen = SignalGenerator(db)
    signals = gen.generate_all()

    print(f"\n{'='*70}")
    print(f"  Generated Signals: {len(signals)}")
    print(f"{'='*70}")

    bullish = [s for s in signals.values() if s.signal_type == "bullish"]
    bearish = [s for s in signals.values() if s.signal_type == "bearish"]
    neutral = [s for s in signals.values() if s.signal_type == "neutral"]

    for label, group, color in [("BULLISH", bullish, "▲"), ("BEARISH", bearish, "▼"), ("NEUTRAL", neutral, "●")]:
        if group:
            print(f"\n  {color} {label} ({len(group)})")
            for sig in sorted(group, key=lambda x: x.strength, reverse=True):
                print(f"    {sig.indicator_id:<22} strength={sig.strength:.2f}  {sig.description}")

    print(f"{'='*70}\n")
    return signals


def cmd_score(db):
    """Composite Score 산출"""
    from analysis.composite_score import CompositeScoreCalculator

    logger.info("=== COMPOSITE SCORE CALCULATION ===")
    calc = CompositeScoreCalculator(db)
    result = calc.calculate()

    regime_mark = {"expansion": "🟢", "late_cycle": "🟡", "contraction": "🔴", "recovery": "🔵"}
    mark = regime_mark.get(result.regime, "⚪")

    print(f"\n{'='*70}")
    print(f"  {mark} Semiconductor Cycle Score: {result.total_score:.1f} / 100")
    print(f"  Regime: {result.regime.upper()}")
    print(f"  {result.regime_description}")
    
    if result.trend_alert:
        print(f"\n  [TREND ALERT] {result.trend_alert}")
        
    print(f"  Confidence: {result.confidence_level} | Data coverage: {result.data_coverage*100:.0f}%")
    print(f"{'='*70}")

    print(f"\n  {'Dimension':<18} {'Score':>6} {'Weight':>8} {'Confidence':>12}")
    print(f"  {'-'*48}")
    for name, dim in result.dimensions.items():
        bar = "█" * int(dim.score / 10) + "░" * (10 - int(dim.score / 10))
        print(f"  {name:<18} {dim.score:>6.1f} {dim.weight*100:>6.0f}%  {bar}  {dim.confidence:.0%}")

    print(f"\n  Investment Action:")
    for action in result.investment_action.split(" | "):
        print(f"    → {action}")
    print(f"{'='*70}\n")

    # DB 저장
    calc.save_to_db(result)
    return result


def cmd_briefing(db, output_format="console"):
    """투자 브리핑 생성"""
    from analysis.briefing import BriefingGenerator

    logger.info(f"=== BRIEFING GENERATION ({output_format}) ===")
    gen = BriefingGenerator(db)

    if output_format == "console":
        gen.to_console()
    elif output_format == "md":
        filepath = gen.save_markdown()
        print(f"\nBriefing saved: {filepath}")
    elif output_format == "json":
        filepath = gen.save_json()
        print(f"\nBriefing JSON saved: {filepath}")


def cmd_scenarios(db, scenario_id=None):
    """시나리오 분석"""
    from analysis.scenario_analyzer import ScenarioAnalyzer

    logger.info("=== SCENARIO ANALYSIS ===")
    analyzer = ScenarioAnalyzer(db)

    if scenario_id:
        # 개별 시나리오
        result = analyzer.analyze_scenario(scenario_id)
        if not result:
            print(f"Unknown scenario: {scenario_id}")
            print(f"Available: {[s['id'] for s in analyzer.list_scenarios()]}")
            return

        sc = result["scenario"]
        print(f"\n{'='*70}")
        print(f"  Scenario: {sc['name']}")
        print(f"  {sc['description']}")
        print(f"  Probability: {sc['probability']*100:.0f}% | Horizon: {sc['time_horizon']}")
        print(f"{'='*70}")
        print(f"  Base Score:     {result['base_score']:.1f} ({result['base_regime']})")
        print(f"  Adjusted Score: {result['adjusted_score']:.1f} ({result['adjusted_regime']})")
        print(f"  Delta:          {result['delta']:+.1f}")
        if result["regime_changed"]:
            print(f"  ⚠️  REGIME CHANGE: {result['base_regime']} → {result['adjusted_regime']}")

        print(f"\n  Dimension Impacts:")
        for dim, impact in result["dimension_impacts"].items():
            print(f"    {dim:<18} {impact['original']:.1f} → {impact['adjusted']:.1f} ({impact['delta']:+.1f})")
            print(f"    {'':18} {impact['explanation']}")

        print(f"\n  Assumptions:")
        for a in result["assumptions"]:
            print(f"    {a['indicator']}: {a['description']}")
        print(f"{'='*70}\n")

    else:
        # 전체 비교
        comparison = analyzer.compare_scenarios()

        print(f"\n{'='*70}")
        print(f"  Scenario Comparison — Base Score: {comparison.base_score:.1f}")
        print(f"{'='*70}")
        print(f"  {'Scenario':<25} {'Prob':>5} {'Delta':>7} {'Score':>7} {'Regime':<15}")
        print(f"  {'-'*62}")
        for sc in comparison.scenarios:
            delta_mark = "+" if sc["delta"] > 0 else ""
            regime_warn = " ⚠️" if sc["regime_changed"] else ""
            print(f"  {sc['scenario']['name']:<25} {sc['scenario']['probability']*100:>4.0f}% "
                  f"{delta_mark}{sc['delta']:>6.1f} {sc['adjusted_score']:>6.1f}  "
                  f"{sc['adjusted_regime']}{regime_warn}")
        print(f"{'='*70}\n")


def cmd_full(fred_api_key, db):
    """전체 파이프라인: 수집 → 분석 → 브리핑"""
    logger.info("=== FULL PIPELINE: Collect + Analyze + Brief ===")
    start = datetime.now()

    # Phase 1: 수집
    cmd_collect_all(fred_api_key, db)

    # Phase 2: 분석
    cmd_score(db)
    cmd_scenarios(db)

    # 브리핑 생성 (콘솔 + 파일)
    cmd_briefing(db, "console")
    cmd_briefing(db, "md")
    cmd_briefing(db, "json")

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(f"=== FULL PIPELINE COMPLETE — {elapsed:.1f}s ===")


# ============================================================
# Main
# ============================================================

def main():
    load_dotenv()

    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_dir = os.getenv("LOG_DIR", "./logs")
    setup_logging(log_dir, log_level)

    # DB 초기화
    db_type = os.getenv("DB_TYPE", "sqlite")
    db_path = os.getenv("DB_PATH", "./data/semi_intel.db")
    db_url = os.getenv("DB_URL")

    from db.database import DatabaseManager
    db = DatabaseManager(db_type=db_type, db_path=db_path, db_url=db_url)
    db.create_tables()

    fred_api_key = os.getenv("FRED_API_KEY", "")

    def require_fred():
        if not fred_api_key or fred_api_key == "your_fred_api_key_here":
            logger.error("FRED_API_KEY not set. Edit .env file first.")
            sys.exit(1)

    # 커맨드 라우팅
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    # Phase 1: Data
    if cmd == "setup":
        cmd_setup(db)
    elif cmd == "validate":
        require_fred()
        cmd_validate(fred_api_key, db)
    elif cmd == "collect":
        require_fred()
        cmd_collect_all(fred_api_key, db)
    elif cmd == "collect-fred":
        require_fred()
        cmd_collect_fred(fred_api_key, db)
    elif cmd == "collect-yahoo":
        cmd_collect_yahoo(db)
    elif cmd == "collect-capex":
        cmd_collect_capex(db)
    elif cmd == "status":
        cmd_status(db)
    elif cmd == "scheduler":
        require_fred()
        cmd_scheduler(fred_api_key, db)

    # Phase 2: Analysis
    elif cmd == "signals":
        cmd_signals(db)
    elif cmd == "score":
        cmd_score(db)
    elif cmd == "briefing":
        cmd_briefing(db, "console")
    elif cmd == "briefing-md":
        cmd_briefing(db, "md")
    elif cmd == "briefing-json":
        cmd_briefing(db, "json")
    elif cmd == "scenarios":
        cmd_scenarios(db)
    elif cmd == "scenario":
        sid = sys.argv[2] if len(sys.argv) > 2 else None
        if not sid:
            print("Usage: python main.py scenario <scenario_id>")
            print("Run 'python main.py scenarios' to see available IDs")
        else:
            cmd_scenarios(db, scenario_id=sid)
    elif cmd == "full":
        require_fred()
        cmd_full(fred_api_key, db)

    # Phase 4: AI Advisory
    elif cmd == "ai-briefing":
        require_llm(db)
    elif cmd == "ai-ask":
        question = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
        if not question:
            print("Usage: python main.py ai-ask \"your question here\"")
        else:
            require_llm_ask(db, question)
    elif cmd == "ai-indicator":
        ind_id = sys.argv[2] if len(sys.argv) > 2 else None
        if not ind_id:
            print("Usage: python main.py ai-indicator <INDICATOR_ID>")
        else:
            require_llm_indicator(db, ind_id)
    elif cmd == "ai-scenario":
        sid = sys.argv[2] if len(sys.argv) > 2 else None
        if not sid:
            print("Usage: python main.py ai-scenario <scenario_id>")
        else:
            require_llm_scenario(db, sid)
    elif cmd == "ai-regime":
        require_llm_regime(db)
    elif cmd == "ai-chat":
        require_llm_chat(db)

    else:
        print("""
Semi-Intel: Semiconductor Investment Intelligence
===================================================

Phase 1 — Data Collection:
  setup            초기 설정 (DB + 메타데이터 + CSV 템플릿)
  validate         FRED 시리즈 유효성 검증
  collect          전체 수집 (FRED + Yahoo + CapEx)
  status           수집 현황 확인
  scheduler        자동 수집 스케줄러 실행

Phase 2 — Analysis:
  signals          전체 지표 시그널 생성
  score            Semiconductor Cycle Composite Score
  briefing         투자 브리핑 (콘솔 출력)
  scenarios        전체 시나리오 비교
  full             수집 → 분석 → 브리핑 전체 실행

Phase 4 — AI Advisory (requires LLM_PROVIDER + API KEY):
  ai-briefing              AI 일일 브리핑 생성
  ai-ask "질문"            자유 질의 (현재 데이터 기반)
  ai-indicator <ID>        지표 심층 분석
  ai-scenario <ID>         시나리오 심층 분석
  ai-regime                Regime 전환 가능성 분석
  ai-chat                  대화형 모드 (REPL)

Quick Start:
  1. cp .env.example .env  # FRED_API_KEY + GOOGLE_API_KEY 입력
  2. pip install -r requirements.txt
  3. python main.py setup && python main.py collect
  4. python main.py ai-chat
        """)


# ============================================================
# Phase 4 Command Implementations
# ============================================================

def _get_engine(db):
    """AdvisoryEngine 초기화 — .env의 LLM_PROVIDER 설정 자동 감지"""
    provider = os.getenv("LLM_PROVIDER", "google")
    key_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
    }
    env_key = key_map.get(provider, "GOOGLE_API_KEY")
    api_key = os.getenv(env_key, "")
    if not api_key:
        logger.error(f"{env_key} not set. Add it to .env file. (LLM_PROVIDER={provider})")
        sys.exit(1)
    from advisory.engine import AdvisoryEngine
    return AdvisoryEngine(db, provider=provider)


def require_llm(db):
    """AI 일일 브리핑"""
    engine = _get_engine(db)
    print(f"\n{'='*70}")
    print(f"  Semi-Intel AI Daily Briefing")
    print(f"{'='*70}\n")

    for chunk in engine.daily_briefing_stream():
        print(chunk, end="", flush=True)

    print(f"\n\n{'='*70}")
    print(f"  {engine.get_usage()}")
    print(f"{'='*70}\n")

    # 파일 저장
    engine.new_conversation()
    content = engine.daily_briefing()
    filepath = engine.save_briefing(content)
    print(f"  Saved: {filepath}")


def require_llm_ask(db, question):
    """AI 자유 질의"""
    engine = _get_engine(db)
    print(f"\n  Q: {question}\n")
    print(f"{'─'*70}\n")

    for chunk in engine.ask_stream(question):
        print(chunk, end="", flush=True)

    print(f"\n\n{'─'*70}")
    print(f"  {engine.get_usage()}\n")


def require_llm_indicator(db, indicator_id):
    """AI 지표 분석"""
    engine = _get_engine(db)
    print(f"\n  Analyzing: {indicator_id}\n")
    print(f"{'─'*70}\n")
    result = engine.analyze_indicator(indicator_id)
    print(result)
    print(f"\n{'─'*70}")
    print(f"  {engine.get_usage()}\n")


def require_llm_scenario(db, scenario_id):
    """AI 시나리오 분석"""
    engine = _get_engine(db)
    print(f"\n  Scenario: {scenario_id}\n")
    print(f"{'─'*70}\n")
    result = engine.analyze_scenario(scenario_id)
    print(result)
    print(f"\n{'─'*70}")
    print(f"  {engine.get_usage()}\n")


def require_llm_regime(db):
    """AI Regime 전환 분석"""
    engine = _get_engine(db)
    print(f"\n  Regime Transition Analysis\n")
    print(f"{'─'*70}\n")
    result = engine.analyze_regime_transition()
    print(result)
    print(f"\n{'─'*70}")
    print(f"  {engine.get_usage()}\n")


def require_llm_chat(db):
    """대화형 REPL 모드"""
    engine = _get_engine(db)

    print(f"""
{'='*70}
  Semi-Intel AI Chat
  반도체/AI 섹터 투자에 대해 질문하세요.
  현재 경제지표 데이터가 자동으로 컨텍스트에 포함됩니다.
{'='*70}
  Commands:
    /new      새 대화 시작 (히스토리 초기화)
    /briefing AI 브리핑 생성
    /regime   Regime 전환 분석
    /usage    토큰 사용량
    /quit     종료
{'='*70}
""")

    while True:
        try:
            user_input = input("  You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  Goodbye!")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd == "/quit" or cmd == "/exit":
                print("  Goodbye!")
                break
            elif cmd == "/new":
                engine.new_conversation()
                print("  ↻ New conversation started.\n")
                continue
            elif cmd == "/briefing":
                print(f"\n{'─'*70}\n")
                for chunk in engine.daily_briefing_stream():
                    print(chunk, end="", flush=True)
                print(f"\n\n{'─'*70}\n")
                continue
            elif cmd == "/regime":
                print(f"\n{'─'*70}\n")
                result = engine.analyze_regime_transition()
                print(result)
                print(f"\n{'─'*70}\n")
                continue
            elif cmd == "/usage":
                print(f"  {engine.get_usage()}\n")
                continue
            else:
                print(f"  Unknown command: {cmd}\n")
                continue

        # 일반 질문
        print(f"\n{'─'*70}\n  Semi-Intel: ", end="")
        for chunk in engine.ask_stream(user_input):
            print(chunk, end="", flush=True)
        print(f"\n\n{'─'*70}\n")


if __name__ == "__main__":
    main()
