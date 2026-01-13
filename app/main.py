"""FastAPI 애플리케이션 진입점"""

from fastapi import FastAPI
from app.utils.logging_config import setup_logging, get_logger
from app.api.routes import router, setup_exception_handlers

# 로깅 설정 초기화
setup_logging()
logger = get_logger(__name__)

# FastAPI 앱 생성
app = FastAPI(title="Stock Price Updater", version="1.0.0")

# 예외 핸들러 설정
setup_exception_handlers(app)

# 라우터 등록
app.include_router(router)
