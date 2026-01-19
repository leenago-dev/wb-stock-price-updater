#!/bin/bash

# POST /sync-stocks-name API 테스트 스크립트
#
# 사용법:
#   1. 환경변수 설정:
#      export API_URL="http://localhost:8080"  # 또는 실제 서버 URL
#      export CRON_SECRET="your_cron_secret_value"
#
#   2. 실행:
#      bash test_sync_stock_names.sh
#
# 또는 직접 값 지정:
#   bash test_sync_stock_names.sh http://localhost:8080 your_cron_secret

# 기본값 설정
API_URL="${1:-${API_URL:-http://localhost:8080}}"
CRON_SECRET="${2:-${CRON_SECRET}}"

if [ -z "$CRON_SECRET" ]; then
    echo "❌ 오류: CRON_SECRET이 설정되지 않았습니다."
    echo "   환경변수로 설정하거나 인자로 전달하세요:"
    echo "   export CRON_SECRET='your_secret'"
    echo "   또는"
    echo "   bash test_sync_stock_names.sh $API_URL your_secret"
    exit 1
fi

echo "🚀 POST /sync-stocks-name API 테스트"
echo "📍 서버: $API_URL"
echo ""

# 테스트 1: 기본값 사용 (markets 지정 안 함 - 모든 기본 시장 사용)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "테스트 1: 기본 markets 사용 (KRX, ETF/KR, S&P500, NASDAQ, NYSE, AMEX)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

curl -X POST "${API_URL}/sync-stocks-name" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${CRON_SECRET}" \
  -d '{}' \
  -w "\n\nHTTP Status: %{http_code}\n" \
  -s | jq '.' 2>/dev/null || cat

echo ""
echo ""

# 테스트 2: 특정 markets 지정 (KRX만)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "테스트 2: 특정 markets 지정 (KRX만)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

curl -X POST "${API_URL}/sync-stocks-name" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${CRON_SECRET}" \
  -d '{"markets": ["KRX"]}' \
  -w "\n\nHTTP Status: %{http_code}\n" \
  -s | jq '.' 2>/dev/null || cat

echo ""
echo ""

# 테스트 3: 여러 markets 지정
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "테스트 3: 여러 markets 지정 (KRX, NASDAQ)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

curl -X POST "${API_URL}/sync-stocks-name" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${CRON_SECRET}" \
  -d '{"markets": ["KRX", "NASDAQ"]}' \
  -w "\n\nHTTP Status: %{http_code}\n" \
  -s | jq '.' 2>/dev/null || cat

echo ""
echo "✅ 테스트 완료"
