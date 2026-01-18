# Supabase 테이블 스키마

이 프로젝트에서 사용하는 Supabase 테이블 구조입니다.

## 1. `stock_prices` 테이블

주식 가격 데이터를 저장하는 메인 테이블입니다.

### 저장되는 데이터

```python
{
    "symbol": "AAPL",              # 주식 심볼 (대문자로 정규화됨)
    "date": "2025-01-15",          # 날짜 (YYYY-MM-DD 형식, 한국 시간 기준)
    "close_price": 185.50,         # 종가 (float)
    "currency": "USD",             # 통화 (optional)
    "name": "Apple Inc.",           # 회사명 (optional)
    "change_percent": 1.23         # 변동률 (optional, float)
}
```

### 코드에서 사용하는 컬럼

- `symbol` (string): 주식 심볼 (예: "AAPL", "MSFT")
- `date` (string): 날짜 (YYYY-MM-DD 형식)
- `close_price` (float): 종가
- `currency` (string, nullable): 통화 코드
- `name` (string, nullable): 회사명
- `change_percent` (float, nullable): 변동률 (%)

### 제약 조건

- **Unique Constraint**: `(symbol, date)` 조합이 유니크해야 함
- **Upsert 동작**: `on_conflict="symbol,date"`로 중복 시 업데이트

### 저장 로직

```python
# app/repositories/supabase_client.py의 save_stock_price_to_db 함수
data = {
    "symbol": normalized_symbol,        # 대문자로 정규화
    "date": target_date,                # 오늘 날짜 (한국 시간 기준)
    "close_price": quote_data["price"], # Yahoo Finance에서 가져온 가격
    "currency": quote_data.get("currency"),
    "name": quote_data.get("name"),
    "change_percent": quote_data.get("changePercent"),
}

supabase.table("stock_prices").upsert(data, on_conflict="symbol,date").execute()
```

### 조회 로직

- **오늘 날짜 데이터 조회**: `get_today_stock_prices()` - 배치 조회로 N+1 문제 방지
- **단일 심볼 조회**: `get_stock_price_from_db()` - 오늘 날짜 우선, 없으면 어제 날짜

---

## 2. `managed_stocks` 테이블

관리할 주식 심볼 목록을 저장하는 테이블입니다.

### 조회되는 컬럼

- `symbol` (string): 주식 심볼
- `enabled` (boolean): 활성화 여부
- `country` (string, optional): 국가 필터

### 조회 로직

```python
# app/repositories/supabase_client.py의 get_managed_stocks 함수
query = supabase.table("managed_stocks")
    .select("symbol")
    .eq("enabled", True)

# country 필터가 있으면 추가
if country:
    query = query.eq("country", country)

response = query.execute()
```

### 사용 시나리오

1. **요청 본문에 심볼이 없을 때**: `managed_stocks` 테이블에서 `enabled=true`인 심볼들을 조회
2. **국가 필터 적용**: `country` 파라미터가 있으면 해당 국가의 심볼만 조회

---

## 3. `stock_names` 테이블

화면에서 ticker(symbol)를 입력했을 때 **종목명(name)** 등을 빠르게 조회하기 위한 테이블입니다.
주식, 환율, 인덱스, 암호화폐 등 모든 자산 타입의 심볼 메타데이터를 저장합니다.

- 가격 수집 파이프라인의 심볼 소스는 기존대로 `managed_stocks`를 사용합니다.
- `stock_names`은 **name/country 보강용**이며, 조회는 **symbol 정확 일치 1건 조회**를 전제로 설계합니다.
- 환율/인덱스 심볼도 이 테이블에 저장되며, `asset_type`으로 구분됩니다.

### 저장되는 데이터 (예시)

**주식 종목:**
```python
{
    "symbol": "AAPL",         # 대문자로 정규화
    "name": "Apple Inc.",     # 종목명
    "country": "US",          # 국가 코드 (예: KR, US)
    "source": "FDR",          # 수집 소스 (현재는 FinanceDataReader)
    "is_active": True,        # 활성 여부
    "asset_type": "STOCK",    # 자산 타입 (기본값)
    "currency": "KRW",       # 통화 코드 (기본값)
    "fdr_symbol": None       # FDR 심볼 (선택적)
}
```

**환율/인덱스:**
```python
{
    "symbol": "USD/KRW",      # 심볼
    "name": "원달러환율",      # 한글명
    "country": None,          # 국가 코드 (환율은 없을 수 있음)
    "source": "FDR",          # 수집 소스
    "is_active": True,        # 활성 여부
    "asset_type": "FX",       # 자산 타입 (FX, CRYPTO, INDEX)
    "currency": "KRW",        # 통화 코드
    "fdr_symbol": None        # FDR 심볼 (선택적)
}
```

### 코드에서 사용하는 컬럼

- `symbol` (string): 종목 심볼 (unique)
- `name` (string, nullable): 종목명
- `country` (string, nullable): 국가 코드 (KR/US 등)
- `source` (string): 데이터 소스 (기본값 `FDR`)
- `is_active` (boolean): 활성 여부
- `asset_type` (string): 자산 타입 (STOCK, FX, CRYPTO, INDEX) - 기본값 'STOCK'
- `currency` (string): 통화 코드 (기본값 'KRW')
- `fdr_symbol` (string, nullable): FDR 심볼 (기존 symbol과 다를 경우 사용)

### 제약 조건/인덱스

- **Unique Constraint**: `symbol` 단일 unique (화면은 symbol 정확 일치 조회)
- **조회 성능**: `symbol` unique 인덱스로 point lookup이 매우 빠름 (전체 로드 방지)
- (옵션) `country`, `is_active` 인덱스

### 예상되는 테이블 스키마 (SQL)

```sql
CREATE TABLE stock_names (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(255),
    country VARCHAR(10),
    source VARCHAR(50) NOT NULL DEFAULT 'FDR',
    is_active BOOLEAN NOT NULL DEFAULT true,
    asset_type VARCHAR(20) NOT NULL DEFAULT 'STOCK',
    currency VARCHAR(10) NOT NULL DEFAULT 'KRW',
    fdr_symbol VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_stock_names_country ON stock_names(country);
CREATE INDEX idx_stock_names_is_active ON stock_names(is_active);
CREATE INDEX idx_stock_names_asset_type ON stock_names(asset_type);
```

### (옵션) 파티셔닝 DDL (대용량 대비)

화면이 **symbol 1건 조회(정확 일치)**만 한다면 기본적으로 파티셔닝이 필요하지 않습니다.
다만, 데이터가 매우 커지고(수천만 단위) 운영/청소(vacuum) 단위를 나누고 싶다면 아래처럼
**HASH 파티셔닝 by symbol**을 고려할 수 있습니다.

```sql
-- 예시: 16개 파티션
CREATE TABLE stock_names (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(255),
    country VARCHAR(10),
    source VARCHAR(50) NOT NULL DEFAULT 'FDR',
    is_active BOOLEAN NOT NULL DEFAULT true,
    asset_type VARCHAR(20) NOT NULL DEFAULT 'STOCK',
    currency VARCHAR(10) NOT NULL DEFAULT 'KRW',
    fdr_symbol VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(symbol)
) PARTITION BY HASH (symbol);

CREATE TABLE stock_names_p0 PARTITION OF stock_names FOR VALUES WITH (MODULUS 16, REMAINDER 0);
CREATE TABLE stock_names_p1 PARTITION OF stock_names FOR VALUES WITH (MODULUS 16, REMAINDER 1);
-- ...
CREATE TABLE stock_names_p15 PARTITION OF stock_names FOR VALUES WITH (MODULUS 16, REMAINDER 15);
```

---

## 4. `exchange_rates` 테이블

환율(USD/KRW, BTC/KRW, BTC/USD)과 인덱스(^NYICDX) 시계열 데이터를 저장하는 테이블입니다.

### 저장되는 데이터 (예시)

```python
{
    "symbol": "USD/KRW",         # 심볼 (예: "USD/KRW", "^NYICDX", "BTC/KRW", "BTC/USD")
    "date": "2025-01-15",        # 날짜 (YYYY-MM-DD 형식)
    "close_price": 1320.50,       # Close 가격
    "adj_close_price": 1320.50,   # Adj Close 가격 (환율/암호화폐는 대부분 동일)
    "currency": "KRW",            # 기준 통화
    "name": "원달러환율",          # 한글명
}
```

### 코드에서 사용하는 컬럼

- `symbol` (string): 심볼 (예: "USD/KRW", "^NYICDX")
- `date` (string): 날짜 (YYYY-MM-DD 형식)
- `close_price` (float): Close 가격
- `adj_close_price` (float, nullable): Adj Close 가격
- `currency` (string, nullable): 기준 통화 (예: "USD", "KRW")
- `name` (string, nullable): 한글명 (예: "원달러환율", "달러인덱스")

### 제약 조건/인덱스

- **Unique Constraint**: `(symbol, date)` 조합이 유니크
- **증분 수집 최적화**: MAX(date) 기반으로 최신 날짜 이후 데이터만 수집
- 인덱스: `(symbol, date)`, `(date)`

### 예상되는 테이블 스키마 (SQL)

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

### 저장 로직

```python
# app/repositories/supabase_client.py의 upsert_exchange_rates 함수
data = {
    "symbol": symbol,                    # 심볼
    "date": date,                        # 날짜
    "close_price": close_price,          # Close 가격
    "adj_close_price": adj_close_price,  # Adj Close 가격
    "currency": currency,                 # SYMBOL_META에서 가져온 통화
    "name": name,                        # SYMBOL_META에서 가져온 한글명
}

supabase.table("exchange_rates").upsert(data, on_conflict="symbol,date").execute()
```

### 조회 로직

- **최신 값 조회**: `get_exchange_rate(symbol)` - 가장 최근 날짜 데이터
- **시계열 조회**: `get_exchange_rate_history(symbol, start_date, end_date)` - 기간별 데이터
- **MAX(date) 조회**: `get_max_date(symbol)` - 증분 수집 최적화용

---

## 예상되는 테이블 스키마 (SQL)

### `stock_prices` 테이블

```sql
CREATE TABLE stock_prices (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    close_price DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(10),
    name VARCHAR(255),
    change_percent DECIMAL(5, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(symbol, date)
);

CREATE INDEX idx_stock_prices_symbol_date ON stock_prices(symbol, date);
CREATE INDEX idx_stock_prices_date ON stock_prices(date);
```

### `managed_stocks` 테이블

```sql
CREATE TABLE managed_stocks (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL UNIQUE,
    name VARCHAR(255),
    country VARCHAR(10),
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_managed_stocks_enabled ON managed_stocks(enabled);
CREATE INDEX idx_managed_stocks_country ON managed_stocks(country);
```

---

## 데이터 흐름

1. **심볼 결정**:
   - 요청 본문의 `symbols` → 우선 사용
   - 없으면 환경변수 `STOCK_SYMBOLS` → 사용
   - 없으면 `managed_stocks` 테이블에서 `enabled=true` 조회

2. **중복 체크**:
   - `stock_prices` 테이블에서 오늘 날짜 데이터 조회
   - 이미 있는 심볼은 스킵

3. **Yahoo Finance API 호출**:
   - 중복이 아닌 심볼만 API 호출

4. **Supabase 저장**:
   - `stock_prices` 테이블에 `upsert` (중복 시 업데이트)

---

## 주의사항

1. **날짜 형식**: 한국 시간(KST, UTC+9) 기준으로 `YYYY-MM-DD` 형식 사용
2. **심볼 정규화**: 모든 심볼은 대문자로 변환되어 저장됨
3. **Unique Constraint**: `(symbol, date)` 조합이 유니크하므로 같은 날짜에 같은 심볼은 하나만 존재
4. **Upsert 동작**: 같은 `(symbol, date)` 조합으로 저장 시 기존 데이터가 업데이트됨
