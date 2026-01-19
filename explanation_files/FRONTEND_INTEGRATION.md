# 프론트엔드 연결 가이드

Cloud Run에 배포한 백엔드 API를 프론트엔드와 연결하는 방법을 설명합니다.

## 목차

1. [CORS 설정](#1-cors-설정)
2. [Cloud Run 배포 및 URL 확인](#2-cloud-run-배포-및-url-확인)
3. [API 엔드포인트 정리](#3-api-엔드포인트-정리)
4. [프론트엔드 연결 방법](#4-프론트엔드-연결-방법)
5. [실제 사용 예시](#5-실제-사용-예시)
6. [환경변수 설정](#6-환경변수-설정)
7. [트러블슈팅](#7-트러블슈팅)

---

## 1. CORS 설정

프론트엔드에서 API를 호출하려면 **CORS(Cross-Origin Resource Sharing)** 설정이 필요합니다.

### 1.1. 백엔드에 CORS 미들웨어 추가

`app/main.py`에 CORS 미들웨어를 추가합니다:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# FastAPI 앱 생성
app = FastAPI(title="Stock Price Updater", version="1.0.0", lifespan=lifespan)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # 로컬 개발 환경
        "http://localhost:5173",  # Vite 기본 포트
        "https://your-frontend-domain.com",  # 프로덕션 도메인
        # 또는 모든 도메인 허용 (개발용, 프로덕션에서는 특정 도메인만 허용 권장)
        # "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)

# 예외 핸들러 설정
setup_exception_handlers(app)

# 라우터 등록
app.include_router(router)
```

### 1.2. 환경변수로 CORS 도메인 관리 (권장)

프로덕션에서는 환경변수로 허용할 도메인을 관리하는 것이 좋습니다:

```python
import os
from fastapi.middleware.cors import CORSMiddleware

# 환경변수에서 허용할 도메인 목록 가져오기
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Cloud Run 배포 시:
```bash
gcloud run deploy stock-price-updater \
  --set-env-vars ALLOWED_ORIGINS="https://your-frontend-domain.com,https://www.your-frontend-domain.com" \
  ...
```

---

## 2. Cloud Run 배포 및 URL 확인

### 2.1. 배포

```bash
# Docker 이미지 빌드 및 푸시
docker build -t asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/stock-price-updater/stock-price-updater:latest .
gcloud auth configure-docker asia-northeast3-docker.pkg.dev
docker push asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/stock-price-updater/stock-price-updater:latest

# Cloud Run 배포
gcloud run deploy stock-price-updater \
  --image asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/stock-price-updater/stock-price-updater:latest \
  --platform managed \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --set-env-vars SUPABASE_URL=your_supabase_url,SUPABASE_ANON_KEY=your_supabase_anon_key,CRON_SECRET=your_cron_secret \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 1
```

### 2.2. 서비스 URL 확인

```bash
# 명령어로 확인
gcloud run services describe stock-price-updater \
  --region asia-northeast3 \
  --format 'value(status.url)'

# 출력 예시:
# https://stock-price-updater-xxxxx-xx.a.run.app
```

또는 Google Cloud Console에서:
1. Cloud Run 메뉴로 이동
2. `stock-price-updater` 서비스 선택
3. 상단에 표시된 URL 확인

---

## 3. API 엔드포인트 정리

### 3.1. 인증 불필요한 엔드포인트 (프론트엔드에서 자유롭게 호출 가능)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/health` | 헬스체크 |
| GET | `/stocks-name/{symbol}` | 종목 정보 조회 |
| GET | `/exchange-rates/{symbol_or_name}` | 환율/인덱스 조회 |
| GET | `/exchange-rates/{symbol_or_name}/history` | 환율/인덱스 시계열 조회 |

### 3.2. 인증 필요한 엔드포인트 (관리자용)

| 메서드 | 엔드포인트 | 설명 | 인증 |
|--------|-----------|------|------|
| POST | `/update-prices` | 주식 가격 업데이트 | Bearer Token |
| POST | `/sync-stocks-name` | 종목 목록 동기화 | Bearer Token |
| POST | `/sync-exchange-rates` | 환율/인덱스 동기화 | Bearer Token |

**인증 방법:**
```http
Authorization: Bearer YOUR_CRON_SECRET
```

---

## 4. 프론트엔드 연결 방법

### 4.1. API Base URL 설정

프론트엔드 프로젝트에 환경변수 파일을 생성합니다:

**`.env.local` (로컬 개발)**
```env
NEXT_PUBLIC_API_URL=http://localhost:8080
# 또는
NEXT_PUBLIC_API_URL=https://stock-price-updater-xxxxx-xx.a.run.app
```

**`.env.production` (프로덕션)**
```env
NEXT_PUBLIC_API_URL=https://stock-price-updater-xxxxx-xx.a.run.app
```

### 4.2. API 클라이언트 생성

**React/Next.js 예시:**

```typescript
// lib/api.ts
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

export interface StockName {
  symbol: string;
  name: string | null;
  country: string | null;
  source: string | null;
  is_active: boolean | null;
}

export interface ExchangeRate {
  symbol: string;
  date: string;
  close_price: number | null;
  adj_close_price: number | null;
  currency: string | null;
  name: string | null;
}

// 종목 정보 조회
export async function getStockName(symbol: string): Promise<StockName> {
  const response = await fetch(`${API_BASE_URL}/stocks-name/${symbol}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch stock name: ${response.statusText}`);
  }
  return response.json();
}

// 환율 조회
export async function getExchangeRate(symbolOrName: string, date?: string): Promise<ExchangeRate> {
  const url = date 
    ? `${API_BASE_URL}/exchange-rates/${symbolOrName}?date=${date}`
    : `${API_BASE_URL}/exchange-rates/${symbolOrName}`;
  
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch exchange rate: ${response.statusText}`);
  }
  return response.json();
}

// 환율 시계열 조회
export async function getExchangeRateHistory(
  symbolOrName: string,
  startDate: string,
  endDate: string
): Promise<ExchangeRate[]> {
  const response = await fetch(
    `${API_BASE_URL}/exchange-rates/${symbolOrName}/history?start_date=${startDate}&end_date=${endDate}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch exchange rate history: ${response.statusText}`);
  }
  const data = await response.json();
  return data.data;
}
```

---

## 5. 실제 사용 예시

### 5.1. React 컴포넌트 예시

```tsx
// components/ExchangeRateDisplay.tsx
'use client';

import { useState, useEffect } from 'react';
import { getExchangeRate } from '@/lib/api';

export default function ExchangeRateDisplay({ symbol }: { symbol: string }) {
  const [rate, setRate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchRate() {
      try {
        setLoading(true);
        const data = await getExchangeRate(symbol);
        setRate(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    fetchRate();
  }, [symbol]);

  if (loading) return <div>로딩 중...</div>;
  if (error) return <div>오류: {error}</div>;
  if (!rate) return <div>데이터 없음</div>;

  return (
    <div>
      <h2>{rate.name || rate.symbol}</h2>
      <p>가격: {rate.close_price?.toLocaleString()} {rate.currency}</p>
      <p>날짜: {rate.date}</p>
    </div>
  );
}
```

### 5.2. 한국어 이름으로 조회 예시

```tsx
// "원달러환율"이라는 한글 이름으로 조회 가능
<ExchangeRateDisplay symbol="원달러환율" />
// 또는 심볼로 직접 조회
<ExchangeRateDisplay symbol="USD/KRW" />
```

### 5.3. 시계열 차트 예시

```tsx
// components/ExchangeRateChart.tsx
'use client';

import { useState, useEffect } from 'react';
import { getExchangeRateHistory } from '@/lib/api';
import { Line } from 'react-chartjs-2';

export default function ExchangeRateChart({ symbol }: { symbol: string }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchHistory() {
      const endDate = new Date().toISOString().split('T')[0];
      const startDate = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)
        .toISOString()
        .split('T')[0];
      
      try {
        const history = await getExchangeRateHistory(symbol, startDate, endDate);
        setData(history);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }

    fetchHistory();
  }, [symbol]);

  if (loading) return <div>로딩 중...</div>;

  const chartData = {
    labels: data.map(d => d.date),
    datasets: [{
      label: symbol,
      data: data.map(d => d.close_price),
      borderColor: 'rgb(75, 192, 192)',
      tension: 0.1
    }]
  };

  return <Line data={chartData} />;
}
```

---

## 6. 환경변수 설정

### 6.1. 프론트엔드 환경변수

**Next.js 예시:**

```env
# .env.local
NEXT_PUBLIC_API_URL=https://stock-price-updater-xxxxx-xx.a.run.app
```

**Vite/React 예시:**

```env
# .env.local
VITE_API_URL=https://stock-price-updater-xxxxx-xx.a.run.app
```

### 6.2. 백엔드 환경변수 (Cloud Run)

```bash
gcloud run services update stock-price-updater \
  --region asia-northeast3 \
  --update-env-vars ALLOWED_ORIGINS="https://your-frontend-domain.com"
```

---

## 7. 트러블슈팅

### 7.1. CORS 오류

**증상:**
```
Access to fetch at 'https://...' from origin 'http://localhost:3000' has been blocked by CORS policy
```

**해결:**
1. `app/main.py`에 CORS 미들웨어가 추가되었는지 확인
2. `ALLOWED_ORIGINS` 환경변수에 프론트엔드 도메인이 포함되어 있는지 확인
3. Cloud Run 서비스를 재배포

### 7.2. 404 오류

**증상:**
```
404 Not Found
```

**해결:**
1. API URL이 정확한지 확인 (끝에 `/` 없이)
2. 엔드포인트 경로가 정확한지 확인 (`/stocks-name/{symbol}`)
3. Cloud Run 서비스가 정상 실행 중인지 확인 (`/health` 엔드포인트로 확인)

### 7.3. 401 Unauthorized 오류

**증상:**
```
401 Unauthorized
```

**해결:**
- 인증이 필요한 엔드포인트(`/update-prices`, `/sync-*`)를 호출하는 경우
- Bearer Token을 헤더에 포함해야 함
- 프론트엔드에서 일반 사용자용으로는 인증 불필요한 엔드포인트만 사용

### 7.4. 네트워크 오류

**증상:**
```
Failed to fetch
NetworkError when attempting to fetch resource
```

**해결:**
1. Cloud Run 서비스가 실행 중인지 확인
2. 인터넷 연결 확인
3. 방화벽 설정 확인
4. Cloud Run 서비스의 `--allow-unauthenticated` 옵션 확인

### 7.5. 타임아웃 오류

**증상:**
```
504 Gateway Timeout
```

**해결:**
1. Cloud Run의 `--timeout` 값을 증가 (최대 300초)
2. 요청하는 데이터 양을 줄이기
3. Cloud Run 인스턴스 사양 증가 (`--memory`, `--cpu`)

---

## 8. 보안 권장사항

### 8.1. 프로덕션 환경

- ✅ CORS에서 특정 도메인만 허용 (와일드카드 `*` 사용 금지)
- ✅ HTTPS 사용 필수
- ✅ 환경변수로 민감한 정보 관리
- ✅ API Rate Limiting 고려

### 8.2. 인증이 필요한 엔드포인트

- 관리자 전용 엔드포인트는 프론트엔드에서 직접 호출하지 않음
- 서버 사이드에서만 호출하거나, 별도의 관리자 페이지에서만 사용

---

## 9. 체크리스트

배포 전 확인사항:

- [ ] CORS 미들웨어 추가됨
- [ ] `ALLOWED_ORIGINS` 환경변수 설정됨
- [ ] Cloud Run 서비스 배포 완료
- [ ] 서비스 URL 확인됨
- [ ] `/health` 엔드포인트 정상 동작 확인
- [ ] 프론트엔드 환경변수 설정됨
- [ ] API 클라이언트 코드 작성됨
- [ ] 테스트 요청 성공 확인

---

## 10. 추가 리소스

- [FastAPI CORS 문서](https://fastapi.tiangolo.com/tutorial/cors/)
- [Cloud Run 문서](https://cloud.google.com/run/docs)
- [Next.js 환경변수](https://nextjs.org/docs/basic-features/environment-variables)
