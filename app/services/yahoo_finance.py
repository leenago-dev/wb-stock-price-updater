import asyncio
import yfinance as yf
import json
from typing import Optional
from curl_cffi import requests as crequests
from app.utils.rate_limiter import request_queue
from app.config import settings
from app.utils.logging_config import get_logger
from app.exceptions import YahooFinanceException, RateLimitException

logger = get_logger(__name__)

# curl_cffi 세션 생성 (Chrome 브라우저로 위장)
# 모듈 레벨에서 한 번 생성하여 재사용
_curl_session = crequests.Session(impersonate="chrome")


async def fetch_with_retry(symbol: str, retry_count: int = 0) -> Optional[yf.Ticker]:
    """Yahoo Finance API에서 주식 정보를 가져오고 재시도 로직 적용"""
    try:
        # Rate limiting 적용 (yfinance는 동기 함수이므로 asyncio.to_thread로 래핑)
        async def fetch_ticker():
            # curl_cffi 세션을 사용하여 Chrome 브라우저로 위장
            ticker = yf.Ticker(symbol, session=_curl_session)
            # info를 호출하여 실제 API 요청 발생
            _ = ticker.info
            return ticker

        ticker = await request_queue.add(fetch_ticker)
        return ticker
    except json.JSONDecodeError as error:
        # JSON 디코드 오류는 보통 rate limit이나 빈 응답으로 인해 발생
        # "Expecting value: line 1 column 1 (char 0)"는 빈 응답을 의미
        error_message = str(error)
        logger.warning(
            f"JSON 디코드 오류 (rate limit 가능성): {error_message} - 심볼: {symbol}"
        )

        if retry_count < settings.max_retries:
            delay = min(
                settings.initial_retry_delay_ms * (2**retry_count),
                settings.max_retry_delay_ms,
            )

            logger.warning(
                f"JSON 파싱 실패로 인한 재시도. {delay}ms 후 재시도 "
                f"({retry_count + 1}/{settings.max_retries}): {symbol}"
            )

            await asyncio.sleep(delay / 1000)
            return await fetch_with_retry(symbol, retry_count + 1)

        raise YahooFinanceException(f"JSON 디코드 오류: {error_message}") from error
    except Exception as error:
        error_message = str(error)
        is_rate_limit_error = (
            "429" in error_message
            or "Too Many Requests" in error_message
            or "rate limit" in error_message.lower()
            or "JSONDecodeError" in error_message
        )

        if is_rate_limit_error and retry_count < settings.max_retries:
            delay = min(
                settings.initial_retry_delay_ms * (2**retry_count),
                settings.max_retry_delay_ms,
            )

            logger.warning(
                f"Rate limit 오류 발생. {delay}ms 후 재시도 "
                f"({retry_count + 1}/{settings.max_retries}): {symbol}"
            )

            await asyncio.sleep(delay / 1000)
            return await fetch_with_retry(symbol, retry_count + 1)

        if is_rate_limit_error:
            raise RateLimitException(f"Rate limit 오류: {error_message}") from error
        raise YahooFinanceException(
            f"Yahoo Finance API 오류: {error_message}"
        ) from error


async def get_quote_data(symbol: str) -> tuple[Optional[dict], Optional[str]]:
    """
    심볼에 대한 주식 정보를 가져와서 정제된 데이터로 반환

    Returns:
        tuple[Optional[dict], Optional[str]]: (quote_data, error_reason)
        - quote_data: 성공 시 가격 정보 딕셔너리, 실패 시 None
        - error_reason: 실패 시 에러 원인 문자열, 성공 시 None
    """
    try:
        ticker = await fetch_with_retry(symbol)

        if ticker is None:
            error_reason = "Ticker 객체를 가져오지 못함"
            logger.error(f"{symbol}: {error_reason}")
            return None, error_reason

        # ticker.info 접근 시에도 예외가 발생할 수 있으므로 다시 시도
        try:
            info = ticker.info
        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            logger.warning(f"{symbol}: ticker.info 접근 실패, 재시도: {str(e)}")
            # 한 번 더 재시도
            ticker = await fetch_with_retry(symbol)
            if ticker is None:
                error_reason = "재시도 후에도 Ticker 객체를 가져오지 못함"
                logger.error(f"{symbol}: {error_reason}")
                return None, error_reason
            info = ticker.info

        # info가 None이거나 빈 딕셔너리인지 체크
        if not info:
            error_reason = "ticker.info가 None이거나 빈 딕셔너리"
            logger.warning(f"{symbol}: {error_reason}")
            return None, error_reason

        if not isinstance(info, dict):
            error_reason = (
                f"ticker.info가 딕셔너리가 아님 (타입: {type(info).__name__})"
            )
            logger.warning(f"{symbol}: {error_reason}")
            return None, error_reason

        # 가격 정보 추출
        regular_market_price = (
            info.get("regularMarketPrice")
            or info.get("currentPrice")
            or info.get("previousClose")
        )

        if not regular_market_price:
            error_reason = "가격 정보가 응답에 없음 (regularMarketPrice, currentPrice, previousClose 모두 없음)"
            logger.warning(
                f"{symbol}: {error_reason} - 응답 키: {list(info.keys())[:10] if info else '없음'}"
            )
            return None, error_reason

        quote_data = {
            "symbol": info.get("symbol", symbol).upper(),
            "price": float(regular_market_price),
            "currency": info.get("currency"),
            "name": (info.get("shortName") or info.get("longName") or info.get("name")),
            "changePercent": info.get("regularMarketChangePercent"),
        }

        return quote_data, None
    except json.JSONDecodeError as e:
        error_reason = f"JSON 디코드 오류: {str(e)}"
        logger.error(f"JSON 디코드 오류 ({symbol}): {str(e)}", exc_info=True)
        logger.error(f"yfinance 응답 파싱 실패 - 심볼: {symbol}")
        # JSONDecodeError는 이미 fetch_with_retry에서 재시도했으므로 여기서는 None 반환
        return None, error_reason
    except RateLimitException as e:
        error_reason = f"Rate limit 오류 (429 Too Many Requests)"
        # 커스텀 예외는 이미 로깅되었으므로 None 반환
        return None, error_reason
    except YahooFinanceException as e:
        error_reason = f"Yahoo Finance API 오류: {str(e)}"
        # 커스텀 예외는 이미 로깅되었으므로 None 반환
        return None, error_reason
    except Exception as e:
        error_message = str(e)
        # Rate limit 관련 오류는 None 반환 (재시도는 이미 했음)
        if "429" in error_message or "Too Many Requests" in error_message:
            error_reason = f"Rate limit 오류: {error_message}"
            logger.error(f"{symbol}: Rate limit 오류로 인한 실패")
            return None, error_reason
        logger.error(f"{symbol} 조회 실패: {error_message}", exc_info=True)
        raise YahooFinanceException(f"{symbol} 조회 실패: {error_message}") from e
