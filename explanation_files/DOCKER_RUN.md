# Docker 이미지 실행 가이드

## 기본 실행 방법

### 1. 환경변수 직접 전달 (가장 간단)

```bash
docker run -d \
  --name stock-price-updater \
  -p 8080:8080 \
  -e SUPABASE_URL="your_supabase_url" \
  -e SUPABASE_ANON_KEY="your_supabase_anon_key" \
  -e CRON_SECRET="your_cron_secret" \
  stock-price-updater:latest
```

**옵션 설명**:
- `-d`: 백그라운드 실행 (detached mode)
- `--name stock-price-updater`: 컨테이너 이름 지정
- `-p 8080:8080`: 호스트 포트 8080을 컨테이너 포트 8080에 매핑
- `-e`: 환경변수 설정
- `stock-price-updater:latest`: 이미지 이름 (빌드 시 지정한 이름)

### 2. .env 파일 사용 (권장)

`.env` 파일이 있다면:

```bash
docker run -d \
  --name stock-price-updater \
  -p 8080:8080 \
  --env-file .env \
  stock-price-updater:latest
```

**`.env` 파일 예시**:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
CRON_SECRET=your_cron_secret_here
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... (선택사항)
```

### 3. 선택적 환경변수 포함

```bash
docker run -d \
  --name stock-price-updater \
  -p 8080:8080 \
  -e SUPABASE_URL="your_supabase_url" \
  -e SUPABASE_ANON_KEY="your_supabase_anon_key" \
  -e CRON_SECRET="your_cron_secret" \
  -e SLACK_WEBHOOK_URL="your_slack_webhook_url" \
  -e STOCK_SYMBOLS="AAPL,MSFT,GOOGL" \
  stock-price-updater:latest
```

## 컨테이너 관리

### 실행 중인 컨테이너 확인

```bash
docker ps
```

### 로그 확인

```bash
# 실시간 로그 보기
docker logs -f stock-price-updater

# 최근 100줄만 보기
docker logs --tail 100 stock-price-updater
```

### 컨테이너 중지

```bash
docker stop stock-price-updater
```

### 컨테이너 시작 (중지된 컨테이너 재시작)

```bash
docker start stock-price-updater
```

### 컨테이너 삭제

```bash
# 먼저 중지
docker stop stock-price-updater

# 삭제
docker rm stock-price-updater
```

### 컨테이너 재시작

```bash
docker restart stock-price-updater
```

## 테스트

### 헬스체크

```bash
curl http://localhost:8080/health
```

**예상 응답**:
```json
{"status":"healthy"}
```

### API 테스트

```bash
# 환율 조회 (인증 불필요)
curl http://localhost:8080/exchange-rates/USD/KRW

# 종목 정보 조회
curl http://localhost:8080/stocks-name/AAPL
```

## 포트 변경

다른 포트를 사용하려면:

```bash
docker run -d \
  --name stock-price-updater \
  -p 3000:8080 \
  -e SUPABASE_URL="your_supabase_url" \
  -e SUPABASE_ANON_KEY="your_supabase_anon_key" \
  -e CRON_SECRET="your_cron_secret" \
  stock-price-updater:latest
```

이 경우 `http://localhost:3000`으로 접속합니다.

## 문제 해결

### 포트가 이미 사용 중인 경우

```bash
# 포트 사용 중인 프로세스 확인
lsof -i :8080

# 또는
netstat -an | grep 8080
```

**해결 방법**:
1. 다른 포트 사용: `-p 3000:8080`
2. 기존 프로세스 종료
3. 다른 컨테이너 이름 사용

### 환경변수 확인

```bash
# 컨테이너 내부 환경변수 확인
docker exec stock-price-updater env
```

### 컨테이너 내부 접속

```bash
docker exec -it stock-price-updater /bin/bash
```

### 이미지 이름 확인

빌드 시 이미지 이름을 확인하려면:

```bash
docker images
```

출력에서 이미지 이름을 확인하고 위 명령어의 `stock-price-updater:latest` 부분을 실제 이미지 이름으로 변경하세요.

## Docker Compose 사용 (선택사항)

더 편리한 관리를 위해 `docker-compose.yml` 파일을 만들 수 있습니다:

```yaml
version: '3.8'

services:
  stock-price-updater:
    image: stock-price-updater:latest
    container_name: stock-price-updater
    ports:
      - "8080:8080"
    env_file:
      - .env
    restart: unless-stopped
```

**실행**:
```bash
docker-compose up -d
```

**중지**:
```bash
docker-compose down
```

**로그 확인**:
```bash
docker-compose logs -f
```

## 빠른 참조

### 전체 실행 명령어 (한 줄)

```bash
docker run -d --name stock-price-updater -p 8080:8080 --env-file .env stock-price-updater:latest
```

### 로그 확인

```bash
docker logs -f stock-price-updater
```

### 중지 및 삭제

```bash
docker stop stock-price-updater && docker rm stock-price-updater
```
