import asyncio
import yfinance as yf
import logging
from typing import Optional
from app.rate_limiter import request_queue
from app.config import settings

logger = logging.getLogger(__name__)


async def fetch_with_retry(
    symbol: str, retry_count: int = 0
) -> Optional[yf.Ticker]:
    """Yahoo Finance API에서 주식 정보를 가져오고 재시도 로직 적용"""
    try:
        # Rate limiting 적용 (yfinance는 동기 함수이므로 asyncio.to_thread로 래핑)
        async def fetch_ticker():
            ticker = yf.Ticker(symbol)
            # info를 호출하여 실제 API 요청 발생
            _ = ticker.info
            return ticker

        ticker = await request_queue.add(fetch_ticker)
        return ticker
    except Exception as error:
        error_message = str(error)
        is_rate_limit_error = (
            "429" in error_message
            or "Too Many Requests" in error_message
            or "rate limit" in error_message.lower()
        )

        if is_rate_limit_error and retry_count < settings.max_retries:
            delay = min(
                settings.initial_retry_delay_ms * (2 ** retry_count),
                settings.max_retry_delay_ms
            )

            logger.warning(
                f"Rate limit 오류 발생. {delay}ms 후 재시도 "
                f"({retry_count + 1}/{settings.max_retries}): {symbol}"
            )

            await asyncio.sleep(delay / 1000)
            return await fetch_with_retry(symbol, retry_count + 1)

        raise error


async def get_quote_data(symbol: str) -> Optional[dict]:
    """심볼에 대한 주식 정보를 가져와서 정제된 데이터로 반환"""
    try:
        ticker = await fetch_with_retry(symbol)
        info = ticker.info

        # 가격 정보 추출
        regular_market_price = (
            info.get("regularMarketPrice")
            or info.get("currentPrice")
            or info.get("previousClose")
        )

        if not regular_market_price:
            logger.warning(f"{symbol}: 가격 정보를 찾을 수 없습니다.")
            return None

        quote_data = {
            "symbol": info.get("symbol", symbol).upper(),
            "price": float(regular_market_price),
            "currency": info.get("currency"),
            "name": (
                info.get("shortName")
                or info.get("longName")
                or info.get("name")
            ),
            "changePercent": info.get("regularMarketChangePercent"),
        }

        return quote_data
    except Exception as e:
        logger.error(f"{symbol} 조회 실패: {str(e)}", exc_info=True)
        raise
