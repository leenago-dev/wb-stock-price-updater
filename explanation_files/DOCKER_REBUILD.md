# Docker 이미지 재빌드 및 재시작 가이드

## 문제 상황

`/sync-exchange-rates` 엔드포인트가 보이지 않는 경우, Docker 이미지가 오래된 코드로 빌드되었을 가능성이 높습니다.

## 해결 방법

### 1단계: 기존 컨테이너 중지 및 삭제

```bash
# 컨테이너 중지
docker stop stock

# 컨테이너 삭제
docker rm stock
```

### 2단계: 이미지 재빌드

```bash
# 프로젝트 디렉토리로 이동
cd /Users/leena/Desktop/dev/side-project/backend/wb-stock-price-updater

# 이미지 재빌드 (캐시 없이)
docker build --no-cache -t stock-price-updater:latest .
```

또는 캐시를 사용하여 빠르게 빌드:

```bash
docker build -t stock-price-updater:latest .
```

### 3단계: 새 컨테이너 실행

```bash
docker run -d \
  --name stock \
  -p 8080:8080 \
  --env-file .env \
  stock-price-updater:latest
```

### 4단계: 엔드포인트 확인

```bash
# 모든 엔드포인트 확인
curl -s http://localhost:8080/openapi.json | python3 -c "import json, sys; data = json.load(sys.stdin); paths = data.get('paths', {}); print('등록된 엔드포인트:'); [print(f'  {method.upper()} {path}') for path, methods in paths.items() for method in methods.keys()]"
```

**예상 출력**:
```
등록된 엔드포인트:
  GET /health
  GET /exchange-rates/{symbol_or_name}
  GET /exchange-rates/{symbol_or_name}/history
  GET /stocks-name/{symbol}
  POST /sync-exchange-rates
  POST /sync-stocks-name
  POST /update-prices
```

### 5단계: 로그 확인

```bash
# 서버 시작 로그 확인
docker logs stock

# 실시간 로그 확인
docker logs -f stock
```

## 빠른 재빌드 스크립트

한 번에 실행:

```bash
cd /Users/leena/Desktop/dev/side-project/backend/wb-stock-price-updater

# 기존 컨테이너 정리
docker stop stock 2>/dev/null || true
docker rm stock 2>/dev/null || true

# 이미지 재빌드
docker build -t stock-price-updater:latest .

# 새 컨테이너 실행
docker run -d \
  --name stock \
  -p 8080:8080 \
  --env-file .env \
  stock-price-updater:latest

# 로그 확인
docker logs -f stock
```

## 문제 해결

### 여전히 엔드포인트가 보이지 않는 경우

1. **코드가 제대로 복사되었는지 확인**:
```bash
docker exec stock ls -la /app/app/api/routes.py
docker exec stock grep -n "sync-exchange-rates" /app/app/api/routes.py
```

2. **서버 시작 시 에러 확인**:
```bash
docker logs stock 2>&1 | grep -i "error\|exception\|traceback"
```

3. **Python 모듈 import 확인**:
```bash
docker exec stock python -c "from app.api.routes import router; print([r.path for r in router.routes])"
```

4. **직접 테스트**:
```bash
# 인증 없이 테스트 (401이 나와야 정상)
curl -X POST http://localhost:8080/sync-exchange-rates \
  -H "Content-Type: application/json" \
  -d '{}'
```

**예상 응답**: `401 Unauthorized` (엔드포인트는 존재하지만 인증이 필요함)

## 주의사항

- `.env` 파일이 있는지 확인하세요
- 환경변수가 올바르게 설정되었는지 확인하세요
- 빌드 시 코드 변경사항이 반영되었는지 확인하세요
