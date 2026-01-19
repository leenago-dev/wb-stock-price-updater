from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
from supabase import create_client, Client
from app.config import settings
from app.utils.logging_config import get_logger
from app.utils.slack_notifier import send_slack_error_log
from app.exceptions import SupabaseException
import json

logger = get_logger(__name__)

# Supabase 클라이언트 초기화.
supabase: Client = create_client(settings.supabase_url, settings.supabase_anon_key)


def get_today_date() -> str:
    """오늘 날짜를 YYYY-MM-DD 형식으로 반환 (한국 시간 기준 UTC+9)"""
    kst = timezone(timedelta(hours=9))
    now = datetime.now(timezone.utc)
    korea_time = now.astimezone(kst)
    return korea_time.strftime("%Y-%m-%d")


def get_yesterday_date() -> str:
    """어제 날짜를 YYYY-MM-DD 형식으로 반환 (한국 시간 기준 UTC+9)"""
    kst = timezone(timedelta(hours=9))
    now = datetime.now(timezone.utc)
    korea_time = now.astimezone(kst)
    yesterday = korea_time - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


async def get_managed_stocks(country: Optional[str] = None) -> List[Dict[str, str]]:
    """
    managed_stocks 테이블에서 활성화된 심볼 목록 조회
    country가 있으면 해당 국가만, 없으면 전체 조회
    """
    try:
        # symbol과 country를 같이 조회해야 나중에 저장할 때 국가를 알 수 있습니다.
        query = (
            supabase.table("managed_stocks")
            .select("symbol, country")
            .eq("enabled", True)
        )

        # country가 있을 때만 조건을 추가합니다.
        if country:
            query = query.eq("country", country)

        response = query.execute()

        # 결과 데이터를 딕셔너리 리스트로 변환
        stocks = [
            {"symbol": row["symbol"].upper(), "country": row["country"]}
            for row in response.data
        ]

        # 로그에는 심볼만 예쁘게 출력
        symbols_only = [s["symbol"] for s in stocks]
        logger.info(
            f"활성화된 종목 {len(stocks)}개 조회 (국가: {country}): {symbols_only}"
        )

        return stocks

    except json.JSONDecodeError as e:
        error_message = f"JSON 디코드 오류 (managed_stocks): {str(e)}"
        logger.error(error_message, exc_info=True)
        logger.error(f"오류 발생")
        send_slack_error_log(None, e)
        raise SupabaseException(error_message) from e
    except Exception as e:
        error_message = f"managed_stocks 조회 실패: {str(e)}"
        logger.error(error_message, exc_info=True)
        send_slack_error_log(None, e)
        raise SupabaseException(error_message) from e


async def get_today_stock_prices(symbols: List[str]) -> Dict[str, dict]:
    """
    오늘 날짜의 주식 가격을 한 번에 조회 (N+1 문제 방지)

    Returns:
        Dict[symbol, quote_data]: 심볼을 키로 하는 딕셔너리
    """
    if not symbols:
        return {}

    normalized_symbols = [s.strip().upper() for s in symbols]
    today = get_today_date()

    result: Dict[str, dict] = {}
    response = None

    try:
        # 오늘 날짜로 한 번에 조회
        response = (
            supabase.table("stock_prices")
            .select("*")
            .in_("symbol", normalized_symbols)
            .eq("date", today)
            .execute()
        )

        for row in response.data:
            symbol = row["symbol"].upper()
            result[symbol] = {
                "symbol": symbol,
                "price": float(row["close_price"]),
                "currency": row.get("currency"),
                "name": row.get("name"),
                "changePercent": (
                    float(row["change_percent"]) if row.get("change_percent") else None
                ),
            }

        logger.info(f"오늘 날짜 데이터 {len(result)}개 조회 완료")
    except json.JSONDecodeError as e:
        logger.error(
            f"JSON 디코드 오류 (get_today_stock_prices): {str(e)}", exc_info=True
        )
        if response is not None:
            logger.error(f"응답 내용: {getattr(response, 'text', 'N/A')}")
        # 에러가 발생해도 빈 딕셔너리 반환하여 계속 진행
    except Exception as e:
        logger.error(f"stock_prices 조회 실패: {str(e)}", exc_info=True)
        # 에러가 발생해도 빈 딕셔너리 반환하여 계속 진행

    return result


async def get_stock_price_from_db(symbol: str) -> Optional[dict]:
    """
    단일 심볼의 주식 종가 조회 (호환성 유지)
    오늘 날짜 기준으로 조회하고, 없으면 어제 날짜 조회
    """
    normalized_symbol = symbol.strip().upper()
    today = get_today_date()
    yesterday = get_yesterday_date()

    try:
        # 먼저 오늘 날짜로 조회
        response = (
            supabase.table("stock_prices")
            .select("*")
            .eq("symbol", normalized_symbol)
            .eq("date", today)
            .limit(1)
            .execute()
        )

        if response.data:
            row = response.data[0]
            return {
                "symbol": row["symbol"],
                "price": float(row["close_price"]),
                "currency": row.get("currency"),
                "name": row.get("name"),
                "changePercent": (
                    float(row["change_percent"]) if row.get("change_percent") else None
                ),
            }

        # 오늘 데이터가 없으면 어제 날짜로 조회
        response = (
            supabase.table("stock_prices")
            .select("*")
            .eq("symbol", normalized_symbol)
            .eq("date", yesterday)
            .limit(1)
            .execute()
        )

        if response.data:
            row = response.data[0]
            return {
                "symbol": row["symbol"],
                "price": float(row["close_price"]),
                "currency": row.get("currency"),
                "name": row.get("name"),
                "changePercent": (
                    float(row["change_percent"]) if row.get("change_percent") else None
                ),
            }

        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON 디코드 오류 ({symbol}): {str(e)}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"{symbol} 조회 실패: {str(e)}", exc_info=True)
        return None


async def save_stock_price_to_db(
    symbol: str,
    quote_data: dict,
    date: Optional[str] = None,
    country: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """
    Supabase에 주식 종가 저장
    중복 체크 후 저장 (symbol, date 조합이 unique)

    Args:
        symbol: 종목 코드
        quote_data: 가격 데이터
        date: 저장할 날짜 (None이면 자동 계산)
        country: 국가 코드 (US인 경우 어제 날짜 사용)

    Returns:
        tuple[bool, Optional[str]]: (성공 여부, 에러 메시지)
    """
    normalized_symbol = symbol.strip().upper()

    # date가 명시되지 않았을 때만 자동 계산
    if not date:
        if country == "US":
            # 미국 주식은 시차 때문에 어제 날짜 사용
            target_date = get_yesterday_date()
        else:
            # 그 외 국가는 오늘 날짜 사용
            target_date = get_today_date()
    else:
        target_date = date

    response = None

    try:
        data = {
            "symbol": normalized_symbol,
            "date": target_date,
            "close_price": quote_data["price"],
            "currency": quote_data.get("currency"),
            "name": quote_data.get("name"),
            "change_percent": quote_data.get("changePercent"),
        }

        response = (
            supabase.table("stock_prices")
            .upsert(data, on_conflict="symbol,date")
            .execute()
        )

        if response.data:
            logger.debug(f"{symbol} 저장 완료: {target_date}")
            return True, None
        else:
            error_msg = f"응답 데이터 없음 (symbol: {symbol}, date: {target_date})"
            logger.warning(f"{symbol} 저장 실패: {error_msg}")
            return False, error_msg
    except json.JSONDecodeError as e:
        error_msg = f"JSON 디코드 오류: {str(e)}"
        logger.error(f"JSON 디코드 오류 ({symbol} 저장): {str(e)}", exc_info=True)
        if response is not None:
            response_text = getattr(response, "text", "N/A")
            logger.error(f"응답 내용: {response_text}")
            error_msg = f"{error_msg} (응답: {response_text[:200]})"
        logger.error(f"요청 데이터: {data}")
        send_slack_error_log(symbol, e)
        return False, error_msg
    except Exception as e:
        error_msg = f"Supabase 저장 실패: {str(e)}"
        logger.error(f"{symbol} 저장 실패: {str(e)}", exc_info=True)
        # Supabase 클라이언트 에러의 경우 더 구체적인 정보 추출
        error_str = str(e)
        if hasattr(e, "message"):
            error_msg = f"Supabase 저장 실패: {e.message}"
        elif (
            "duplicate key" in error_str.lower()
            or "unique constraint" in error_str.lower()
        ):
            error_msg = f"중복 키 오류: 이미 존재하는 데이터입니다 (symbol: {symbol}, date: {target_date})"
        elif "foreign key" in error_str.lower():
            error_msg = f"외래 키 오류: 참조하는 테이블에 데이터가 없습니다"
        elif "permission" in error_str.lower() or "unauthorized" in error_str.lower():
            error_msg = f"권한 오류: Supabase 인증 실패"
        send_slack_error_log(symbol, e)
        return False, error_msg


async def get_stock_name_by_symbol(symbol: str) -> Optional[dict]:
    """
    stock_names 테이블에서 symbol로 종목 정보를 조회합니다.

    Args:
        symbol: 종목 심볼

    Returns:
        Optional[dict]: 종목 정보 (없으면 None)
    """
    normalized_symbol = symbol.strip().upper()

    try:
        response = (
            supabase.table("stock_names")
            .select("*")
            .eq("symbol", normalized_symbol)
            .limit(1)
            .execute()
        )

        if response.data:
            row = response.data[0]
            return {
                "symbol": row["symbol"],
                "name": row.get("name"),
                "country": row.get("country"),
                "source": row.get("source"),
                "is_active": row.get("is_active"),
            }

        return None
    except Exception as e:
        logger.error(f"stock_names 조회 실패 ({symbol}): {str(e)}", exc_info=True)
        return None


async def upsert_stock_names(records: List[dict]) -> tuple[int, Optional[str]]:
    """
    stock_names 테이블에 대량 upsert를 수행합니다.

    Args:
        records: upsert할 레코드 리스트

    Returns:
        tuple[int, Optional[str]]: (upsert된 개수, 에러 메시지)
    """
    if not records:
        return 0, None

    try:
        response = (
            supabase.table("stock_names")
            .upsert(records, on_conflict="symbol")
            .execute()
        )

        upserted = len(response.data) if response.data else 0
        logger.info(f"stock_names {upserted}개 레코드 upsert 완료")
        return upserted, None
    except Exception as e:
        error_msg = f"stock_names upsert 실패: {str(e)}"
        logger.error(error_msg, exc_info=True)
        send_slack_error_log(None, e)
        return 0, error_msg


async def get_active_stock_symbols_by_country(
    country: Optional[str] = None,
) -> List[str]:
    """
    stock_names 테이블에서 활성화된 심볼 목록을 조회합니다.

    Args:
        country: 국가 코드 (None이면 전체)

    Returns:
        List[str]: 활성화된 심볼 리스트
    """
    try:
        query = supabase.table("stock_names").select("symbol").eq("is_active", True)

        if country:
            query = query.eq("country", country)

        response = query.execute()

        symbols = [row["symbol"] for row in response.data]
        logger.info(f"활성화된 종목 {len(symbols)}개 조회 (국가: {country})")
        return symbols
    except Exception as e:
        logger.error(f"활성화된 종목 조회 실패: {str(e)}", exc_info=True)
        return []


async def deactivate_missing_stocks(
    symbols: List[str], country: Optional[str] = None
) -> int:
    """
    stock_names 테이블에서 지정된 심볼 목록에 없는 활성화된 종목을 비활성화합니다.

    Args:
        symbols: 유지할 심볼 목록
        country: 국가 코드 (None이면 전체)

    Returns:
        int: 비활성화된 종목 수
    """
    if not symbols:
        return 0

    try:
        # 활성화된 종목 중에서 symbols에 없는 것들을 찾기
        active_symbols = await get_active_stock_symbols_by_country(country)
        symbols_set = set(s.upper() for s in symbols)
        missing_symbols = [s for s in active_symbols if s not in symbols_set]

        if not missing_symbols:
            return 0

        # 비활성화
        response = (
            supabase.table("stock_names")
            .update({"is_active": False})
            .in_("symbol", missing_symbols)
            .execute()
        )

        deactivated = len(missing_symbols)
        logger.info(f"stock_names {deactivated}개 종목 비활성화 완료")
        return deactivated
    except Exception as e:
        logger.error(f"종목 비활성화 실패: {str(e)}", exc_info=True)
        send_slack_error_log(None, e)
        return 0


async def get_exchange_rate(symbol: str, date: Optional[str] = None) -> Optional[dict]:
    """
    exchange_rates 테이블에서 환율/인덱스 데이터를 조회합니다.

    Args:
        symbol: 심볼
        date: 날짜 (None이면 가장 최근 날짜)

    Returns:
        Optional[dict]: 환율 데이터 (없으면 None)
    """
    try:
        query = supabase.table("exchange_rates").select("*").eq("symbol", symbol)

        if date:
            query = query.eq("date", date)
        else:
            query = query.order("date", desc=True).limit(1)

        response = query.execute()

        if response.data:
            row = response.data[0]
            return {
                "symbol": row["symbol"],
                "date": row["date"],
                "close_price": float(row["close_price"]),
                "adj_close_price": (
                    float(row["adj_close_price"])
                    if row.get("adj_close_price")
                    else None
                ),
                "currency": row.get("currency"),
                "name": row.get("name"),
            }

        return None
    except Exception as e:
        logger.error(f"exchange_rates 조회 실패 ({symbol}): {str(e)}", exc_info=True)
        return None


async def get_exchange_rate_history(
    symbol: str, start_date: str, end_date: str
) -> List[dict]:
    """
    exchange_rates 테이블에서 시계열 데이터를 조회합니다.

    Args:
        symbol: 심볼
        start_date: 시작 날짜 (YYYY-MM-DD)
        end_date: 종료 날짜 (YYYY-MM-DD)

    Returns:
        List[dict]: 시계열 데이터 리스트
    """
    try:
        response = (
            supabase.table("exchange_rates")
            .select("*")
            .eq("symbol", symbol)
            .gte("date", start_date)
            .lte("date", end_date)
            .order("date", desc=False)
            .execute()
        )

        result = []
        for row in response.data:
            result.append(
                {
                    "date": row["date"],
                    "close_price": float(row["close_price"]),
                    "adj_close_price": (
                        float(row["adj_close_price"])
                        if row.get("adj_close_price")
                        else None
                    ),
                    "currency": row.get("currency"),
                    "name": row.get("name"),
                }
            )

        return result
    except Exception as e:
        logger.error(
            f"exchange_rates 시계열 조회 실패 ({symbol}): {str(e)}", exc_info=True
        )
        return []


# 심볼 캐시 (메모리)
SYMBOL_CACHE: Dict[str, str] = {}


async def load_symbol_cache() -> None:
    """
    서버 시작 시 stock_names 테이블에서 심볼 캐시를 로드합니다.
    이름→심볼, 심볼→심볼 매핑을 메모리에 저장합니다.
    """
    try:
        response = (
            supabase.table("stock_names")
            .select("symbol, name")
            .eq("is_active", True)
            .execute()
        )

        SYMBOL_CACHE.clear()
        for row in response.data:
            symbol = row["symbol"]
            name = row.get("name")

            # 심볼 → 심볼 매핑
            SYMBOL_CACHE[symbol] = symbol

            # 이름 → 심볼 매핑
            if name:
                SYMBOL_CACHE[name] = symbol

        logger.info(f"심볼 캐시 로드 완료: {len(SYMBOL_CACHE)}개 항목")
    except Exception as e:
        logger.error(f"심볼 캐시 로드 실패: {str(e)}", exc_info=True)


def resolve_symbol_from_cache(name_or_symbol: str) -> str:
    """
    SYMBOL_CACHE에서 심볼을 조회합니다.
    없으면 입력값을 그대로 반환합니다.

    Args:
        name_or_symbol: 한국어 이름 또는 심볼

    Returns:
        str: 변환된 심볼 (없으면 입력값 그대로)
    """
    return SYMBOL_CACHE.get(name_or_symbol, name_or_symbol)


async def get_max_date(symbol: str) -> Optional[str]:
    """
    exchange_rates 테이블에서 특정 심볼의 최대 날짜를 조회합니다.
    증분 수집 최적화에 사용됩니다.

    Args:
        symbol: 심볼

    Returns:
        Optional[str]: 최대 날짜 (YYYY-MM-DD 형식, 없으면 None)
    """
    try:
        response = (
            supabase.table("exchange_rates")
            .select("date")
            .eq("symbol", symbol)
            .order("date", desc=True)
            .limit(1)
            .execute()
        )

        if response.data:
            return response.data[0]["date"]
        return None
    except Exception as e:
        logger.error(f"최대 날짜 조회 실패 ({symbol}): {str(e)}", exc_info=True)
        return None


async def upsert_exchange_rates(records: List[dict]) -> tuple[int, Optional[str]]:
    """
    exchange_rates 테이블에 대량 upsert를 수행합니다.

    Args:
        records: upsert할 레코드 리스트

    Returns:
        tuple[int, Optional[str]]: (upsert된 개수, 에러 메시지)
    """
    if not records:
        return 0, None

    try:
        response = (
            supabase.table("exchange_rates")
            .upsert(records, on_conflict="symbol,date")
            .execute()
        )

        upserted = len(response.data) if response.data else 0
        logger.info(f"exchange_rates {upserted}개 레코드 upsert 완료")
        return upserted, None
    except Exception as e:
        error_msg = f"exchange_rates upsert 실패: {str(e)}"
        logger.error(error_msg, exc_info=True)
        send_slack_error_log(None, e)
        return 0, error_msg


async def get_active_exchange_rate_symbols() -> List[str]:
    """
    stock_names 테이블에서 활성화된 환율/인덱스 심볼 목록을 조회합니다.

    Returns:
        List[str]: 활성화된 심볼 리스트
    """
    try:
        response = (
            supabase.table("stock_names")
            .select("symbol")
            .eq("is_active", True)
            .in_("asset_type", ["FX", "CRYPTO", "INDEX"])
            .execute()
        )

        symbols = [row["symbol"] for row in response.data]
        logger.info(f"활성화된 환율/인덱스 심볼 {len(symbols)}개 조회")
        return symbols
    except Exception as e:
        logger.error(f"활성화된 환율/인덱스 심볼 조회 실패: {str(e)}", exc_info=True)
        return []


async def get_symbol_metadata(symbol: str) -> Optional[dict]:
    """
    stock_names 테이블에서 심볼 메타데이터를 조회합니다.

    Args:
        symbol: 심볼

    Returns:
        Optional[dict]: 메타데이터 (name, currency 등, 없으면 None)
    """
    try:
        response = (
            supabase.table("stock_names")
            .select("name, currency")
            .eq("symbol", symbol)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )

        if response.data:
            row = response.data[0]
            return {
                "name": row.get("name"),
                "currency": row.get("currency"),
            }
        return None
    except Exception as e:
        logger.error(f"심볼 메타데이터 조회 실패 ({symbol}): {str(e)}", exc_info=True)
        return None
