# Stock Price Updater

Yahoo Finance API를 사용하여 주식 가격을 수집하고 Supabase에 저장하는 Python 백엔드 서비스입니다.

## 기능

- Supabase `managed_stocks` 테이블에서 활성화된 종목 목록 자동 조회
- Yahoo Finance API를 통한 주식 가격 수집
- N+1 문제 방지를 위한 배치 처리 최적화
- 개별 종목 실패 격리 (Resilience)
- Rate limiting 및 재시도 로직

## 프로젝트 구조

```
stock-price-updater/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 애플리케이션
│   ├── yahoo_finance.py     # Yahoo Finance API 클라이언트
│   ├── supabase_client.py   # Supabase 연동
│   ├── rate_limiter.py      # Rate limiting 로직
│   └── config.py            # 설정 관리
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## 로컬 개발

### 1. uv 설치

`uv`가 설치되어 있지 않다면 설치하세요:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 또는 pip로 설치
pip install uv
```

### 2. 환경변수 설정

`.env.example`을 참고하여 `.env` 파일을 생성하고 필요한 값들을 설정하세요.

```bash
cp .env.example .env
# .env 파일을 편집하여 실제 값 입력
```

### 3. 의존성 설치 및 가상환경 생성

```bash
# uv로 프로젝트 초기화 및 의존성 설치
uv sync

# 또는 기존 pip 사용 시
pip install -r requirements.txt
```

### 4. 서버 실행

**uv 사용 (권장)**:
```bash
# 간단한 실행
uv run app

# 개발 모드 (자동 리로드)
uv run dev

# 프로덕션 모드
uv run start

# 또는 직접 실행
uv run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

**또는 일반 Python 사용**:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## API 엔드포인트

### POST /update-prices

주식 가격을 업데이트합니다.

**인증**: Bearer 토큰 필요 (`Authorization: Bearer <CRON_SECRET>`)

**요청 본문** (선택사항):
```json
{
  "symbols": ["AAPL", "MSFT"]
}
```

`symbols`를 제공하지 않으면 `managed_stocks` 테이블에서 활성화된 종목을 자동으로 조회합니다.

**응답**:
```json
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

### POST /sync-apt-sales

공공데이터포털 API를 통해 아파트 실거래가 데이터를 수집하고 Supabase에 저장합니다.

**인증**: Bearer 토큰 필요 (`Authorization: Bearer <CRON_SECRET>`)

**요청 본문** (선택사항):
```json
{
  "lawd_codes": ["11110", "11140"],
  "deal_ym": "202501",
  "priority": 1
}
```

- `lawd_codes`: 법정동코드 리스트 (지정 시 priority 무시)
- `deal_ym`: 거래연월 YYYYMM 형식 (미지정 시 이번 달과 지난달 자동 수집)
- `priority`: 우선순위 필터 (1=최우선, 2=중요까지, 3=일반까지) - 기본값 1

**응답**:
```json
{
  "success": true,
  "total": 1523,
  "upserted": 1520,
  "lawd_codes": ["11110", "11140"],
  "deal_months": ["202412", "202501"],
  "errors": []
}
```

**특징**:
- **우선순위 기반 수집**: priority 1 (서울 주요 구 10개)만 기본 수집하여 API 할당량 보호
- **numOfRows=999**: 한 번에 최대 999건 수집 (기본값 10건 방지)
- MD5 해시 기반 고유 ID로 중복 방지 (아파트명+금액+면적+층+거래일)
- 법정동코드별 독립적 에러 격리
- 이번 달과 지난달 자동 수집으로 데이터 누락 방지
- XML 파싱 및 데이터 정제 (금액 콤마 제거, trim 처리, zfill 날짜 형식)

## Cloud Run 배포

### 1. Docker 이미지 빌드

```bash
docker build -t stock-price-updater .
```

### 2. Google Cloud에 배포

```bash
gcloud run deploy stock-price-updater \
  --source . \
  --platform managed \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --set-env-vars SUPABASE_URL=your_url,SUPABASE_ANON_KEY=your_key,CRON_SECRET=your_secret
```

## Cloud Scheduler 설정

Cloud Scheduler에서 다음 설정으로 Job을 생성하세요:

- **이름**: `update-stock-prices`
- **타겟**: Cloud Run 서비스 URL
- **HTTP 메서드**: POST
- **인증**: Bearer 토큰 (`CRON_SECRET` 값)
- **요청 본문**: 빈 객체 `{}` 또는 생략
- **스케줄**: 예) `0 7 * * *` (매일 오전 7시)

## 성능 최적화

- **N+1 문제 방지**: 모든 종목의 오늘 날짜 데이터를 한 번에 조회
- **메모리 비교**: 실제 API 호출이 필요한 종목만 필터링
- **Rate Limiting**: 최소 200ms 지연, 최대 3개 동시 요청

## 실패 격리

각 종목 처리는 독립적인 try-except 블록으로 보호되어, 한 종목의 실패가 전체 배치 작업을 중단시키지 않습니다.
