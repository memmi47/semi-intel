from __future__ import annotations
"""
Investment Briefing Generator
==============================
Composite Score + Signals + Scenarios → 사람이 읽을 수 있는 투자 브리핑 생성

출력 형식:
  - 콘솔 출력 (Rich library)
  - 마크다운 파일
  - JSON (대시보드 API용)
"""

import json
from datetime import date, datetime
from pathlib import Path

from loguru import logger

from analysis.composite_score import CompositeResult, CompositeScoreCalculator
from analysis.scenario_analyzer import ScenarioAnalyzer, ScenarioComparison


class BriefingGenerator:
    """투자 브리핑 생성기"""

    def __init__(self, db):
        self.db = db

    def generate_full_briefing(self) -> dict:
        """전체 브리핑 생성 (스코어 + 시그널 + 시나리오)"""

        # 1) Composite Score
        calc = CompositeScoreCalculator(self.db)
        result = calc.calculate()

        # 2) Scenario Analysis
        analyzer = ScenarioAnalyzer(self.db)
        comparison = analyzer.compare_scenarios(base_result=result)

        # 3) 브리핑 조립
        briefing = {
            "generated_at": datetime.utcnow().isoformat(),
            "date": str(date.today()),

            # 핵심 요약
            "summary": {
                "total_score": result.total_score,
                "regime": result.regime,
                "regime_description": result.regime_description,
                "confidence": result.confidence_level,
                "data_coverage": result.data_coverage,
                "investment_action": result.investment_action,
            },

            # 차원별 상세
            "dimensions": {},

            # 주요 시그널 (bullish/bearish만)
            "key_signals": {
                "bullish": [],
                "bearish": [],
                "neutral_count": 0,
            },

            # 시나리오 분석
            "scenarios": [],

            # 리스크 및 모니터링 포인트
            "risk_watch": [],
        }

        # 차원별 상세
        for dim_name, dim in result.dimensions.items():
            briefing["dimensions"][dim_name] = {
                "score": dim.score,
                "weight": f"{dim.weight * 100:.0f}%",
                "confidence": dim.confidence,
                "top_signals": [
                    {
                        "indicator": s["indicator_id"],
                        "signal": s["signal_type"],
                        "strength": s["strength"],
                        "description": s["description"],
                    }
                    for s in sorted(dim.contributing_signals,
                                    key=lambda x: x["strength"], reverse=True)[:3]
                ],
            }

        # 주요 시그널 분류
        all_signals = []
        for dim in result.dimensions.values():
            all_signals.extend(dim.contributing_signals)

        for sig in all_signals:
            if sig["signal_type"] == "bullish" and sig["strength"] >= 0.3:
                briefing["key_signals"]["bullish"].append({
                    "indicator": sig["indicator_id"],
                    "strength": sig["strength"],
                    "description": sig["description"],
                })
            elif sig["signal_type"] == "bearish" and sig["strength"] >= 0.3:
                briefing["key_signals"]["bearish"].append({
                    "indicator": sig["indicator_id"],
                    "strength": sig["strength"],
                    "description": sig["description"],
                })
            else:
                briefing["key_signals"]["neutral_count"] += 1

        # 강도순 정렬
        briefing["key_signals"]["bullish"].sort(key=lambda x: x["strength"], reverse=True)
        briefing["key_signals"]["bearish"].sort(key=lambda x: x["strength"], reverse=True)

        # 시나리오
        for sc in comparison.scenarios:
            briefing["scenarios"].append({
                "name": sc["scenario"]["name"],
                "probability": sc["scenario"]["probability"],
                "delta": sc["delta"],
                "adjusted_score": sc["adjusted_score"],
                "adjusted_regime": sc["adjusted_regime"],
                "regime_changed": sc["regime_changed"],
            })

        # 리스크 워치 (bearish 시그널 + 위험 시나리오)
        for sig in briefing["key_signals"]["bearish"][:3]:
            briefing["risk_watch"].append({
                "type": "signal",
                "source": sig["indicator"],
                "description": sig["description"],
            })
        for sc in briefing["scenarios"]:
            if sc["delta"] < -10 and sc["probability"] >= 0.15:
                briefing["risk_watch"].append({
                    "type": "scenario",
                    "source": sc["name"],
                    "description": f"발생확률 {sc['probability']*100:.0f}% | Score {sc['delta']:+.1f}pt",
                })

        # DB에 저장
        calc.save_to_db(result)

        return briefing

    def to_markdown(self, briefing: dict = None) -> str:
        """마크다운 브리핑 생성"""
        if briefing is None:
            briefing = self.generate_full_briefing()

        s = briefing["summary"]
        lines = []

        lines.append(f"# Semiconductor Cycle Briefing — {briefing['date']}")
        lines.append("")

        # 핵심 요약
        regime_emoji = {
            "expansion": "🟢", "late_cycle": "🟡",
            "contraction": "🔴", "recovery": "🔵"
        }
        emoji = regime_emoji.get(s["regime"], "⚪")

        lines.append(f"## {emoji} Score: {s['total_score']:.1f}/100 | Regime: {s['regime'].upper()}")
        lines.append(f"> {s['regime_description']}")
        lines.append(f"> Confidence: {s['confidence']} | Data coverage: {s['data_coverage']*100:.0f}%")
        lines.append("")

        # 투자 행동
        lines.append("## Investment Action")
        for action in s["investment_action"].split(" | "):
            lines.append(f"- {action}")
        lines.append("")

        # 차원별 스코어
        lines.append("## Dimension Scores")
        lines.append("| Dimension | Score | Weight | Confidence |")
        lines.append("|-----------|-------|--------|------------|")
        for name, dim in briefing["dimensions"].items():
            bar = self._score_bar(dim["score"])
            lines.append(f"| {name} | {dim['score']:.1f} {bar} | {dim['weight']} | {dim['confidence']:.0%} |")
        lines.append("")

        # 핵심 시그널
        lines.append("## Key Signals")
        if briefing["key_signals"]["bullish"]:
            lines.append("### Bullish")
            for sig in briefing["key_signals"]["bullish"]:
                lines.append(f"- **{sig['indicator']}** ({sig['strength']:.2f}): {sig['description']}")

        if briefing["key_signals"]["bearish"]:
            lines.append("### Bearish")
            for sig in briefing["key_signals"]["bearish"]:
                lines.append(f"- **{sig['indicator']}** ({sig['strength']:.2f}): {sig['description']}")

        lines.append(f"\n_Neutral signals: {briefing['key_signals']['neutral_count']}_")
        lines.append("")

        # 시나리오 비교
        lines.append("## Scenario Analysis")
        lines.append(f"| Scenario | Prob | Delta | Adj. Score | Regime |")
        lines.append("|----------|------|-------|------------|--------|")
        for sc in briefing["scenarios"]:
            delta_str = f"{sc['delta']:+.1f}"
            regime_mark = "⚠️" if sc["regime_changed"] else ""
            lines.append(f"| {sc['name']} | {sc['probability']*100:.0f}% | {delta_str} | {sc['adjusted_score']:.1f} | {sc['adjusted_regime']} {regime_mark} |")
        lines.append("")

        # 리스크 워치
        if briefing["risk_watch"]:
            lines.append("## Risk Watch")
            for risk in briefing["risk_watch"]:
                lines.append(f"- [{risk['type'].upper()}] **{risk['source']}**: {risk['description']}")

        lines.append(f"\n---\n_Generated: {briefing['generated_at']}_")
        return "\n".join(lines)

    def to_console(self, briefing: dict = None):
        """콘솔 출력 (Rich 사용 가능 시)"""
        if briefing is None:
            briefing = self.generate_full_briefing()

        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel
            from rich.text import Text
            console = Console()
            self._rich_output(console, briefing)
        except ImportError:
            # Rich 없으면 일반 출력
            print(self.to_markdown(briefing))

    def _rich_output(self, console, briefing):
        """Rich library를 이용한 콘솔 출력"""
        from rich.table import Table
        from rich.panel import Panel

        s = briefing["summary"]

        # 헤더
        color_map = {
            "expansion": "green", "late_cycle": "yellow",
            "contraction": "red", "recovery": "cyan"
        }
        color = color_map.get(s["regime"], "white")

        console.print()
        console.print(Panel(
            f"[bold {color}]Score: {s['total_score']:.1f}/100  |  "
            f"Regime: {s['regime'].upper()}[/]\n"
            f"[dim]{s['regime_description']}[/]\n"
            f"[dim]Confidence: {s['confidence']}  |  "
            f"Data coverage: {s['data_coverage']*100:.0f}%[/]",
            title=f"[bold]Semiconductor Cycle Briefing — {briefing['date']}[/]",
            border_style=color,
        ))

        # 차원별 테이블
        dim_table = Table(title="Dimension Scores", show_header=True)
        dim_table.add_column("Dimension", style="bold")
        dim_table.add_column("Score", justify="right")
        dim_table.add_column("Bar")
        dim_table.add_column("Weight", justify="right")

        for name, dim in briefing["dimensions"].items():
            bar = self._score_bar(dim["score"])
            score_color = "green" if dim["score"] >= 60 else "red" if dim["score"] < 40 else "yellow"
            dim_table.add_row(
                name, f"[{score_color}]{dim['score']:.1f}[/]",
                bar, dim["weight"]
            )
        console.print(dim_table)

        # 주요 시그널
        if briefing["key_signals"]["bullish"]:
            console.print("\n[bold green]▲ Bullish Signals[/]")
            for sig in briefing["key_signals"]["bullish"]:
                console.print(f"  [green]●[/] {sig['indicator']}: {sig['description']}")

        if briefing["key_signals"]["bearish"]:
            console.print("\n[bold red]▼ Bearish Signals[/]")
            for sig in briefing["key_signals"]["bearish"]:
                console.print(f"  [red]●[/] {sig['indicator']}: {sig['description']}")

        # 시나리오
        sc_table = Table(title="\nScenario Comparison", show_header=True)
        sc_table.add_column("Scenario")
        sc_table.add_column("Prob", justify="right")
        sc_table.add_column("Delta", justify="right")
        sc_table.add_column("Score", justify="right")
        sc_table.add_column("Regime")

        for sc in briefing["scenarios"]:
            delta_color = "green" if sc["delta"] > 0 else "red"
            sc_table.add_row(
                sc["name"],
                f"{sc['probability']*100:.0f}%",
                f"[{delta_color}]{sc['delta']:+.1f}[/]",
                f"{sc['adjusted_score']:.1f}",
                sc["adjusted_regime"],
            )
        console.print(sc_table)

        # 투자 행동
        console.print(Panel(
            "\n".join(f"→ {a}" for a in s["investment_action"].split(" | ")),
            title="[bold]Investment Action[/]",
            border_style="blue",
        ))

    def _score_bar(self, score: float, width: int = 10) -> str:
        """스코어를 시각적 바로 표현"""
        filled = int(score / 100 * width)
        return "█" * filled + "░" * (width - filled)

    def save_markdown(self, output_dir: str = "./reports"):
        """마크다운 파일로 저장"""
        briefing = self.generate_full_briefing()
        md = self.to_markdown(briefing)

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        filepath = Path(output_dir) / f"briefing_{date.today()}.md"

        with open(filepath, "w") as f:
            f.write(md)
        logger.info(f"Briefing saved: {filepath}")
        return str(filepath)

    def save_json(self, output_dir: str = "./reports"):
        """JSON 파일로 저장 (대시보드 API용)"""
        briefing = self.generate_full_briefing()

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        filepath = Path(output_dir) / f"briefing_{date.today()}.json"

        with open(filepath, "w") as f:
            json.dump(briefing, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Briefing JSON saved: {filepath}")
        return str(filepath)
