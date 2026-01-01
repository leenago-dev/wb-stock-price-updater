# 테스트 가이드

## 로컬 환경 테스트

### 1. 환경변수 설정

`.env` 파일을 생성하고 다음 값들을 설정하세요:

```bash
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key
CRON_SECRET=your_secret_key
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. Supabase 테이블 확인

`managed_stocks` 테이블에 테스트 데이터를 추가하세요:

```sql
INSERT INTO managed_stocks (symbol, name, enabled) VALUES
  ('AAPL', 'Apple Inc.', true),
  ('MSFT', 'Microsoft Corporation', true),
  ('GOOGL', 'Alphabet Inc.', true);
```

### 4. 서버 실행

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### 5. API 테스트

#### 헬스체크

```bash
curl http://localhost:8080/health
```

#### 주식 가격 업데이트 (Bearer 토큰 필요)

```bash
curl -X POST http://localhost:8080/update-prices \
  -H "Authorization: Bearer your_secret_key" \
  -H "Content-Type: application/json" \
  -d '{}'
```

또는 특정 심볼만 테스트:

```bash
curl -X POST http://localhost:8080/update-prices \
  -H "Authorization: Bearer your_secret_key" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL", "MSFT"]}'
```

### 6. 로그 확인

서버 로그에서 다음을 확인하세요:
- 활성화된 종목 조회 성공
- 오늘 날짜 데이터 조회 성공
- API 호출이 필요한 종목만 필터링됨
- 각 종목 처리 성공/실패 로그
- 실패 격리 동작 (한 종목 실패가 전체를 중단시키지 않음)

### 7. Supabase 확인

`stock_prices` 테이블에서 오늘 날짜 데이터가 저장되었는지 확인:

```sql
SELECT * FROM stock_prices
WHERE date = CURRENT_DATE
ORDER BY symbol;
```

## 테스트 시나리오

### 시나리오 1: 정상 동작

1. `managed_stocks`에 활성화된 종목 3개 추가
2. API 호출
3. 모든 종목이 성공적으로 저장되는지 확인

### 시나리오 2: 중복 데이터 처리

1. 이미 오늘 날짜 데이터가 있는 종목 포함
2. API 호출
3. 중복 체크가 작동하여 불필요한 API 호출이 없는지 확인

### 시나리오 3: 실패 격리

1. 잘못된 심볼 (예: "INVALID") 추가
2. 정상 심볼과 함께 API 호출
3. 잘못된 심볼은 실패하지만 정상 심볼은 성공하는지 확인

### 시나리오 4: N+1 문제 방지

1. `managed_stocks`에 100개 종목 추가
2. API 호출
3. 로그에서 DB 쿼리가 2번만 발생하는지 확인:
   - `managed_stocks` 조회 1번
   - `stock_prices` 오늘 날짜 조회 1번
