# Exchange Rate 기능 전체 프로세스 가이드

## 목차

1. [개요](#1-개요)
2. [전체 프로세스 개요](#2-전체-프로세스-개요)
3. [프로세스 1: 데이터 수집 및 저장](#3-프로세스-1-데이터-수집-및-저장)
4. [프로세스 2: 데이터 조회](#4-프로세스-2-데이터-조회)
5. [프로세스 3: 심볼 관리](#5-프로세스-3-심볼-관리)
6. [심볼 변환 메커니즘](#6-심볼-변환-메커니즘)
7. [증분 수집 최적화](#7-증분-수집-최적화)
8. [실제 사용 예시](#8-실제-사용-예시)

---

## 1. 개요

Exchange Rate 기능은 **환율, 암호화폐, 인덱스** 데이터를 수집하고 조회하는 시스템입니다.

### 지원하는 데이터 타입

- **FX (환율)**: USD/KRW (원달러환율)
- **CRYPTO (암호화폐)**: BTC/KRW, BTC/USD
- **INDEX (인덱스)**: ^NYICDX (달러인덱스)

### 주요 기능

1. **데이터 수집**: FDR (FinanceDataReader)에서 데이터 수집
2. **데이터 저장**: Supabase `exchange_rates` 테이블에 저장
3. **데이터 조회**: API를 통해 조회 (한국어 이름 지원)
4. **증분 수집**: 최신 데이터만 수집하여 효율성 향상

---

## 2. 전체 프로세스 개요

```
┌─────────────────────────────────────────────────────────────┐
│              Exchange Rate 전체 프로세스                     │
└─────────────────────────────────────────────────────────────┘

[초기 설정]
┌──────────────┐
│ stock_names  │ ← 심볼 메타데이터 저장
│ 테이블       │   (USD/KRW, 원달러환율, KRW, FX)
└──────┬───────┘
       │
       │ 서버 시작 시
       ▼
┌──────────────┐
│ SYMBOL_CACHE │ ← 메모리 캐시 로드
│ (메모리)     │   {"원달러환율": "USD/KRW", ...}
└──────────────┘

[데이터 수집 프로세스]
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ Cloud        │─────▶│ POST         │─────▶│ 백엔드       │
│ Scheduler    │      │ /sync-       │      │ 처리         │
│ (정기 실행)  │      │ exchange-    │      │              │
│              │      │ rates        │      │              │
└──────────────┘      └──────────────┘      └──────┬───────┘
                                                    │
                                                    ▼
                                           ┌──────────────┐
                                           │ FDR          │
                                           │ DataReader   │
                                           └──────┬───────┘
                                                  │
                                                  ▼
                                           ┌──────────────┐
                                           │ Supabase     │
                                           │ exchange_rates│
                                           │ 테이블 저장  │
                                           └──────────────┘

[데이터 조회 프로세스]
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ 프론트엔드   │─────▶│ GET          │─────▶│ 백엔드       │
│ 또는 외부    │      │ /exchange-   │      │ API          │
│ 시스템       │      │ rates/원달러 │      │              │
│              │      │ 환율         │      │              │
└──────────────┘      └──────────────┘      └──────┬───────┘
                                                    │
                                                    ▼
                                           ┌──────────────┐
                                           │ SYMBOL_CACHE │
                                           │ 변환:        │
                                           │ "원달러환율"  │
                                           │ → "USD/KRW"  │
                                           └──────┬───────┘
                                                  │
                                                  ▼
                                           ┌──────────────┐
                                           │ Supabase     │
                                           │ exchange_rates│
                                           │ 테이블 조회  │
                                           └──────┬───────┘
                                                  │
                                                  ▼
                                           ┌──────────────┐
                                           │ JSON 응답    │
                                           │ 반환         │
                                           └──────────────┘
```

---

## 3. 프로세스 1: 데이터 수집 및 저장

### 3.1. 전체 흐름

```
[트리거]
Cloud Scheduler 또는 수동 호출
    ↓
POST /sync-exchange-rates
    ├─ 인증: Bearer Token (CRON_SECRET)
    └─ 요청 본문: {"symbols": ["USD/KRW", "^NYICDX"]} (선택)
    ↓
[1단계: 심볼 목록 결정]
    ├─ Request Body에 symbols가 있으면 → 사용
    └─ 없으면 → DB에서 조회
       └─ get_active_exchange_rate_symbols()
          └─ stock_names 테이블 조회
             └─ WHERE asset_type IN ('FX', 'CRYPTO', 'INDEX')
                AND is_active = true
    ↓
[2단계: 심볼 변환]
    └─ resolve_symbol() → 한국어 이름을 심볼로 변환
       └─ SYMBOL_CACHE에서 조회
          예: "원달러환율" → "USD/KRW"
    ↓
[3단계: 각 심볼별 병렬 처리]
    └─ asyncio.gather()로 모든 심볼 병렬 처리
       │
       └─ 각 심볼별 process_symbol()
          │
          ├─ [3-1] 최근 날짜 조회
          │  └─ get_max_date(symbol)
          │     └─ exchange_rates 테이블에서
          │        SELECT MAX(date) WHERE symbol = 'USD/KRW'
          │        → 예: "2025-01-14"
          │
          ├─ [3-2] FDR DataReader 호출
          │  └─ fetch_exchange_rate_data(symbol, last_date)
          │     ├─ Rate Limiter 적용 (200ms 간격)
          │     └─ fdr.DataReader("USD/KRW", start="2025-01-14")
          │        → DataFrame 반환
          │
          ├─ [3-3] 데이터 정규화
          │  └─ normalize_exchange_rate_data(symbol, df)
          │     ├─ get_symbol_metadata(symbol) → 메타데이터 조회
          │     │  └─ stock_names 테이블에서 name, currency 조회
          │     │
          │     ├─ DataFrame → 레코드 리스트 변환
          │     │  └─ 각 행을 dict로 변환
          │     │     {
          │     │       "symbol": "USD/KRW",
          │     │       "date": "2025-01-15",
          │     │       "close_price": 1320.50,
          │     │       "adj_close_price": 1320.50,
          │     │       "currency": "KRW",
          │     │       "name": "원달러환율"
          │     │     }
          │     │
          │     └─ 레코드 리스트 반환
          │
          └─ [3-4] Supabase에 저장
             └─ upsert_exchange_rates(records)
                └─ exchange_rates 테이블에 upsert
                   └─ ON CONFLICT (symbol, date) DO UPDATE
    ↓
[4단계: 응답 반환]
    {
      "success": true,
      "symbols": ["USD/KRW", "^NYICDX"],
      "upserted": 150,
      "errors": []
    }
```

### 3.2. 단계별 상세 설명

#### 3.2.1. 심볼 목록 결정

**코드 위치**: `app/services/exchange_rates_service.py:sync_exchange_rates()`

```python
if symbols is None:
    # DB에서 활성화된 환율/인덱스 심볼 조회
    target_symbols = await get_active_exchange_rate_symbols()
    # → ["USD/KRW", "^NYICDX", "BTC/KRW", "BTC/USD"]
else:
    target_symbols = symbols
```

**DB 쿼리**:
```sql
SELECT symbol 
FROM stock_names 
WHERE asset_type IN ('FX', 'CRYPTO', 'INDEX')
  AND is_active = true;
```

**결과 예시**:
```python
["USD/KRW", "^NYICDX", "BTC/KRW", "BTC/USD"]
```

#### 3.2.2. 최근 날짜 조회 (증분 수집)

**코드 위치**: `app/repositories/supabase_client.py:get_max_date()`

**목적**: 이미 저장된 최신 날짜 이후 데이터만 수집하여 효율성 향상

**쿼리**:
```sql
SELECT date 
FROM exchange_rates 
WHERE symbol = 'USD/KRW' 
ORDER BY date DESC 
LIMIT 1;
```

**결과 예시**:
- 데이터가 있으면: `"2025-01-14"` → 이 날짜 이후만 수집
- 데이터가 없으면: `None` → 최근 1년 데이터 수집

**효과**:
- 첫 수집: 365일 데이터 수집
- 이후 수집: 최신 1-2일 데이터만 수집 (매우 효율적)

#### 3.2.3. FDR DataReader 호출

**코드 위치**: `app/services/exchange_rates_service.py:fetch_exchange_rate_data()`

**동작**:
```python
if start_date:
    # 증분 수집: 특정 날짜 이후만
    return fdr.DataReader(symbol, start=start_date)
else:
    # 첫 수집: 최근 1년
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    return fdr.DataReader(symbol, start=one_year_ago)
```

**Rate Limiter 적용**:
```python
async def fetch_data():
    return await asyncio.to_thread(fetch_exchange_rate_data, symbol, last_date)

df = await request_queue.add(fetch_data)
# → 최소 200ms 간격으로 요청
```

**반환 데이터 (DataFrame)**:
```
            Close    Adj Close
Date                          
2025-01-15  1320.50  1320.50
2025-01-16  1321.20  1321.20
...
```

#### 3.2.4. 데이터 정규화

**코드 위치**: `app/services/exchange_rates_service.py:normalize_exchange_rate_data()`

**과정**:

1. **메타데이터 조회**:
```python
meta = await get_symbol_metadata(symbol)
# → {"name": "원달러환율", "currency": "KRW"}
```

2. **DataFrame → 레코드 변환**:
```python
for idx, row in df.iterrows():
    records.append({
        "symbol": "USD/KRW",
        "date": "2025-01-15",
        "close_price": 1320.50,
        "adj_close_price": 1320.50,
        "currency": "KRW",  # 메타데이터에서 가져옴
        "name": "원달러환율",  # 메타데이터에서 가져옴
    })
```

**결과**:
```python
[
    {"symbol": "USD/KRW", "date": "2025-01-15", "close_price": 1320.50, ...},
    {"symbol": "USD/KRW", "date": "2025-01-16", "close_price": 1321.20, ...},
    ...
]
```

#### 3.2.5. Supabase에 저장

**코드 위치**: `app/repositories/supabase_client.py:upsert_exchange_rates()`

**동작**:
```python
supabase.table("exchange_rates").upsert(
    records,
    on_conflict="symbol,date"  # (symbol, date) 조합이 unique
).execute()
```

**SQL 동작**:
```sql
INSERT INTO exchange_rates (symbol, date, close_price, ...)
VALUES ('USD/KRW', '2025-01-15', 1320.50, ...)
ON CONFLICT (symbol, date) 
DO UPDATE SET 
    close_price = EXCLUDED.close_price,
    ...
```

**효과**:
- 중복 데이터 자동 처리
- 기존 데이터 업데이트
- 신규 데이터 삽입

### 3.3. 병렬 처리

**코드 위치**: `app/services/exchange_rates_service.py:sync_exchange_rates()`

```python
# 모든 심볼을 병렬로 처리
tasks = [process_symbol(s) for s in resolved_symbols]
await asyncio.gather(*tasks, return_exceptions=True)
```

**효과**:
- 여러 심볼을 동시에 처리하여 속도 향상
- 한 심볼 실패가 다른 심볼에 영향 없음

---

## 4. 프로세스 2: 데이터 조회

### 4.1. 최신 데이터 조회

**엔드포인트**: `GET /exchange-rates/{symbol_or_name}`

**전체 흐름**:

```
[1단계: 요청]
GET /exchange-rates/원달러환율
    ↓
[2단계: 심볼 변환]
resolve_symbol("원달러환율")
    └─ SYMBOL_CACHE에서 조회
       └─ "원달러환율" → "USD/KRW"
    ↓
[3단계: Supabase 조회]
get_exchange_rate("USD/KRW", date=None)
    └─ exchange_rates 테이블 조회
       └─ SELECT * 
          FROM exchange_rates 
          WHERE symbol = 'USD/KRW' 
          ORDER BY date DESC 
          LIMIT 1;
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

**코드 위치**: `app/api/routes.py:get_exchange_rate_endpoint()`

```python
@router.get("/exchange-rates/{symbol_or_name}")
async def get_exchange_rate_endpoint(symbol_or_name: str, date: Optional[str] = None):
    # 1. 심볼 변환
    symbol = resolve_symbol(symbol_or_name)  # "원달러환율" → "USD/KRW"
    
    # 2. Supabase 조회
    result = await get_exchange_rate(symbol, date=date)
    
    # 3. 응답 반환
    return ExchangeRateResponse(**result)
```

### 4.2. 시계열 데이터 조회

**엔드포인트**: `GET /exchange-rates/{symbol_or_name}/history`

**전체 흐름**:

```
[1단계: 요청]
GET /exchange-rates/원달러환율/history?start_date=2025-01-01&end_date=2025-01-15
    ↓
[2단계: 심볼 변환]
resolve_symbol("원달러환율") → "USD/KRW"
    ↓
[3단계: Supabase 조회]
get_exchange_rate_history("USD/KRW", "2025-01-01", "2025-01-15")
    └─ exchange_rates 테이블 조회
       └─ SELECT * 
          FROM exchange_rates 
          WHERE symbol = 'USD/KRW' 
            AND date >= '2025-01-01' 
            AND date <= '2025-01-15'
          ORDER BY date ASC;
    ↓
[4단계: 응답 반환]
{
  "symbol": "USD/KRW",
  "start_date": "2025-01-01",
  "end_date": "2025-01-15",
  "data": [
    {"symbol": "USD/KRW", "date": "2025-01-01", "close_price": 1310.00, ...},
    {"symbol": "USD/KRW", "date": "2025-01-02", "close_price": 1311.50, ...},
    ...
  ]
}
```

**코드 위치**: `app/api/routes.py:get_exchange_rate_history_endpoint()`

```python
@router.get("/exchange-rates/{symbol_or_name}/history")
async def get_exchange_rate_history_endpoint(
    symbol_or_name: str,
    start_date: str,
    end_date: str,
):
    # 1. 심볼 변환
    symbol = resolve_symbol(symbol_or_name)
    
    # 2. Supabase 조회
    result = await get_exchange_rate_history(symbol, start_date, end_date)
    
    # 3. 응답 반환
    return {
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "data": result,
    }
```

### 4.3. 특정 날짜 데이터 조회

**쿼리 파라미터**: `?date=2025-01-15`

```python
GET /exchange-rates/원달러환율?date=2025-01-15
    ↓
get_exchange_rate("USD/KRW", date="2025-01-15")
    └─ SELECT * 
       FROM exchange_rates 
       WHERE symbol = 'USD/KRW' 
         AND date = '2025-01-15' 
       LIMIT 1;
```

---

## 5. 프로세스 3: 심볼 관리

### 5.1. 심볼 메타데이터 저장

**테이블**: `stock_names`

**초기 데이터 삽입** (SQL):
```sql
INSERT INTO stock_names (symbol, name, currency, asset_type, is_active, source) VALUES 
('USD/KRW', '원달러환율', 'KRW', 'FX', true, 'FDR'),
('^NYICDX', '달러인덱스', 'USD', 'INDEX', true, 'FDR'),
('BTC/KRW', '비트코인(원)', 'KRW', 'CRYPTO', true, 'FDR'),
('BTC/USD', '비트코인(달러)', 'USD', 'CRYPTO', true, 'FDR')
ON CONFLICT (symbol) DO UPDATE SET
  name = EXCLUDED.name,
  currency = EXCLUDED.currency,
  asset_type = EXCLUDED.asset_type,
  is_active = EXCLUDED.is_active;
```

**데이터 구조**:
```python
{
    "symbol": "USD/KRW",
    "name": "원달러환율",
    "currency": "KRW",
    "asset_type": "FX",
    "is_active": true,
    "source": "FDR"
}
```

### 5.2. 심볼 활성화/비활성화

**활성화된 심볼만 수집**:
```python
# is_active = true인 심볼만 수집 대상
get_active_exchange_rate_symbols()
    └─ WHERE asset_type IN ('FX', 'CRYPTO', 'INDEX')
       AND is_active = true
```

**비활성화 방법**:
```sql
UPDATE stock_names 
SET is_active = false 
WHERE symbol = 'USD/KRW';
```

---

## 6. 심볼 변환 메커니즘

### 6.1. 서버 시작 시 캐시 로드

**코드 위치**: `app/main.py:lifespan()`

```python
@app.on_event("startup")
async def startup_event():
    await load_symbol_cache()
    # → stock_names 테이블에서 모든 활성 심볼 로드
    # → SYMBOL_CACHE에 저장
```

**캐시 구조**:
```python
SYMBOL_CACHE = {
    # 심볼 → 심볼 매핑
    "USD/KRW": "USD/KRW",
    "^NYICDX": "^NYICDX",
    
    # 이름 → 심볼 매핑
    "원달러환율": "USD/KRW",
    "달러인덱스": "^NYICDX",
    "비트코인(원)": "BTC/KRW",
    "비트코인(달러)": "BTC/USD",
}
```

### 6.2. 심볼 변환 과정

**코드 위치**: `app/services/exchange_rates_service.py:resolve_symbol()`

```python
def resolve_symbol(name_or_symbol: str) -> str:
    return resolve_symbol_from_cache(name_or_symbol)
    # → SYMBOL_CACHE에서 조회
    # → 없으면 입력값 그대로 반환
```

**예시**:
```python
resolve_symbol("원달러환율")  # → "USD/KRW"
resolve_symbol("USD/KRW")     # → "USD/KRW"
resolve_symbol("INVALID")      # → "INVALID" (그대로 반환)
```

### 6.3. 변환 사용 사례

**API 호출 시**:
```python
GET /exchange-rates/원달러환율
    ↓
resolve_symbol("원달러환율") → "USD/KRW"
    ↓
get_exchange_rate("USD/KRW")
```

**수집 시**:
```python
POST /sync-exchange-rates
Body: {"symbols": ["원달러환율", "USD/KRW"]}
    ↓
resolve_symbol("원달러환율") → "USD/KRW"
resolve_symbol("USD/KRW") → "USD/KRW"
    ↓
["USD/KRW", "USD/KRW"] → 중복 제거 → ["USD/KRW"]
```

---

## 7. 증분 수집 최적화

### 7.1. 동작 원리

```
[첫 수집]
get_max_date("USD/KRW") → None
    ↓
fdr.DataReader("USD/KRW", start=None)
    ↓
최근 1년 데이터 수집 (365일)
    ↓
Supabase에 저장

[두 번째 수집 (다음 날)]
get_max_date("USD/KRW") → "2025-01-14"
    ↓
fdr.DataReader("USD/KRW", start="2025-01-14")
    ↓
2025-01-14 이후 데이터만 수집 (1-2일)
    ↓
Supabase에 upsert
```

### 7.2. 성능 비교

| 방식 | 수집 데이터량 | 시간 | 네트워크 |
|------|-------------|------|----------|
| **전체 수집** | 365일 × 4개 심볼 = 1,460건 | 느림 | 많음 |
| **증분 수집** | 1-2일 × 4개 심볼 = 4-8건 | 빠름 | 적음 |

### 7.3. 코드 구현

**최근 날짜 조회**:
```python
async def get_max_date(symbol: str) -> Optional[str]:
    response = (
        supabase.table("exchange_rates")
        .select("date")
        .eq("symbol", symbol)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    return response.data[0].get("date") if response.data else None
```

**증분 수집**:
```python
last_date = await get_max_date(symbol)
# → "2025-01-14" 또는 None

df = await fetch_exchange_rate_data(symbol, last_date)
# → last_date가 있으면 해당 날짜 이후만 수집
```

---

## 8. 실제 사용 예시

### 예시 1: Cloud Scheduler 자동 수집

**설정**:
```bash
gcloud scheduler jobs create http sync-exchange-rates \
  --schedule="0 9 * * *" \
  --uri="https://your-backend.run.app/sync-exchange-rates" \
  --http-method=POST \
  --headers="Authorization=Bearer YOUR_CRON_SECRET" \
  --message-body='{}'
```

**실행 흐름**:
```
매일 오전 9시
    ↓
Cloud Scheduler 트리거
    ↓
POST /sync-exchange-rates
    ↓
DB에서 활성 심볼 조회: ["USD/KRW", "^NYICDX", "BTC/KRW", "BTC/USD"]
    ↓
각 심볼별 병렬 처리
    ├─ USD/KRW: 최근 날짜 조회 → FDR 호출 → 저장
    ├─ ^NYICDX: 최근 날짜 조회 → FDR 호출 → 저장
    ├─ BTC/KRW: 최근 날짜 조회 → FDR 호출 → 저장
    └─ BTC/USD: 최근 날짜 조회 → FDR 호출 → 저장
    ↓
응답: {"success": true, "upserted": 8, ...}
```

### 예시 2: 프론트엔드에서 환율 조회

**프론트엔드 코드**:
```typescript
// React 컴포넌트
const [rate, setRate] = useState(null);

useEffect(() => {
  async function fetchRate() {
    // 한국어 이름으로 조회 가능
    const response = await fetch(
      'https://your-backend.run.app/exchange-rates/원달러환율'
    );
    const data = await response.json();
    setRate(data);
  }
  fetchRate();
}, []);

// 화면에 표시
<div>
  <h2>{rate.name}</h2>
  <p>{rate.close_price} {rate.currency}</p>
  <p>날짜: {rate.date}</p>
</div>
```

**실행 흐름**:
```
사용자가 페이지 접속
    ↓
프론트엔드: GET /exchange-rates/원달러환율
    ↓
백엔드: resolve_symbol("원달러환율") → "USD/KRW"
    ↓
백엔드: get_exchange_rate("USD/KRW")
    ↓
Supabase: SELECT * FROM exchange_rates 
          WHERE symbol = 'USD/KRW' 
          ORDER BY date DESC LIMIT 1
    ↓
응답: {
      "symbol": "USD/KRW",
      "date": "2025-01-15",
      "close_price": 1320.50,
      "name": "원달러환율",
      "currency": "KRW"
    }
    ↓
프론트엔드: 화면에 표시
```

### 예시 3: 시계열 차트 표시

**프론트엔드 코드**:
```typescript
const [history, setHistory] = useState([]);

useEffect(() => {
  async function fetchHistory() {
    const endDate = new Date().toISOString().split('T')[0];
    const startDate = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)
      .toISOString().split('T')[0];
    
    const response = await fetch(
      `https://your-backend.run.app/exchange-rates/원달러환율/history?start_date=${startDate}&end_date=${endDate}`
    );
    const data = await response.json();
    setHistory(data.data);
  }
  fetchHistory();
}, []);

// 차트 라이브러리로 표시
<LineChart data={history} />
```

**실행 흐름**:
```
사용자가 차트 보기 클릭
    ↓
프론트엔드: GET /exchange-rates/원달러환율/history?start_date=2024-12-15&end_date=2025-01-15
    ↓
백엔드: resolve_symbol("원달러환율") → "USD/KRW"
    ↓
백엔드: get_exchange_rate_history("USD/KRW", "2024-12-15", "2025-01-15")
    ↓
Supabase: SELECT * FROM exchange_rates 
          WHERE symbol = 'USD/KRW' 
            AND date >= '2024-12-15' 
            AND date <= '2025-01-15'
          ORDER BY date ASC
    ↓
응답: {
      "symbol": "USD/KRW",
      "start_date": "2024-12-15",
      "end_date": "2025-01-15",
      "data": [
        {"date": "2024-12-15", "close_price": 1300.00, ...},
        {"date": "2024-12-16", "close_price": 1301.50, ...},
        ...
      ]
    }
    ↓
프론트엔드: 차트로 표시
```

---

## 9. 데이터베이스 스키마

### 9.1. exchange_rates 테이블

```sql
CREATE TABLE exchange_rates (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    close_price DECIMAL(20, 8) NOT NULL,
    adj_close_price DECIMAL(20, 8),
    currency VARCHAR(10),
    name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(symbol, date)
);

CREATE INDEX idx_exchange_rates_symbol_date ON exchange_rates(symbol, date);
CREATE INDEX idx_exchange_rates_date ON exchange_rates(date);
```

### 9.2. stock_names 테이블 (메타데이터)

```sql
CREATE TABLE stock_names (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(255),
    currency VARCHAR(10) DEFAULT 'KRW',
    asset_type VARCHAR(20) DEFAULT 'STOCK',
    is_active BOOLEAN DEFAULT true,
    source VARCHAR(50) DEFAULT 'FDR',
    ...
);
```

---

## 10. 에러 처리

### 10.1. 수집 실패 처리

```python
try:
    # FDR 호출
    df = await request_queue.add(fetch_data)
    
    # 정규화
    records = await normalize_exchange_rate_data(symbol, df)
    
    # 저장
    await upsert_exchange_rates(records)
    
except Exception as e:
    # 실패 격리: 한 심볼 실패가 다른 심볼에 영향 없음
    error_msg = f"{symbol}: 수집 실패 - {str(e)}"
    logger.error(error_msg)
    send_slack_error_log(None, e)
    errors.append(error_msg)
```

### 10.2. 조회 실패 처리

```python
result = await get_exchange_rate(symbol, date=date)
if not result:
    raise HTTPException(
        status_code=404,
        detail=f"Symbol '{symbol}' not found in exchange_rates"
    )
```

---

## 11. 성능 최적화 포인트

### 11.1. 증분 수집
- ✅ 최신 데이터만 수집하여 네트워크 트래픽 감소
- ✅ 수집 시간 단축

### 11.2. 병렬 처리
- ✅ 여러 심볼을 동시에 처리하여 전체 시간 단축

### 11.3. 메모리 캐시
- ✅ 심볼 변환 시 DB 조회 없이 즉시 반환
- ✅ 서버 시작 시 한 번만 로드

### 11.4. Rate Limiting
- ✅ 외부 API 호출 제한으로 안정성 향상
- ✅ 최소 200ms 간격으로 요청

---

## 12. 요약

### 전체 프로세스 요약

1. **초기 설정**: `stock_names` 테이블에 심볼 메타데이터 저장
2. **서버 시작**: 심볼 캐시 로드 (메모리)
3. **데이터 수집**: FDR → 정규화 → Supabase 저장 (증분 수집)
4. **데이터 조회**: Supabase → JSON 응답 (한국어 이름 지원)

### 주요 특징

- ✅ **증분 수집**: 최신 데이터만 수집하여 효율적
- ✅ **병렬 처리**: 여러 심볼 동시 처리
- ✅ **한국어 지원**: "원달러환율" 같은 이름으로 조회 가능
- ✅ **메모리 캐시**: 빠른 심볼 변환
- ✅ **실패 격리**: 한 심볼 실패가 다른 심볼에 영향 없음

---

**문서 버전**: 1.0  
**최종 업데이트**: 2025-01-15  
**작성 목적**: Exchange Rate 기능의 전체 프로세스를 단계별로 상세히 설명
