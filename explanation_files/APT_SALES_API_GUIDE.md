# 아파트 실거래가 API 가이드

## 개요

공공데이터포털의 아파트 실거래가 API를 사용하여 실거래 데이터를 수집하고 Supabase에 저장하는 기능입니다.

## 테이블 스키마

### apt_sales 테이블

```sql
CREATE TABLE apt_sales (
    id VARCHAR(64) PRIMARY KEY,        -- MD5 해시 기반 고유 ID
    apt_name VARCHAR(255) NOT NULL,     -- 아파트명
    area DECIMAL(10, 2),                -- 전용면적 (㎡)
    floor INTEGER,                      -- 층
    deal_amount BIGINT NOT NULL,        -- 거래금액 (단위: 만원)
    deal_date DATE NOT NULL,            -- 거래일 (YYYY-MM-DD)
    deal_year VARCHAR(4),               -- 거래연도
    deal_month VARCHAR(2),              -- 거래월
    deal_day VARCHAR(2),                -- 거래일
    lawd_code VARCHAR(5),               -- 법정동코드 (5자리)
    locatadd_nm VARCHAR(255),           -- 법정동명 (예: "서울특별시 종로구")
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_apt_sales_deal_date ON apt_sales(deal_date);
CREATE INDEX idx_apt_sales_lawd_code ON apt_sales(lawd_code);
CREATE INDEX idx_apt_sales_apt_name ON apt_sales(apt_name);
CREATE INDEX idx_apt_sales_locatadd_nm ON apt_sales(locatadd_nm);
```

## 환경 변수

`.env` 파일에 다음 환경변수를 추가하세요:

```bash
# 공공데이터포털 API 키
DATA_GO_API_KEY=your_api_key_here
```

## API 엔드포인트

### POST /sync-apt-sales

아파트 실거래가 데이터를 수집하여 Supabase에 저장합니다.

#### 인증

Bearer 토큰 필요:
```
Authorization: Bearer <CRON_SECRET>
```

#### 요청 본문 (선택사항)

```json
{
  "lawd_codes": ["11110", "11140"],
  "deal_ym": "202501",
  "priority": 1
}
```

**파라미터**:
- `lawd_codes` (optional): 법정동코드 리스트
  - 지정 시 priority 무시하고 해당 코드만 수집
  - 미지정 시 `priority` 기준으로 DB 조회
- `deal_ym` (optional): 거래연월 (YYYYMM 형식)
  - 미지정 시 이번 달과 지난달 자동 수집
- `priority` (optional): 우선순위 필터 (기본값: 1)
  - `1`: 최우선 지역만 (서울 주요 구 10개, 약 20회/월)
  - `2`: 1~2순위 (서울 전체, 약 50회/월)
  - `3`: 1~3순위 (서울+경기 주요 시, 약 100회/월)

#### 응답

```json
{
  "success": true,
  "total": 7341,
  "upserted": 7341,
  "new": 5820,
  "updated": 1521,
  "lawd_codes": ["11110", "11140"],
  "deal_months": ["202512", "202601"],
  "errors": []
}
```

**응답 필드**:
- `success`: 전체 성공 여부 (에러가 없으면 true)
- `total`: 수집된 총 레코드 수 (API에서 가져온 데이터)
- `upserted`: Supabase에 저장된 레코드 수
- `new`: 신규로 추가된 데이터 개수 ✨
- `updated`: 기존 데이터를 업데이트한 개수 ✨
- `lawd_codes`: 처리된 법정동코드 리스트
- `deal_months`: 처리된 연월 리스트
- `errors`: 에러 메시지 리스트

> **💡 Tip**: `new`와 `updated` 값으로 중복 수집 여부를 확인할 수 있습니다.
> - `new > 0`: 새로운 거래 데이터가 추가됨
> - `updated > 0`: 기존 데이터가 업데이트됨 (재수집)

## 사용 예시

### 1. 기본 (1순위만 수집 - 권장)

```bash
curl -X POST "http://localhost:8080/sync-apt-sales" \
  -H "Authorization: Bearer your_cron_secret" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 2. 1~2순위 수집 (서울 전체)

```bash
curl -X POST "http://localhost:8080/sync-apt-sales" \
  -H "Authorization: Bearer your_cron_secret" \
  -H "Content-Type: application/json" \
  -d '{"priority": 2}'
```

### 3. 특정 법정동코드만 수집

```bash
curl -X POST "http://localhost:8080/sync-apt-sales" \
  -H "Authorization: Bearer your_cron_secret" \
  -H "Content-Type: application/json" \
  -d '{
    "lawd_codes": ["11110", "11140"]
  }'
```

### 4. 특정 연월 지정

```bash
curl -X POST "http://localhost:8080/sync-apt-sales" \
  -H "Authorization: Bearer your_cron_secret" \
  -H "Content-Type: application/json" \
  -d '{
    "deal_ym": "202412"
  }'
```

### 5. 법정동코드와 연월 모두 지정

```bash
curl -X POST "http://localhost:8080/sync-apt-sales" \
  -H "Authorization: Bearer your_cron_secret" \
  -H "Content-Type: application/json" \
  -d '{
    "lawd_codes": ["11110"],
    "deal_ym": "202412"
  }'
```

## 데이터 흐름

```
1. API 요청 수신
   ↓
2. 인증 확인 (CRON_SECRET)
   ↓
3. 법정동코드 결정
   - 요청에 있으면 사용
   - 없으면 DB에서 전체 조회
   ↓
4. 거래연월 결정
   - 요청에 있으면 사용
   - 없으면 이번 달 + 지난달
   ↓
5. 각 법정동코드 × 연월 조합으로 처리
   ├─ 공공데이터 API 호출
   ├─ XML 파싱
   ├─ 데이터 정제
   │  ├─ dealAmount: 콤마 제거, 정수 변환
   │  └─ 모든 필드: trim (공백 제거)
   ├─ MD5 해시 ID 생성
   └─ Supabase upsert
   ↓
6. 결과 집계 및 응답
```

## 핵심 기능

### 1. 고유 ID 생성

MD5 해시를 사용하여 중복을 방지합니다:

```python
unique_str = f"{apt_name}_{deal_amount}_{area}_{floor}_{deal_date}"
id = hashlib.md5(unique_str.encode('utf-8')).hexdigest()
```

예시:
- 아파트명: "래미안아파트"
- 거래금액: 50000 (만원)
- 면적: 84.5 (㎡)
- 층: 10
- 거래일: "2025-01-15"
- 생성된 ID: `a3f5e8c9d1b2...` (64자리 MD5 해시)

### 2. 데이터 정제

공공데이터 API의 응답 데이터를 정제합니다:

```python
# 거래금액: 콤마 제거 및 정수 변환
deal_amount_str = "50,000"
deal_amount = int(deal_amount_str.replace(',', '').replace(' ', ''))
# 결과: 50000

# 모든 필드 trim
apt_name = "  래미안아파트  ".strip()
# 결과: "래미안아파트"
```

### 3. 증분 수집

데이터 누락을 방지하기 위해 이번 달과 지난달 데이터를 수집합니다:

```python
def get_target_months():
    now = datetime.now()
    current_month = now.strftime('%Y%m')  # 예: "202501"
    last_month = (now - timedelta(days=30)).strftime('%Y%m')  # 예: "202412"
    return [last_month, current_month]
```

### 4. 에러 격리

각 법정동코드별로 독립적으로 처리하여, 일부 실패해도 전체 작업이 중단되지 않습니다:

```python
# 법정동코드 11110 실패해도 11140은 계속 처리됨
for lawd_code in lawd_codes:
    try:
        # 처리 로직
    except Exception as e:
        errors.append(f"{lawd_code}: {str(e)}")
        continue  # 다음 법정동코드로 계속
```

## 법정동코드 우선순위 관리

### bjd_code 테이블

법정동코드는 Supabase의 `bjd_code` 테이블에서 `priority` 컬럼으로 관리됩니다:

```sql
SELECT region_cd_5, locatadd_nm, priority
FROM bjd_code
WHERE priority IS NOT NULL
ORDER BY priority, region_cd_5;

-- 예시 데이터:
-- region_cd_5 | locatadd_nm        | priority
-- 11110       | 서울특별시 종로구   | 1
-- 11140       | 서울특별시 중구     | 1
-- 11170       | 서울특별시 용산구   | 1
-- 11680       | 서울특별시 강북구   | 2
-- 41110       | 경기도 수원시       | 3
```

### 우선순위 정책

- **Priority 1 (최우선)**: 서울시 주요 구 10개
  - 강남, 서초, 송파, 강동, 마포, 용산, 종로, 중구, 영등포, 강서
  - API 호출: 약 20회/월

- **Priority 2 (중요)**: 서울시 나머지 구 15개
  - API 호출: 약 50회/월 (누적)

- **Priority 3 (일반)**: 경기도 주요 시
  - 수원, 성남, 고양, 용인, 부천, 안산, 남양주, 화성
  - API 호출: 약 100회/월 (누적)

- **Priority null**: 수집 제외

### 우선순위 설정 예시

```sql
-- 새로운 지역을 1순위로 추가
UPDATE bjd_code SET priority = 1 WHERE region_cd_5 = '11545';  -- 금천구

-- 특정 지역을 2순위로 변경
UPDATE bjd_code SET priority = 2 WHERE region_cd_5 = '11230';  -- 동대문구

-- 특정 지역 수집 제외
UPDATE bjd_code SET priority = NULL WHERE region_cd_5 = '11200';  -- 성동구
```

## 공공데이터포털 API

### API 정보

- **API 이름**: 국토교통부 아파트매매 실거래 상세 자료
- **서비스 URL**: `https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade`
- **인증 방식**: Service Key (URL 파라미터)

### 요청 파라미터

- `serviceKey`: 공공데이터포털에서 발급받은 API 키
- `LAWD_CD`: 법정동코드 (5자리)
- `DEAL_YMD`: 거래연월 (YYYYMM)

### 응답 예시

```xml
<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>00</resultCode>
    <resultMsg>NORMAL SERVICE.</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <거래금액>50,000</거래금액>
        <거래일>15</거래일>
        <거래월>01</거래월>
        <거래년도>2025</거래년도>
        <아파트>래미안아파트</아파트>
        <전용면적>84.5</전용면적>
        <층>10</층>
      </item>
    </items>
  </body>
</response>
```

## 에러 처리

### 1. API 호출 실패

```python
# API 호출 실패 시 에러 메시지 반환
{
  "success": false,
  "errors": [
    "11110/202501: API 호출 실패 - Connection timeout"
  ]
}
```

### 2. XML 파싱 오류

```python
# XML 파싱 실패 시 에러 메시지 반환
{
  "success": false,
  "errors": [
    "11110/202501: XML 파싱 오류 - Invalid XML format"
  ]
}
```

### 3. Slack 알림

에러 발생 시 Slack으로 자동 알림이 전송됩니다 (SLACK_WEBHOOK_URL이 설정된 경우).

## Cloud Scheduler 설정

매일 자동으로 아파트 실거래가를 수집하려면 Cloud Scheduler를 설정하세요:

```bash
gcloud scheduler jobs create http sync-apt-sales \
  --location=asia-northeast3 \
  --schedule="0 8 * * *" \
  --uri="https://YOUR_SERVICE_URL/sync-apt-sales" \
  --http-method=POST \
  --headers="Authorization=Bearer YOUR_CRON_SECRET" \
  --headers="Content-Type=application/json" \
  --message-body='{}' \
  --time-zone="Asia/Seoul"
```

- 매일 오전 8시에 실행
- 전체 법정동코드에 대해 이번 달과 지난달 데이터 수집

## 성능 최적화

### 1. 병렬 처리

법정동코드별로 병렬 처리하여 수집 속도를 향상시킵니다:

```python
tasks = [
    process_combination(code, ym)
    for code in lawd_codes
    for ym in target_months
]
await asyncio.gather(*tasks)
```

### 2. Upsert 최적화

MD5 해시 ID를 사용하여 중복 체크 없이 바로 upsert합니다:

```python
supabase.table("apt_sales").upsert(records, on_conflict="id").execute()
```

## 주의사항

1. **API 키 관리**: 공공데이터포털 API 키는 외부 노출 금지
2. **Rate Limiting**: 공공데이터포털 API는 일일 호출 제한이 있을 수 있음
3. **법정동코드**: 행정구역 개편 시 법정동코드가 변경될 수 있음
4. **데이터 지연**: 실거래가 데이터는 신고 후 반영까지 시간이 걸림
