"""API 라우트 정의"""

import json
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Depends, Body
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.api.dependencies import verify_auth
from app.services.stock_service import update_stock_prices
from app.services.listings.fdr_listings import sync_stock_names
from app.services.exchange_rates_service import sync_exchange_rates, resolve_symbol
from app.repositories.supabase_client import (
    get_stock_name_by_symbol,
    get_exchange_rate,
    get_exchange_rate_history,
)
from app.utils.logging_config import get_logger
from app.utils.slack_notifier import send_slack_error_log
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


class SyncStocksNameRequest(BaseModel):
    markets: Optional[List[str]] = None


class SyncStocksNameResponse(BaseModel):
    success: bool
    markets: List[str]
    uniqueSymbols: int
    upserted: int
    deactivated: int
    errors: List[str]


class StockNameResponse(BaseModel):
    symbol: str
    name: Optional[str] = None
    country: Optional[str] = None
    source: Optional[str] = None
    is_active: Optional[bool] = None


class SyncExchangeRatesRequest(BaseModel):
    symbols: Optional[List[str]] = None


class SyncExchangeRatesResponse(BaseModel):
    success: bool
    symbols: List[str]
    upserted: int
    errors: List[str]


class ExchangeRateResponse(BaseModel):
    symbol: str
    date: str
    close_price: Optional[float] = None
    adj_close_price: Optional[float] = None
    currency: Optional[str] = None
    name: Optional[str] = None


@router.get("/health")
async def health_check():
    """헬스체크 엔드포인트"""
    return {"status": "healthy"}


@router.post("/update-prices", response_model=UpdatePricesResponse)
async def update_prices(
    request_body: Optional[UpdatePricesRequest] = Body(None),
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
        # request_body가 None이면 빈 요청으로 처리
        request_symbols = request_body.symbols if request_body else None
        country = request_body.country if request_body else None

        result = await update_stock_prices(
            request_symbols=request_symbols,
            country=country,
        )

        return UpdatePricesResponse(**result)

    except json.JSONDecodeError as e:
        error_message = f"JSON 파싱 오류가 발생했습니다: {str(e)}"
        logger.error(f"JSON 디코드 오류 (배치 작업): {str(e)}", exc_info=True)
        send_slack_error_log(None, e)
        raise HTTPException(
            status_code=500,
            detail=error_message,
        )
    except StockPriceUpdaterException as e:
        error_message = str(e)
        logger.error(f"배치 작업 중 오류 발생: {error_message}", exc_info=True)
        send_slack_error_log(None, e)
        raise HTTPException(
            status_code=500,
            detail=error_message,
        )
    except Exception as e:
        error_message = f"배치 작업 중 오류가 발생했습니다: {str(e)}"
        logger.error(
            f"배치 작업 중 예상치 못한 오류 발생: {str(error_message)}", exc_info=True
        )
        send_slack_error_log(None, e)
        raise HTTPException(
            status_code=500,
            detail=error_message,
        )


@router.post("/sync-stocks-name", response_model=SyncStocksNameResponse)
async def sync_stock_names_endpoint(
    request_body: Optional[SyncStocksNameRequest] = Body(None),
    _: bool = Depends(verify_auth),
):
    """
    FDR StockListing으로 stock_names 테이블을 동기화합니다.

    markets를 지정하지 않으면 기본값(KRX, ETF/KR, S&P500, NASDAQ, NYSE, AMEX)을 사용합니다.
    """
    try:
        markets = request_body.markets if request_body else None
        result = await sync_stock_names(markets=markets)
        return SyncStocksNameResponse(**result)
    except Exception as e:
        error_message = f"stock_names 동기화 중 오류가 발생했습니다: {str(e)}"
        logger.error(
            f"stock_names 동기화 중 예상치 못한 오류 발생: {str(error_message)}",
            exc_info=True,
        )
        send_slack_error_log(None, e)
        raise HTTPException(
            status_code=500,
            detail=error_message,
        )


@router.get("/stocks-name/{symbol}", response_model=StockNameResponse)
async def get_stock_name(symbol: str):
    """
    symbol 정확 일치로 stock_names에서 종목 정보를 조회합니다.
    화면에서 ticker 입력 시 전체 로드 없이 1건만 조회합니다.
    """
    try:
        result = await get_stock_name_by_symbol(symbol)
        if not result:
            raise HTTPException(
                status_code=404, detail=f"Symbol '{symbol}' not found in stock_names"
            )
        return StockNameResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        error_message = f"stock_names 조회 중 오류가 발생했습니다: {str(e)}"
        logger.error(
            f"stock_names 조회 중 예상치 못한 오류 발생: {str(error_message)}",
            exc_info=True,
        )
        send_slack_error_log(None, e)
        raise HTTPException(
            status_code=500,
            detail=error_message,
        )


@router.post("/sync-exchange-rates", response_model=SyncExchangeRatesResponse)
async def sync_exchange_rates_endpoint(
    request_body: Optional[SyncExchangeRatesRequest] = Body(None),
    _: bool = Depends(verify_auth),
):
    """
    FDR DataReader로 exchange_rates 테이블을 동기화합니다.

    symbols를 지정하지 않으면 기본값(^NYICDX, USD/KRW, BTC/KRW, BTC/USD)을 사용합니다.
    한국어 이름(예: "원달러환율", "달러인덱스")도 지원합니다.
    """
    try:
        symbols = request_body.symbols if request_body else None
        result = await sync_exchange_rates(symbols=symbols)
        return SyncExchangeRatesResponse(**result)
    except Exception as e:
        error_message = f"exchange_rates 동기화 중 오류가 발생했습니다: {str(e)}"
        logger.error(
            f"exchange_rates 동기화 중 예상치 못한 오류 발생: {str(error_message)}",
            exc_info=True,
        )
        send_slack_error_log(None, e)
        raise HTTPException(
            status_code=500,
            detail=error_message,
        )


@router.get("/exchange-rates/{symbol_or_name}", response_model=ExchangeRateResponse)
async def get_exchange_rate_endpoint(symbol_or_name: str, date: Optional[str] = None):
    """
    symbol 또는 한국어 이름으로 exchange_rates에서 최신 환율/인덱스 데이터를 조회합니다.
    date 파라미터가 있으면 해당 날짜 데이터를 조회합니다.
    """
    try:
        symbol = resolve_symbol(symbol_or_name)
        result = await get_exchange_rate(symbol, date=date)
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Symbol '{symbol_or_name}' (resolved: '{symbol}') not found in exchange_rates",
            )
        return ExchangeRateResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        error_message = f"exchange_rates 조회 중 오류가 발생했습니다: {str(e)}"
        logger.error(
            f"exchange_rates 조회 중 예상치 못한 오류 발생: {str(error_message)}",
            exc_info=True,
        )
        send_slack_error_log(None, e)
        raise HTTPException(
            status_code=500,
            detail=error_message,
        )


@router.get("/exchange-rates/{symbol_or_name}/history")
async def get_exchange_rate_history_endpoint(
    symbol_or_name: str,
    start_date: str,
    end_date: str,
):
    """
    symbol 또는 한국어 이름으로 exchange_rates에서 시계열 데이터를 조회합니다.

    Query Parameters:
        start_date: 시작 날짜 (YYYY-MM-DD)
        end_date: 종료 날짜 (YYYY-MM-DD)
    """
    try:
        symbol = resolve_symbol(symbol_or_name)
        result = await get_exchange_rate_history(symbol, start_date, end_date)
        return {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "data": result,
        }
    except Exception as e:
        error_message = f"exchange_rates 시계열 조회 중 오류가 발생했습니다: {str(e)}"
        logger.error(
            f"exchange_rates 시계열 조회 중 예상치 못한 오류 발생: {str(error_message)}",
            exc_info=True,
        )
        send_slack_error_log(None, e)
        raise HTTPException(
            status_code=500,
            detail=error_message,
        )


def setup_exception_handlers(app):
    """예외 핸들러 설정"""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """요청 검증 오류 처리 (JSON 파싱 오류 포함)"""
        error_message = f"요청 검증 오류: {str(exc)} (경로: {request.url.path})"
        logger.error(error_message)
        logger.error(f"요청 경로: {request.url.path}")
        send_slack_error_log(None, RequestValidationError(error_message))
        try:
            body = await request.body()
            logger.error(
                f"요청 본문 (첫 500자): {body[:500].decode('utf-8', errors='ignore') if body else 'N/A'}"
            )
        except Exception as e:
            logger.error(f"요청 본문 읽기 실패: {str(e)}")

        # exc.errors()를 안전하게 직렬화 (bytes 객체 및 기타 직렬화 불가능한 객체 처리)
        def sanitize_value(value):
            """값을 JSON 직렬화 가능한 형태로 변환"""
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="ignore")
            elif isinstance(value, (dict, list)):
                # 재귀적으로 처리
                try:
                    return json.loads(json.dumps(value, default=str))
                except (TypeError, ValueError):
                    return str(value)
            elif isinstance(value, (str, int, float, bool, type(None))):
                return value
            else:
                # 기타 타입은 문자열로 변환
                try:
                    json.dumps(value, default=str)
                    return value
                except (TypeError, ValueError):
                    return str(value)

        def sanitize_errors(errors):
            """에러 객체를 JSON 직렬화 가능한 형태로 변환"""
            sanitized = []
            for error in errors:
                sanitized_error = {}
                for key, value in error.items():
                    sanitized_error[key] = sanitize_value(value)
                sanitized.append(sanitized_error)
            return sanitized

        try:
            sanitized_errors = sanitize_errors(exc.errors())
        except Exception as e:
            logger.error(f"에러 직렬화 실패: {str(e)}", exc_info=True)
            # 최소한의 에러 정보라도 반환
            sanitized_errors = [
                {"error": "에러 정보를 직렬화할 수 없습니다", "raw_error": str(exc)}
            ]

        try:
            return JSONResponse(
                status_code=422,
                content={"detail": str(exc), "errors": sanitized_errors},
            )
        except Exception as e:
            # JSONResponse 생성도 실패하면 최소한의 응답 반환
            logger.error(f"JSONResponse 생성 실패: {str(e)}", exc_info=True)
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "요청 형식 오류가 발생했습니다",
                    "errors": [{"error": "에러 정보를 처리할 수 없습니다"}],
                },
            )

    @app.exception_handler(json.JSONDecodeError)
    async def json_decode_exception_handler(
        request: Request, exc: json.JSONDecodeError
    ):
        """JSON 디코드 오류 처리"""
        logger.error(f"JSON 디코드 오류: {str(exc)}")
        logger.error(f"요청 경로: {request.url.path}")
        logger.error(f"오류 위치: line {exc.lineno}, column {exc.colno}")
        send_slack_error_log(None, exc)
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
