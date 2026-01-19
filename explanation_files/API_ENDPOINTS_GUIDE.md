# API 엔드포인트 동작 방식 가이드

## 목차

1. [POST /update-prices](#1-post-update-prices)
2. [POST /sync-stocks-name](#2-post-sync-stocks-name)
3. [GET /stocks-name/{symbol}](#3-get-stocks-namesymbol)
4. [POST /sync-exchange-rates](#4-post-sync-exchange-rates)
5. [GET /exchange-rates/{symbol_or_name}](#5-get-exchange-ratessymbol_or_name)
6. [GET /exchange-rates/{symbol_or_name}/history](#6-get-exchange-ratessymbol_or_namehistory)

---

## 1. POST /update-prices

### 목적
주식 가격을 Yahoo Finance API에서 수집하여 Supabase에 저장합니다.

### 인증
**필수**: Bearer Token (`Authorization: Bearer YOUR_CRON_SECRET`)

### 요청 형식

```http
POST /update-prices
Authorization: Bearer YOUR_CRON_SECRET
Content-Type: application/json

{
  "symbols": ["AAPL", "MSFT"],  // 선택사항
  "country": "US"               // 선택사항
}
```

**요청 본문이 비어있거나 없으면**: DB의 `managed_stocks` 테이블에서 활성화된 종목을 자동 조회

### 동작 과정

```
[1단계: 요청 수신]
POST /update-prices
    ├─ 인증 확인 (Bearer Token)
    └─ 요청 본문 파싱
    ↓
[2단계: 심볼 목록 결정]
determine_symbols()
    ├─ Request Body의 symbols가 있으면 → 사용
    ├─ 없으면 환경변수 STOCK_SYMBOLS 확인
    └─ 없으면 DB (managed_stocks) 조회
       └─ SELECT symbol, country
          FROM managed_stocks
          WHERE enabled = true
    ↓
[3단계: 중복 제거 (N+1 문제 방지)]
filter_symbols_to_fetch()
    ├─ 모든 심볼의 오늘 날짜 데이터를 한 번에 조회
    │  └─ SELECT * FROM stock_prices
    │     WHERE date = '2025-01-15'
    │       AND symbol IN ('AAPL', 'MSFT', ...)
    │
    └─ 메모리에서 비교
       └─ 수집할 심볼 = 전체 심볼 - 이미 있는 심볼
    ↓
[4단계: 각 심볼별 처리 (순차)]
for each symbol in stocks_to_fetch:
    ├─ Yahoo Finance API 호출
    │  ├─ Rate Limiter 적용 (200ms 간격)
    │  ├─ 재시도 로직 (최대 3회)
    │  └─ yf.Ticker(symbol).info
    │
    ├─ 데이터 검증
    │
    └─ Supabase에 저장
       └─ stock_prices 테이블에 upsert
          └─ ON CONFLICT (symbol, date) DO UPDATE
    ↓
[5단계: 응답 반환]
{
  "success": true,
  "total": 100,
  "successCount": 98,
  "failureCount": 2,
  "results": [
    {"symbol": "AAPL", "success": true},
    {"symbol": "INVALID", "success": false, "error": "Symbol not found"}
  ]
}
```

### 성능 최적화

1. **N+1 문제 방지**: 모든 심볼의 오늘 날짜 데이터를 한 번에 조회
2. **중복 제거**: 이미 있는 데이터는 API 호출하지 않음
3. **실패 격리**: 한 종목 실패가 전체를 중단시키지 않음
4. **Rate Limiting**: 최소 200ms 간격으로 요청

### 예시

**요청**:
```bash
curl -X POST http://localhost:8080/update-prices \
  -H "Authorization: Bearer YOUR_CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL", "MSFT"]}'
```

**응답**:
```json
{
  "success": true,
  "total": 2,
  "successCount": 2,
  "failureCount": 0,
  "results": [
    {"symbol": "AAPL", "success": true},
    {"symbol": "MSFT", "success": true}
  ]
}
```

---

## 2. POST /sync-stocks-name

### 목적
FDR StockListing API에서 종목 목록을 수집하여 `stock_names` 테이블에 동기화합니다.

### 인증
**필수**: Bearer Token

### 요청 형식

```http
POST /sync-stocks-name
Authorization: Bearer YOUR_CRON_SECRET
Content-Type: application/json

{
  "markets": ["KRX", "NASDAQ"]  // 선택사항
}
```

**markets를 지정하지 않으면**: 기본값 사용
- `KRX` (한국 주식)
- `ETF/KR` (한국 ETF)
- `S&P500` (미국 S&P500)
- `NASDAQ` (나스닥)
- `NYSE` (뉴욕증권거래소)
- `AMEX` (아멕스)

### 동작 과정

```
[1단계: 요청 수신]
POST /sync-stocks-name
    ├─ 인증 확인
    └─ markets 파라미터 확인
    ↓
[2단계: 시장별 병렬 수집]
sync_stock_names()
    ├─ 각 시장별로 병렬 처리
    │  └─ asyncio.gather()
    │
    └─ fetch_and_normalize_market(market)
       └─ FDR StockListing API 호출
          └─ fdr.StockListing(market)
    ↓
[3단계: 중복 제거]
    └─ symbol 기준으로 중복 제거
       └─ 마지막 값 우선
    ↓
[4단계: 국가별 그룹핑]
_partition_by_country()
    └─ country별로 그룹핑
       ├─ KR 그룹
       ├─ US 그룹
       └─ None 그룹
    ↓
[5단계: 각 국가별 처리]
for each country:
    ├─ 신규/갱신: upsert_stock_names()
    │  └─ stock_names 테이블에 upsert
    │     └─ is_active = true
    │
    └─ 누락 비활성화
       ├─ 기존 활성 심볼 조회
       ├─ 현재 수집된 심볼과 비교
       └─ 누락된 심볼은 is_active = false
    ↓
[6단계: 응답 반환]
{
  "success": true,
  "markets": ["KRX", "NASDAQ"],
  "uniqueSymbols": 5000,
  "upserted": 5000,
  "deactivated": 10,
  "errors": []
}
```

### 특징

- **병렬 처리**: 여러 시장을 동시에 수집
- **자동 비활성화**: 더 이상 존재하지 않는 종목은 자동으로 비활성화
- **중복 제거**: 같은 심볼이 여러 시장에 있어도 하나만 저장

### 예시

**요청**:
```bash
curl -X POST http://localhost:8080/sync-stocks-name \
  -H "Authorization: Bearer YOUR_CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"markets": ["KRX", "NASDAQ"]}'
```

**응답**:
```json
{
  "success": true,
  "markets": ["KRX", "NASDAQ"],
  "uniqueSymbols": 5000,
  "upserted": 5000,
  "deactivated": 10,
  "errors": []
}
```

---

## 3. GET /stocks-name/{symbol}

### 목적
특정 심볼의 종목 정보(이름, 국가, 소스 등)를 조회합니다. 필요한 필드만 선택적으로 조회할 수 있습니다.

### 인증
**불필요** (공개 API)

### 요청 형식

```http
GET /stocks-name/{symbol}?fields={field1},{field2}
```

**Query Parameters**:
- `fields` (선택사항): 조회할 필드 목록을 쉼표로 구분
  - 지정하지 않으면 모든 필드 반환
  - 예: `?fields=name`, `?fields=country`, `?fields=name,country`
  - `symbol`은 항상 포함됩니다 (식별자이므로 필수)

**예시**:
- `GET /stocks-name/AAPL` - 모든 필드 조회
- `GET /stocks-name/AAPL?fields=name` - name 필드만 조회
- `GET /stocks-name/AAPL?fields=country` - country 필드만 조회
- `GET /stocks-name/AAPL?fields=name,country` - name과 country 필드만 조회
- `GET /stocks-name/005930` - 모든 필드 조회

### 동작 과정

```
[1단계: 요청 수신]
GET /stocks-name/AAPL?fields=name,country
    ↓
[2단계: 필드 파싱]
fields = ["name", "country"]
    ↓
[3단계: Supabase 조회]
get_stock_name_by_symbol("AAPL", fields=["name", "country"])
    └─ SELECT symbol, name, country
       FROM stock_names
       WHERE symbol = 'AAPL'
       LIMIT 1
    ↓
[4단계: 응답 반환]
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "country": "US"
}
```

**fields 파라미터 없을 경우**:
```
[1단계: 요청 수신]
GET /stocks-name/AAPL
    ↓
[2단계: Supabase 조회]
get_stock_name_by_symbol("AAPL", fields=None)
    └─ SELECT *
       FROM stock_names
       WHERE symbol = 'AAPL'
       LIMIT 1
    ↓
[3단계: 응답 반환]
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "country": "US",
  "source": "FDR",
  "is_active": true,
  "asset_type": "STOCK",
  "currency": "USD"
}
```

### 특징

- **빠른 조회**: symbol unique 인덱스로 즉시 조회
- **메타데이터 제공**: 종목명, 국가, 통화 등 정보 제공
- **활성 상태 확인**: `is_active`로 수집 대상 여부 확인
- **필드 선택 조회**: `fields` 파라미터로 필요한 필드만 조회 가능 (네트워크 트래픽 최적화)
- **항상 symbol 포함**: `symbol`은 식별자이므로 항상 응답에 포함됩니다

### 예시

**모든 필드 조회**:
```bash
curl http://localhost:8080/stocks-name/AAPL
```

**name 필드만 조회**:
```bash
curl "http://localhost:8080/stocks-name/AAPL?fields=name"
```

**country 필드만 조회**:
```bash
curl "http://localhost:8080/stocks-name/AAPL?fields=country"
```

**name과 country 필드만 조회**:
```bash
curl "http://localhost:8080/stocks-name/AAPL?fields=name,country"
```

**응답 (fields=name,country)**:
```json
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "country": "US"
}
```

**응답 (fields 없음 - 모든 필드)**:
```json
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "country": "US",
  "source": "FDR",
  "is_active": true,
  "asset_type": "STOCK",
  "currency": "USD"
}
```

**심볼이 없을 경우**:
```json
{
  "detail": "Symbol 'INVALID' not found in stock_names"
}
```
(HTTP 404)

---

## 4. POST /sync-exchange-rates

### 목적
FDR DataReader를 통해 환율, 암호화폐, 인덱스 데이터를 수집하여 `exchange_rates` 테이블에 저장합니다.

### 인증
**필수**: Bearer Token

### 요청 형식

```http
POST /sync-exchange-rates
Authorization: Bearer YOUR_CRON_SECRET
Content-Type: application/json

{
  "symbols": ["USD/KRW", "^NYICDX"]  // 선택사항
}
```

**symbols를 지정하지 않으면**: DB에서 활성화된 환율/인덱스 심볼을 자동 조회
- `stock_names` 테이블에서 `asset_type IN ('FX', 'CRYPTO', 'INDEX')`이고 `is_active = true`인 심볼

### 동작 과정

```
[1단계: 요청 수신]
POST /sync-exchange-rates
    ├─ 인증 확인
    └─ symbols 파라미터 확인
    ↓
[2단계: 심볼 목록 결정]
sync_exchange_rates()
    ├─ Request Body의 symbols가 있으면 → 사용
    └─ 없으면 DB에서 조회
       └─ get_active_exchange_rate_symbols()
          └─ SELECT symbol
             FROM stock_names
             WHERE asset_type IN ('FX', 'CRYPTO', 'INDEX')
               AND is_active = true
    ↓
[3단계: 심볼 변환]
    └─ 한국어 이름을 심볼로 변환
       └─ resolve_symbol("원달러환율") → "USD/KRW"
    ↓
[4단계: 각 심볼별 병렬 처리]
asyncio.gather()로 모든 심볼 동시 처리
    │
    └─ process_symbol(symbol)
       ├─ [4-1] 최근 날짜 조회 (증분 수집)
       │  └─ get_max_date(symbol)
       │     └─ SELECT MAX(date)
       │        FROM exchange_rates
       │        WHERE symbol = 'USD/KRW'
       │     → 예: "2025-01-14"
       │
       ├─ [4-2] FDR DataReader 호출
       │  └─ fetch_exchange_rate_data(symbol, last_date)
       │     ├─ Rate Limiter 적용
       │     └─ fdr.DataReader("USD/KRW", start="2025-01-14")
       │        → DataFrame 반환 (2025-01-14 이후 데이터만)
       │
       ├─ [4-3] 데이터 정규화
       │  └─ normalize_exchange_rate_data(symbol, df)
       │     ├─ get_symbol_metadata(symbol) → 메타데이터 조회
       │     │  └─ name, currency 조회
       │     │
       │     └─ DataFrame → 레코드 리스트 변환
       │        [
       │          {
       │            "symbol": "USD/KRW",
       │            "date": "2025-01-15",
       │            "close_price": 1320.50,
       │            "adj_close_price": 1320.50,
       │            "currency": "KRW",
       │            "name": "원달러환율"
       │          },
       │          ...
       │        ]
       │
       └─ [4-4] Supabase에 저장
          └─ upsert_exchange_rates(records)
             └─ exchange_rates 테이블에 upsert
                └─ ON CONFLICT (symbol, date) DO UPDATE
    ↓
[5단계: 응답 반환]
{
  "success": true,
  "symbols": ["USD/KRW", "^NYICDX"],
  "upserted": 150,
  "errors": []
}
```

### 특징

- **증분 수집**: 최신 데이터만 수집하여 효율적
- **병렬 처리**: 여러 심볼을 동시에 처리
- **한국어 이름 지원**: "원달러환율" 같은 이름으로도 요청 가능
- **자동 심볼 조회**: symbols를 지정하지 않으면 DB에서 자동 조회

### 예시

**요청** (심볼 지정):
```bash
curl -X POST http://localhost:8080/sync-exchange-rates \
  -H "Authorization: Bearer YOUR_CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["USD/KRW", "원달러환율"]}'
```

**요청** (자동 조회):
```bash
curl -X POST http://localhost:8080/sync-exchange-rates \
  -H "Authorization: Bearer YOUR_CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**응답**:
```json
{
  "success": true,
  "symbols": ["USD/KRW", "^NYICDX", "BTC/KRW", "BTC/USD"],
  "upserted": 150,
  "errors": []
}
```

---

## 5. GET /exchange-rates/{symbol_or_name}

### 목적
환율/인덱스의 최신 데이터 또는 특정 날짜 데이터를 조회합니다.

### 인증
**불필요** (공개 API)

### 요청 형식

```http
GET /exchange-rates/{symbol_or_name}?date=2025-01-15
```

**파라미터**:
- `{symbol_or_name}`: 심볼 또는 한국어 이름
  - 예: `USD/KRW`, `원달러환율`, `^NYICDX`, `달러인덱스`
- `date` (선택사항): 특정 날짜 조회
  - 없으면: 최신 데이터 조회

### 동작 과정

```
[1단계: 요청 수신]
GET /exchange-rates/원달러환율
    ↓
[2단계: 심볼 변환]
resolve_symbol("원달러환율")
    └─ SYMBOL_CACHE에서 조회
       └─ "원달러환율" → "USD/KRW"
    ↓
[3단계: Supabase 조회]
get_exchange_rate("USD/KRW", date=None)
    └─ date가 없으면 최신 데이터 조회
       └─ SELECT *
          FROM exchange_rates
          WHERE symbol = 'USD/KRW'
          ORDER BY date DESC
          LIMIT 1
    ↓
[4단계: 응답 반환]
{
  "symbol": "USD/KRW",
  "date": "2025-01-15",
  "close_price": 1320.50,
  "adj_close_price": 1320.50,
  "currency": "KRW",
  "name": "원달러환율"
}
```

### 특징

- **한국어 이름 지원**: "원달러환율" 같은 이름으로 조회 가능
- **메모리 캐시**: 심볼 변환 시 DB 조회 없이 즉시 반환
- **최신 데이터**: date 파라미터 없으면 자동으로 최신 데이터 반환

### 예시

**최신 데이터 조회**:
```bash
curl http://localhost:8080/exchange-rates/원달러환율
```

**특정 날짜 조회**:
```bash
curl "http://localhost:8080/exchange-rates/USD/KRW?date=2025-01-15"
```

**응답**:
```json
{
  "symbol": "USD/KRW",
  "date": "2025-01-15",
  "close_price": 1320.50,
  "adj_close_price": 1320.50,
  "currency": "KRW",
  "name": "원달러환율"
}
```

**데이터가 없을 경우**:
```json
{
  "detail": "Symbol 'INVALID' (resolved: 'INVALID') not found in exchange_rates"
}
```
(HTTP 404)

---

## 6. GET /exchange-rates/{symbol_or_name}/history

### 목적
환율/인덱스의 시계열 데이터를 조회합니다. (차트 표시용)

### 인증
**불필요** (공개 API)

### 요청 형식

```http
GET /exchange-rates/{symbol_or_name}/history?start_date=2025-01-01&end_date=2025-01-15
```

**파라미터**:
- `{symbol_or_name}`: 심볼 또는 한국어 이름
- `start_date` (필수): 시작 날짜 (YYYY-MM-DD)
- `end_date` (필수): 종료 날짜 (YYYY-MM-DD)

### 동작 과정

```
[1단계: 요청 수신]
GET /exchange-rates/원달러환율/history?start_date=2025-01-01&end_date=2025-01-15
    ↓
[2단계: 심볼 변환]
resolve_symbol("원달러환율")
    └─ "원달러환율" → "USD/KRW"
    ↓
[3단계: Supabase 조회]
get_exchange_rate_history("USD/KRW", "2025-01-01", "2025-01-15")
    └─ SELECT *
       FROM exchange_rates
       WHERE symbol = 'USD/KRW'
         AND date >= '2025-01-01'
         AND date <= '2025-01-15'
       ORDER BY date ASC
    ↓
[4단계: 응답 반환]
{
  "symbol": "USD/KRW",
  "start_date": "2025-01-01",
  "end_date": "2025-01-15",
  "data": [
    {
      "symbol": "USD/KRW",
      "date": "2025-01-01",
      "close_price": 1310.00,
      "adj_close_price": 1310.00,
      "currency": "KRW",
      "name": "원달러환율"
    },
    {
      "symbol": "USD/KRW",
      "date": "2025-01-02",
      "close_price": 1311.50,
      "adj_close_price": 1311.50,
      "currency": "KRW",
      "name": "원달러환율"
    },
    ...
  ]
}
```

### 특징

- **기간별 조회**: 시작일과 종료일 사이의 모든 데이터 반환
- **정렬**: 날짜 오름차순으로 정렬 (차트 표시에 적합)
- **한국어 이름 지원**: "원달러환율" 같은 이름으로 조회 가능

### 예시

**요청**:
```bash
curl "http://localhost:8080/exchange-rates/원달러환율/history?start_date=2025-01-01&end_date=2025-01-15"
```

**응답**:
```json
{
  "symbol": "USD/KRW",
  "start_date": "2025-01-01",
  "end_date": "2025-01-15",
  "data": [
    {
      "symbol": "USD/KRW",
      "date": "2025-01-01",
      "close_price": 1310.00,
      "adj_close_price": 1310.00,
      "currency": "KRW",
      "name": "원달러환율"
    },
    {
      "symbol": "USD/KRW",
      "date": "2025-01-02",
      "close_price": 1311.50,
      "adj_close_price": 1311.50,
      "currency": "KRW",
      "name": "원달러환율"
    }
  ]
}
```

---

## 엔드포인트 비교표

| 엔드포인트 | 메서드 | 인증 | 목적 | 데이터 소스 | 저장 위치 |
|-----------|--------|------|------|------------|----------|
| `/update-prices` | POST | 필요 | 주식 가격 수집 | Yahoo Finance | `stock_prices` |
| `/sync-stocks-name` | POST | 필요 | 종목 목록 동기화 | FDR StockListing | `stock_names` |
| `/stocks-name/{symbol}` | GET | 불필요 | 종목 정보 조회 | Supabase | - |
| `/sync-exchange-rates` | POST | 필요 | 환율/인덱스 수집 | FDR DataReader | `exchange_rates` |
| `/exchange-rates/{symbol}` | GET | 불필요 | 환율/인덱스 조회 | Supabase | - |
| `/exchange-rates/{symbol}/history` | GET | 불필요 | 시계열 조회 | Supabase | - |

---

## 인증 구분

### 인증 필요 (관리자용)

- `POST /update-prices`
- `POST /sync-stocks-name`
- `POST /sync-exchange-rates`

**인증 방법**:
```http
Authorization: Bearer YOUR_CRON_SECRET
```

### 인증 불필요 (공개 API)

- `GET /health`
- `GET /stocks-name/{symbol}`
- `GET /exchange-rates/{symbol_or_name}`
- `GET /exchange-rates/{symbol_or_name}/history`

---

## 성능 최적화 포인트

### 1. N+1 문제 방지
- `/update-prices`: 모든 심볼의 오늘 날짜 데이터를 한 번에 조회
- `/sync-exchange-rates`: 병렬 처리로 여러 심볼 동시 수집

### 2. 증분 수집
- `/sync-exchange-rates`: 최신 데이터만 수집 (MAX(date) 기반)

### 3. 메모리 캐시
- 심볼 변환: DB 조회 없이 메모리에서 즉시 반환

### 4. Rate Limiting
- 외부 API 호출 시 최소 200ms 간격 유지

---

## 에러 처리

### 공통 에러 처리

1. **인증 실패** (401):
```json
{
  "detail": "Unauthorized"
}
```

2. **심볼 없음** (404):
```json
{
  "detail": "Symbol 'INVALID' not found"
}
```

3. **서버 오류** (500):
```json
{
  "detail": "배치 작업 중 오류가 발생했습니다: ..."
}
```

### 실패 격리

- `/update-prices`: 한 종목 실패가 다른 종목에 영향 없음
- `/sync-exchange-rates`: 한 심볼 실패가 다른 심볼에 영향 없음

---

## 실제 사용 시나리오

### 시나리오 1: 주식 가격 수집 (Cloud Scheduler)

```bash
# 매일 오전 7시 자동 실행
POST /update-prices
Body: {}
→ DB에서 활성 종목 자동 조회
→ Yahoo Finance에서 가격 수집
→ Supabase에 저장
```

### 시나리오 2: 환율 정보 표시 (프론트엔드)

```typescript
// 사용자가 환율 페이지 접속
GET /exchange-rates/원달러환율
→ 최신 환율 데이터 반환
→ 화면에 표시
```

### 시나리오 3: 환율 차트 표시 (프론트엔드)

```typescript
// 사용자가 차트 보기 클릭
GET /exchange-rates/원달러환율/history?start_date=2024-12-15&end_date=2025-01-15
→ 30일간의 시계열 데이터 반환
→ 차트로 표시
```

---

**문서 버전**: 1.0
**최종 업데이트**: 2025-01-15
**작성 목적**: 각 API 엔드포인트의 상세한 동작 방식을 단계별로 설명
