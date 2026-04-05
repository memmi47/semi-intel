# Semi-Intel: Semiconductor Investment Intelligence

반도체/AI 섹터 투자 의사결정 지원 시스템 — Phase 1: 데이터 인프라

## 개요

## 개요

Bernard Baumohl의 "The Secrets of Economic Indicators" 3판과 최신 사이클 연구를 기반하여 총 26개 경제 지표를 데이터베이스화하고, 반도체 섹터에 특화된 투자 시그널을 생성하는 예측 중심의 지능형 시스템 구축.

### 🌟 v4.1 핵심 업데이트 (Memory Cycle Now)

*   **Interactive Scenario Dashboard**: 사전 정의된 시나리오 고정 점수를 넘어, 사용자 스스로 각 경제/반도체 이벤트 발생 확률(0~100%)을 실시간으로 조절하며 예상 점수(Expected Score)를 시뮬레이션 할 수 있는 프론트엔드 엔진 구축.
*   **Offline Memory Reference**: 실시간 엔진과 격리된 보조 지표로서, Omdia(1Q11~4Q25) 및 WSTS 과거 수급률 및 시장 규모 데이터를 독자적인 UI 탭으로 별도 시각화.
*   **Methodology & Action 고도화**: 국면 전환 임계값(Threshold)을 방법론에 명문화하고, Investment Action의 주관적 추천 멘트를 배제, 향후 6개월 기준 관점의 객관적/방어적 투자 지침으로 전면 개편.
*   **3-Layer Scoring Architecture**: 단일 점수가 아닌, 지표의 선후행성(Timing)에 따라 3개 계층(Predictive 선행, Diagnostic 동행, Confirmation 후행)으로 점수를 분리하여 산출해 시장 변곡점을 조기 포착 (v4.0 기반 상속).
*   **2대 핵심 매크로 지표 편입**: 하이일드 신용 스프레드(리스크 탐지)와 샴의 법칙(Sahm Rule; 실시간 리세션 탐지)의 레이어 반영.

## 지표 체계

| Tier | 구분 | 지표 수 | FRED 시리즈 | 역할 |
|------|------|---------|------------|------|
| 1 | 핵심 선행 | 5 | 25 | 반도체 투자에 직접적 인과관계 |
| 2 | 매크로 환경 | 9 | 27 | 수요/금리/인플레이션 경로 (신용 스프레드, 리세션 포함) |
| 3 | 보조 확인 | 4 | 6 | 경기 방향성 교차검증 |
| S | 섹터 특화 | 8 | 1+ | 반도체 전용 (SOX, DRAM 가격, HBM, CapEx 등) |

## 🚀 Installation & Quick Start

간단한 4단계만 거치면 모든 데이터 수집 및 분석 파이프라인이 자동으로 구동되는 대시보드를 사용할 수 있습니다.

### 1. 환경 준비 및 의존성 설치
```bash
# 프로젝트 디렉토리로 이동
cd semi-intel

# 가상환경 생성 및 활성화 (권장)
python3 -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate

# 패키지 설치
pip install -r requirements.txt
```

### 2. API Key 설정
`.env.example` 파일을 복사하여 `.env` 파일을 생성하고 필요한 키를 입력합니다.
```bash
cp .env.example .env
```
- **FRED_API_KEY**: 매크로 경제 데이터 수집 필수 ([무료 발급](https://fred.stlouisfed.org/docs/api/api_key.html))
- **ANTHROPIC_API_KEY**: AI 분석가 기능 사용 시 (선택)

### 3. 초기 DB 셋업
데이터베이스 테이블과 지표 메타데이터를 초기화합니다. (최초 1회만 실행)
```bash
python main.py setup
```

### 4. 대시보드 서버 실행 (추천)
아래 명령어를 실행하면 웹 대시보드가 열리며, **백그라운드에서 매일 자동으로 데이터를 수집하고 시장 변곡점 점수를 갱신**합니다.
```bash
python -m api.server
```
👉 브라우저에서 접속: [http://localhost:8000](http://localhost:8000)

*(수동으로 지금 당장 데이터를 1회 전체 갱신하고 싶다면 `python main.py full` 입력)*

## 명령어

| 명령어 | 설명 |
|--------|------|
| `setup` | DB 생성 + 지표 메타데이터 동기화 + CSV 템플릿 생성 |
| `validate` | 모든 FRED 시리즈 코드 유효성 검증 |
| `collect` | 전체 수집 (FRED + Yahoo + CapEx) |
| `collect-fred` | FRED 데이터만 수집 |
| `collect-yahoo` | Yahoo Finance 데이터만 수집 |
| `collect-capex` | Hyperscaler CapEx 수집 |
| `status` | 수집 현황 대시보드 |
| `scheduler` | 자동 수집 데몬 실행 |

## 수동 데이터 입력 (DRAM 가격 등)

```bash
# 사용 가능한 수동 시리즈 목록
python -m collectors.manual_collector list

# CSV 템플릿 생성
python -m collectors.manual_collector template DRAM_SPOT

# 단일 입력
python -m collectors.manual_collector add DRAM_SPOT DDR5_8Gb_SPOT 2025-01-15 3.45

# CSV 임포트
python -m collectors.manual_collector import DRAM_SPOT ./data/manual/dram_prices.csv
```

## 프로젝트 구조

```
semi-intel/
├── main.py                    # 메인 엔트리포인트 (Phase 1 + 2 통합)
├── requirements.txt           # Python 의존성
├── .env.example              # 환경변수 템플릿
├── config/
│   ├── __init__.py
│   └── indicators.py         # 22개 지표 레지스트리 (핵심 파일)
├── collectors/
│   ├── __init__.py
│   ├── fred_collector.py     # FRED API 수집기
│   ├── yahoo_collector.py    # Yahoo Finance 수집기
│   └── manual_collector.py   # 수동 입력 (DRAM, SEMI B/B)
├── db/
│   ├── __init__.py
│   └── database.py           # SQLAlchemy ORM + DB 매니저
├── analysis/                  # Phase 2: 분석 엔진
│   ├── __init__.py
│   ├── transforms.py         # 데이터 변환 (YoY%, MoM%, Z-score, MA 등)
│   ├── signal_generator.py   # 22개 지표별 시그널 생성 로직
│   ├── composite_score.py    # 5차원 가중합산 → Composite Score
│   ├── scenario_analyzer.py  # 시나리오 분석 (6개 사전정의 + 커스텀)
│   └── briefing.py           # 투자 브리핑 생성 (콘솔/MD/JSON)
├── data/                     # 자동 생성
│   ├── semi_intel.db         # SQLite 데이터베이스
│   └── manual/               # 수동 입력 CSV 템플릿
├── reports/                   # 자동 생성 (briefing 출력)
└── logs/                     # 자동 생성
```

## 데이터 소스

| 소스 | 접근 | 지표 |
|------|------|------|
| FRED API | 무료 (API key) | 매크로 지표 56개 시리즈 |
| Yahoo Finance | 무료 | SOX, SOXX, SMH, Hyperscaler 주가/CapEx |
| TrendForce | 기본 무료 | DRAM/NAND 가격 (수동 입력) |
| SEMI | 일부 유료 | Book-to-Bill Ratio (수동 입력) |
| SIA/WSTS | 보고서 기반 | 글로벌 반도체 매출 (수동 입력) |

## 자동 수집 스케줄

| 소스 | 주기 | 시간 |
|------|------|------|
| FRED | 매일 | 10:00 |
| Yahoo Finance | 매일 | 17:30 |
| Hyperscaler CapEx | 매주 월 | 08:00 |

## 로드맵

- [x] Phase 1: 데이터 인프라
- [x] Phase 2: 분석 엔진 (Signal Generator, Composite Score, Scenarios)
- [x] Phase 3: 웹 대시보드 (React + FastAPI)
- [x] Phase 4: AI 조언 레이어 (Claude API 연동)

## Phase 4: AI Advisory Layer

### 설정

```bash
# .env 파일에 추가 (3개 중 선택)
LLM_PROVIDER=google  # google / anthropic / openai 중 택 1

# 선택한 Provider에 맞는 API 키 입력
GOOGLE_API_KEY=AIza-your-key-here
# ANTHROPIC_API_KEY=sk-ant-your-key-here
# OPENAI_API_KEY=sk-your-key-here
```

### CLI 명령어

| 명령어 | 설명 |
|--------|------|
| `ai-briefing` | AI가 현재 데이터 기반으로 일일 투자 브리핑 생성 |
| `ai-ask "질문"` | 자유 질의 (현재 경제지표 컨텍스트 자동 포함) |
| `ai-indicator ISM_MFG` | 개별 지표 심층 분석 |
| `ai-scenario ai_capex_surge` | 시나리오 심층 분석 (전달경로, 세그먼트별 영향) |
| `ai-regime` | Regime 전환 가능성 분석 |
| `ai-chat` | 대화형 REPL 모드 (연속 질의, /briefing, /regime 지원) |

### API 엔드포인트

| 엔드포인트 | 설명 |
|-----------|------|
| `POST /api/ai/ask` | 자유 질의 `{"question": "..."}` |
| `GET /api/ai/briefing` | AI 일일 브리핑 |
| `GET /api/ai/indicator/{id}` | 지표 심층 분석 |
| `GET /api/ai/scenario/{id}` | 시나리오 심층 분석 |
| `GET /api/ai/regime` | Regime 전환 분석 |

### 아키텍처

```
[경제지표 DB] → [Signal Generator] → [Composite Score]
                                          ↓
                                   [Context Builder] → System Prompt + 데이터 컨텍스트
                                          ↓
                                   [Claude API] → 투자 조언/브리핑/분석
```

- 모든 AI 호출에 현재 Composite Score, 시그널, 시나리오 데이터가 컨텍스트로 자동 주입
- 대화형 모드에서는 히스토리 유지로 연속 질의 가능
- 토큰 사용량 자동 추적

## Phase 3: 웹 대시보드

### 실행법

```bash
# 1. FastAPI 서버 시작
cd semi-intel
python -m api.server
# → http://localhost:8000 (API docs: http://localhost:8000/docs)

# 2. React 대시보드
# 옵션 A: Claude.ai에서 JSX 아티팩트로 미리보기
# 옵션 B: 로컬 React 앱에 frontend/dashboard.jsx 통합
```

### API 엔드포인트

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /api/status` | 시스템 상태 |
| `GET /api/indicators` | 전체 지표 메타데이터 |
| `GET /api/indicators/{id}` | 개별 지표 + 최근 데이터 |
| `GET /api/series/{code}` | 시계열 데이터 |
| `GET /api/signals` | 전체 시그널 생성 |
| `GET /api/score` | Composite Score 산출 |
| `GET /api/score/history` | 스코어 히스토리 |
| `GET /api/scenarios/compare` | 시나리오 비교 |
| `GET /api/briefing` | 투자 브리핑 JSON |
| `POST /api/collect/fred` | FRED 수집 트리거 |
| `POST /api/collect/yahoo` | Yahoo 수집 트리거 |

### 대시보드 구성

4개 탭: Overview, Signals, Scenarios, Trends
- Overview: Cycle Score 게이지 + 5차원 분해 + 레이더 차트 + 핵심 시그널 + 투자 행동
- Signals: 차원별 시그널 상세 (bullish/bearish/neutral 분류)
- Scenarios: 6개 시나리오 비교 + 임팩트 차트 + Regime Zone
- Trends: 스코어/차원별 시계열 추이 + 오버레이

## Phase 2: 분석 엔진

### 명령어

| 명령어 | 설명 |
|--------|------|
| `signals` | 22개 지표의 bullish/bearish/neutral 시그널 생성 |
| `score` | Semiconductor Cycle Composite Score (0-100) 산출 |
| `briefing` | 투자 브리핑 콘솔 출력 (Rich 지원) |
| `briefing-md` | 마크다운 파일로 브리핑 저장 |
| `briefing-json` | JSON 파일로 브리핑 저장 (대시보드 API용) |
| `scenarios` | 6개 사전 정의 시나리오 비교 분석 |
| `scenario <id>` | 개별 시나리오 상세 분석 |
| `full` | 수집 → 분석 → 브리핑 전체 파이프라인 |

### Composite Score 구조

5개 차원의 가중합산으로 반도체 사이클 위치를 0-100 스코어로 산출:

| 차원 | 가중치 | 구성 지표 |
|------|--------|-----------|
| Demand Cycle | 30% | 내구재주문, ISM PMI, 소매판매, Hyperscaler CapEx, SOX |
| Supply Cycle | 20% | 산업생산/가동률, SEMI B/B, 생산성 |
| Price Cycle | 20% | DRAM 가격, CPI, PPI |
| Macro Regime | 20% | GDP, Yield Curve, Fed, LEI, 실업수당 |
| Global Demand | 10% | 무역수지, 중국 PMI |

### Regime Detection (4단계 사이클)

| Regime | Score 범위 | 투자 행동 |
|--------|-----------|-----------|
| Expansion | 65-100 | 반도체 비중 확대, AI/HBM 집중 |
| Late Cycle | 50-65 | 선별적 유지, 차익실현 검토 |
| Contraction | 35-50 | 비중 축소, 바닥 신호 모니터링 |
| Recovery | 0-35→상승 | 바닥 매수 시작, 장비/소재 선행 |

### 사전 정의 시나리오

| ID | 시나리오 | 확률 |
|----|----------|------|
| `ai_capex_surge` | AI CapEx 급증 | 25% |
| `fed_pivot_dovish` | Fed 비둘기파 전환 | 30% |
| `china_recovery` | 중국 경기 회복 | 20% |
| `recession_hard` | 경기 침체 (Hard Landing) | 15% |
| `trade_war_escalation` | 미중 기술전쟁 격화 | 20% |
| `ai_bubble_burst` | AI 투자 거품 붕괴 | 10% |
