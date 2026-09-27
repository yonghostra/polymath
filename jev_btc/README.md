# Jev BTC 10초 방향 예측 실험 (MVP)

**목적:** 현재 시장 상태를 Jev에게 입력하면, BTCUSDT의 10초 뒤 가격 방향을 랜덤보다 유의미하게 잘 맞히는지 검증합니다.

> ⚠️ 이 프로그램은 **주문을 보내지 않습니다.** Binance는 공개 시장 데이터만 받으므로 Binance API key도 필요 없습니다.

## 폴더 구조

```
jev_btc/
  main.py                 실행 진입점 (collect / predict / label / report / export / jev-test)
  config.py               모든 설정 (.env에서 읽음)
  .env.example            설정 예시 → .env로 복사해서 사용
  requirements.txt
  market/
    binance_ws.py         Binance WebSocket 수집 + 자동 재접속, open interest 조회
    feature_engine.py     1초마다 feature 계산
  jev/
    client.py             Jev API adapter (API 형식은 이 파일에만 있음) + Mock
    predictor.py          Jev에게 보낼 JSON/질문 생성, 비교용 기준선(baseline)
  storage/
    database.py           SQLite 저장 + 10초 뒤 결과 labeling
  evaluation/
    evaluator.py          정확도 / precision / recall / p-value / 비용 리포트
  tests/test_pipeline.py  오프라인 테스트 (인터넷 불필요)
  data/                   DB·로그 저장 위치 (git에 올라가지 않음)
```

## 설치 (처음 한 번만)

Python 3.10 이상이 필요합니다.

```bash
cd jev_btc
python -m venv .venv
# Mac/Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
```

`.env`를 열어서 `JEV_API_KEY=` 뒤에 키를 붙여 넣습니다.

## 실행 순서 (추천)

**1) Jev API 형식 확인 (필수, 1회, 비용 거의 0)**
```bash
python main.py jev-test
```
Jev가 보낸 원본 응답(RAW RESPONSE)과 해석 결과(PARSED)를 출력합니다.
`FAILED`가 나오면 응답 형식이 코드와 다른 것입니다. 그러면 `jev/client.py`만 고치면 됩니다. 이때 출력된 내용을 저에게 보여주세요.

**2) Phase 1: 데이터만 수집 (Jev 호출 없음, 무료)**
```bash
python main.py collect
```
1초마다 feature를 `data/jev_btc.db`에 저장합니다. 끄려면 Ctrl+C를 누르세요.

**3) Phase 2+3: Jev 예측 + 10초 뒤 결과 자동 기록**
```bash
python main.py predict
```
처음 30초는 준비 시간(warm-up)이라 예측을 하지 않습니다.
키 없이 흐름만 먼저 보고 싶으면 `.env`에서 `JEV_MOCK=1`로 설정하세요. 랜덤 예측이라 정확도가 약 50%로 나와야 정상입니다.

**4) 결과 리포트**
```bash
python main.py report              # 전체
python main.py report --run <run_id>   # 특정 실행만 (run_id는 화면 상단에 표시됨)
```

**기타**
```bash
python main.py label    # FLAT_THRESHOLD / HORIZON_SEC를 바꾼 뒤 과거 데이터 결과를 다시 계산
python main.py export   # 모든 테이블을 data/csv/*.csv로 저장 (엑셀에서 열기)
python -m pytest tests -q   # 오프라인 테스트 (pip install pytest 필요)
```

## 리포트 읽는 법

| 항목 | 의미 |
|---|---|
| `acc` | 방향 정확도. FLAT(움직임이 threshold보다 작음)은 제외 |
| `p-val` | "사실은 50% 동전 던지기"일 확률. **0.05 미만이어야 우연이 아니라고 볼 수 있음** |
| `Base rate UP` | 무조건 UP이라고 찍었을 때의 정확도. Jev가 이것보다 높아야 의미가 있음 |
| `Spearman` | P(up)가 높을수록 실제 수익률도 높은지를 나타내는 값 (0보다 크면 좋음) |
| `sgnRet` | 예측한 방향으로 거래했을 때의 평균 수익(bps). **아직 수수료를 빼기 전 값**이며, 수수료 반영은 Phase 5에서 함 |
| `base:*` | 무료 기준선. **같은 초(second)** 에서 비교함 |

`base:*` 기준선은 네 가지입니다.
- `momentum`: 최근 10초에 오른 방향으로 계속 간다
- `reversal`: 반대로 되돌아간다
- `obi`: 호가 매수 잔량이 많으면 오른다
- `flow`: 시장가 매수가 많으면 오른다

**Jev가 이 기준선들보다 나아야 "Jev만의 alpha"가 있다고 볼 수 있습니다.**

## 주요 설정 (.env)

| 설정 | 기본값 | 설명 |
|---|---|---|
| `PREDICT_EVERY_SEC` | 1 | 예측 주기(초). 2나 5로 바꾸면 비용과 성능을 비교할 수 있음. 실행마다 따로 기록됨 |
| `FLAT_THRESHOLD` | 0.0002 | 0.02%. 10초 수익률의 절댓값이 이보다 작으면 FLAT으로 봄 |
| `HORIZON_SEC` | 10 | 몇 초 뒤를 맞힐지 |
| `PRICE_SOURCE` | mid | 기준 가격. mid=(bid+ask)/2 (추천), last=마지막 체결가 |
| `HIGH_CONF_PROB` | 0.80 | P(up)가 0.8 이상이거나 0.2 이하면 "고확신"으로 분류 |
| `JEV_MAX_CALLS_PER_SEC` | 5 | Jev 호출 속도 제한 |
| `JEV_COST_PER_M_INPUT` | 0.042 | 입력 토큰 100만 개당 비용(USD). **공식 가격을 확인해서 넣으세요** |

## 장애 처리

- **Binance 연결 끊김**: 자동으로 다시 접속합니다. 1초에서 시작해 최대 30초까지 대기 시간을 늘려 가며 재시도합니다. 10초 동안 데이터가 안 오면 끊긴 것으로 판단합니다.
- **데이터 누락**: 호가 데이터가 5초보다 오래되면 그 초는 저장하지 않습니다. 10초 뒤 가격이 없는 예측은 `NA`로 표시하고 통계에서 제외합니다. 다른 시점의 가격으로 대신 채우지 않습니다.
- **Jev 오류**: 시간 초과, 429(요청 과다), 5xx(서버 오류)는 1회 재시도합니다. 4xx 오류와 잘못된 형식의 응답은 그 초만 건너뜁니다. 어떤 경우에도 프로그램은 계속 실행되고, 오류는 모두 `api_calls` 테이블에 기록됩니다.
- **중복 timestamp**: 같은 초의 데이터는 한 번만 저장합니다.
- **종료(Ctrl+C)**: 진행 중인 Jev 호출을 기다린 뒤, 마지막 결과를 기록하고 DB를 닫습니다.
- 자세한 로그는 `data/app.log`에 남습니다.

## Jev API 관련 확인 필요 사항 (TODO)

`jev/client.py` 상단에 적어 둔 API 형식은 TypeSafe AI가 공개한 예시를 기준으로 작성했습니다.

- 엔드포인트: `POST https://api.typesafe.ai/v1/systemone`
- 인증: `Authorization: Bearer <키>`
- 요청: `state` + `questions` (question type: `choice`)

개발 환경에서는 공식 문서(docs.typesafe.ai)에 접속할 수 없었습니다. **장시간 실행 전에 `python main.py jev-test`로 꼭 확인하세요.**

## 다음 단계

- Phase 4: 확률 구간별(0.5–0.6, 0.6–0.7 …) 분석 + 차트 (`evaluation/charts.py`)
- Phase 5: 수수료·spread·slippage를 반영한 paper trading (`evaluation/backtest.py`)
