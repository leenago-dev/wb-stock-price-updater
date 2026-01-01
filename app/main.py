import logging
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from app.config import settings, get_stock_symbols_override
from app.supabase_client import (
    get_managed_stocks,
    get_today_stock_prices,
    save_stock_price_to_db,
)
from app.yahoo_finance import get_quote_data

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Stock Price Updater", version="1.0.0")


class UpdatePricesRequest(BaseModel):
    symbols: Optional[List[str]] = None


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


async def verify_auth(authorization: Optional[str] = Header(None)):
    """Bearer 토큰 인증"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization.replace("Bearer ", "")

    if token != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return True


@app.get("/health")
async def health_check():
    """헬스체크 엔드포인트"""
    return {"status": "healthy"}


@app.post("/update-prices", response_model=UpdatePricesResponse)
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
        # 1. 심볼 목록 결정 (우선순위: request body > 환경변수 > DB)
        symbols: List[str] = []

        if request and request.symbols:
            symbols = [s.strip().upper() for s in request.symbols if s.strip()]
            logger.info(f"Request body에서 {len(symbols)}개 심볼 받음: {symbols}")
        else:
            # 환경변수 오버라이드 확인
            env_symbols = get_stock_symbols_override()
            if env_symbols:
                symbols = env_symbols
                logger.info(f"환경변수에서 {len(symbols)}개 심볼 로드: {symbols}")
            else:
                # DB에서 활성화된 종목 조회
                symbols = await get_managed_stocks()
                logger.info(f"DB에서 {len(symbols)}개 활성화된 종목 조회: {symbols}")

        if not symbols:
            return UpdatePricesResponse(
                success=True,
                total=0,
                successCount=0,
                failureCount=0,
                results=[],
            )

        # 2. 오늘 날짜 데이터를 한 번에 조회 (N+1 문제 방지)
        existing_prices = await get_today_stock_prices(symbols)
        existing_symbols = set(existing_prices.keys())
        all_symbols = set(s.upper() for s in symbols)

        # 3. 메모리에서 비교: 수집해야 할 목록 - 이미 있는 목록 = API 호출할 목록
        symbols_to_fetch = list(all_symbols - existing_symbols)

        logger.info(
            f"배치 작업 시작: 전체 {len(all_symbols)}개, "
            f"이미 있음 {len(existing_symbols)}개, "
            f"API 호출 필요 {len(symbols_to_fetch)}개"
        )

        # 4. 각 심볼에 대해 개별 try-except로 실패 격리
        results: List[SymbolResult] = []

        # 이미 있는 종목은 성공으로 처리
        for symbol in existing_symbols:
            results.append(SymbolResult(symbol=symbol, success=True))

        # API 호출이 필요한 종목 처리
        for symbol in symbols_to_fetch:
            try:
                # Yahoo Finance API에서 데이터 가져오기
                quote_data = await get_quote_data(symbol)

                if not quote_data:
                    results.append(
                        SymbolResult(
                            symbol=symbol,
                            success=False,
                            error="가격 정보를 찾을 수 없습니다.",
                        )
                    )
                    continue

                # Supabase에 저장
                saved = await save_stock_price_to_db(symbol, quote_data)

                if saved:
                    results.append(SymbolResult(symbol=symbol, success=True))
                    logger.info(f"{symbol} 업데이트 성공")
                else:
                    results.append(
                        SymbolResult(
                            symbol=symbol,
                            success=False,
                            error="Supabase 저장 실패",
                        )
                    )
                    logger.error(f"{symbol} 저장 실패")

            except Exception as e:
                # 실패 격리: 한 종목 실패가 전체를 중단시키지 않음
                error_message = str(e)
                results.append(
                    SymbolResult(symbol=symbol, success=False, error=error_message)
                )
                logger.error(f"{symbol} 처리 실패: {error_message}", exc_info=True)

        # 통계 계산
        success_count = sum(1 for r in results if r.success)
        failure_count = sum(1 for r in results if not r.success)

        logger.info(
            f"배치 작업 완료: 전체 {len(results)}개, "
            f"성공 {success_count}개, 실패 {failure_count}개"
        )

        return UpdatePricesResponse(
            success=True,
            total=len(results),
            successCount=success_count,
            failureCount=failure_count,
            results=results,
        )

    except Exception as e:
        logger.error(f"배치 작업 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"배치 작업 중 오류가 발생했습니다: {str(e)}",
        )
