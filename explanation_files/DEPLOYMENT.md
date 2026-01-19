# 배포 가이드

## Cloud Run 배포

### 1. Google Cloud 프로젝트 설정

```bash
# Google Cloud CLI 로그인
gcloud auth login

# 프로젝트 설정
gcloud config set project YOUR_PROJECT_ID
```

### 2. Docker 이미지 빌드 및 푸시

```bash
# Artifact Registry에 리포지토리 생성 (최초 1회)
gcloud artifacts repositories create stock-price-updater \
  --repository-format=docker \
  --location=asia-northeast3

# 이미지 빌드
docker build -t asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/stock-price-updater/stock-price-updater:latest .

# 인증
gcloud auth configure-docker asia-northeast3-docker.pkg.dev

# 이미지 푸시
docker push asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/stock-price-updater/stock-price-updater:latest
```

### 3. Cloud Run 서비스 배포

```bash
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

또는 Secret Manager 사용 (권장):

```bash
# Secret 생성
echo -n "your_supabase_url" | gcloud secrets create supabase-url --data-file=-
echo -n "your_supabase_anon_key" | gcloud secrets create supabase-anon-key --data-file=-
echo -n "your_cron_secret" | gcloud secrets create cron-secret --data-file=-

# Secret에 접근 권한 부여
gcloud secrets add-iam-policy-binding supabase-url \
  --member="serviceAccount:YOUR_SERVICE_ACCOUNT@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Cloud Run 배포 (Secret 사용)
gcloud run deploy stock-price-updater \
  --image asia-northeast3-docker.pkg.dev/YOUR_PROJECT_ID/stock-price-updater/stock-price-updater:latest \
  --platform managed \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --set-secrets SUPABASE_URL=supabase-url:latest,SUPABASE_ANON_KEY=supabase-anon-key:latest,CRON_SECRET=cron-secret:latest \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 1
```

### 4. 서비스 URL 확인

배포 후 서비스 URL을 확인하세요:

```bash
gcloud run services describe stock-price-updater \
  --region asia-northeast3 \
  --format 'value(status.url)'
```

## Cloud Scheduler 설정

### 1. Scheduler Job 생성

```bash
gcloud scheduler jobs create http update-stock-prices \
  --location=asia-northeast3 \
  --schedule="0 7 * * *" \
  --uri="https://YOUR_SERVICE_URL/update-prices" \
  --http-method=POST \
  --headers="Authorization=Bearer YOUR_CRON_SECRET" \
  --headers="Content-Type=application/json" \
  --message-body='{}' \
  --time-zone="Asia/Seoul"
```

### 2. 여러 스케줄 설정 (예: 오전 7시, 오후 4시)

```bash
# 오전 7시
gcloud scheduler jobs create http update-stock-prices-morning \
  --location=asia-northeast3 \
  --schedule="0 7 * * *" \
  --uri="https://YOUR_SERVICE_URL/update-prices" \
  --http-method=POST \
  --headers="Authorization=Bearer YOUR_CRON_SECRET" \
  --headers="Content-Type=application/json" \
  --message-body='{}' \
  --time-zone="Asia/Seoul"

# 오후 4시
gcloud scheduler jobs create http update-stock-prices-evening \
  --location=asia-northeast3 \
  --schedule="0 16 * * *" \
  --uri="https://YOUR_SERVICE_URL/update-prices" \
  --http-method=POST \
  --headers="Authorization=Bearer YOUR_CRON_SECRET" \
  --headers="Content-Type=application/json" \
  --message-body='{}' \
  --time-zone="Asia/Seoul"
```

### 3. Job 테스트

```bash
gcloud scheduler jobs run update-stock-prices --location=asia-northeast3
```

### 4. Job 목록 확인

```bash
gcloud scheduler jobs list --location=asia-northeast3
```

### 5. Job 삭제

```bash
gcloud scheduler jobs delete update-stock-prices --location=asia-northeast3
```

## 모니터링

### Cloud Run 로그 확인

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=stock-price-updater" \
  --limit 50 \
  --format json
```

### Cloud Scheduler 실행 이력 확인

Google Cloud Console에서:
1. Cloud Scheduler 메뉴로 이동
2. Job 선택
3. "실행 기록" 탭에서 실행 이력 확인

## 트러블슈팅

### 인증 오류

- `CRON_SECRET`이 Cloud Scheduler의 Bearer 토큰과 일치하는지 확인
- Cloud Run 서비스의 환경변수 확인

### 타임아웃 오류

- Cloud Run의 `--timeout` 값을 증가 (최대 300초)
- 종목 수가 많으면 배치 크기를 줄이거나 인스턴스 사양 증가

### 메모리 부족

- Cloud Run의 `--memory` 값을 증가 (예: 1Gi)
- Rate limiting 설정 조정
