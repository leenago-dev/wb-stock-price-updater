"""API 라우트 정의"""

import json
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.api.dependencies import verify_auth
from app.services.stock_service import update_stock_prices
from app.utils.logging_config import get_logger
from app.exceptions import StockPriceUpdaterException

logger = get_logger(__name__)

router = APIRouter()


class UpdatePricesRequest(BaseModel):
    symbols: Optional[List[str]] = None
    country: Optional[str] = None


class SymbolResult(BaseModel):
    symbol: str
    success: bool
    error: Optional[str] = None


class UpdatePricesResponse(BaseModel):
    success: bool
    total: int
    successCount: int
    failureCount: int
    results: List[SymbolResult]


@router.get("/health")
async def health_check():
    """헬스체크 엔드포인트"""
    return {"status": "healthy"}


@router.post("/update-prices", response_model=UpdatePricesResponse)
async def update_prices(
    request: Optional[UpdatePricesRequest] = None,
    _: bool = Depends(verify_auth),
):
    """
    주식 가격을 업데이트합니다.

    성능 최적화:
    1. managed_stocks에서 활성화된 심볼 목록 조회 (쿼리 1번)
    2. stock_prices에서 오늘 날짜 데이터를 한 번에 조회 (쿼리 1번)
    3. 메모리에서 비교하여 실제 API 호출이 필요한 심볼만 필터링
    4. 각 심볼에 대해 개별 try-except로 실패 격리
    """
    try:
        request_symbols = request.symbols if request else None
        country = request.country if request else None

        result = await update_stock_prices(
            request_symbols=request_symbols,
            country=country,
        )

        return UpdatePricesResponse(**result)

    except json.JSONDecodeError as e:
        logger.error(f"JSON 디코드 오류 (배치 작업): {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"JSON 파싱 오류가 발생했습니다: {str(e)}",
        )
    except StockPriceUpdaterException as e:
        logger.error(f"배치 작업 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"배치 작업 중 예상치 못한 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"배치 작업 중 오류가 발생했습니다: {str(e)}",
        )


def setup_exception_handlers(app):
    """예외 핸들러 설정"""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """요청 검증 오류 처리 (JSON 파싱 오류 포함)"""
        logger.error(f"요청 검증 오류: {str(exc)}")
        logger.error(f"요청 경로: {request.url.path}")
        try:
            body = await request.body()
            logger.error(
                f"요청 본문 (첫 500자): {body[:500].decode('utf-8', errors='ignore') if body else 'N/A'}"
            )
        except Exception as e:
            logger.error(f"요청 본문 읽기 실패: {str(e)}")
        return JSONResponse(
            status_code=422,
            content={"detail": f"요청 형식 오류: {str(exc)}", "errors": exc.errors()},
        )

    @app.exception_handler(json.JSONDecodeError)
    async def json_decode_exception_handler(request: Request, exc: json.JSONDecodeError):
        """JSON 디코드 오류 처리"""
        logger.error(f"JSON 디코드 오류: {str(exc)}")
        logger.error(f"요청 경로: {request.url.path}")
        logger.error(f"오류 위치: line {exc.lineno}, column {exc.colno}")
        try:
            body = await request.body()
            logger.error(
                f"요청 본문 (첫 500자): {body[:500].decode('utf-8', errors='ignore') if body else 'N/A'}"
            )
        except Exception as e:
            logger.error(f"요청 본문 읽기 실패: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={
                "detail": f"JSON 파싱 오류: {str(exc)}",
                "line": exc.lineno,
                "column": exc.colno,
            },
        )
