# Cloud Scheduler 404 오류 해결 가이드

## 문제
Cloud Scheduler가 `POST /` 경로로 요청을 보내서 404 Not Found 오류가 발생합니다.

## 원인
Cloud Scheduler Job의 URI 설정이 잘못되었습니다. 실제 API 엔드포인트는 `/update-prices`인데, Job이 `/`로 요청을 보내고 있습니다.

## 해결 방법

### 1. 현재 Job 설정 확인

```bash
gcloud scheduler jobs describe update-stock-prices \
  --location=asia-northeast3
```

또는 Google Cloud Console에서:
1. Cloud Scheduler 메뉴로 이동
2. `update-stock-prices` Job 선택
3. "구성" 탭에서 URI 확인

### 2. Job URI 수정

#### 방법 A: gcloud CLI로 수정

```bash
# 서비스 URL 확인
SERVICE_URL=$(gcloud run services describe stock-price-updater \
  --region asia-northeast3 \
  --format 'value(status.url)')

# Job URI 수정
gcloud scheduler jobs update http update-stock-prices \
  --location=asia-northeast3 \
  --uri="${SERVICE_URL}/update-prices"
```

#### 방법 B: Google Cloud Console에서 수정

1. Cloud Scheduler 메뉴로 이동
2. `update-stock-prices` Job 선택
3. "편집" 클릭
4. "URL" 필드 확인:
   - ❌ 잘못된 예: `https://stock-price-updater-xxx.a.run.app`
   - ✅ 올바른 예: `https://stock-price-updater-xxx.a.run.app/update-prices`
5. URI 끝에 `/update-prices` 추가
6. "업데이트" 클릭

### 3. Job 테스트

수정 후 즉시 테스트:

```bash
gcloud scheduler jobs run update-stock-prices \
  --location=asia-northeast3
```

### 4. 로그 확인

테스트 후 로그에서 확인:

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=stock-price-updater" \
  --limit 10 \
  --format json
```

성공 시:
- `POST /update-prices HTTP/1.1" 200 OK` 또는
- `POST /update-prices HTTP/1.1" 401 Unauthorized` (인증 문제인 경우)

## 추가 확인 사항

### 인증 헤더 확인

Job의 인증 헤더도 확인하세요:

```bash
gcloud scheduler jobs describe update-stock-prices \
  --location=asia-northeast3 \
  --format="yaml(httpTarget)"
```

다음과 같이 설정되어 있어야 합니다:
```yaml
httpTarget:
  headers:
    Authorization: 'Bearer YOUR_CRON_SECRET'
    Content-Type: 'application/json'
  httpMethod: POST
  uri: 'https://YOUR_SERVICE_URL/update-prices'
```

### 전체 Job 재생성 (필요시)

문제가 계속되면 Job을 삭제하고 다시 생성:

```bash
# 기존 Job 삭제
gcloud scheduler jobs delete update-stock-prices \
  --location=asia-northeast3

# 서비스 URL 확인
SERVICE_URL=$(gcloud run services describe stock-price-updater \
  --region asia-northeast3 \
  --format 'value(status.url)')

# 새 Job 생성
gcloud scheduler jobs create http update-stock-prices \
  --location=asia-northeast3 \
  --schedule="0 7 * * *" \
  --uri="${SERVICE_URL}/update-prices" \
  --http-method=POST \
  --headers="Authorization=Bearer YOUR_CRON_SECRET" \
  --headers="Content-Type=application/json" \
  --message-body='{}' \
  --time-zone="Asia/Seoul"
```

## 예방 방법

앞으로 Job을 생성할 때 항상 전체 URL을 사용하세요:

```bash
# ✅ 올바른 방법
--uri="https://stock-price-updater-xxx.a.run.app/update-prices"

# ❌ 잘못된 방법
--uri="https://stock-price-updater-xxx.a.run.app"
```
