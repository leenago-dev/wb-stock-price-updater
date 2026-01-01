import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase 설정
    supabase_url: str
    supabase_anon_key: str

    # 인증
    cron_secret: str

    # 오버라이드용 심볼 목록 (선택사항)
    stock_symbols: Optional[str] = None

    # Rate Limiting 설정
    min_request_delay_ms: int = 200
    max_concurrent_requests: int = 3
    max_retries: int = 3
    initial_retry_delay_ms: int = 1000
    max_retry_delay_ms: int = 10000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# 전역 설정 인스턴스
settings = Settings()


def get_stock_symbols_override() -> Optional[list[str]]:
    """환경변수에서 심볼 목록을 파싱하여 반환"""
    if not settings.stock_symbols:
        return None
    return [s.strip().upper() for s in settings.stock_symbols.split(",") if s.strip()]
