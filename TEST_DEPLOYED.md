# 배포된 서비스 테스트 가이드

배포된 Cloud Run 서비스를 테스트하는 방법입니다.

## 1. 서비스 URL 확인

먼저 배포된 서비스의 URL을 확인하세요:

```bash
# Cloud Run 서비스 URL 확인
gcloud run services describe stock-price-updater \
  --region asia-northeast3 \
  --format 'value(status.url)'
```

또는 Google Cloud Console에서:
1. Cloud Run 메뉴로 이동
2. `stock-price-updater` 서비스 선택
3. 상단의 URL 복사

예시 URL: `https://stock-price-updater-xxxxx-xx.a.run.app`

## 2. 헬스체크 테스트

가장 간단한 테스트부터 시작합니다:

### 브라우저에서 테스트
```
https://YOUR_SERVICE_URL/health
```

예상 응답:
```json
{
  "status": "healthy"
}
```

### curl로 테스트
```bash
curl https://YOUR_SERVICE_URL/health
```

### 응답 확인
- ✅ `200 OK` + `{"status": "healthy"}` → 서비스 정상 작동
- ❌ `404 Not Found` → URL이 잘못되었거나 라우트가 등록되지 않음
- ❌ `502 Bad Gateway` → 서비스가 시작되지 않았거나 오류 발생

## 3. 주식 가격 업데이트 API 테스트

### 3.1 환경변수 설정 (선택사항)

테스트를 쉽게 하기 위해 환경변수로 설정:

```bash
# .env 파일 생성 또는 환경변수 설정
export SERVICE_URL="https://YOUR_SERVICE_URL"
export CRON_SECRET="your_cron_secret"
```

### 3.2 전체 종목 업데이트 테스트

DB의 `managed_stocks` 테이블에서 활성화된 종목을 자동으로 조회하여 업데이트:

```bash
curl -X POST https://YOUR_SERVICE_URL/update-prices \
  -H "Authorization: Bearer YOUR_CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 3.3 특정 종목만 테스트

특정 심볼만 지정하여 테스트 (빠르고 안전):

```bash
curl -X POST https://YOUR_SERVICE_URL/update-prices \
  -H "Authorization: Bearer YOUR_CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL", "MSFT", "GOOGL"]}'
```

### 3.4 국가별 필터 테스트

특정 국가의 종목만 업데이트:

```bash
curl -X POST https://YOUR_SERVICE_URL/update-prices \
  -H "Authorization: Bearer YOUR_CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"country": "US"}'
```

### 3.5 예상 응답

성공 시:
```json
{
  "success": true,
  "total": 3,
  "successCount": 3,
  "failureCount": 0,
  "results": [
    {"symbol": "AAPL", "success": true},
    {"symbol": "MSFT", "success": true},
    {"symbol": "GOOGL", "success": true}
  ]
}
```

일부 실패 시:
```json
{
  "success": true,
  "total": 3,
  "successCount": 2,
  "failureCount": 1,
  "results": [
    {"symbol": "AAPL", "success": true},
    {"symbol": "MSFT", "success": true},
    {"symbol": "INVALID", "success": false, "error": "가격 정보를 찾을 수 없습니다."}
  ]
}
```

## 4. 오류 상황 테스트

### 4.1 인증 오류 테스트

잘못된 토큰으로 요청:

```bash
curl -X POST https://YOUR_SERVICE_URL/update-prices \
  -H "Authorization: Bearer wrong_token" \
  -H "Content-Type: application/json" \
  -d '{}'
```

예상 응답:
```json
{
  "detail": "Unauthorized"
}
```

### 4.2 토큰 없이 요청

```bash
curl -X POST https://YOUR_SERVICE_URL/update-prices \
  -H "Content-Type: application/json" \
  -d '{}'
```

예상 응답:
```json
{
  "detail": "Authorization header required"
}
```

### 4.3 잘못된 JSON 형식

```bash
curl -X POST https://YOUR_SERVICE_URL/update-prices \
  -H "Authorization: Bearer YOUR_CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{invalid json}'
```

예상 응답:
```json
{
  "detail": "JSON 파싱 오류: ..."
}
```

## 5. 로그 확인

### 5.1 Cloud Run 로그 실시간 확인

```bash
gcloud logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=stock-price-updater" \
  --format json
```

### 5.2 최근 로그 조회

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=stock-price-updater" \
  --limit 50 \
  --format json
```

### 5.3 특정 시간대 로그 조회

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=stock-price-updater AND timestamp>=\"2024-01-01T00:00:00Z\"" \
  --limit 100 \
  --format json
```

### 5.4 Google Cloud Console에서 확인

1. Google Cloud Console → Cloud Run
2. `stock-price-updater` 서비스 선택
3. "로그" 탭 클릭
4. 실시간 로그 확인

## 6. Supabase 데이터 확인

### 6.1 오늘 날짜 데이터 확인

```sql
SELECT
  symbol,
  close_price,
  currency,
  name,
  change_percent,
  date,
  created_at
FROM stock_prices
WHERE date = CURRENT_DATE
ORDER BY symbol;
```

### 6.2 특정 심볼 확인

```sql
SELECT *
FROM stock_prices
WHERE symbol = 'AAPL'
ORDER BY date DESC
LIMIT 10;
```

### 6.3 최근 업데이트된 종목 확인

```sql
SELECT
  symbol,
  close_price,
  date,
  created_at
FROM stock_prices
WHERE created_at >= NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;
```

## 7. 종합 테스트 스크립트

다음 스크립트를 사용하여 전체 테스트를 한 번에 실행할 수 있습니다:

```bash
#!/bin/bash

# 환경변수 설정
SERVICE_URL="https://YOUR_SERVICE_URL"
CRON_SECRET="YOUR_CRON_SECRET"

echo "=== 1. 헬스체크 테스트 ==="
curl -s "${SERVICE_URL}/health"
echo -e "\n"

echo "=== 2. 인증 오류 테스트 ==="
curl -s -X POST "${SERVICE_URL}/update-prices" \
  -H "Authorization: Bearer wrong_token" \
  -H "Content-Type: application/json" \
  -d '{}'
echo -e "\n"

echo "=== 3. 특정 종목 업데이트 테스트 ==="
curl -s -X POST "${SERVICE_URL}/update-prices" \
  -H "Authorization: Bearer ${CRON_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL", "MSFT"]}'
echo -e "\n"

echo "=== 테스트 완료 ==="
```

스크립트를 저장하고 실행:

```bash
chmod +x test_deployed.sh
./test_deployed.sh
```

## 8. 성능 테스트

### 8.1 응답 시간 측정

```bash
time curl -X POST https://YOUR_SERVICE_URL/update-prices \
  -H "Authorization: Bearer YOUR_CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]}'
```

### 8.2 동시 요청 테스트

```bash
# 5개의 동시 요청
for i in {1..5}; do
  curl -X POST https://YOUR_SERVICE_URL/update-prices \
    -H "Authorization: Bearer YOUR_CRON_SECRET" \
    -H "Content-Type: application/json" \
    -d '{"symbols": ["AAPL"]}' &
done
wait
```

## 9. 트러블슈팅

### 문제: 401 Unauthorized
- ✅ `CRON_SECRET` 환경변수가 올바른지 확인
- ✅ Authorization 헤더 형식 확인: `Bearer YOUR_CRON_SECRET`
- ✅ Cloud Run 환경변수 확인: `gcloud run services describe stock-price-updater --region asia-northeast3`

### 문제: 500 Internal Server Error
- ✅ Cloud Run 로그 확인
- ✅ Supabase 연결 확인 (URL, 키)
- ✅ 환경변수 누락 확인

### 문제: 타임아웃
- ✅ Cloud Run 타임아웃 설정 확인 (기본 300초)
- ✅ 종목 수가 너무 많은지 확인
- ✅ Rate limiting 설정 확인

### 문제: 데이터가 저장되지 않음
- ✅ Supabase 테이블 권한 확인
- ✅ `stock_prices` 테이블 스키마 확인
- ✅ 로그에서 에러 메시지 확인

## 10. 모니터링 설정

### 10.1 Cloud Monitoring 알림 설정

중요한 메트릭에 대한 알림을 설정하세요:

```bash
# 에러율 알림
gcloud alpha monitoring policies create \
  --notification-channels=YOUR_CHANNEL_ID \
  --display-name="Stock Price Updater - High Error Rate" \
  --condition-display-name="Error rate > 5%" \
  --condition-threshold-value=0.05 \
  --condition-threshold-duration=300s
```

### 10.2 Cloud Run 메트릭 확인

Google Cloud Console에서:
1. Cloud Run → stock-price-updater
2. "메트릭" 탭에서 확인:
   - 요청 수
   - 응답 시간
   - 에러율
   - 인스턴스 수
