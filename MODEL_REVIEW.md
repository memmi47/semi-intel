# Semi-Intel Model Review — LLM 자문 요청서

> **문서 목적**: 이 문서는 반도체 사이클 투자 인텔리전스 시스템인 "Semi-Intel"의 모델 구조를 분석하고 개선 방안을 도출하기 위해 작성되었습니다. LLM에게 이 문서를 전달하여 모델의 예측력 향상, 가중치 최적화, 백테스트 방법론 등에 대한 전문적 의견을 요청합니다.

---

## 1. 프로젝트 개요

### 1.1 Semi-Intel이란?

Semi-Intel(Semiconductor Investment Intelligence)은 24개 경제·섹터 지표를 수집·분석하여 **반도체 사이클의 현재 위치**를 진단하고, 투자 판단을 지원하는 대시보드 시스템입니다.

### 1.2 핵심 산출물

| 산출물 | 설명 |
|--------|------|
| **Composite Score** | 0~100점의 반도체 사이클 점수. 5개 차원의 가중평균 |
| **Regime** | 4가지 사이클 단계: Recovery → Expansion → Late Cycle → Contraction |
| **Signals** | 각 지표별 Bullish/Bearish/Neutral 판정 |
| **Trend Alert** | 변곡점(Divergence, Momentum) 감지 알람 |
| **Investment Action** | Regime별 투자 전략 권고 |

### 1.3 데이터 소스

- **FRED (Federal Reserve Economic Data)**: 58개 시계열 (자동 수집, 일/주/월/분기별)
- **Yahoo Finance**: 반도체 섹터 주가·지수 13종 (자동 수집, 일별)
- **수동 입력**: WSTS 반도체 매출 (SIA 보도자료 기반, 2개월 후행)

---

## 2. 현재 모델 아키텍처

### 2.1 5차원 가중평균 구조

```
개별 지표 → Signal 생성 → 5개 차원 점수 → 가중평균 → Composite Score → Regime 판별
```

#### 차원별 비중 및 소속 지표

| 차원 | 비중 | 소속 지표 (개별 가중치) | 비중 설정 근거 |
|------|------|------------------------|----------------|
| **Demand Cycle** | 30% | DGORDER(1.2), ISM_MFG(1.3), RETAIL(0.8), CONSUMER_CONF(0.7), NFP(1.0), HOUSING(0.5), SOX(1.0), HYPERSCALER_CAPEX(1.5), HBM_PREMIUM(1.2), WSTS(0.5) | 반도체 매출의 80% 이상이 수요 사이클에 직접 연동 |
| **Supply Cycle** | 20% | INDPRO(1.0), EQUIP_PROXY(1.3), PRODUCTIVITY(0.8) | 공급 과잉/부족이 가격과 마진을 결정 |
| **Price Cycle** | 20% | DRAM_PROXY(1.3), NAND_PROXY(1.2), CPI(0.8), PPI(0.8) | DRAM/NAND 가격이 반도체 기업 실적에 직접 반영 |
| **Macro Regime** | 20% | GDP(1.0), YIELD_CURVE(1.2), FOMC(1.1), LEI(1.0), CLAIMS(0.7) | 금리·유동성 환경이 테크 밸류에이션의 할인율을 결정 |
| **Global Demand** | 10% | TRADE(1.0), CHINA_PMI(1.2) | 최대 소비국 중국의 경기가 지표이나, 수출규제로 직접 영향 제한 |

### 2.2 점수 산출 공식

```
1단계: Signal 생성
   - 각 지표의 시계열 데이터에서 추세, 임계값, 이동평균 교차 등 분석
   - 결과: signal_type (bullish/bearish/neutral) + strength (0~1)

2단계: 개별 점수 변환
   - Bullish:  score = 50 + (strength × 50)  → 50~100
   - Bearish:  score = 50 - (strength × 50)  → 0~50
   - Neutral:  score = 50

3단계: 차원 점수
   - dim_score = Σ(indicator_score × indicator_weight) / Σ(indicator_weight)
   - 데이터 미확보 지표는 제외 (합산에서 빠짐)

4단계: 총점
   - total = Σ(dim_score × dim_weight) / Σ(사용된 dim_weight)
   - 모든 차원의 데이터가 0이면 50점 (중립)

5단계: Regime 판별
   - 65+ → Expansion
   - 50-65 → Late Cycle (Macro < 45 또는 Demand > 60 조건부)
   - 35-50 → Contraction 또는 Recovery (Demand > Macro일 때 Recovery)
   - 0-35 → Contraction 또는 Recovery (Price > 45일 때 Recovery)
```

### 2.3 지표 분류: 선행 / 동행 / 후행

| 유형 | Lead Time | 지표 |
|------|-----------|------|
| **선행 (Leading)** | 2~18개월 | ISM 신규주문(2-3m), 수율곡선(12-18m), LEI(6-9m), 내구재주문(1-2m), 건축허가(3-6m), 장비주 Proxy(1-3m), HBM Premium(1-3m) |
| **동행 (Coincident)** | 실시간 | 산업생산, 소매판매, SOX 지수, DRAM/NAND Proxy, 실업수당, 소비자심리, FOMC, 중국 PMI |
| **후행 (Lagging)** | 이미 지나간 것 | GDP(30일+), CPI(13일), PPI(15일), 고용(3일), 무역수지(35일), WSTS(60일), 생산성(35일), CapEx(45일) |

---

## 3. 현재 모델의 한계 및 개선 필요 사항

### 3.1 예측력 vs 진단력

**핵심 질문: 이 모델은 미래를 예측하는가, 아니면 현재를 설명하는가?**

현재 모델은 선행·동행·후행 지표를 **동일한 가중평균** 방식으로 합산합니다. 이는 다음과 같은 결과를 낳습니다:

- ✅ **현재 사이클 위치 진단**에는 정확함 (모든 유형의 데이터를 종합하므로)
- ❌ **미래 사이클 전환 예측**에는 부적합 (후행지표가 선행지표의 신호를 희석시킴)

**예시**: ISM 신규주문이 급락(선행 bearish)해도, GDP와 고용이 아직 견조(후행 bullish)하면, 총점이 중간에서 머물러 경고 신호가 약해집니다. 실제로는 3-6개월 후 다운사이클이 시작될 수 있지만, 모델은 이를 포착하지 못합니다.

### 3.2 고정 비중 vs 동적 비중

사이클 단계별로 중요한 지표가 달라야 합니다:

| 사이클 단계 | 더 중요해야 할 것 | 현재 반영 여부 |
|-------------|-------------------|----------------|
| **Recovery** | 선행지표(신규주문, 수율곡선 정상화), 가격 바닥 반등 | ❌ 미반영 |
| **Expansion** | 수요 지속성, 공급 병목, 가격 상승 모멘텀 | ❌ 미반영 |
| **Late Cycle** | 경고 신호(재고 축적, 금리 인상), 매크로 건전성 | ⚠️ 일부 반영 (교차검증) |
| **Contraction** | 바닥 신호(재고 소진, 감산 효과), 글로벌 수요 회복 | ❌ 미반영 |

### 3.3 Coverage 부재 처리

현재 데이터가 없는 지표는 합산에서 **제외**됩니다 (가중합의 분모에서 빠짐). 이는 해당 차원의 점수가 소수 지표에 의존하게 만들어, 데이터 가용 지표의 방향성에 과도하게 편향될 수 있습니다.

### 3.4 시나리오 확률의 정적 설정

What-if 시나리오의 Delta 값이 고정되어 있어, 현재 경제 상황에 따른 동적 조정이 이루어지지 않습니다.

---

## 4. 구체적 질문 목록

아래 질문들에 대해 학술적 근거와 실무적 경험을 바탕으로 답변해 주세요.

### A. 모델 구조

1. **선행/동행/후행 지표를 하나의 가중평균으로 합산하는 것이 적절한가?** 별도의 "Leading Score"와 "Coincident Score"를 분리하여 표시하는 것이 사용자에게 더 유용하지 않은가?

2. **각 차원의 비중(30/20/20/20/10%)에 학술적 또는 실증적 근거가 있는가?** 반도체 산업에 특화된 최적의 비중 배분은 어떻게 결정할 수 있는가?

3. **사이클 단계별로 차원 비중을 동적으로 조정한다면, 각 단계에서 적절한 비중 배분은 무엇인가?** 예: Recovery기에는 Leading 지표 비중을 2배로 올리는 것이 합리적인가?

### B. 예측력 향상

4. **현재 모델의 예측력을 검증하려면 어떤 백테스팅 방법론을 사용해야 하는가?** Rolling window, out-of-sample 테스트 등 구체적 절차를 제안해 주세요.

5. **선행지표만으로 구성된 "Predictive Score"를 만든다면, 어떤 지표 조합과 가중치가 최적인가?**

6. **각 지표의 "lead time"이 사이클 단계에 따라 달라지는가?** 예: 수율곡선의 선행 기간이 Expansion기 vs Contraction기에 다를 수 있는가?

### C. 점수 산출 로직

7. **Signal의 strength 값을 선형으로 점수에 반영하는 것(50 ± strength×50)이 최적인가?** 비선형 변환(로그, 시그모이드 등)이 더 적절할 수 있는가?

8. **데이터 미확보 지표를 합산에서 제외하는 현재 방식의 문제점은 무엇인가?** Multiple imputation이나 Bayesian 접근이 더 나은 대안인가?

### D. 반도체 산업 특화

9. **반도체 사이클의 평균 기간(trough-to-trough)과 현재 사이클의 위치를 판단하는 데 가장 신뢰할 수 있는 단일 지표는 무엇인가?**

10. **AI/HBM이라는 구조적 변화가 전통적 반도체 사이클의 패턴을 어떻게 변형시키고 있으며, 이를 모델에 반영하려면 어떤 조정이 필요한가?**

---

## 5. 참고: 현재 시스템 기술 스택

| 항목 | 기술 |
|------|------|
| Backend | Python 3.12 + FastAPI |
| Database | SQLite (Railway Volume 영구 저장) |
| Frontend | HTML/JS + Chart.js |
| Data | FRED API + Yahoo Finance (자동 수집) |
| AI Advisory | Google Gemini / OpenAI / Anthropic (선택) |
| Deployment | Railway (GitHub 연동 자동 배포) |
| Automation | APScheduler (평일 18:30 자동 수집·분석) |

---

## 6. 요청 사항

위 내용을 검토한 후, 다음 형식으로 피드백 부탁드립니다:

1. **모델 구조 평가**: 현재 5차원 가중평균 방식의 장단점
2. **우선순위 개선 제안**: 가장 효과적인 1~3가지 개선안 (구현 난이도 포함)
3. **구체적 수치 제안**: 동적 비중, 선행지표 가중치 등의 목표값
4. **백테스트 설계**: 예측력 검증을 위한 구체적 절차
5. **학술적 참고문헌**: 관련 논문이나 방법론

---

*이 문서는 Semi-Intel v3.1 기준으로 작성되었습니다. (2026-04-05)*
