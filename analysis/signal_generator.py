from __future__ import annotations
"""
Signal Generator
=================
각 지표별 raw 데이터 → bullish/bearish/neutral 시그널 변환
책의 해석 로직 + 반도체 섹터 특화 규칙 적용

Signal 구조:
    signal_type: "bullish" | "bearish" | "neutral"
    strength: 0.0 ~ 1.0 (시그널 강도)
    description: 시그널 근거 설명
"""

from dataclasses import dataclass
from datetime import date
from typing import Callable

import numpy as np
import pandas as pd
from loguru import logger

from analysis.transforms import (
    mom_pct, yoy_pct, sma, z_score, percentile_rank,
    threshold_signal, spread_signal, consecutive_direction,
    direction, rate_of_change, to_score_0_100, diff,
)


@dataclass
class Signal:
    indicator_id: str
    date: date
    signal_type: str          # bullish, bearish, neutral
    strength: float           # 0.0 ~ 1.0
    dimension: str            # demand_cycle, supply_cycle, etc.
    sub_signals: dict         # 세부 시그널 분해
    description: str          # 사람이 읽을 수 있는 설명


class SignalGenerator:
    """
    지표별 시그널 생성 엔진

    사용법:
        gen = SignalGenerator(db)
        signal = gen.generate("ISM_MFG")  # 최신 시그널
        signals = gen.generate_all()       # 전체 지표 시그널
    """

    def __init__(self, db):
        self.db = db
        # 지표 ID → 시그널 생성 함수 매핑
        self._generators: dict[str, Callable] = {
            "DGORDER": self._signal_durable_goods,
            "INDPRO": self._signal_industrial_production,
            "ISM_MFG": self._signal_ism_manufacturing,
            "GDP": self._signal_gdp,
            "YIELD_CURVE": self._signal_yield_curve,
            "NFP": self._signal_nfp,
            "CPI": self._signal_cpi,
            "PPI": self._signal_ppi,
            "RETAIL": self._signal_retail,
            "CONSUMER_CONF": self._signal_consumer_confidence,
            "TRADE": self._signal_trade,
            "FOMC": self._signal_fomc,
            "LEI": self._signal_lei,
            "HOUSING": self._signal_housing,
            "CLAIMS": self._signal_claims,
            "PRODUCTIVITY": self._signal_productivity,
            "SOX": self._signal_sox,
            "CHINA_PMI": self._signal_china_pmi,
            "DRAM_PROXY": self._signal_dram_proxy,
            "NAND_PROXY": self._signal_nand_proxy,
            "HBM_PREMIUM": self._signal_hbm_premium,
            "EQUIP_PROXY": self._signal_equip_proxy,
            "WSTS": self._signal_wsts,
            "HYPERSCALER_CAPEX": self._signal_hyperscaler_capex,
            # v4.0 신규
            "HY_SPREAD": self._signal_hy_spread,
            "SAHM_RULE": self._signal_sahm_rule,
        }

    def _load_series(self, series_code: str, months: int = 60) -> pd.Series | None:
        """DB에서 시리즈 로드 → pandas Series (date index)"""
        from datetime import timedelta
        cutoff = date.today() - timedelta(days=months * 30)
        data = self.db.get_series_data(series_code, start_date=cutoff)
        if not data:
            return None
        s = pd.Series(
            [d["value"] for d in data],
            index=pd.DatetimeIndex([d["date"] for d in data]),
            name=series_code,
        )
        return s.sort_index().dropna()

    def _make_signal(self, indicator_id: str, dimension: str,
                     score: float, sub_signals: dict,
                     description: str,
                     use_sigmoid: bool = False) -> Signal:
        """
        표준 시그널 객체 생성

        Args:
            use_sigmoid: True = 선행지표용 Sigmoid 변환 적용.
                         중앙값(0.5) 근처에서 불감대를 만들고 극단값에서 신호를 강화.
                         k=6: 변곡점이 0.35/0.65에 위치 → 임계값 근처 신호 날카롭게 포착.
        """
        if use_sigmoid:
            # Sigmoid: score = 1 / (1 + exp(-k*(x-0.5)))
            # k=6 → 0.35 이하 bearish, 0.65 이상 bullish 로 수렴
            import math
            score = 1.0 / (1.0 + math.exp(-6 * (score - 0.5)))

        if score >= 0.6:
            sig_type = "bullish"
        elif score <= 0.4:
            sig_type = "bearish"
        else:
            sig_type = "neutral"

        strength = abs(score - 0.5) * 2  # 0~1 범위

        return Signal(
            indicator_id=indicator_id,
            date=date.today(),
            signal_type=sig_type,
            strength=min(strength, 1.0),
            dimension=dimension,
            sub_signals=sub_signals,
            description=description,
        )

    # ============================================================
    # TIER 1 시그널 생성 로직
    # ============================================================

    def _signal_durable_goods(self) -> Signal | None:
        """
        내구재 주문 → 반도체 수요 시그널
        핵심: 비국방 자본재(항공기 제외) = NEWORDER
        규칙:
          - 3개월 연속 증가 → strong bullish
          - MoM% 양수 + YoY% 양수 → bullish
          - 3개월 연속 감소 → bearish
        """
        core = self._load_series("NEWORDER")       # 비국방 자본재 ex 항공기
        total = self._load_series("DGORDER")       # 전체 내구재
        if core is None:
            return None

        sub = {}

        # 1) MoM 변화율
        core_mom = mom_pct(core)
        sub["core_mom_pct"] = round(float(core_mom.iloc[-1]), 2) if len(core_mom) > 0 else 0

        # 2) 연속 방향
        consec = consecutive_direction(core)
        sub["consecutive_months"] = int(consec.iloc[-1]) if len(consec) > 0 else 0

        # 3) YoY
        core_yoy = yoy_pct(core)
        sub["core_yoy_pct"] = round(float(core_yoy.iloc[-1]), 2) if len(core_yoy) > 0 else 0

        # 4) 3개월 이동평균 추세
        ma3 = sma(core, 3)
        ma6 = sma(core, 6)
        sub["ma3_above_ma6"] = bool(ma3.iloc[-1] > ma6.iloc[-1]) if len(ma3) > 0 and len(ma6) > 0 else False

        # 스코어 산출 (0~1)
        score = 0.5
        if sub["consecutive_months"] >= 3:
            score += 0.25
        elif sub["consecutive_months"] <= -3:
            score -= 0.25
        if sub["core_mom_pct"] > 0:
            score += 0.1
        elif sub["core_mom_pct"] < -2:
            score -= 0.15
        if sub["core_yoy_pct"] > 5:
            score += 0.1
        elif sub["core_yoy_pct"] < -5:
            score -= 0.15
        if sub["ma3_above_ma6"]:
            score += 0.05

        score = max(0, min(1, score))

        desc_parts = []
        if sub["consecutive_months"] > 0:
            desc_parts.append(f"비국방자본재 {sub['consecutive_months']}개월 연속 증가")
        elif sub["consecutive_months"] < 0:
            desc_parts.append(f"비국방자본재 {abs(sub['consecutive_months'])}개월 연속 감소")
        desc_parts.append(f"MoM {sub['core_mom_pct']:+.1f}%, YoY {sub['core_yoy_pct']:+.1f}%")

        return self._make_signal("DGORDER", "demand_cycle", score, sub,
                                 " | ".join(desc_parts))

    def _signal_industrial_production(self) -> Signal | None:
        """
        산업생산 + 가동률 → 반도체 공급 사이클 시그널
        핵심: TCU(가동률) 80% 이상 → 증설 투자 트리거
        """
        indpro = self._load_series("INDPRO")
        tcu = self._load_series("TCU")
        mfg_cu = self._load_series("CUMFNS")
        if indpro is None:
            return None

        sub = {}

        # 산업생산 MoM
        ip_mom = mom_pct(indpro)
        sub["ip_mom_pct"] = round(float(ip_mom.iloc[-1]), 2) if len(ip_mom) > 0 else 0

        # 가동률 레벨
        if tcu is not None and len(tcu) > 0:
            sub["capacity_util"] = round(float(tcu.iloc[-1]), 1)
            sub["cu_above_80"] = sub["capacity_util"] >= 80.0
        else:
            sub["capacity_util"] = None
            sub["cu_above_80"] = False

        # 제조업 가동률
        if mfg_cu is not None and len(mfg_cu) > 0:
            sub["mfg_capacity_util"] = round(float(mfg_cu.iloc[-1]), 1)
        else:
            sub["mfg_capacity_util"] = None

        # 산업생산 추세 (3개월)
        ip_dir = direction(indpro, periods=3)
        sub["ip_3m_direction"] = int(ip_dir.iloc[-1]) if len(ip_dir) > 0 else 0

        score = 0.5
        if sub["cu_above_80"]:
            score += 0.2
        elif sub.get("capacity_util") and sub["capacity_util"] < 75:
            score -= 0.2
        if sub["ip_mom_pct"] > 0.3:
            score += 0.1
        elif sub["ip_mom_pct"] < -0.3:
            score -= 0.15
        if sub["ip_3m_direction"] > 0:
            score += 0.1
        elif sub["ip_3m_direction"] < 0:
            score -= 0.1

        score = max(0, min(1, score))

        desc = f"가동률 {sub.get('capacity_util', 'N/A')}% | 산업생산 MoM {sub['ip_mom_pct']:+.1f}%"
        return self._make_signal("INDPRO", "supply_cycle", score, sub, desc)

    def _signal_ism_manufacturing(self) -> Signal | None:
        """
        ISM 제조업 PMI → 반도체 수요 시그널
        핵심: PMI > 50 확장, New Orders > Inventories → 강한 수요
        Supplier Deliveries 상승 → 공급 병목 (반도체에 유리할 수 있음)
        """
        pmi = self._load_series("NAPM")
        new_orders = self._load_series("NAPMNOI")
        inventories = self._load_series("NAPMII")
        supplier_del = self._load_series("NAPMSDI")
        if pmi is None:
            return None

        sub = {}
        sub["pmi_level"] = round(float(pmi.iloc[-1]), 1)
        sub["pmi_above_50"] = sub["pmi_level"] > 50

        if new_orders is not None and len(new_orders) > 0:
            sub["new_orders"] = round(float(new_orders.iloc[-1]), 1)
        if inventories is not None and len(inventories) > 0:
            sub["inventories"] = round(float(inventories.iloc[-1]), 1)

        if "new_orders" in sub and "inventories" in sub:
            sub["orders_inv_spread"] = round(sub["new_orders"] - sub["inventories"], 1)
        else:
            sub["orders_inv_spread"] = 0

        if supplier_del is not None and len(supplier_del) > 0:
            sub["supplier_deliveries"] = round(float(supplier_del.iloc[-1]), 1)

        # PMI 방향
        pmi_dir = direction(pmi, periods=3)
        sub["pmi_3m_trend"] = int(pmi_dir.iloc[-1]) if len(pmi_dir) > 0 else 0

        score = 0.5
        if sub["pmi_above_50"]:
            score += 0.15
            if sub["pmi_level"] > 55:
                score += 0.1
        else:
            score -= 0.15
            if sub["pmi_level"] < 45:
                score -= 0.1

        if sub["orders_inv_spread"] > 5:
            score += 0.15
        elif sub["orders_inv_spread"] < -5:
            score -= 0.15

        if sub["pmi_3m_trend"] > 0:
            score += 0.05
        elif sub["pmi_3m_trend"] < 0:
            score -= 0.05

        score = max(0, min(1, score))

        desc = f"PMI {sub['pmi_level']} | New Orders-Inventories spread {sub['orders_inv_spread']:+.1f}"
        return self._make_signal("ISM_MFG", "demand_cycle", score, sub, desc)

    def _signal_gdp(self) -> Signal | None:
        """
        GDP → 매크로 환경 시그널
        핵심: Real GDP 성장률 + IT 투자 성장률 비교
        """
        real_gdp = self._load_series("GDPC1")
        it_invest = self._load_series("Y006RC1Q027SBEA")
        if real_gdp is None:
            return None

        sub = {}
        gdp_qoq = mom_pct(real_gdp)  # quarterly이므로 QoQ
        sub["gdp_qoq_pct"] = round(float(gdp_qoq.iloc[-1]), 2) if len(gdp_qoq) > 0 else 0

        gdp_yoy = yoy_pct(real_gdp, "quarterly")
        sub["gdp_yoy_pct"] = round(float(gdp_yoy.iloc[-1]), 2) if len(gdp_yoy) > 0 else 0

        if it_invest is not None and len(it_invest) > 1:
            it_yoy = yoy_pct(it_invest, "quarterly")
            sub["it_invest_yoy_pct"] = round(float(it_yoy.iloc[-1]), 2) if len(it_yoy) > 0 else 0
            sub["it_outpacing_gdp"] = sub["it_invest_yoy_pct"] > sub["gdp_yoy_pct"]
        else:
            sub["it_invest_yoy_pct"] = None
            sub["it_outpacing_gdp"] = False

        score = 0.5
        if sub["gdp_qoq_pct"] > 0.5:
            score += 0.15
        elif sub["gdp_qoq_pct"] < 0:
            score -= 0.2

        if sub["it_outpacing_gdp"]:
            score += 0.15
        if sub.get("it_invest_yoy_pct") and sub["it_invest_yoy_pct"] > 10:
            score += 0.1

        score = max(0, min(1, score))

        desc = f"GDP QoQ {sub['gdp_qoq_pct']:+.1f}% | IT투자 YoY {sub.get('it_invest_yoy_pct', 'N/A')}%"
        return self._make_signal("GDP", "macro_regime", score, sub, desc)

    def _signal_yield_curve(self) -> Signal | None:
        """
        수익률 곡선 → 경기 선행/반도체 사이클 시그널
        역전(음수) → 12-18개월 후 침체 → bearish
        정상화 초기(음→양 전환) → 바닥 근접 → bullish
        """
        spread_10y2y = self._load_series("T10Y2Y")
        spread_10y3m = self._load_series("T10Y3M")
        if spread_10y2y is None:
            return None

        sub = {}
        current = float(spread_10y2y.iloc[-1])
        sub["spread_10y2y"] = round(current, 2)
        sub["inverted"] = current < 0

        # 1개월 전 대비 변화
        if len(spread_10y2y) > 20:
            prev = float(spread_10y2y.iloc[-20])
            sub["spread_change_1m"] = round(current - prev, 2)
            sub["normalizing"] = prev < 0 and current > prev  # 역전에서 정상화 방향
        else:
            sub["spread_change_1m"] = 0
            sub["normalizing"] = False

        # 10Y3M도 확인
        if spread_10y3m is not None and len(spread_10y3m) > 0:
            sub["spread_10y3m"] = round(float(spread_10y3m.iloc[-1]), 2)

        score = 0.5
        if sub["inverted"]:
            score -= 0.25
            if current < -0.5:
                score -= 0.1
        else:
            score += 0.1
            if current > 1.0:
                score += 0.1

        if sub["normalizing"]:
            score += 0.15  # 역전에서 정상화 → 바닥 접근 신호

        score = max(0, min(1, score))

        status = "역전" if sub["inverted"] else "정상"
        desc = f"10Y-2Y spread {sub['spread_10y2y']:+.2f}% ({status})"
        if sub["normalizing"]:
            desc += " | 정상화 진행 중"

        return self._make_signal("YIELD_CURVE", "macro_regime", score, sub, desc)

    # ============================================================
    # TIER 2 시그널 생성 로직
    # ============================================================

    def _signal_nfp(self) -> Signal | None:
        """고용 → 수요 환경"""
        payems = self._load_series("PAYEMS")
        unrate = self._load_series("UNRATE")
        info_emp = self._load_series("USINFO")
        if payems is None:
            return None

        sub = {}
        nfp_change = diff(payems)
        sub["nfp_change_k"] = round(float(nfp_change.iloc[-1]), 0) if len(nfp_change) > 0 else 0
        sub["nfp_3m_avg_k"] = round(float(sma(nfp_change, 3).iloc[-1]), 0) if len(nfp_change) > 2 else 0

        if unrate is not None and len(unrate) > 0:
            sub["unemployment_rate"] = round(float(unrate.iloc[-1]), 1)
        if info_emp is not None and len(info_emp) > 1:
            info_chg = mom_pct(info_emp)
            sub["info_sector_mom"] = round(float(info_chg.iloc[-1]), 2) if len(info_chg) > 0 else 0

        score = 0.5
        if sub["nfp_3m_avg_k"] > 200:
            score += 0.15
        elif sub["nfp_3m_avg_k"] < 50:
            score -= 0.2
        if sub.get("info_sector_mom", 0) > 0:
            score += 0.1

        score = max(0, min(1, score))
        desc = f"NFP 변화 {sub['nfp_change_k']:+.0f}K | 3개월평균 {sub['nfp_3m_avg_k']:+.0f}K"
        return self._make_signal("NFP", "demand_cycle", score, sub, desc)

    def _signal_cpi(self) -> Signal | None:
        """CPI → 금리/밸류에이션 환경 (인플레 높으면 bearish)"""
        core_cpi = self._load_series("CPILFESL")
        core_pce = self._load_series("PCEPILFE")
        if core_cpi is None:
            return None

        sub = {}
        core_yoy = yoy_pct(core_cpi)
        sub["core_cpi_yoy"] = round(float(core_yoy.iloc[-1]), 2) if len(core_yoy) > 0 else 0

        core_mom = mom_pct(core_cpi)
        sub["core_cpi_mom"] = round(float(core_mom.iloc[-1]), 2) if len(core_mom) > 0 else 0

        # 추세 방향 (3개월)
        if len(core_yoy) > 3:
            sub["cpi_trend_down"] = bool(core_yoy.iloc[-1] < core_yoy.iloc[-3])
        else:
            sub["cpi_trend_down"] = False

        # CPI 높으면 bearish (invert)
        score = 0.5
        if sub["core_cpi_yoy"] < 2.5:
            score += 0.2  # Fed target 근접 → dovish 가능
        elif sub["core_cpi_yoy"] > 4.0:
            score -= 0.25
        elif sub["core_cpi_yoy"] > 3.0:
            score -= 0.1

        if sub["cpi_trend_down"]:
            score += 0.1

        score = max(0, min(1, score))
        desc = f"Core CPI YoY {sub['core_cpi_yoy']:.1f}% | {'하락 추세' if sub['cpi_trend_down'] else '상승/횡보'}"
        return self._make_signal("CPI", "price_cycle", score, sub, desc)

    def _signal_ppi(self) -> Signal | None:
        """PPI → 반도체 비용/마진 환경"""
        ppi_semi = self._load_series("PCU33443344")
        ppi_final = self._load_series("WPSFD4")
        if ppi_final is None:
            return None

        sub = {}
        final_yoy = yoy_pct(ppi_final)
        sub["ppi_final_yoy"] = round(float(final_yoy.iloc[-1]), 2) if len(final_yoy) > 0 else 0

        if ppi_semi is not None and len(ppi_semi) > 12:
            semi_yoy = yoy_pct(ppi_semi)
            sub["ppi_semi_yoy"] = round(float(semi_yoy.iloc[-1]), 2) if len(semi_yoy) > 0 else 0

        score = 0.5
        if sub["ppi_final_yoy"] < 2:
            score += 0.1
        elif sub["ppi_final_yoy"] > 5:
            score -= 0.15
        if sub.get("ppi_semi_yoy", 0) > 0:
            score += 0.1  # 반도체 가격 상승 → 마진 개선

        score = max(0, min(1, score))
        desc = f"PPI Final Demand YoY {sub['ppi_final_yoy']:.1f}%"
        return self._make_signal("PPI", "price_cycle", score, sub, desc)

    def _signal_retail(self) -> Signal | None:
        """소매판매 → 소비자 전자기기 수요"""
        electronics = self._load_series("RSEAS")
        total = self._load_series("RSAFS")
        if total is None:
            return None

        sub = {}
        total_mom = mom_pct(total)
        sub["retail_mom_pct"] = round(float(total_mom.iloc[-1]), 2) if len(total_mom) > 0 else 0

        if electronics is not None and len(electronics) > 1:
            elec_mom = mom_pct(electronics)
            sub["electronics_mom_pct"] = round(float(elec_mom.iloc[-1]), 2) if len(elec_mom) > 0 else 0
            elec_yoy = yoy_pct(electronics)
            sub["electronics_yoy_pct"] = round(float(elec_yoy.iloc[-1]), 2) if len(elec_yoy) > 0 else 0

        score = 0.5
        if sub.get("electronics_yoy_pct", 0) > 3:
            score += 0.15
        elif sub.get("electronics_yoy_pct", 0) < -3:
            score -= 0.15
        if sub["retail_mom_pct"] > 0.5:
            score += 0.05

        score = max(0, min(1, score))
        desc = f"전자/가전 소매 YoY {sub.get('electronics_yoy_pct', 'N/A')}%"
        return self._make_signal("RETAIL", "demand_cycle", score, sub, desc)

    def _signal_consumer_confidence(self) -> Signal | None:
        """소비 심리 → 내구재 수요 전망"""
        sentiment = self._load_series("UMCSENT")
        if sentiment is None:
            return None

        sub = {}
        sub["sentiment_level"] = round(float(sentiment.iloc[-1]), 1)
        sent_pctile = percentile_rank(sentiment, window=120)
        sub["percentile_5yr"] = round(float(sent_pctile.iloc[-1]), 1) if len(sent_pctile) > 0 else 50

        score = sub["percentile_5yr"] / 100
        score = max(0, min(1, score))

        desc = f"소비심리 {sub['sentiment_level']} (5년 백분위 {sub['percentile_5yr']:.0f}%)"
        return self._make_signal("CONSUMER_CONF", "demand_cycle", score, sub, desc)

    def _signal_trade(self) -> Signal | None:
        """무역수지 → 글로벌 수요"""
        exports = self._load_series("EXPGS")
        tech_exports = self._load_series("IEABC")
        if exports is None:
            return None

        sub = {}
        exp_yoy = yoy_pct(exports)
        sub["exports_yoy_pct"] = round(float(exp_yoy.iloc[-1]), 2) if len(exp_yoy) > 0 else 0

        if tech_exports is not None and len(tech_exports) > 12:
            tech_yoy = yoy_pct(tech_exports)
            sub["tech_exports_yoy"] = round(float(tech_yoy.iloc[-1]), 2) if len(tech_yoy) > 0 else 0

        score = 0.5
        if sub["exports_yoy_pct"] > 5:
            score += 0.15
        elif sub["exports_yoy_pct"] < -5:
            score -= 0.15

        score = max(0, min(1, score))
        desc = f"수출 YoY {sub['exports_yoy_pct']:+.1f}%"
        return self._make_signal("TRADE", "global_demand", score, sub, desc)

    def _signal_fomc(self) -> Signal | None:
        """Fed 금리 → 밸류에이션 환경"""
        fed_rate = self._load_series("FEDFUNDS")
        balance_sheet = self._load_series("WALCL")
        if fed_rate is None:
            return None

        sub = {}
        sub["fed_rate"] = round(float(fed_rate.iloc[-1]), 2)

        # 금리 방향 (3개월)
        rate_dir = direction(fed_rate, periods=3)
        sub["rate_direction"] = int(rate_dir.iloc[-1]) if len(rate_dir) > 0 else 0
        sub["rate_falling"] = sub["rate_direction"] < 0

        if balance_sheet is not None and len(balance_sheet) > 4:
            bs_mom = mom_pct(balance_sheet)
            sub["bs_expanding"] = bool(bs_mom.iloc[-1] > 0) if len(bs_mom) > 0 else False

        # 금리 인하 → bullish, 인상 → bearish
        score = 0.5
        if sub["rate_falling"]:
            score += 0.2
        elif sub["rate_direction"] > 0:
            score -= 0.2

        if sub["fed_rate"] < 3.0:
            score += 0.1
        elif sub["fed_rate"] > 5.0:
            score -= 0.1

        score = max(0, min(1, score))
        trend = "인하" if sub["rate_falling"] else "인상" if sub["rate_direction"] > 0 else "동결"
        desc = f"Fed Funds Rate {sub['fed_rate']:.2f}% | {trend} 기조"
        return self._make_signal("FOMC", "macro_regime", score, sub, desc)

    # ============================================================
    # TIER 3 시그널
    # ============================================================

    def _signal_lei(self) -> Signal | None:
        """선행지수 → 경기 방향"""
        lei = self._load_series("USSLIND")
        if lei is None:
            return None

        sub = {}
        consec = consecutive_direction(lei)
        sub["consecutive_months"] = int(consec.iloc[-1]) if len(consec) > 0 else 0
        lei_mom = mom_pct(lei)
        sub["lei_mom_pct"] = round(float(lei_mom.iloc[-1]), 2) if len(lei_mom) > 0 else 0

        score = 0.5
        if sub["consecutive_months"] >= 6:
            score += 0.2
        elif sub["consecutive_months"] <= -6:
            score -= 0.3  # 6개월 연속 하락 → 강한 경고
        elif sub["consecutive_months"] <= -3:
            score -= 0.15

        score = max(0, min(1, score))
        desc = f"LEI {sub['consecutive_months']:+d}개월 연속 | MoM {sub['lei_mom_pct']:+.1f}%"
        return self._make_signal("LEI", "macro_regime", score, sub, desc)

    def _signal_housing(self) -> Signal | None:
        """주택 착공 → 간접 수요"""
        starts = self._load_series("HOUST")
        if starts is None:
            return None

        sub = {}
        starts_yoy = yoy_pct(starts)
        sub["starts_yoy_pct"] = round(float(starts_yoy.iloc[-1]), 2) if len(starts_yoy) > 0 else 0

        score = 0.5
        if sub["starts_yoy_pct"] > 10:
            score += 0.1
        elif sub["starts_yoy_pct"] < -10:
            score -= 0.1

        score = max(0, min(1, score))
        desc = f"주택착공 YoY {sub['starts_yoy_pct']:+.1f}%"
        return self._make_signal("HOUSING", "demand_cycle", score, sub, desc)

    def _signal_claims(self) -> Signal | None:
        """주간 실업수당 → 실시간 경기"""
        initial = self._load_series("ICSA")
        if initial is None:
            return None

        sub = {}
        ma4 = sma(initial, 4)
        sub["claims_4wk_avg"] = round(float(ma4.iloc[-1]), 0) if len(ma4) > 0 else 0
        sub["claims_latest"] = round(float(initial.iloc[-1]), 0)

        claims_dir = direction(ma4, periods=4)
        sub["trend_rising"] = bool(claims_dir.iloc[-1] > 0) if len(claims_dir) > 0 else False

        # claims가 높으면 bearish (invert)
        score = 0.5
        if sub["claims_4wk_avg"] < 220000:
            score += 0.15
        elif sub["claims_4wk_avg"] > 300000:
            score -= 0.2
        if sub["trend_rising"]:
            score -= 0.1

        score = max(0, min(1, score))
        desc = f"실업수당 4주평균 {sub['claims_4wk_avg']/1000:.0f}K"
        return self._make_signal("CLAIMS", "macro_regime", score, sub, desc)

    def _signal_productivity(self) -> Signal | None:
        """생산성 → AI 투자 정당화"""
        prod = self._load_series("OPHNFB")
        if prod is None:
            return None

        sub = {}
        prod_yoy = yoy_pct(prod, "quarterly")
        sub["productivity_yoy"] = round(float(prod_yoy.iloc[-1]), 2) if len(prod_yoy) > 0 else 0

        score = 0.5
        if sub["productivity_yoy"] > 3:
            score += 0.15
        elif sub["productivity_yoy"] < 0:
            score -= 0.1

        score = max(0, min(1, score))
        desc = f"생산성 YoY {sub['productivity_yoy']:+.1f}%"
        return self._make_signal("PRODUCTIVITY", "supply_cycle", score, sub, desc)

    # ============================================================
    # TIER S 시그널 (반도체 특화)
    # ============================================================

    def _signal_sox(self) -> Signal | None:
        """SOX 지수 → 섹터 심리"""
        sox = self._load_series("^SOX")
        if sox is None:
            sox = self._load_series("SOXX")
        if sox is None:
            return None

        sub = {}
        sub["sox_current"] = round(float(sox.iloc[-1]), 1)

        # 200일 이동평균
        ma200 = sma(sox, 200)
        if len(ma200) > 0:
            sub["above_200dma"] = bool(sox.iloc[-1] > ma200.iloc[-1])
            sub["pct_from_200dma"] = round((sox.iloc[-1] / ma200.iloc[-1] - 1) * 100, 1)
        else:
            sub["above_200dma"] = True
            sub["pct_from_200dma"] = 0

        # 52주 고점 대비
        if len(sox) >= 252:
            high_52w = sox.iloc[-252:].max()
            sub["pct_from_52w_high"] = round((sox.iloc[-1] / high_52w - 1) * 100, 1)
        else:
            sub["pct_from_52w_high"] = 0

        score = 0.5
        if sub["above_200dma"]:
            score += 0.15
        else:
            score -= 0.15
        if sub["pct_from_200dma"] > 10:
            score += 0.1
        elif sub["pct_from_200dma"] < -10:
            score -= 0.1

        score = max(0, min(1, score))
        above_below = "위" if sub["above_200dma"] else "아래"
        desc = f"SOX {sub['sox_current']:.0f} | 200일선 {above_below} ({sub['pct_from_200dma']:+.1f}%)"
        return self._make_signal("SOX", "demand_cycle", score, sub, desc)

    def _signal_china_pmi(self) -> Signal | None:
        """중국 PMI → 글로벌 반도체 수요"""
        pmi = self._load_series("CHNMPMINDMEI")
        if pmi is None:
            return None

        sub = {}
        sub["china_pmi"] = round(float(pmi.iloc[-1]), 1)
        sub["above_50"] = sub["china_pmi"] > 50

        pmi_dir = direction(pmi, periods=3)
        sub["improving"] = bool(pmi_dir.iloc[-1] > 0) if len(pmi_dir) > 0 else False

        score = 0.5
        if sub["above_50"]:
            score += 0.15
        else:
            score -= 0.15
        if sub["improving"]:
            score += 0.1

        score = max(0, min(1, score))
        desc = f"중국 제조업 PMI {sub['china_pmi']:.1f} | {'확장' if sub['above_50'] else '수축'}"
        return self._make_signal("CHINA_PMI", "global_demand", score, sub, desc)

    def _load_basket_mom(self, symbols: list[str], months: int = 12) -> tuple[float | None, dict]:
        """여러 심볼의 평균 MoM% 계산 (basket proxy용)"""
        moms = {}
        valid = []
        for sym in symbols:
            s = self._load_series(sym, months)
            if s is not None and len(s) > 1:
                m = mom_pct(s)
                if len(m) > 0 and not np.isnan(m.iloc[-1]):
                    val = round(float(m.iloc[-1]), 2)
                    moms[sym] = val
                    valid.append(val)
        avg = round(np.mean(valid), 2) if valid else None
        return avg, moms

    def _signal_dram_proxy(self) -> Signal | None:
        """DRAM 가격 Proxy: Micron(MU) + Nanya(2408.TW) basket MoM%"""
        avg_mom, moms = self._load_basket_mom(["MU", "2408.TW"])
        if avg_mom is None:
            return None

        sub = {"basket_mom_pct": avg_mom, "components": moms}

        # 3개월 추세 (MU 기준, 더 안정적)
        mu = self._load_series("MU")
        if mu is not None and len(mu) > 60:
            dir3 = direction(mu, periods=60)  # ~3개월 (trading days)
            sub["3m_trend"] = int(dir3.iloc[-1]) if len(dir3) > 0 else 0
        else:
            sub["3m_trend"] = 0

        score = 0.5
        if avg_mom > 10:
            score += 0.3
        elif avg_mom > 3:
            score += 0.15
        elif avg_mom > 0:
            score += 0.05
        elif avg_mom < -10:
            score -= 0.3
        elif avg_mom < -3:
            score -= 0.15
        elif avg_mom < 0:
            score -= 0.05

        if sub["3m_trend"] > 0:
            score += 0.1
        elif sub["3m_trend"] < 0:
            score -= 0.1

        score = max(0, min(1, score))
        components = ", ".join(f"{k}: {v:+.1f}%" for k, v in moms.items())
        desc = f"DRAM basket MoM {avg_mom:+.1f}% ({components})"
        return self._make_signal("DRAM_PROXY", "price_cycle", score, sub, desc)

    def _signal_nand_proxy(self) -> Signal | None:
        """NAND 가격 Proxy: SanDisk(SNDK) + Kioxia(285A.T) basket MoM%"""
        avg_mom, moms = self._load_basket_mom(["SNDK", "285A.T"])

        # Kioxia 데이터 없으면 SanDisk 단독 fallback
        if avg_mom is None:
            avg_mom, moms = self._load_basket_mom(["SNDK"])
        if avg_mom is None:
            return None

        sub = {"basket_mom_pct": avg_mom, "components": moms, "fallback": "285A.T" not in moms}

        score = 0.5
        if avg_mom > 10:
            score += 0.3
        elif avg_mom > 3:
            score += 0.15
        elif avg_mom > 0:
            score += 0.05
        elif avg_mom < -10:
            score -= 0.3
        elif avg_mom < -3:
            score -= 0.15
        elif avg_mom < 0:
            score -= 0.05

        score = max(0, min(1, score))
        components = ", ".join(f"{k}: {v:+.1f}%" for k, v in moms.items())
        fallback_note = " [SNDK only]" if sub["fallback"] else ""
        desc = f"NAND basket MoM {avg_mom:+.1f}% ({components}){fallback_note}"
        return self._make_signal("NAND_PROXY", "price_cycle", score, sub, desc)

    def _signal_hbm_premium(self) -> Signal | None:
        """HBM Premium: SK하이닉스 초과수익률 = SK MoM% - DRAM basket MoM%"""
        sk = self._load_series("000660.KS")
        if sk is None or len(sk) < 2:
            return None

        sk_mom_val = mom_pct(sk)
        if len(sk_mom_val) < 1 or np.isnan(sk_mom_val.iloc[-1]):
            return None
        sk_mom = round(float(sk_mom_val.iloc[-1]), 2)

        # DRAM basket MoM
        dram_avg, dram_moms = self._load_basket_mom(["MU", "2408.TW"])
        if dram_avg is None:
            dram_avg = 0.0

        premium = round(sk_mom - dram_avg, 2)

        sub = {
            "sk_hynix_mom": sk_mom,
            "dram_basket_mom": dram_avg,
            "hbm_premium": premium,
        }

        # premium > 0: HBM 프리미엄 인정, < 0: 프리미엄 소멸
        score = 0.5
        if premium > 10:
            score += 0.3
        elif premium > 3:
            score += 0.15
        elif premium > 0:
            score += 0.05
        elif premium < -10:
            score -= 0.2
        elif premium < -3:
            score -= 0.1

        score = max(0, min(1, score))
        status = "HBM 프리미엄 확대" if premium > 3 else "HBM 프리미엄 유지" if premium > 0 else "HBM 프리미엄 축소"
        desc = f"SK하이닉스 MoM {sk_mom:+.1f}% vs DRAM basket {dram_avg:+.1f}% → 초과수익률 {premium:+.1f}% ({status})"
        return self._make_signal("HBM_PREMIUM", "demand_cycle", score, sub, desc)

    def _signal_equip_proxy(self) -> Signal | None:
        """장비 투자 Proxy: AMAT + LRCX + ASML basket MoM% (SEMI B/B 대체)"""
        avg_mom, moms = self._load_basket_mom(["AMAT", "LRCX", "ASML"])
        if avg_mom is None:
            return None

        sub = {"basket_mom_pct": avg_mom, "components": moms}

        # 200일선 대비 (AMAT 기준)
        amat = self._load_series("AMAT", months=18)
        if amat is not None and len(amat) > 200:
            ma200 = sma(amat, 200)
            sub["amat_above_200dma"] = bool(amat.iloc[-1] > ma200.iloc[-1])
        else:
            sub["amat_above_200dma"] = True  # 데이터 부족 시 중립

        score = 0.5
        if avg_mom > 8:
            score += 0.25
        elif avg_mom > 2:
            score += 0.1
        elif avg_mom < -8:
            score -= 0.25
        elif avg_mom < -2:
            score -= 0.1

        if sub["amat_above_200dma"]:
            score += 0.1
        else:
            score -= 0.1

        score = max(0, min(1, score))
        components = ", ".join(f"{k}: {v:+.1f}%" for k, v in moms.items())
        desc = f"장비 basket MoM {avg_mom:+.1f}% ({components}) | 200일선 {'위' if sub['amat_above_200dma'] else '아래'}"
        return self._make_signal("EQUIP_PROXY", "supply_cycle", score, sub, desc)

    def _signal_wsts(self) -> Signal | None:
        """WSTS 글로벌 반도체 매출 (SIA 경유, 2개월 후행 확인 지표)"""
        total = self._load_series("WSTS_GLOBAL_TOTAL")
        memory = self._load_series("WSTS_MEMORY")
        if total is None and memory is None:
            return None

        target = memory if memory is not None else total
        sub = {}

        target_yoy = yoy_pct(target)
        sub["yoy_pct"] = round(float(target_yoy.iloc[-1]), 2) if len(target_yoy) > 0 else 0
        sub["data_type"] = "memory" if memory is not None else "total"
        sub["lagging_months"] = 2

        consec = consecutive_direction(target)
        sub["consecutive_months"] = int(consec.iloc[-1]) if len(consec) > 0 else 0

        score = 0.5
        if sub["yoy_pct"] > 10:
            score += 0.2
        elif sub["yoy_pct"] > 0:
            score += 0.1
        elif sub["yoy_pct"] < -10:
            score -= 0.2
        elif sub["yoy_pct"] < 0:
            score -= 0.1

        score = max(0, min(1, score))
        desc = f"WSTS {sub['data_type']} YoY {sub['yoy_pct']:+.1f}% (2개월 후행, 확인용)"
        return self._make_signal("WSTS", "demand_cycle", score, sub, desc)

    def _signal_hyperscaler_capex(self) -> Signal | None:
        """빅테크 CapEx → AI 반도체 수요"""
        msft = self._load_series("MSFT_CAPEX")
        googl = self._load_series("GOOGL_CAPEX")
        amzn = self._load_series("AMZN_CAPEX")
        meta = self._load_series("META_CAPEX")

        available = [(s, n) for s, n in [(msft, "MSFT"), (googl, "GOOGL"),
                      (amzn, "AMZN"), (meta, "META")] if s is not None]
        if not available:
            return None

        sub = {}
        yoy_changes = []

        for series, name in available:
            if len(series) >= 5:
                capex_yoy = yoy_pct(series, "quarterly")
                if len(capex_yoy) > 0 and not np.isnan(capex_yoy.iloc[-1]):
                    val = round(float(capex_yoy.iloc[-1]), 1)
                    sub[f"{name}_capex_yoy"] = val
                    yoy_changes.append(val)

        if yoy_changes:
            sub["avg_capex_yoy"] = round(np.mean(yoy_changes), 1)
        else:
            sub["avg_capex_yoy"] = 0

        score = 0.5
        avg = sub["avg_capex_yoy"]
        if avg > 30:
            score += 0.3
        elif avg > 15:
            score += 0.2
        elif avg > 0:
            score += 0.1
        elif avg < -10:
            score -= 0.2

        score = max(0, min(1, score))
        desc = f"Hyperscaler CapEx 평균 YoY {sub['avg_capex_yoy']:+.1f}%"
        return self._make_signal("HYPERSCALER_CAPEX", "demand_cycle", score, sub, desc)

    # ============================================================
    # 통합 인터페이스
    # ============================================================

    def generate(self, indicator_id: str) -> Signal | None:
        """단일 지표 시그널 생성"""
        gen_func = self._generators.get(indicator_id)
        if not gen_func:
            logger.warning(f"No signal generator for: {indicator_id}")
            return None
        try:
            return gen_func()
        except Exception as e:
            logger.error(f"Signal generation failed for {indicator_id}: {e}")
            return None

    def generate_all(self) -> dict[str, Signal]:
        """전체 지표 시그널 생성"""
        signals = {}
        for ind_id in self._generators:
            sig = self.generate(ind_id)
            if sig:
                signals[ind_id] = sig
                logger.info(f"  {ind_id}: {sig.signal_type} ({sig.strength:.2f}) — {sig.description}")
            else:
                logger.debug(f"  {ind_id}: no data or skipped")
        return signals

    # ============================================================
    # v4.0 신규: HY Credit Spread + Sahm Rule
    # ============================================================

    def _signal_hy_spread(self) -> Signal | None:
        """
        HY Credit Spread (ICE BofA) → 리스크 선호도 / 신용 환경 시그널

        해석:
          - 3%p 미만: 신용환경 양호 → bullish (위험자산 선호)
          - 3~5%p: 경계 → bearish (리스크 오프 진행)
          - 5%p 이상: 신용경색 위험 → strong bearish
          - 추세(MoM 변화): 확대 추세면 악화, 축소 전환이면 바닥 신호
        """
        spread = self._load_series("BAMLH0A0HYM2", months=24)
        if spread is None or len(spread) < 5:
            return None

        sub = {}
        current = float(spread.iloc[-1])
        sub["spread_pct"] = round(current, 2)

        # MoM 변화 (월별 이동평균 비교)
        ma1m = float(spread.iloc[-1:].mean())
        ma3m = float(spread.iloc[-66:].mean()) if len(spread) >= 66 else ma1m
        trend = ma1m - ma3m
        sub["trend_3m"] = round(trend, 3)  # 양수 = 확대 추세 (악화), 음수 = 축소 추세 (개선)

        # 스프레드 레벨 기반 점수 (낮을수록 bullish)
        if current < 3.0:
            level_score = 0.75   # best: 신용환경 양호
        elif current < 4.0:
            level_score = 0.60
        elif current < 5.0:
            level_score = 0.40
        else:
            level_score = 0.20   # worst: 신용경색 위험

        # 추세 보정 (0~±0.15)
        trend_adj = max(-0.15, min(0.15, -trend * 0.05))  # 축소 추세(음수) → 점수 상향
        score = max(0.05, min(0.95, level_score + trend_adj))
        sub["level_score"] = round(level_score, 2)

        # 추세 전환 감지 (바닥 시그널)
        if trend < -0.2 and current < 5.0:
            desc = f"HY Spread {current:.1f}%p (3개월 축소 추세 −{abs(trend):.2f}p) → 위험 선호 회복, 사이클 바닥 근접 시사"
        elif current >= 5.0:
            desc = f"HY Spread {current:.1f}%p — 신용경색 수준, 반도체 섹터 리스크 오프 압력 강함"
        elif trend > 0.3:
            desc = f"HY Spread {current:.1f}%p (확대 추세 +{trend:.2f}p) — 신용 리스크 증가, 방어적 포지션 필요"
        else:
            dir_txt = "안정적" if abs(trend) < 0.1 else ("개선 중" if trend < 0 else "소폭 악화")
            desc = f"HY Spread {current:.1f}%p ({dir_txt}) — 신용환경 양호, 위험 선호 지속"

        return self._make_signal(
            indicator_id="HY_SPREAD",
            dimension="macro_regime",
            score=score,
            sub_signals=sub,
            description=desc,
            use_sigmoid=True,  # 선행지표: sigmoid 적용
        )

    def _signal_sahm_rule(self) -> Signal | None:
        """
        Sahm Rule Recession Indicator → 실시간 경기침체 탐지

        Sahm Rule: 실업률 3개월 이동평균 - 직전 12개월 최저치
          - 0.5 이상: 경기침체 시작 (1970년 이후 모든 리세션 정확히 포착)
          - 0.3~0.5: 경기 둔화 경고
          - 0.3 미만: 정상 범위
        """
        sahm = self._load_series("SAHMREALTIME", months=24)
        if sahm is None or len(sahm) < 3:
            return None

        sub = {}
        current = float(sahm.iloc[-1])
        sub["sahm_value"] = round(current, 3)

        # 3개월 전 값과 비교 (추세)
        prev3m = float(sahm.iloc[-4]) if len(sahm) >= 4 else current
        trend = current - prev3m
        sub["trend_3m"] = round(trend, 3)

        # 점수 산출
        if current >= 0.5:
            score = 0.10  # strong bearish: 리세션 진입
        elif current >= 0.3:
            score = 0.35  # bearish: 경기 둔화 경고
        elif current >= 0.1:
            score = 0.55  # 약간 상승, 모니터링
        else:
            score = 0.70  # 정상 범위, 경기침체 위험 낮음

        # 추세 보정
        trend_adj = max(-0.1, min(0.1, -trend * 0.5))  # 상승 추세 → bearish 보정
        score = max(0.05, min(0.95, score + trend_adj))

        if current >= 0.5:
            desc = f"Sahm Rule {current:.2f} — 경기침체 진입 기준 초과 (0.5p). 반도체 수요 급냉 우려"
        elif current >= 0.3:
            desc = f"Sahm Rule {current:.2f} — 경기 둔화 경고 구간 (0.3~0.5p). 방어적 포지션 강화"
        elif trend > 0.1:
            desc = f"Sahm Rule {current:.2f} (↑ 상승 추세) — 아직 정상이나 악화 추이. 모니터링 필요"
        else:
            desc = f"Sahm Rule {current:.2f} — 정상 범위 (0.3p 미만). 경기침체 위험 낮음"

        return self._make_signal(
            indicator_id="SAHM_RULE",
            dimension="macro_regime",
            score=score,
            sub_signals=sub,
            description=desc,
            use_sigmoid=False,  # 동행지표: 선형 변환 유지
        )
