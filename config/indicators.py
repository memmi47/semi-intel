from __future__ import annotations
"""
Semi-Intel Indicator Registry
==============================
책 기반 16개 매크로 지표 + 6개 반도체 특화 지표
각 지표에 FRED 시리즈 코드, 수집 주기, 반도체 연관성 매핑
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Tier(Enum):
    CORE = 1        # 반도체 직접 연관
    MACRO = 2       # 매크로 환경 (간접)
    AUX = 3         # 보조/확인
    SECTOR = "S"    # 섹터 특화 (책 외)


class Frequency(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class Dimension(Enum):
    DEMAND = "demand_cycle"
    SUPPLY = "supply_cycle"
    PRICE = "price_cycle"
    MACRO = "macro_regime"
    GLOBAL = "global_demand"


@dataclass
class FredSeries:
    """FRED에서 수집할 개별 시리즈"""
    code: str               # FRED series ID
    name: str               # 설명
    transform: str = "raw"  # raw, yoy_pct, mom_pct, diff, ma3, ma6


@dataclass
class Indicator:
    """경제 지표 정의"""
    id: str
    name: str
    tier: Tier
    category: str
    source: str
    frequency: Frequency
    dimension: Dimension
    book_chapter: str
    semi_relevance: str
    signal_logic: str
    fred_series: list[FredSeries] = field(default_factory=list)
    yahoo_symbols: list[str] = field(default_factory=list)
    external_source: Optional[str] = None
    lag_days: int = 0
    weight_in_dimension: float = 1.0


# ============================================================
# TIER 1: 핵심 선행지표 — 반도체 투자판단에 직접적 인과관계
# ============================================================

DURABLE_GOODS = Indicator(
    id="DGORDER",
    name="Durable Goods Orders",
    tier=Tier.CORE,
    category="Production & Orders",
    source="Census Bureau",
    frequency=Frequency.MONTHLY,
    dimension=Dimension.DEMAND,
    book_chapter="Ch3 p148",
    lag_days=26,
    semi_relevance="비국방 자본재(항공기 제외) 주문은 기업의 IT/반도체 장비 투자 의향을 직접 반영",
    signal_logic="3개월 연속 증가 → 반도체 수요 확대 신호, 감소 → 재고조정/수요 둔화",
    weight_in_dimension=1.2,
    fred_series=[
        FredSeries("DGORDER", "Durable Goods New Orders, Total"),
        FredSeries("NEWORDER", "Manufacturers New Orders: Nondefense Capital Goods ex Aircraft"),
        FredSeries("ACDGNO", "Value of Manufacturers' New Orders: Durable Goods"),
        FredSeries("ADXTNO", "Manufacturers New Orders: Nondefense Capital Goods ex Aircraft (real)"),
        FredSeries("AMDMUO", "Manufacturers Unfilled Orders: Durable Goods"),
    ],
)

INDUSTRIAL_PRODUCTION = Indicator(
    id="INDPRO",
    name="Industrial Production & Capacity Utilization",
    tier=Tier.CORE,
    category="Production & Orders",
    source="Federal Reserve",
    frequency=Frequency.MONTHLY,
    dimension=Dimension.SUPPLY,
    book_chapter="Ch3 p170",
    lag_days=16,
    semi_relevance="제조업 가동률은 반도체 fab 투자 사이클과 직결. 가동률 80%+ → 증설 투자 트리거",
    signal_logic="Capacity Util > 80% → 반도체 증설 수요 증가, < 75% → 과잉설비 리스크",
    weight_in_dimension=1.0,
    fred_series=[
        FredSeries("INDPRO", "Industrial Production: Total Index"),
        FredSeries("TCU", "Capacity Utilization: Total Industry"),
        FredSeries("CUMFNS", "Capacity Utilization: Manufacturing (NAICS)"),
        FredSeries("IPB51220SQ", "Industrial Production: Durable Manufacturing: Computers and Electronic Products"),
        FredSeries("IPMAN", "Industrial Production: Manufacturing (NAICS)"),
    ],
)

ISM_MANUFACTURING = Indicator(
    id="ISM_MFG",
    name="ISM Manufacturing PMI",
    tier=Tier.CORE,
    category="Production & Orders",
    source="ISM",
    frequency=Frequency.MONTHLY,
    dimension=Dimension.DEMAND,
    book_chapter="Ch3 p181",
    lag_days=1,
    semi_relevance="New Orders 세부지표가 반도체 수요 2-3개월 선행. Supplier Deliveries는 공급망 병목 신호",
    signal_logic="PMI > 50 확장, New Orders > Inventories → 반도체 수요 강세",
    weight_in_dimension=1.3,
    fred_series=[
        FredSeries("NAPM", "ISM Manufacturing: PMI Composite Index"),
        FredSeries("NAPMNOI", "ISM Manufacturing: New Orders Index"),
        FredSeries("NAPMII", "ISM Manufacturing: Inventories Index"),
        FredSeries("NAPMSDI", "ISM Manufacturing: Supplier Deliveries Index"),
        FredSeries("NAPMPRI", "ISM Manufacturing: Prices Index"),
    ],
)

GDP = Indicator(
    id="GDP",
    name="Gross Domestic Product",
    tier=Tier.CORE,
    category="National Output",
    source="BEA",
    frequency=Frequency.QUARTERLY,
    dimension=Dimension.MACRO,
    book_chapter="Ch3 p130",
    lag_days=30,
    semi_relevance="IT 투자(Equipment & Software) 세부항목이 반도체 수요의 거시적 프레임",
    signal_logic="GDP 성장 + IT투자 가속 → 반도체 슈퍼사이클, GDP 둔화 + IT투자 유지 → AI 구조적 성장",
    weight_in_dimension=1.0,
    fred_series=[
        FredSeries("GDP", "Gross Domestic Product (nominal)"),
        FredSeries("GDPC1", "Real GDP"),
        FredSeries("A006RC1Q027SBEA", "Real GDP: Private Fixed Investment: Nonresidential: Equipment"),
        FredSeries("Y006RC1Q027SBEA", "Real Private Fixed Investment: Information Processing Equipment"),
        FredSeries("PCECC96", "Real PCE"),
        FredSeries("A007RC1Q027SBEA", "Real Private Fixed Investment: Intellectual Property Products"),
    ],
)

YIELD_CURVE = Indicator(
    id="YIELD_CURVE",
    name="Yield Curve (10Y-2Y Spread)",
    tier=Tier.CORE,
    category="Financial Markets",
    source="Federal Reserve",
    frequency=Frequency.DAILY,
    dimension=Dimension.MACRO,
    book_chapter="Ch3 p349",
    lag_days=0,
    semi_relevance="역전 시 12-18개월 후 경기침체 → 반도체 다운사이클 선행 경고",
    signal_logic="역전 → 반도체 주식 비중 축소 준비, 정상화 재개 → 사이클 바닥 근접",
    weight_in_dimension=1.1,
    fred_series=[
        FredSeries("T10Y2Y", "10-Year Treasury Minus 2-Year Treasury"),
        FredSeries("T10Y3M", "10-Year Treasury Minus 3-Month Treasury"),
        FredSeries("DGS10", "10-Year Treasury Constant Maturity Rate"),
        FredSeries("DGS2", "2-Year Treasury Constant Maturity Rate"),
        FredSeries("DFII10", "10-Year TIPS (real yield)"),
    ],
)

# ============================================================
# TIER 2: 매크로 환경 — 수요/금리/인플레이션 간접 경로
# ============================================================

NONFARM_PAYROLLS = Indicator(
    id="NFP",
    name="Nonfarm Payrolls",
    tier=Tier.MACRO,
    category="Employment",
    source="BLS",
    frequency=Frequency.MONTHLY,
    dimension=Dimension.DEMAND,
    book_chapter="Ch3 p31",
    lag_days=3,
    semi_relevance="IT/전문서비스 고용 추이는 테크 투자 방향성 반영",
    signal_logic="IT/전문서비스 고용 증가 + 제조업 고용 안정 → 반도체 수요 견조",
    fred_series=[
        FredSeries("PAYEMS", "All Employees: Total Nonfarm"),
        FredSeries("MANEMP", "All Employees: Manufacturing"),
        FredSeries("USINFO", "All Employees: Information"),
        FredSeries("USPRIV", "All Employees: Total Private"),
        FredSeries("CES0500000003", "Average Hourly Earnings: Total Private"),
        FredSeries("UNRATE", "Unemployment Rate"),
    ],
)

CPI = Indicator(
    id="CPI",
    name="Consumer Price Index",
    tier=Tier.MACRO,
    category="Prices & Inflation",
    source="BLS",
    frequency=Frequency.MONTHLY,
    dimension=Dimension.PRICE,
    book_chapter="Ch3 p305",
    lag_days=13,
    semi_relevance="인플레이션 → Fed 금리 인상 → 테크 밸류에이션 압박",
    signal_logic="Core CPI 하락 추세 → Fed 완화 기대 → 반도체 주식 멀티플 확장",
    fred_series=[
        FredSeries("CPIAUCSL", "CPI: All Items"),
        FredSeries("CPILFESL", "CPI: All Items Less Food & Energy (Core)"),
        FredSeries("CPIENGSL", "CPI: Energy"),
        FredSeries("CUSR0000SEHA", "CPI: Rent of Primary Residence"),
        FredSeries("PCEPILFE", "PCE ex Food & Energy (Core PCE) — Fed preferred"),
    ],
)

PPI = Indicator(
    id="PPI",
    name="Producer Price Index",
    tier=Tier.MACRO,
    category="Prices & Inflation",
    source="BLS",
    frequency=Frequency.MONTHLY,
    dimension=Dimension.PRICE,
    book_chapter="Ch3 p317",
    lag_days=15,
    semi_relevance="중간재 PPI는 반도체 원자재/장비 비용 반영",
    signal_logic="중간재 PPI 상승 + 최종재 안정 → 반도체 마진 압박",
    fred_series=[
        FredSeries("PPIACO", "PPI: All Commodities"),
        FredSeries("WPSID61", "PPI: Intermediate Demand"),
        FredSeries("WPSFD4", "PPI: Final Demand"),
        FredSeries("PCU33443344", "PPI: Semiconductor and Electronic Components"),
    ],
)

RETAIL_SALES = Indicator(
    id="RETAIL",
    name="Retail Sales",
    tier=Tier.MACRO,
    category="Consumer Spending",
    source="Census Bureau",
    frequency=Frequency.MONTHLY,
    dimension=Dimension.DEMAND,
    book_chapter="Ch3 p93",
    lag_days=14,
    semi_relevance="전자/가전 소매판매가 소비자향 반도체(Mobile DRAM, NAND) 수요 proxy",
    signal_logic="전자제품 소매 증가 → 모바일/PC DRAM/NAND 수요 강세",
    fred_series=[
        FredSeries("RSAFS", "Advance Retail Sales: Retail and Food Services"),
        FredSeries("RSEAS", "Retail Sales: Electronics and Appliance Stores"),
        FredSeries("MRTSSM44X72USS", "Retail Sales: Retail Trade and Food Services ex Autos"),
    ],
)

CONSUMER_CONFIDENCE = Indicator(
    id="CONSUMER_CONF",
    name="Consumer Confidence / Sentiment",
    tier=Tier.MACRO,
    category="Consumer Spending",
    source="Conference Board / UMich",
    frequency=Frequency.MONTHLY,
    dimension=Dimension.DEMAND,
    book_chapter="Ch3 p112",
    lag_days=5,
    semi_relevance="소비심리 → 전자기기 구매 의향 선행",
    signal_logic="기대지수 상승 → 내구재(전자기기) 소비 회복 기대",
    fred_series=[
        FredSeries("UMCSENT", "University of Michigan: Consumer Sentiment"),
        FredSeries("CSCICP03USM665S", "Consumer Opinion Surveys: Confidence Indicators: OECD"),
        FredSeries("MICH", "University of Michigan: Inflation Expectation"),
    ],
)

TRADE_BALANCE = Indicator(
    id="TRADE",
    name="International Trade Balance",
    tier=Tier.MACRO,
    category="Foreign Trade",
    source="Census/BEA",
    frequency=Frequency.MONTHLY,
    dimension=Dimension.GLOBAL,
    book_chapter="Ch3 p269",
    lag_days=35,
    semi_relevance="반도체/전자부품 수출입 세부 데이터로 글로벌 수요 방향 파악",
    signal_logic="반도체 수출 증가 → 글로벌 수요 회복",
    fred_series=[
        FredSeries("BOPGSTB", "Trade Balance: Goods and Services"),
        FredSeries("EXPGS", "Exports of Goods and Services"),
        FredSeries("IMPGS", "Imports of Goods and Services"),
        FredSeries("IEABC", "International Trade: Exports: Advanced Technology Products"),
    ],
)

FOMC = Indicator(
    id="FOMC",
    name="FOMC / Fed Funds Rate",
    tier=Tier.MACRO,
    category="Federal Reserve",
    source="Federal Reserve",
    frequency=Frequency.DAILY,
    dimension=Dimension.MACRO,
    book_chapter="Ch3 p260",
    lag_days=0,
    semi_relevance="금리 경로가 테크/반도체 밸류에이션의 할인율 직접 결정",
    signal_logic="Dovish 전환 → 반도체 주식 강세, Hawkish → 밸류에이션 조정",
    fred_series=[
        FredSeries("FEDFUNDS", "Effective Federal Funds Rate"),
        FredSeries("DFEDTARU", "Fed Funds Target Rate Upper"),
        FredSeries("WALCL", "Fed Total Assets (Balance Sheet)"),
        FredSeries("RRPONTSYD", "Overnight Reverse Repurchase Agreements"),
    ],
)

# ============================================================
# TIER 3: 보조/확인 지표
# ============================================================

LEI = Indicator(
    id="LEI",
    name="Leading Economic Indicators",
    tier=Tier.AUX,
    category="Composite",
    source="Conference Board",
    frequency=Frequency.MONTHLY,
    dimension=Dimension.MACRO,
    book_chapter="Ch3 p196",
    lag_days=22,
    semi_relevance="6개월 연속 하락 시 경기침체 경고 → 반도체 다운사이클 대비",
    signal_logic="3개월 연속 하락 → 경계, 6개월 → 방어적 포지션",
    fred_series=[
        FredSeries("USSLIND", "Leading Index for the United States"),
        FredSeries("USREC", "NBER Recession Indicators"),
    ],
)

HOUSING = Indicator(
    id="HOUSING",
    name="Housing Starts & Building Permits",
    tier=Tier.AUX,
    category="Housing",
    source="Census Bureau",
    frequency=Frequency.MONTHLY,
    dimension=Dimension.DEMAND,
    book_chapter="Ch3 p204",
    lag_days=18,
    semi_relevance="건설 경기 → 가전/IoT 수요 간접 연결",
    signal_logic="주택 착공 증가 → 가전/스마트홈 반도체 수요 간접 지지",
    fred_series=[
        FredSeries("HOUST", "New Privately-Owned Housing Units Started"),
        FredSeries("PERMIT", "New Privately-Owned Housing Units Authorized"),
    ],
)

WEEKLY_CLAIMS = Indicator(
    id="CLAIMS",
    name="Weekly Unemployment Claims",
    tier=Tier.AUX,
    category="Employment",
    source="DOL",
    frequency=Frequency.WEEKLY,
    dimension=Dimension.MACRO,
    book_chapter="Ch3 p55",
    lag_days=4,
    semi_relevance="고빈도 경기 실시간 모니터링",
    signal_logic="4주 이동평균 상승 추세 → 경기 둔화 초기 신호",
    fred_series=[
        FredSeries("ICSA", "Initial Claims"),
        FredSeries("CCSA", "Continued Claims"),
    ],
)

PRODUCTIVITY = Indicator(
    id="PRODUCTIVITY",
    name="Productivity and Costs",
    tier=Tier.AUX,
    category="Productivity",
    source="BLS",
    frequency=Frequency.QUARTERLY,
    dimension=Dimension.SUPPLY,
    book_chapter="Ch3 p335",
    lag_days=35,
    semi_relevance="생산성 향상 → IT/AI 투자 정당화 근거",
    signal_logic="생산성 가속 → AI/자동화 투자 확대 근거 강화",
    fred_series=[
        FredSeries("OPHNFB", "Nonfarm Business Sector: Real Output Per Hour"),
        FredSeries("ULCNFB", "Nonfarm Business Sector: Unit Labor Cost"),
    ],
)

# ============================================================
# TIER S: 반도체 특화 지표 (책 외 추가)
# ============================================================

SOX_INDEX = Indicator(
    id="SOX",
    name="Philadelphia Semiconductor Index",
    tier=Tier.SECTOR,
    category="Sector Specific",
    source="Nasdaq",
    frequency=Frequency.DAILY,
    dimension=Dimension.DEMAND,
    book_chapter="N/A",
    lag_days=0,
    semi_relevance="반도체 섹터 시장 심리 직접 반영",
    signal_logic="200일 이동평균 대비 위치 → 추세 판단",
    yahoo_symbols=["^SOX", "SOXX", "SMH"],
)

CHINA_PMI = Indicator(
    id="CHINA_PMI",
    name="China Caixin Manufacturing PMI",
    tier=Tier.SECTOR,
    category="International",
    source="S&P Global/Caixin",
    frequency=Frequency.MONTHLY,
    dimension=Dimension.GLOBAL,
    book_chapter="Ch4 p396",
    lag_days=1,
    semi_relevance="중국은 반도체 최대 소비국. 제조업 경기가 레거시 반도체 수요 좌우",
    signal_logic="PMI > 50 + 신규주문 확대 → 반도체 수출 수요 회복",
    fred_series=[
        FredSeries("CHNMPMINDMEI", "China Manufacturing PMI (OECD)"),
    ],
)

# --- Memory Price Proxies (3-Layer 구조) ---
# 수동 입력 제거, 전량 자동 수집

MEMORY_DRAM_PROXY = Indicator(
    id="DRAM_PROXY",
    name="DRAM Price Proxy (Pure Player Basket)",
    tier=Tier.SECTOR,
    category="Sector Specific",
    source="Yahoo Finance (자동 수집)",
    frequency=Frequency.DAILY,
    dimension=Dimension.PRICE,
    book_chapter="N/A",
    lag_days=0,
    semi_relevance=(
        "DRAM pure player 주가 basket으로 DRAM 가격 방향성 대리. "
        "Micron(DRAM ~70% 매출) + Nanya(DRAM only, 레거시 비중 높아 범용 DRAM 가격의 순수 반영체). "
        "주가는 DRAM 계약가를 1-3개월 선행 반영하므로 투자 판단에 더 유리"
    ),
    signal_logic="Basket MoM% 양수 → DRAM 가격 상승 기대, 음수 → 하락 기대. 3개월 연속 방향 전환 시 사이클 전환 신호",
    yahoo_symbols=["MU", "2408.TW"],
)

MEMORY_NAND_PROXY = Indicator(
    id="NAND_PROXY",
    name="NAND Price Proxy (Pure Player Basket)",
    tier=Tier.SECTOR,
    category="Sector Specific",
    source="Yahoo Finance (자동 수집)",
    frequency=Frequency.DAILY,
    dimension=Dimension.PRICE,
    book_chapter="N/A",
    lag_days=0,
    semi_relevance=(
        "NAND pure player 주가 basket으로 NAND 가격 방향성 대리. "
        "SanDisk(SNDK, NAND only, NASDAQ 대형주) + Kioxia(285A.T, NAND only, 2024 IPO). "
        "Kioxia 데이터 불안정 시 SanDisk 단독으로 fallback"
    ),
    signal_logic="Basket MoM% 양수 → NAND 가격 상승 기대. SanDisk의 데이터센터 NAND 비중 증가로 AI 스토리지 수요도 반영",
    yahoo_symbols=["SNDK", "285A.T"],
)

HBM_PREMIUM = Indicator(
    id="HBM_PREMIUM",
    name="HBM Premium (SK hynix Outperformance)",
    tier=Tier.SECTOR,
    category="Sector Specific",
    source="Yahoo Finance (자동 수집)",
    frequency=Frequency.DAILY,
    dimension=Dimension.DEMAND,
    book_chapter="N/A",
    lag_days=0,
    semi_relevance=(
        "SK하이닉스 주가의 DRAM peer 대비 초과수익률 = HBM/AI 수요 프리미엄. "
        "SK하이닉스와 Micron/Nanya 모두 DRAM을 생산하지만, SK하이닉스만 더 오르면 "
        "그 차이는 HBM/AI 수요 프리미엄. 초과수익률 확대 → HBM 수요 강세, 축소/역전 → 프리미엄 소멸"
    ),
    signal_logic="SK하이닉스 MoM% - DRAM basket MoM% > 0 → HBM 수요 강세. 차이 확대 → AI 투자 가속, 축소 → 둔화 경고",
    yahoo_symbols=["000660.KS"],
    # Note: Signal 산출 시 DRAM_PROXY의 MU, 2408.TW 데이터와 교차 계산 필요
)

# --- Equipment Stocks Proxy (SEMI B/B 대체) ---

EQUIP_PROXY = Indicator(
    id="EQUIP_PROXY",
    name="Semiconductor Equipment Proxy (SEMI B/B 대체)",
    tier=Tier.SECTOR,
    category="Sector Specific",
    source="Yahoo Finance (자동 수집)",
    frequency=Frequency.DAILY,
    dimension=Dimension.SUPPLY,
    book_chapter="N/A",
    lag_days=0,
    semi_relevance=(
        "SEMI B/B Ratio 직접 확보 불가 → 장비 3대 기업 주가 basket으로 대체. "
        "ASML(리소그래피 독점), Applied Materials(증착/에칭), Lam Research(에칭/증착). "
        "시장이 B/B 정보를 주가에 선행 반영하므로, 원본 B/B보다 빠른 신호"
    ),
    signal_logic="Basket MoM% 양수 → 장비 투자 확대 기대(B/B>1.0 대리), 음수 → 투자 위축. 200일선 대비 위치도 추세 판단에 활용",
    yahoo_symbols=["AMAT", "LRCX", "ASML"],
)

# --- WSTS (SIA 경유, 확인 지표) ---

WSTS_SALES = Indicator(
    id="WSTS",
    name="WSTS Global Semiconductor Sales (via SIA)",
    tier=Tier.SECTOR,
    category="Sector Specific",
    source="SIA Press Release (WSTS 기반)",
    frequency=Frequency.MONTHLY,
    dimension=Dimension.DEMAND,
    book_chapter="N/A",
    lag_days=60,  # 2개월 후행 명시
    weight_in_dimension=0.5,  # 후행 지표이므로 가중치 하향
    semi_relevance=(
        "WSTS 글로벌 반도체 매출 데이터 (SIA 보도자료 경유). "
        "2개월 후행하므로 선행 지표가 아닌 사이클 확인(confirmation) 용도. "
        "DRAM/NAND 매출로 메모리 사이클 바닥/피크를 사후 검증"
    ),
    signal_logic="DRAM+NAND 매출 YoY% 반등 → 사이클 바닥 확인. 주가 proxy가 선행 시사한 전환을 WSTS가 뒤따라 확인하면 신뢰도 상승",
    external_source="sia_press_release",
    # CSV import: python -m collectors.manual_collector import WSTS ./data/wsts_data.csv
)

HYPERSCALER_CAPEX = Indicator(
    id="HYPERSCALER_CAPEX",
    name="Hyperscaler CapEx",
    tier=Tier.SECTOR,
    category="Sector Specific",
    source="SEC EDGAR (10-Q)",
    frequency=Frequency.QUARTERLY,
    dimension=Dimension.DEMAND,
    book_chapter="N/A",
    lag_days=45,
    semi_relevance="AI 데이터센터 투자의 직접 지표. GPU/HBM/eSSD 수요의 최종 드라이버",
    signal_logic="CapEx YoY 30%+ → AI 반도체 수요 강세 지속",
    yahoo_symbols=["MSFT", "GOOGL", "AMZN", "META"],
    external_source="sec_edgar",
)

# ============================================================
# Registry: 전체 지표 목록
# ============================================================

ALL_INDICATORS: list[Indicator] = [
    # Tier 1
    DURABLE_GOODS, INDUSTRIAL_PRODUCTION, ISM_MANUFACTURING, GDP, YIELD_CURVE,
    # Tier 2
    NONFARM_PAYROLLS, CPI, PPI, RETAIL_SALES, CONSUMER_CONFIDENCE,
    TRADE_BALANCE, FOMC,
    # Tier 3
    LEI, HOUSING, WEEKLY_CLAIMS, PRODUCTIVITY,
    # Tier S
    SOX_INDEX, CHINA_PMI,
    MEMORY_DRAM_PROXY, MEMORY_NAND_PROXY, HBM_PREMIUM,
    EQUIP_PROXY, WSTS_SALES, HYPERSCALER_CAPEX,
]

FRED_INDICATORS = [ind for ind in ALL_INDICATORS if ind.fred_series]
YAHOO_INDICATORS = [ind for ind in ALL_INDICATORS if ind.yahoo_symbols]
MANUAL_INDICATORS = [ind for ind in ALL_INDICATORS if ind.external_source]


def get_all_fred_series() -> list[tuple[str, str, str]]:
    """Returns (indicator_id, series_code, series_name) for all FRED series"""
    result = []
    for ind in FRED_INDICATORS:
        for series in ind.fred_series:
            result.append((ind.id, series.code, series.name))
    return result


def get_indicator(indicator_id: str) -> Indicator | None:
    """ID로 지표 조회"""
    for ind in ALL_INDICATORS:
        if ind.id == indicator_id:
            return ind
    return None


# Quick stats
if __name__ == "__main__":
    total_fred = sum(len(ind.fred_series) for ind in FRED_INDICATORS)
    print(f"Total indicators: {len(ALL_INDICATORS)}")
    print(f"  Tier 1 (Core):   {sum(1 for i in ALL_INDICATORS if i.tier == Tier.CORE)}")
    print(f"  Tier 2 (Macro):  {sum(1 for i in ALL_INDICATORS if i.tier == Tier.MACRO)}")
    print(f"  Tier 3 (Aux):    {sum(1 for i in ALL_INDICATORS if i.tier == Tier.AUX)}")
    print(f"  Tier S (Sector): {sum(1 for i in ALL_INDICATORS if i.tier == Tier.SECTOR)}")
    print(f"FRED series total: {total_fred}")
    print(f"Yahoo symbols:     {sum(len(i.yahoo_symbols) for i in YAHOO_INDICATORS)}")
    print(f"Manual sources:    {len(MANUAL_INDICATORS)}")
