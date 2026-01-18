# 백엔드 아키텍처 및 데이터 흐름 가이드

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [시스템 아키텍처](#2-시스템-아키텍처)
3. [프로젝트 구조](#3-프로젝트-구조)
4. [데이터 흐름 개요](#4-데이터-흐름-개요)
5. [주요 기능별 상세 흐름](#5-주요-기능별-상세-흐름)
6. [데이터베이스 스키마](#6-데이터베이스-스키마)
7. [API 엔드포인트](#7-api-엔드포인트)
8. [서비스 레이어 상세](#8-서비스-레이어-상세)
9. [유틸리티 및 미들웨어](#9-유틸리티-및-미들웨어)
10. [에러 처리 전략](#10-에러-처리-전략)
11. [성능 최적화 전략](#11-성능-최적화-전략)
12. [보안 및 인증](#12-보안-및-인증)

---

## 1. 프로젝트 개요

### 1.1. 목적

주식 가격, 환율, 인덱스 데이터를 수집하고 관리하는 백엔드 API 서비스입니다.

### 1.2. 주요 기능

- **주식 가격 수집**: Yahoo Finance API를 통한 실시간 주식 가격 수집
- **환율/인덱스 수집**: FinanceDataReader를 통한 환율 및 인덱스 데이터 수집
- **종목 목록 동기화**: FDR StockListing을 통한 종목 메타데이터 동기화
- **데이터 조회 API**: 프론트엔드를 위한 RESTful API 제공
- **자동화된 스케줄링**: Cloud Scheduler를 통한 정기적 데이터 수집

### 1.3. 기술 스택

- **프레임워크**: FastAPI (Python 3.11+)
- **데이터베이스**: Supabase (PostgreSQL)
- **외부 API**: 
  - Yahoo Finance (yfinance)
  - FinanceDataReader (FDR)
- **배포**: Google Cloud Run
- **스케줄링**: Google Cloud Scheduler
- **모니터링**: Slack Webhook

---

## 2. 시스템 아키텍처

### 2.1. 전체 아키텍처 다이어그램

```
┌─────────────────┐
│  Cloud Scheduler│
│  (정기 실행)     │
└────────┬────────┘
         │ HTTP POST
         │ Bearer Token
         ▼
┌─────────────────────────────────────────┐
│         FastAPI Application             │
│  ┌───────────────────────────────────┐  │
│  │  API Routes (app/api/routes.py)   │  │
│  │  - /update-prices                 │  │
│  │  - /sync-exchange-rates           │  │
│  │  - /sync-stocks-name              │  │
│  │  - /exchange-rates/{symbol}      │  │
│  │  - /stocks-name/{symbol}          │  │
│  └──────────────┬────────────────────┘  │
│                 │                        │
│  ┌──────────────▼────────────────────┐  │
│  │  Service Layer                  │
│  │  - stock_service.py                    │  │
│  │  - exchange_rates_service.py  │  │
│  │  - stock_names_sync_service.py│  │
│  │  - yahoo_finance.py           │  │
│  └──────────────┬────────────────────┘  │
│                 │                        │
│  ┌──────────────▼────────────────────┐  │
│  │  Repository Layer                 │  │
│  │  supabase_client.py               │  │
│  └──────────────┬────────────────────┘  │
└─────────────────┼────────────────────────┘
                  │
                  │ Supabase Client
                  ▼
         ┌─────────────────┐
         │   Supabase      │
         │   (PostgreSQL)  │
         │                 │
         │  - stock_prices │
         │  - stock_names  │
         │  - exchange_rates│
         │  - managed_stocks│
         └─────────────────┘
                  │
                  │ External APIs
                  ▼
         ┌─────────────────┐
         │ Yahoo Finance   │
         │ FinanceDataReader│
         └─────────────────┘
```

### 2.2. 레이어 구조

```
┌─────────────────────────────────────┐
│  Presentation Layer                 │
│  - FastAPI Routes                   │
│  - Request/Response Models          │
│  - Exception Handlers               │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Business Logic Layer               │
│  - Service Classes                  │
│  - Business Rules                   │
│  - Data Transformation              │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Data Access Layer                  │
│  - Repository Pattern               │
│  - Database Queries                 │
│  - External API Clients             │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Infrastructure Layer                │
│  - Configuration                    │
│  - Logging                          │
│  - Rate Limiting                    │
│  - Error Notifications              │
└─────────────────────────────────────┘
```

---

## 3. 프로젝트 구조

```
wb-stock-price-updater/
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI 애플리케이션 진입점
│   ├── config.py                    # 설정 관리 (환경변수)
│   ├── exceptions.py                # 커스텀 예외 클래스
│   │
│   ├── api/                         # API 레이어
│   │   ├── __init__.py
│   │   ├── routes.py                # API 엔드포인트 정의
│   │   └── dependencies.py         # 인증 등 의존성
│   │
│   ├── services/                     # 비즈니스 로직 레이어
│   │   ├── __init__.py
│   │   ├── stock_service.py          # 주식 가격 업데이트 로직
│   │   ├── exchange_rates_service.py # 환율/인덱스 수집 로직
│   │   ├── stock_names_sync_service.py # 종목 목록 동기화
│   │   ├── yahoo_finance.py         # Yahoo Finance API 클라이언트
│   │   └── listings/
│   │       ├── __init__.py
│   │       └── fdr_listings.py       # FDR StockListing 처리
│   │
│   ├── repositories/                 # 데이터 접근 레이어
│   │   ├── __init__.py
│   │   └── supabase_client.py       # Supabase 클라이언트 및 쿼리
│   │
│   └── utils/                       # 유틸리티
│       ├── __init__.py
│       ├── logging_config.py        # 로깅 설정
│       ├── rate_limiter.py          # Rate limiting 로직
│       └── slack_notifier.py        # Slack 알림
│
├── Dockerfile                       # Docker 이미지 빌드
├── pyproject.toml                   # 프로젝트 의존성
├── uv.lock                          # 의존성 잠금 파일
└── README.md                        # 프로젝트 문서
```

---

## 4. 데이터 흐름 개요

### 4.1. 주식 가격 수집 흐름

```
1. Cloud Scheduler 트리거
   ↓
2. POST /update-prices (Bearer Token 인증)
   ↓
3. stock_service.update_stock_prices()
   ├─ determine_symbols() → 심볼 목록 결정
   │  ├─ Request Body 우선
   │  ├─ 환경변수 (STOCK_SYMBOLS)
   │  └─ DB (managed_stocks) 최종
   │
   ├─ filter_symbols_to_fetch() → 중복 제거
   │  ├─ get_today_stock_prices() → DB에서 오늘 데이터 조회
   │  └─ 메모리 비교 → API 호출 필요한 심볼만 필터링
   │
   └─ 각 심볼별 처리 (병렬)
      ├─ yahoo_finance.get_quote_data()
      │  ├─ Rate Limiter 적용
      │  ├─ 재시도 로직
      │  └─ Yahoo Finance API 호출
      │
      └─ supabase_client.save_stock_price_to_db()
         └─ stock_prices 테이블에 upsert
```

### 4.2. 환율/인덱스 수집 흐름

```
1. POST /sync-exchange-rates (Bearer Token 인증)
   ↓
2. exchange_rates_service.sync_exchange_rates()
   ├─ get_active_exchange_rate_symbols() → DB에서 활성 심볼 조회
   │  └─ stock_names 테이블 (asset_type IN ('FX', 'CRYPTO', 'INDEX'))
   │
   └─ 각 심볼별 병렬 처리
      ├─ get_max_date() → 최근 저장된 날짜 조회
      ├─ fetch_exchange_rate_data() → FDR DataReader 호출
      │  └─ Rate Limiter 적용
      ├─ normalize_exchange_rate_data() → 데이터 정규화
      │  ├─ get_symbol_metadata() → 메타데이터 조회
      │  └─ 레코드 변환
      └─ upsert_exchange_rates() → exchange_rates 테이블에 저장
```

### 4.3. 종목 목록 동기화 흐름

```
1. POST /sync-stocks-name (Bearer Token 인증)
   ↓
2. stock_names_sync_service.sync_stock_names()
   ├─ fetch_and_normalize_market() → 각 시장별 병렬 수집
   │  └─ FDR StockListing API 호출
   │
   ├─ 중복 제거 (symbol 기준)
   │
   └─ country별 그룹핑 및 처리
      ├─ upsert_stock_names() → 신규/갱신
      └─ deactivate_stock_names() → 누락된 심볼 비활성화
```

### 4.4. 데이터 조회 흐름 (프론트엔드용)

```
1. GET /exchange-rates/{symbol_or_name}
   ↓
2. resolve_symbol() → 심볼 캐시에서 변환
   │  └─ SYMBOL_CACHE (메모리)
   │
3. get_exchange_rate() → Supabase 조회
   └─ exchange_rates 테이블에서 최신 데이터 반환
```

---

## 5. 주요 기능별 상세 흐름

### 5.1. 주식 가격 업데이트 (`/update-prices`)

#### 5.1.1. 심볼 결정 로직

```python
우선순위:
1. Request Body의 symbols
2. 환경변수 STOCK_SYMBOLS
3. DB의 managed_stocks 테이블 (enabled=true)
```

#### 5.1.2. 중복 제거 최적화

```python
# N+1 문제 방지
1. 모든 심볼의 오늘 날짜 데이터를 한 번에 조회
   get_today_stock_prices(symbols) → Dict[symbol, data]

2. 메모리에서 비교
   symbols_to_fetch = all_symbols - existing_symbols

3. 실제 API 호출이 필요한 심볼만 처리
```

#### 5.1.3. 개별 심볼 처리

```python
for each symbol:
    try:
        1. Yahoo Finance API 호출 (Rate Limiter 적용)
        2. 데이터 검증
        3. Supabase에 저장
        4. 성공 로그
    except:
        - 실패 격리 (다른 심볼에 영향 없음)
        - 에러 로그
        - Slack 알림
```

### 5.2. 환율/인덱스 수집 (`/sync-exchange-rates`)

#### 5.2.1. 증분 수집 최적화

```python
for each symbol:
    1. get_max_date(symbol) → 최근 저장된 날짜 조회
    2. FDR DataReader(symbol, start=last_date) → 증분 데이터만 수집
    3. 정규화 및 upsert
```

#### 5.2.2. 병렬 처리

```python
# 모든 심볼을 병렬로 처리
tasks = [process_symbol(s) for s in symbols]
await asyncio.gather(*tasks, return_exceptions=True)
```

### 5.3. 종목 목록 동기화 (`/sync-stocks-name`)

#### 5.3.1. 시장별 병렬 수집

```python
markets = ['KRX', 'ETF/KR', 'S&P500', 'NASDAQ', 'NYSE', 'AMEX']
tasks = [fetch_and_normalize_market(m) for m in markets]
results = await asyncio.gather(*tasks)
```

#### 5.3.2. 비활성화 로직

```python
# 동기화 결과에 없는 기존 활성 심볼은 비활성화
existing_active = get_active_stock_names_symbols(country)
missing = existing_active - current_symbols
deactivate_stock_names(missing)
```

### 5.4. 서버 시작 시 초기화

```python
@lifespan
async def lifespan(_app: FastAPI):
    # Startup
    await load_symbol_cache()
    # stock_names 테이블에서 모든 활성 심볼 로드
    # SYMBOL_CACHE에 저장 (이름→심볼, 심볼→심볼 매핑)
    
    yield  # 서버 실행 중
    
    # Shutdown (필요 시 정리 작업)
```

---

## 6. 데이터베이스 스키마

### 6.1. 주요 테이블

#### `stock_prices`
- **용도**: 주식 가격 시계열 데이터
- **주요 컬럼**: `symbol`, `date`, `close_price`, `currency`, `name`, `change_percent`
- **Unique**: `(symbol, date)`

#### `stock_names`
- **용도**: 종목 메타데이터 (주식, 환율, 인덱스 모두 포함)
- **주요 컬럼**: `symbol`, `name`, `country`, `source`, `is_active`, `asset_type`, `currency`, `fdr_symbol`
- **Unique**: `symbol`

#### `exchange_rates`
- **용도**: 환율/인덱스 시계열 데이터
- **주요 컬럼**: `symbol`, `date`, `close_price`, `adj_close_price`, `currency`, `name`
- **Unique**: `(symbol, date)`

#### `managed_stocks`
- **용도**: 수집 대상 주식 심볼 관리
- **주요 컬럼**: `symbol`, `enabled`, `country`
- **Unique**: `symbol`

### 6.2. 데이터 관계

```
managed_stocks (수집 대상)
    ↓
stock_prices (가격 데이터)

stock_names (메타데이터)
    ├─ asset_type='STOCK' → 주식
    ├─ asset_type='FX' → 환율
    ├─ asset_type='CRYPTO' → 암호화폐
    └─ asset_type='INDEX' → 인덱스
        ↓
exchange_rates (환율/인덱스 데이터)
```

---

## 7. API 엔드포인트

### 7.1. 인증 불필요 (프론트엔드용)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/health` | 헬스체크 |
| GET | `/stocks-name/{symbol}` | 종목 정보 조회 |
| GET | `/exchange-rates/{symbol_or_name}` | 환율/인덱스 조회 |
| GET | `/exchange-rates/{symbol_or_name}/history` | 시계열 조회 |

### 7.2. 인증 필요 (관리자용)

| 메서드 | 엔드포인트 | 설명 | 인증 |
|--------|-----------|------|------|
| POST | `/update-prices` | 주식 가격 업데이트 | Bearer Token |
| POST | `/sync-stocks-name` | 종목 목록 동기화 | Bearer Token |
| POST | `/sync-exchange-rates` | 환율/인덱스 동기화 | Bearer Token |

### 7.3. 요청/응답 예시

#### POST /update-prices

**요청:**
```json
{
  "symbols": ["AAPL", "MSFT"],
  "country": "US"
}
```

**응답:**
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

#### GET /exchange-rates/원달러환율

**응답:**
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

---

## 8. 서비스 레이어 상세

### 8.1. `stock_service.py`

**주요 함수:**

- `determine_symbols()`: 심볼 목록 결정 (우선순위 적용)
- `filter_symbols_to_fetch()`: 중복 제거 및 필터링
- `update_stock_prices()`: 메인 비즈니스 로직

**특징:**
- N+1 문제 방지 (배치 조회)
- 실패 격리 (개별 try-except)
- 상세한 진행 상황 로깅

### 8.2. `exchange_rates_service.py`

**주요 함수:**

- `sync_exchange_rates()`: 환율/인덱스 동기화
- `normalize_exchange_rate_data()`: 데이터 정규화
- `resolve_symbol()`: 한국어 이름 → 심볼 변환

**특징:**
- 증분 수집 (MAX(date) 기반)
- 병렬 처리
- DB 기반 심볼 관리 (Data-Driven)

### 8.3. `stock_names_sync_service.py`

**주요 함수:**

- `sync_stock_names()`: 종목 목록 동기화
- `_partition_by_country()`: 국가별 그룹핑

**특징:**
- 시장별 병렬 수집
- 자동 비활성화 (누락된 심볼)
- 중복 제거

### 8.4. `yahoo_finance.py`

**주요 함수:**

- `get_quote_data()`: 주식 가격 조회
- `fetch_with_retry()`: 재시도 로직 포함

**특징:**
- Rate Limiter 통합
- 지수 백오프 재시도
- 상세한 에러 처리

---

## 9. 유틸리티 및 미들웨어

### 9.1. Rate Limiter (`rate_limiter.py`)

**목적:** 외부 API 호출 제한

**동작:**
```python
- 최소 요청 간격: 200ms (기본값)
- 최대 동시 요청: 3개
- 큐 기반 처리
```

**사용 예시:**
```python
async def fetch_data():
    return await request_queue.add(fetch_ticker)
```

### 9.2. 로깅 (`logging_config.py`)

**구조:**
- 구조화된 로깅
- 로그 레벨별 필터링
- Cloud Run 로그 통합

### 9.3. Slack 알림 (`slack_notifier.py`)

**용도:**
- 에러 알림
- 상세한 에러 정보 (Block Kit 포맷)
- 심볼별 에러 추적

### 9.4. CORS 미들웨어 (`main.py`)

**설정:**
```python
- 환경변수로 허용 도메인 관리
- ALLOWED_ORIGINS (쉼표로 구분)
- 개발/프로덕션 분리
```

---

## 10. 에러 처리 전략

### 10.1. 계층별 에러 처리

#### API 레이어
```python
- HTTPException 변환
- 적절한 상태 코드 반환
- 사용자 친화적 에러 메시지
```

#### 서비스 레이어
```python
- 커스텀 예외 클래스 사용
- 실패 격리 (개별 심볼)
- 상세한 에러 로깅
```

#### Repository 레이어
```python
- SupabaseException 변환
- 재시도 로직
- Slack 알림
```

### 10.2. 예외 클래스

```python
- StockPriceUpdaterException: 일반 비즈니스 예외
- SupabaseException: DB 관련 예외
- YahooFinanceException: Yahoo Finance API 예외
- RateLimitException: Rate Limit 예외
```

### 10.3. 에러 복구 전략

1. **재시도**: 지수 백오프 (최대 3회)
2. **실패 격리**: 한 심볼 실패가 전체 중단시키지 않음
3. **알림**: Slack으로 즉시 알림
4. **로깅**: 상세한 에러 정보 기록

---

## 11. 성능 최적화 전략

### 11.1. N+1 문제 방지

**문제:**
```python
# 나쁜 예
for symbol in symbols:
    price = await get_stock_price(symbol)  # N번 쿼리
```

**해결:**
```python
# 좋은 예
prices = await get_today_stock_prices(symbols)  # 1번 쿼리
for symbol in symbols:
    price = prices.get(symbol)
```

### 11.2. 증분 수집

**환율/인덱스:**
```python
last_date = await get_max_date(symbol)
df = fdr.DataReader(symbol, start=last_date)  # 최신 데이터만
```

### 11.3. 병렬 처리

**사용 사례:**
- 환율/인덱스 수집: 모든 심볼 병렬 처리
- 종목 목록 동기화: 시장별 병렬 수집

### 11.4. 메모리 캐시

**심볼 캐시:**
```python
# 서버 시작 시 로드
SYMBOL_CACHE = {
    "원달러환율": "USD/KRW",
    "USD/KRW": "USD/KRW",
    ...
}

# 조회 시 즉시 반환 (DB 조회 없음)
symbol = SYMBOL_CACHE.get(name_or_symbol)
```

### 11.5. Rate Limiting

**설정:**
- 최소 요청 간격: 200ms
- 최대 동시 요청: 3개
- 큐 기반 순차 처리

---

## 12. 보안 및 인증

### 12.1. API 인증

**방식:** Bearer Token

**구현:**
```python
async def verify_auth(authorization: str = Header(None)):
    token = authorization.replace("Bearer ", "")
    if token != settings.cron_secret:
        raise HTTPException(401, "Unauthorized")
```

**사용:**
```python
@router.post("/update-prices")
async def update_prices(_: bool = Depends(verify_auth)):
    ...
```

### 12.2. 환경변수 관리

**필수 환경변수:**
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `CRON_SECRET`

**선택 환경변수:**
- `STOCK_SYMBOLS` (오버라이드용)
- `SLACK_WEBHOOK_URL`
- `ALLOWED_ORIGINS` (CORS)

### 12.3. CORS 설정

**프로덕션:**
```python
ALLOWED_ORIGINS="https://your-frontend-domain.com"
```

**개발:**
```python
ALLOWED_ORIGINS="http://localhost:3000,http://localhost:5173"
```

---

## 13. 배포 및 운영

### 13.1. Cloud Run 배포

**Docker 이미지:**
- Python 3.11-slim 베이스
- uv 패키지 관리자
- 포트 8080 노출

**환경변수:**
- Secret Manager 사용 권장
- 또는 `--set-env-vars` 사용

### 13.2. Cloud Scheduler 설정

**예시:**
```bash
gcloud scheduler jobs create http update-stock-prices \
  --schedule="0 7 * * *" \
  --uri="https://your-service.run.app/update-prices" \
  --http-method=POST \
  --headers="Authorization=Bearer YOUR_CRON_SECRET"
```

### 13.3. 모니터링

**로그:**
- Cloud Run 로그 통합
- Slack 알림
- 구조화된 로깅

---

## 14. 확장성 고려사항

### 14.1. 수평 확장

- Cloud Run은 자동 스케일링 지원
- 상태 없는 설계 (Stateless)
- 메모리 캐시는 인스턴스별로 로드

### 14.2. 데이터베이스 최적화

- 인덱스 활용 (`symbol`, `date`, `is_active`)
- 파티셔닝 고려 (대용량 시)
- Connection Pooling

### 14.3. 캐싱 전략

- 현재: 메모리 캐시 (인스턴스별)
- 향후: Redis 고려 (분산 캐시)

---

## 15. 개발 가이드

### 15.1. 로컬 개발

```bash
# 의존성 설치
uv sync

# 서버 실행
uv run uvicorn app.main:app --reload --port 8080
```

### 15.2. 테스트

```bash
# 헬스체크
curl http://localhost:8080/health

# 주식 가격 업데이트 (인증 필요)
curl -X POST http://localhost:8080/update-prices \
  -H "Authorization: Bearer YOUR_CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL"]}'
```

### 15.3. 코드 스타일

- Type Hints 사용
- Docstring 작성
- 에러 처리 명시적

---

## 16. 참고 자료

- [FastAPI 문서](https://fastapi.tiangolo.com/)
- [Supabase 문서](https://supabase.com/docs)
- [Yahoo Finance API](https://github.com/ranaroussi/yfinance)
- [FinanceDataReader](https://github.com/FinanceData/FinanceDataReader)
- [Cloud Run 문서](https://cloud.google.com/run/docs)

---

## 부록: 주요 데이터 흐름 다이어그램

### 주식 가격 수집 상세 흐름

```
Cloud Scheduler
    │
    ├─ POST /update-prices
    │  └─ verify_auth() ✓
    │
    ├─ stock_service.update_stock_prices()
    │  │
    │  ├─ determine_symbols()
    │  │  ├─ Request Body? → 사용
    │  │  ├─ 환경변수? → 사용
    │  │  └─ DB (managed_stocks) → 사용
    │  │
    │  ├─ filter_symbols_to_fetch()
    │  │  ├─ get_today_stock_prices() → DB 조회 (1번)
    │  │  └─ 메모리 비교 → 필터링
    │  │
    │  └─ 각 심볼 처리 (순차)
    │     ├─ yahoo_finance.get_quote_data()
    │     │  ├─ request_queue.add() → Rate Limiter
    │     │  ├─ yf.Ticker(symbol)
    │     │  └─ 재시도 로직
    │     │
    │     └─ save_stock_price_to_db()
    │        └─ stock_prices.upsert()
    │
    └─ 응답 반환
```

### 환율/인덱스 수집 상세 흐름

```
POST /sync-exchange-rates
    │
    ├─ verify_auth() ✓
    │
    ├─ exchange_rates_service.sync_exchange_rates()
    │  │
    │  ├─ get_active_exchange_rate_symbols()
    │  │  └─ stock_names 조회 (asset_type IN ('FX', 'CRYPTO', 'INDEX'))
    │  │
    │  └─ 병렬 처리 (asyncio.gather)
    │     │
    │     └─ 각 심볼별 process_symbol()
    │        ├─ get_max_date() → 최근 날짜 조회
    │        ├─ fetch_exchange_rate_data()
    │        │  ├─ request_queue.add() → Rate Limiter
    │        │  └─ fdr.DataReader(symbol, start=last_date)
    │        │
    │        ├─ normalize_exchange_rate_data()
    │        │  ├─ get_symbol_metadata() → 메타데이터 조회
    │        │  └─ 레코드 변환
    │        │
    │        └─ upsert_exchange_rates()
    │           └─ exchange_rates.upsert()
    │
    └─ 응답 반환
```

---

**문서 버전:** 1.0  
**최종 업데이트:** 2025-01-15  
**작성자:** Backend Development Team
