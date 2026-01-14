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
