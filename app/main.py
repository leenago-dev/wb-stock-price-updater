"""FastAPI 애플리케이션 진입점"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.utils.logging_config import setup_logging, get_logger
from app.api.routes import router, setup_exception_handlers

# 로깅 설정 초기화
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 시 실행되는 이벤트 핸들러"""
    # Startup
    from app.repositories.supabase_client import load_symbol_cache

    await load_symbol_cache()
    logger.info("서버 시작 완료: 심볼 캐시 로드됨")
    yield
    # Shutdown (필요한 경우 여기에 정리 코드 추가 가능)


# FastAPI 앱 생성
app = FastAPI(title="Stock Price Updater", version="1.0.0", lifespan=lifespan)

# 예외 핸들러 설정
setup_exception_handlers(app)

# 라우터 등록
app.include_router(router)
