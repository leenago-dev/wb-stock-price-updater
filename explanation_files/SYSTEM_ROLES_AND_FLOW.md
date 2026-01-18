# 시스템 역할 및 데이터 흐름 가이드

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [3가지 주요 역할](#2-3가지-주요-역할)
3. [역할별 상세 설명](#3-역할별-상세-설명)
4. [전체 데이터 흐름도](#4-전체-데이터-흐름도)
5. [실제 사용 시나리오](#5-실제-사용-시나리오)
6. [각 역할의 책임](#6-각-역할의-책임)

---

## 1. 시스템 개요

이 시스템은 **3가지 주요 역할**로 구성되어 있습니다:

```
┌─────────────────────────────────────────────────────────┐
│                    시스템 전체 구조                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  역할 1: 데이터 수집 및 저장                            │
│  외부 API → 백엔드 → Supabase                           │
│                                                          │
│  역할 2: 데이터 조회 API 제공                            │
│  백엔드 → Supabase → JSON 응답                          │
│                                                          │
│  역할 3: 프론트엔드 연동                                 │
│  프론트엔드 → 백엔드 API → Supabase → 프론트엔드        │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 3가지 주요 역할

### 역할 1: 데이터 수집 및 저장 (Backend Job)

**목적**: 외부 API에서 데이터를 가져와서 Supabase에 저장

**트리거**: 
- Cloud Scheduler (정기 실행)
- 수동 API 호출 (관리자)

**흐름**:
```
외부 API (Yahoo Finance, FDR)
    ↓
백엔드 API 서버
    ↓
Supabase 데이터베이스
```

### 역할 2: 데이터 조회 API 제공 (Backend API)

**목적**: Supabase에 저장된 데이터를 조회하여 JSON으로 반환

**트리거**: 
- 프론트엔드 요청
- 외부 시스템 요청

**흐름**:
```
요청 (HTTP GET)
    ↓
백엔드 API 서버
    ↓
Supabase 데이터베이스 조회
    ↓
JSON 응답 반환
```

### 역할 3: 프론트엔드 연동 (Frontend Integration)

**목적**: 프론트엔드 애플리케이션이 백엔드 API를 통해 데이터를 조회

**트리거**: 
- 사용자 액션 (페이지 로드, 버튼 클릭 등)

**흐름**:
```
프론트엔드 (React, Next.js 등)
    ↓
백엔드 API 호출
    ↓
Supabase 데이터 조회
    ↓
프론트엔드에 데이터 표시
```

---

## 3. 역할별 상세 설명

### 역할 1: 데이터 수집 및 저장

#### 3.1.1. 주식 가격 수집

**엔드포인트**: `POST /update-prices` (인증 필요)

**데이터 소스**: Yahoo Finance API

**저장 위치**: `stock_prices` 테이블

**상세 흐름**:

```
1. Cloud Scheduler 트리거
   ↓
2. POST /update-prices 요청
   ├─ 인증: Bearer Token (CRON_SECRET)
   └─ 요청 본문: {"symbols": ["AAPL", "MSFT"]} (선택)
   ↓
3. 백엔드 처리
   ├─ 심볼 목록 결정
   │  ├─ Request Body 우선
   │  ├─ 환경변수 (STOCK_SYMBOLS)
   │  └─ DB (managed_stocks) 최종
   │
   ├─ 중복 제거
   │  └─ 오늘 날짜 데이터가 이미 있으면 스킵
   │
   └─ 각 심볼별 처리
      ├─ Yahoo Finance API 호출
      │  ├─ Rate Limiter 적용 (200ms 간격)
      │  ├─ 재시도 로직 (최대 3회)
      │  └─ 가격 데이터 수집
      │
      └─ Supabase에 저장
         └─ stock_prices 테이블에 upsert
            (symbol, date) unique 기준
   ↓
4. 응답 반환
   {
     "success": true,
     "total": 100,
     "successCount": 98,
     "failureCount": 2,
     "results": [...]
   }
```

**예시 코드**:
```python
# Cloud Scheduler에서 호출
POST https://your-backend.run.app/update-prices
Headers:
  Authorization: Bearer YOUR_CRON_SECRET
Body:
  {}  # 빈 객체 (DB에서 자동 조회)
```

#### 3.1.2. 환율/인덱스 수집

**엔드포인트**: `POST /sync-exchange-rates` (인증 필요)

**데이터 소스**: FinanceDataReader (FDR)

**저장 위치**: `exchange_rates` 테이블

**상세 흐름**:

```
1. POST /sync-exchange-rates 요청
   ├─ 인증: Bearer Token
   └─ 요청 본문: {"symbols": ["USD/KRW", "^NYICDX"]} (선택)
   ↓
2. 백엔드 처리
   ├─ 심볼 목록 결정
   │  ├─ Request Body 우선
   │  └─ DB (stock_names, asset_type IN ('FX', 'CRYPTO', 'INDEX')) 최종
   │
   └─ 각 심볼별 병렬 처리
      ├─ 최근 저장된 날짜 조회 (get_max_date)
      │  └─ 증분 수집 (최신 데이터만)
      │
      ├─ FDR DataReader 호출
      │  └─ Rate Limiter 적용
      │
      ├─ 데이터 정규화
      │  ├─ 메타데이터 조회 (name, currency)
      │  └─ 레코드 변환
      │
      └─ Supabase에 저장
         └─ exchange_rates 테이블에 upsert
   ↓
3. 응답 반환
   {
     "success": true,
     "symbols": ["USD/KRW", "^NYICDX"],
     "upserted": 150,
     "errors": []
   }
```

**예시 코드**:
```python
# Cloud Scheduler에서 호출
POST https://your-backend.run.app/sync-exchange-rates
Headers:
  Authorization: Bearer YOUR_CRON_SECRET
Body:
  {}  # 빈 객체 (DB에서 자동 조회)
```

#### 3.1.3. 종목 목록 동기화

**엔드포인트**: `POST /sync-stocks-name` (인증 필요)

**데이터 소스**: FDR StockListing

**저장 위치**: `stock_names` 테이블

**상세 흐름**:

```
1. POST /sync-stocks-name 요청
   ├─ 인증: Bearer Token
   └─ 요청 본문: {"markets": ["KRX", "NASDAQ"]} (선택)
   ↓
2. 백엔드 처리
   ├─ 시장별 병렬 수집
   │  └─ FDR StockListing API 호출
   │     (KRX, ETF/KR, S&P500, NASDAQ, NYSE, AMEX)
   │
   ├─ 중복 제거 (symbol 기준)
   │
   └─ 국가별 그룹핑 및 처리
      ├─ 신규/갱신: upsert (is_active=true)
      └─ 누락: 비활성화 (is_active=false)
   ↓
3. 응답 반환
   {
     "success": true,
     "markets": ["KRX", "NASDAQ"],
     "uniqueSymbols": 5000,
     "upserted": 5000,
     "deactivated": 10,
     "errors": []
   }
```

**예시 코드**:
```python
# 수동 호출 또는 스케줄러
POST https://your-backend.run.app/sync-stocks-name
Headers:
  Authorization: Bearer YOUR_CRON_SECRET
Body:
  {}  # 빈 객체 (기본 시장 사용)
```

---

### 역할 2: 데이터 조회 API 제공

#### 3.2.1. 환율/인덱스 조회

**엔드포인트**: `GET /exchange-rates/{symbol_or_name}` (인증 불필요)

**데이터 소스**: Supabase `exchange_rates` 테이블

**상세 흐름**:

```
1. GET /exchange-rates/원달러환율 요청
   ↓
2. 백엔드 처리
   ├─ 심볼 변환
   │  └─ resolve_symbol("원달러환율")
   │     └─ SYMBOL_CACHE에서 조회
   │        "원달러환율" → "USD/KRW"
   │
   └─ Supabase 조회
      └─ get_exchange_rate("USD/KRW")
         └─ exchange_rates 테이블에서 최신 데이터 조회
   ↓
3. JSON 응답 반환
   {
     "symbol": "USD/KRW",
     "date": "2025-01-15",
     "close_price": 1320.50,
     "adj_close_price": 1320.50,
     "currency": "KRW",
     "name": "원달러환율"
   }
```

**예시 코드**:
```bash
# 프론트엔드 또는 외부에서 호출
curl https://your-backend.run.app/exchange-rates/원달러환율

# 또는 심볼로 직접 호출
curl https://your-backend.run.app/exchange-rates/USD/KRW
```

#### 3.2.2. 환율/인덱스 시계열 조회

**엔드포인트**: `GET /exchange-rates/{symbol_or_name}/history` (인증 불필요)

**데이터 소스**: Supabase `exchange_rates` 테이블

**상세 흐름**:

```
1. GET /exchange-rates/원달러환율/history?start_date=2025-01-01&end_date=2025-01-15
   ↓
2. 백엔드 처리
   ├─ 심볼 변환
   │  └─ "원달러환율" → "USD/KRW"
   │
   └─ Supabase 조회
      └─ get_exchange_rate_history("USD/KRW", "2025-01-01", "2025-01-15")
         └─ exchange_rates 테이블에서 기간별 데이터 조회
   ↓
3. JSON 응답 반환
   {
     "symbol": "USD/KRW",
     "start_date": "2025-01-01",
     "end_date": "2025-01-15",
     "data": [
       {
         "symbol": "USD/KRW",
         "date": "2025-01-01",
         "close_price": 1310.00,
         ...
       },
       ...
     ]
   }
```

#### 3.2.3. 종목 정보 조회

**엔드포인트**: `GET /stocks-name/{symbol}` (인증 불필요)

**데이터 소스**: Supabase `stock_names` 테이블

**상세 흐름**:

```
1. GET /stocks-name/AAPL 요청
   ↓
2. 백엔드 처리
   └─ Supabase 조회
      └─ get_stock_name_by_symbol("AAPL")
         └─ stock_names 테이블에서 symbol로 조회
   ↓
3. JSON 응답 반환
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

---

### 역할 3: 프론트엔드 연동

#### 3.3.1. 전체 흐름

```
┌─────────────────────┐
│   프론트엔드         │
│   (React/Next.js)   │
│                     │
│   사용자가 페이지   │
│   로드 또는 버튼    │
│   클릭              │
└──────────┬──────────┘
           │
           │ HTTP GET 요청
           │ fetch('/exchange-rates/원달러환율')
           │
           ▼
┌─────────────────────┐
│   백엔드 API        │
│   (Cloud Run)       │
│                     │
│   1. CORS 검증      │
│   2. 요청 처리      │
│   3. Supabase 조회  │
└──────────┬──────────┘
           │
           │ SQL 쿼리
           │
           ▼
┌─────────────────────┐
│   Supabase          │
│   (PostgreSQL)      │
│                     │
│   exchange_rates    │
│   테이블 조회       │
└──────────┬──────────┘
           │
           │ 데이터 반환
           │
           ▼
┌─────────────────────┐
│   백엔드 API        │
│                     │
│   JSON 응답 생성    │
└──────────┬──────────┘
           │
           │ HTTP 응답
           │
           ▼
┌─────────────────────┐
│   프론트엔드         │
│                     │
│   데이터 표시       │
│   (차트, 테이블 등) │
└─────────────────────┘
```

#### 3.3.2. 프론트엔드 코드 예시

**React/Next.js 예시**:

```typescript
// lib/api.ts
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'https://your-backend.run.app';

// 환율 조회 함수
export async function getExchangeRate(symbolOrName: string) {
  const response = await fetch(`${API_BASE_URL}/exchange-rates/${symbolOrName}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch: ${response.statusText}`);
  }
  return response.json();
}

// 컴포넌트에서 사용
'use client';

import { useState, useEffect } from 'react';
import { getExchangeRate } from '@/lib/api';

export default function ExchangeRateDisplay() {
  const [rate, setRate] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchRate() {
      try {
        // 한국어 이름으로 조회 가능
        const data = await getExchangeRate('원달러환율');
        setRate(data);
      } catch (error) {
        console.error('Error:', error);
      } finally {
        setLoading(false);
      }
    }

    fetchRate();
  }, []);

  if (loading) return <div>로딩 중...</div>;
  if (!rate) return <div>데이터 없음</div>;

  return (
    <div>
      <h2>{rate.name}</h2>
      <p>가격: {rate.close_price?.toLocaleString()} {rate.currency}</p>
      <p>날짜: {rate.date}</p>
    </div>
  );
}
```

#### 3.3.3. CORS 설정

프론트엔드에서 백엔드 API를 호출하려면 CORS 설정이 필요합니다:

**백엔드 설정** (`app/main.py`):
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # 로컬 개발
        "https://your-frontend.vercel.app",  # 프로덕션
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 4. 전체 데이터 흐름도

### 4.1. 데이터 수집 → 저장 → 조회 전체 흐름

```
┌─────────────────────────────────────────────────────────────┐
│                    전체 시스템 흐름                          │
└─────────────────────────────────────────────────────────────┘

[1단계: 데이터 수집]
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ 외부 API     │─────▶│ 백엔드 API    │─────▶│ Supabase     │
│              │      │              │      │              │
│ Yahoo Finance│      │ 수집 로직     │      │ stock_prices │
│ FDR          │      │ 저장 로직     │      │ exchange_rates│
└──────────────┘      └──────────────┘      └──────────────┘
     ▲                      │                      │
     │                      │                      │
     │              [2단계: 데이터 조회]          │
     │                      │                      │
     │                      ▼                      │
     │              ┌──────────────┐              │
     │              │ 백엔드 API   │◀─────────────┘
     │              │              │
     │              │ GET /exchange│
     │              │ -rates/...   │
     │              └───────┬───────┘
     │                      │
     │              [3단계: 프론트엔드 연동]
     │                      │
     │                      ▼
     └──────────────┌──────────────┐
                    │ 프론트엔드    │
                    │              │
                    │ React/Next.js│
                    │ 사용자 화면  │
                    └──────────────┘
```

### 4.2. 시간 순서별 흐름

```
시간축: ───────────────────────────────────────────────────▶

[T1] Cloud Scheduler 트리거
     │
     ├─ POST /update-prices
     │  └─ Yahoo Finance → Supabase (stock_prices)
     │
     └─ POST /sync-exchange-rates
        └─ FDR → Supabase (exchange_rates)

[T2] 사용자가 프론트엔드 접속
     │
     └─ GET /exchange-rates/원달러환율
        └─ Supabase 조회 → JSON 응답 → 프론트엔드 표시

[T3] 사용자가 차트 보기 클릭
     │
     └─ GET /exchange-rates/원달러환율/history
        └─ Supabase 조회 → 시계열 데이터 → 차트 표시
```

---

## 5. 실제 사용 시나리오

### 시나리오 1: 주식 가격 수집 및 조회

**1단계: 데이터 수집 (관리자 작업)**
```bash
# Cloud Scheduler가 매일 오전 7시에 자동 실행
POST /update-prices
→ Yahoo Finance에서 AAPL, MSFT 가격 수집
→ Supabase stock_prices 테이블에 저장
```

**2단계: 데이터 조회 (프론트엔드)**
```typescript
// 사용자가 주식 가격 페이지 접속
const price = await fetch('/api/stocks/AAPL');
// → 백엔드가 Supabase에서 조회
// → 프론트엔드에 표시
```

### 시나리오 2: 환율 정보 표시

**1단계: 데이터 수집 (관리자 작업)**
```bash
# Cloud Scheduler가 매일 자동 실행
POST /sync-exchange-rates
→ FDR에서 USD/KRW, BTC/KRW 수집
→ Supabase exchange_rates 테이블에 저장
```

**2단계: 데이터 조회 (프론트엔드)**
```typescript
// 사용자가 환율 페이지 접속
const rate = await fetch('/api/exchange-rates/원달러환율');
// → 백엔드가 "원달러환율" → "USD/KRW" 변환
// → Supabase에서 조회
// → 프론트엔드에 표시
```

### 시나리오 3: 종목 검색

**1단계: 종목 목록 동기화 (관리자 작업)**
```bash
# 주 1회 또는 수동 실행
POST /sync-stocks-name
→ FDR StockListing에서 종목 목록 수집
→ Supabase stock_names 테이블에 저장
```

**2단계: 종목 검색 (프론트엔드)**
```typescript
// 사용자가 종목 검색
const stock = await fetch('/api/stocks-name/AAPL');
// → 백엔드가 Supabase에서 조회
// → 종목명, 국가 등 정보 반환
// → 프론트엔드에 표시
```

---

## 6. 각 역할의 책임

### 역할 1: 데이터 수집 및 저장

**책임**:
- ✅ 외부 API에서 데이터 수집
- ✅ 데이터 검증 및 정규화
- ✅ Supabase에 저장
- ✅ 에러 처리 및 재시도
- ✅ Rate Limiting 적용

**담당 파일**:
- `app/services/stock_service.py` - 주식 가격 수집
- `app/services/exchange_rates_service.py` - 환율/인덱스 수집
- `app/services/stock_names_sync_service.py` - 종목 목록 동기화
- `app/services/yahoo_finance.py` - Yahoo Finance API 클라이언트
- `app/repositories/supabase_client.py` - 저장 로직

**엔드포인트**:
- `POST /update-prices` (인증 필요)
- `POST /sync-exchange-rates` (인증 필요)
- `POST /sync-stocks-name` (인증 필요)

### 역할 2: 데이터 조회 API 제공

**책임**:
- ✅ Supabase에서 데이터 조회
- ✅ 데이터 변환 및 포맷팅
- ✅ JSON 응답 생성
- ✅ 에러 처리

**담당 파일**:
- `app/api/routes.py` - API 엔드포인트 정의
- `app/repositories/supabase_client.py` - 조회 로직
- `app/services/exchange_rates_service.py` - 심볼 변환 로직

**엔드포인트**:
- `GET /health` (인증 불필요)
- `GET /stocks-name/{symbol}` (인증 불필요)
- `GET /exchange-rates/{symbol_or_name}` (인증 불필요)
- `GET /exchange-rates/{symbol_or_name}/history` (인증 불필요)

### 역할 3: 프론트엔드 연동

**책임**:
- ✅ CORS 설정 (백엔드)
- ✅ API 클라이언트 제공 (프론트엔드)
- ✅ 데이터 표시 (프론트엔드)

**담당 파일**:
- `app/main.py` - CORS 미들웨어 설정
- 프론트엔드 프로젝트 - API 호출 및 UI 표시

**연결 포인트**:
- 백엔드: CORS 허용 도메인 설정
- 프론트엔드: API Base URL 설정
- 프론트엔드: API 호출 함수 작성

---

## 7. 데이터 저장 위치 정리

### 주식 가격 데이터

| 데이터 | 저장 테이블 | 수집 소스 | 조회 엔드포인트 |
|--------|------------|----------|----------------|
| 주식 가격 | `stock_prices` | Yahoo Finance | (직접 조회 없음, Supabase에서 직접 조회) |
| 종목 메타데이터 | `stock_names` | FDR StockListing | `GET /stocks-name/{symbol}` |

### 환율/인덱스 데이터

| 데이터 | 저장 테이블 | 수집 소스 | 조회 엔드포인트 |
|--------|------------|----------|----------------|
| 환율/인덱스 가격 | `exchange_rates` | FDR DataReader | `GET /exchange-rates/{symbol}` |
| 환율/인덱스 메타데이터 | `stock_names` | 수동 입력 또는 동기화 | `GET /stocks-name/{symbol}` |

### 관리 테이블

| 테이블 | 용도 | 수정 방법 |
|--------|------|----------|
| `managed_stocks` | 수집 대상 주식 심볼 관리 | DB에서 직접 수정 |
| `stock_names` | 종목 메타데이터 (주식, 환율, 인덱스 모두) | `POST /sync-stocks-name` 또는 DB 직접 수정 |

---

## 8. 인증 구분

### 인증 필요 (관리자용)

**용도**: 데이터 수집 및 동기화

**엔드포인트**:
- `POST /update-prices`
- `POST /sync-exchange-rates`
- `POST /sync-stocks-name`

**인증 방법**:
```http
Authorization: Bearer YOUR_CRON_SECRET
```

**사용자**:
- Cloud Scheduler (자동)
- 관리자 (수동)

### 인증 불필요 (공개 API)

**용도**: 데이터 조회

**엔드포인트**:
- `GET /health`
- `GET /stocks-name/{symbol}`
- `GET /exchange-rates/{symbol_or_name}`
- `GET /exchange-rates/{symbol_or_name}/history`

**사용자**:
- 프론트엔드 애플리케이션
- 외부 시스템
- 일반 사용자

---

## 9. 요약

### 핵심 포인트

1. **역할 1 (데이터 수집)**: 외부 API → 백엔드 → Supabase
   - 정기적으로 실행 (Cloud Scheduler)
   - 인증 필요
   - 데이터를 Supabase에 저장

2. **역할 2 (데이터 조회)**: 요청 → 백엔드 → Supabase → JSON 응답
   - 프론트엔드나 외부에서 호출
   - 인증 불필요
   - Supabase에서 데이터 조회하여 반환

3. **역할 3 (프론트엔드 연동)**: 프론트엔드 → 백엔드 API → Supabase → 프론트엔드
   - 사용자 액션에 따라 실행
   - 백엔드 API를 통해 데이터 조회
   - 화면에 표시

### 데이터 흐름 요약

```
[수집] 외부 API → 백엔드 → Supabase (저장)
                                    ↓
[조회] 프론트엔드 → 백엔드 → Supabase (조회) → 프론트엔드 (표시)
```

### 주요 구분

- **수집 작업**: 인증 필요, 정기 실행, 데이터 저장
- **조회 작업**: 인증 불필요, 요청 시 실행, 데이터 조회
- **프론트엔드**: 백엔드 API를 통해 데이터 조회 및 표시

---

**문서 버전**: 1.0  
**최종 업데이트**: 2025-01-15  
**작성 목적**: 시스템의 역할과 데이터 흐름을 명확히 구분하여 이해하기 쉽게 설명
