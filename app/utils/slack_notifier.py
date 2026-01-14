"""Slack webhook 알림 유틸리티"""

import traceback
import requests
from typing import Optional
from app.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


def send_slack_notification(message: str, symbol: Optional[str] = None) -> bool:
    """
    Slack webhook으로 에러 알림 전송

    Args:
        message: 전송할 메시지
        symbol: 관련 심볼 (있는 경우)

    Returns:
        bool: 전송 성공 여부
    """
    if not settings.slack_webhook_url:
        # webhook URL이 설정되지 않았으면 조용히 무시
        return False

    try:
        # 메시지 템플릿 사용 (설정에서 관리)
        if symbol:
            text = settings.slack_message_template_with_symbol.format(
                symbol=symbol, message=message
            )
        else:
            text = settings.slack_message_template_without_symbol.format(
                message=message
            )

        response = requests.post(
            settings.slack_webhook_url,
            json={"text": text},
            timeout=5,  # 5초 타임아웃
        )
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        # Slack 전송 실패는 로그만 남기고 앱 실행에는 영향 없음
        logger.warning(f"Slack 알림 전송 실패: {str(e)}")
        return False
    except Exception as e:
        # 예상치 못한 에러도 로그만 남김
        logger.warning(f"Slack 알림 전송 중 예상치 못한 에러: {str(e)}")
        return False


def send_slack_error_log(symbol: Optional[str], error: Exception) -> bool:
    """
    에러 발생 시 상세 정보를 Slack Block Kit으로 전송하는 함수

    Args:
        symbol: 종목 코드 (없으면 None)
        error: 발생한 예외 객체

    Returns:
        bool: 전송 성공 여부
    """
    if not settings.slack_webhook_url:
        # webhook URL이 설정되지 않았으면 조용히 무시
        return False

    try:
        # 1. 에러 위치 추적 (traceback 추출)
        tb_str = traceback.format_exc()
        # 너무 길면 슬랙이 자르니까 뒤에서 1500자만 보냄 (1000자보다 조금 더)
        tb_str_trimmed = tb_str[-1500:] if len(tb_str) > 1500 else tb_str

        # 2. 심볼이 있는지에 따라 필드 구성
        if symbol:
            symbol_field = {
                "type": "mrkdwn",
                "text": f"*📌 대상 종목:*\n`{symbol}`",
            }
            header_text = "🚨 [Error] 주가 업데이트 실패"
        else:
            symbol_field = {
                "type": "mrkdwn",
                "text": "*📌 대상:*\n`전체 배치 작업`",
            }
            header_text = "🚨 [Error] 배치 작업 실패"

        # 3. Slack Block Kit 구조로 메시지 구성
        payload = {
            "text": "🚨 주가 업데이트 실패 알림",  # fallback 텍스트
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": header_text,
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        symbol_field,
                        {
                            "type": "mrkdwn",
                            "text": f"*⚠️ 에러 유형:*\n`{type(error).__name__}`",
                        },
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*💬 에러 메시지:*\n```{str(error)}```",
                    },
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📋 상세 로그 (Traceback):*\n```\n{tb_str_trimmed}\n```",
                    },
                },
            ],
        }

        # 3. Slack으로 전송
        response = requests.post(
            settings.slack_webhook_url,
            json=payload,
            timeout=10,  # traceback이 길 수 있으므로 타임아웃을 조금 더 길게
        )
        response.raise_for_status()
        return True

    except requests.exceptions.RequestException as e:
        # Slack 전송 실패는 로그만 남기고 앱 실행에는 영향 없음
        logger.warning(f"Slack 에러 로그 전송 실패: {str(e)}")
        return False
    except Exception as e:
        # 예상치 못한 에러도 로그만 남김
        logger.warning(f"Slack 에러 로그 전송 중 예상치 못한 에러: {str(e)}")
        return False
