"""로깅 설정 중앙화"""

import logging
import sys
from typing import Optional


def setup_logging(
    level: int = logging.INFO,
    format_string: Optional[str] = None,
    stream: Optional[object] = sys.stdout,
) -> None:
    """
    애플리케이션 로깅 설정

    Args:
        level: 로그 레벨 (기본값: logging.INFO)
        format_string: 로그 포맷 문자열 (기본값: 표준 포맷)
        stream: 로그 출력 스트림 (기본값: sys.stdout)
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=level,
        format=format_string,
        stream=stream,
        force=True,  # 기존 핸들러 재설정
    )


def get_logger(name: str) -> logging.Logger:
    """
    로거 인스턴스 반환

    Args:
        name: 로거 이름 (보통 __name__ 사용)

    Returns:
        logging.Logger: 로거 인스턴스
    """
    return logging.getLogger(name)
