from datetime import datetime, timedelta
from typing import Optional, Dict, List
from supabase import create_client, Client
from app.config import settings
import logging
import json

logger = logging.getLogger(__name__)

# Supabase 클라이언트 초기화
supabase: Client = create_client(settings.supabase_url, settings.supabase_anon_key)


def get_today_date() -> str:
    """오늘 날짜를 YYYY-MM-DD 형식으로 반환 (한국 시간 기준 UTC+9)"""
    now = datetime.utcnow()
    korea_time = now + timedelta(hours=9)
    return korea_time.strftime("%Y-%m-%d")


def get_yesterday_date() -> str:
    """어제 날짜를 YYYY-MM-DD 형식으로 반환 (한국 시간 기준 UTC+9)"""
    now = datetime.utcnow()
    korea_time = now + timedelta(hours=9)
    yesterday = korea_time - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


async def get_managed_stocks() -> List[str]:
    """managed_stocks 테이블에서 활성화된 심볼 목록 조회"""
    try:
        response = (
            supabase.table("managed_stocks")
            .select("symbol")
            .eq("enabled", True)
            .execute()
        )

        symbols = [row["symbol"].upper() for row in response.data]
        logger.info(f"활성화된 종목 {len(symbols)}개 조회: {symbols}")
        return symbols
    except json.JSONDecodeError as e:
        logger.error(f"JSON 디코드 오류 (managed_stocks): {str(e)}", exc_info=True)
        logger.error(f"응답 내용: {getattr(response, 'text', 'N/A') if 'response' in locals() else 'N/A'}")
        raise
    except Exception as e:
        logger.error(f"managed_stocks 조회 실패: {str(e)}", exc_info=True)
        raise


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
        logger.error(f"JSON 디코드 오류 (get_today_stock_prices): {str(e)}", exc_info=True)
        logger.error(f"응답 내용: {getattr(response, 'text', 'N/A') if 'response' in locals() else 'N/A'}")
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
        logger.error(f"응답 내용: {getattr(response, 'text', 'N/A') if 'response' in locals() else 'N/A'}")
        return None
    except Exception as e:
        logger.error(f"{symbol} 조회 실패: {str(e)}", exc_info=True)
        return None


async def save_stock_price_to_db(
    symbol: str, quote_data: dict, date: Optional[str] = None
) -> bool:
    """
    Supabase에 주식 종가 저장
    중복 체크 후 저장 (symbol, date 조합이 unique)
    """
    normalized_symbol = symbol.strip().upper()
    target_date = date or get_today_date()

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
            return True
        else:
            logger.warning(f"{symbol} 저장 실패: 응답 데이터 없음")
            return False
    except json.JSONDecodeError as e:
        logger.error(f"JSON 디코드 오류 ({symbol} 저장): {str(e)}", exc_info=True)
        logger.error(f"응답 내용: {getattr(response, 'text', 'N/A') if 'response' in locals() else 'N/A'}")
        logger.error(f"요청 데이터: {data}")
        return False
    except Exception as e:
        logger.error(f"{symbol} 저장 실패: {str(e)}", exc_info=True)
        return False
