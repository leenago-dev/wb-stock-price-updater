#!/usr/bin/env python3
"""Slack 에러 알림 테스트 스크립트

send_slack_error_log 함수를 테스트합니다.
실제 에러를 발생시켜서 Slack Block Kit 형식의 상세 에러 리포트가 전송되는지 확인합니다.
"""

import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.slack_notifier import send_slack_error_log
from app.config import settings


def test_slack_error_log():
    """Slack 에러 로그 테스트"""
    print("=" * 70)
    print("Slack 에러 로그 테스트 시작")
    print("=" * 70)
    print()
    
    # 1. 설정 확인
    if not hasattr(settings, 'slack_webhook_url') or not settings.slack_webhook_url:
        print("❌ SLACK_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
        print("\n설정 방법:")
        print("  .env 파일에 다음을 추가하세요:")
        print("  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL")
        print("\n또는 환경변수로 설정:")
        print("  export SLACK_WEBHOOK_URL='https://hooks.slack.com/services/YOUR/WEBHOOK/URL'")
        print("\n⚠️  참고: config.py에 slack_webhook_url 필드가 없으면 추가해야 합니다.")
        return False
    
    print(f"✅ Slack webhook URL이 설정되어 있습니다.")
    print(f"   URL: {settings.slack_webhook_url[:50]}...")
    print()
    
    # 2. 기본 에러 리포트 테스트 (심볼 있음)
    print("테스트 1: 기본 에러 리포트 (심볼 있음)")
    print("-" * 70)
    try:
        raise ValueError("테스트용 에러: 가격 정보를 찾을 수 없습니다.")
    except Exception as test_error:
        print(f"  에러 유형: {type(test_error).__name__}")
        print(f"  에러 메시지: {str(test_error)}")
        print(f"  심볼: AAPL")
        print("  전송 중...")
        result1 = send_slack_error_log("AAPL", test_error)
        if result1:
            print("  ✅ Slack 에러 리포트 전송 성공!")
        else:
            print("  ❌ Slack 에러 리포트 전송 실패")
        print()
    
    # 3. 다양한 에러 유형 테스트
    print("테스트 2: 다양한 에러 유형 테스트")
    print("-" * 70)
    
    test_cases = [
        ("MSFT", KeyError("'price' 키를 찾을 수 없습니다")),
        ("GOOGL", RuntimeError("Rate limit 오류: 429 Too Many Requests")),
        ("TSLA", ConnectionError("Supabase 연결 실패: 타임아웃")),
        ("NVDA", ValueError("JSON 디코드 오류: Expecting value: line 1 column 1 (char 0)")),
    ]
    
    for symbol, error in test_cases:
        print(f"  [{symbol}] {type(error).__name__}: {str(error)[:50]}...")
        result = send_slack_error_log(symbol, error)
        if result:
            print(f"  ✅ 성공")
        else:
            print(f"  ❌ 실패")
        print()
    
    # 4. 중첩된 에러 테스트 (실제 traceback 생성)
    print("테스트 3: 중첩된 에러 테스트 (실제 traceback 포함)")
    print("-" * 70)
    try:
        def inner_function():
            """내부 함수에서 에러 발생"""
            data = {"price": 100}
            return data["invalid_key"]  # KeyError 발생
        
        def outer_function():
            """외부 함수에서 내부 함수 호출"""
            return inner_function()
        
        # 에러 발생
        outer_function()
    except Exception as nested_error:
        print(f"  에러 유형: {type(nested_error).__name__}")
        print(f"  에러 메시지: {str(nested_error)}")
        print(f"  심볼: AMZN")
        print("  전송 중... (traceback 포함)")
        result3 = send_slack_error_log("AMZN", nested_error)
        if result3:
            print("  ✅ Slack 에러 리포트 전송 성공!")
        else:
            print("  ❌ Slack 에러 리포트 전송 실패")
        print()
    
    # 5. 배치 작업 실패 테스트 (심볼 없음)
    print("테스트 4: 배치 작업 실패 (심볼 없음)")
    print("-" * 70)
    try:
        raise RuntimeError("배치 작업 전체 실패: 데이터베이스 연결 오류")
    except Exception as batch_error:
        print(f"  에러 유형: {type(batch_error).__name__}")
        print(f"  에러 메시지: {str(batch_error)}")
        print(f"  심볼: None (배치 작업 전체)")
        print("  전송 중...")
        result4 = send_slack_error_log(None, batch_error)
        if result4:
            print("  ✅ Slack 에러 리포트 전송 성공!")
        else:
            print("  ❌ Slack 에러 리포트 전송 실패")
        print()
    
    # 6. 커스텀 예외 테스트
    print("테스트 5: 커스텀 예외 테스트")
    print("-" * 70)
    try:
        from app.exceptions import YahooFinanceException, RateLimitException
        
        # YahooFinanceException 테스트
        print("  YahooFinanceException 테스트...")
        yahoo_error = YahooFinanceException("Yahoo Finance API 오류: 응답 파싱 실패")
        result5a = send_slack_error_log("GOOGL", yahoo_error)
        if result5a:
            print("  ✅ 성공")
        else:
            print("  ❌ 실패")
        print()
        
        # RateLimitException 테스트
        print("  RateLimitException 테스트...")
        rate_limit_error = RateLimitException("Rate limit 오류: 429 Too Many Requests")
        result5b = send_slack_error_log("AAPL", rate_limit_error)
        if result5b:
            print("  ✅ 성공")
        else:
            print("  ❌ 실패")
        print()
    except ImportError:
        print("  ⚠️  커스텀 예외를 import할 수 없습니다. 스킵합니다.")
        print()
    
    # 7. 긴 traceback 테스트
    print("테스트 6: 긴 traceback 테스트")
    print("-" * 70)
    try:
        def level1():
            return level2()
        def level2():
            return level3()
        def level3():
            return level4()
        def level4():
            return level5()
        def level5():
            raise Exception("깊은 스택 트레이스 테스트: " + "A" * 100)
        level1()
    except Exception as deep_error:
        print(f"  에러 유형: {type(deep_error).__name__}")
        print(f"  에러 메시지: {str(deep_error)[:50]}...")
        print(f"  심볼: DEEP")
        print("  전송 중... (긴 traceback)")
        result6 = send_slack_error_log("DEEP", deep_error)
        if result6:
            print("  ✅ Slack 에러 리포트 전송 성공!")
            print("  💡 Traceback이 1500자로 제한되어 전송되었습니다.")
        else:
            print("  ❌ Slack 에러 리포트 전송 실패")
        print()
    
    print("=" * 70)
    print("테스트 완료!")
    print("=" * 70)
    print("\n💡 Slack 채널에서 다음을 확인하세요:")
    print("   - Block Kit 형식의 구조화된 메시지")
    print("   - 에러 유형, 메시지, 종목 코드")
    print("   - 상세한 Traceback 정보")
    print("   - 가독성 높은 코드 블록 형식")
    print()
    
    return True


if __name__ == "__main__":
    try:
        success = test_slack_error_log()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  테스트가 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
