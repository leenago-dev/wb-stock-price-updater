"""FinanceDataReader StockListing을 사용한 종목 목록 수집"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

import FinanceDataReader as fdr
import pandas as pd

from app.repositories.supabase_client import (
    upsert_stock_names,
    deactivate_missing_stocks,
)
from app.utils.logging_config import get_logger
from app.utils.rate_limiter import request_queue
from app.utils.slack_notifier import send_slack_error_log

logger = get_logger(__name__)

# 기본 시장 목록
DEFAULT_MARKETS = ["KRX", "ETF/KR", "S&P500", "NASDAQ", "NYSE", "AMEX"]

# 시장별 국가 매핑
MARKET_TO_COUNTRY = {
    "KRX": "KR",
    "ETF/KR": "KR",
    "S&P500": "US",
    "NASDAQ": "US",
    "NYSE": "US",
    "AMEX": "US",
}


def fetch_stock_listing(market: str) -> pd.DataFrame:
    """
    동기 함수: FinanceDataReader.StockListing 호출.
    """
    return fdr.StockListing(market)


async def fetch_and_normalize_market(market: str) -> List[dict]:
    """
    특정 시장의 종목 목록을 가져와서 정규화합니다.

    Args:
        market: 시장 코드 (예: "KRX", "NASDAQ")

    Returns:
        List[dict]: 정규화된 종목 레코드 리스트
    """
    try:
        # FDR StockListing 호출 (비동기로 래핑)
        async def fetch_data():
            return await asyncio.to_thread(fetch_stock_listing, market)

        df = await request_queue.add(fetch_data)

        if df is None or df.empty:
            logger.warning(f"{market}: FDR StockListing 결과가 비어있습니다")
            return []

        # Symbol과 Name 컬럼 확인
        if "Symbol" not in df.columns or "Name" not in df.columns:
            logger.warning(
                f"{market}: Symbol 또는 Name 컬럼이 없습니다. columns={list(df.columns)}"
            )
            return []

        # 국가 코드 결정
        country = MARKET_TO_COUNTRY.get(market)

        # 정규화
        records = []
        for _, row in df.iterrows():
            symbol = str(row["Symbol"]).strip().upper()
            name = str(row["Name"]).strip() if pd.notna(row["Name"]) else None

            if not symbol:
                continue

            records.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "country": country,
                    "source": "FDR",
                    "is_active": True,
                    "asset_type": "STOCK",
                }
            )

        logger.info(f"{market}: {len(records)}개 종목 수집 완료")
        return records

    except Exception as e:
        error_msg = f"{market}: 수집 실패 - {str(e)}"
        logger.error(error_msg, exc_info=True)
        send_slack_error_log(None, e)
        return []


def _partition_by_country(records: List[dict]) -> Dict[Optional[str], List[dict]]:
    """
    레코드를 country별로 그룹핑합니다.

    Args:
        records: 종목 레코드 리스트

    Returns:
        Dict[Optional[str], List[dict]]: country별로 그룹핑된 레코드
    """
    partitioned: Dict[Optional[str], List[dict]] = {}

    for record in records:
        country = record.get("country")
        if country not in partitioned:
            partitioned[country] = []
        partitioned[country].append(record)

    return partitioned


def _deduplicate_by_symbol(records: List[dict]) -> List[dict]:
    """
    symbol 기준으로 중복을 제거합니다. 마지막 값이 우선됩니다.

    Args:
        records: 종목 레코드 리스트

    Returns:
        List[dict]: 중복 제거된 레코드 리스트
    """
    seen = {}
    for record in records:
        symbol = record["symbol"]
        seen[symbol] = record

    return list(seen.values())


async def sync_stock_names(markets: Optional[List[str]] = None) -> Dict:
    """
    FDR StockListing으로 stock_names 테이블을 동기화합니다.

    Args:
        markets: 동기화할 시장 목록 (None이면 기본값 사용)

    Returns:
        Dict: 동기화 결과
    """
    if markets is None:
        markets = DEFAULT_MARKETS

    logger.info(f"종목 목록 동기화 시작: {markets}")

    # 1. 시장별 병렬 수집
    tasks = [fetch_and_normalize_market(market) for market in markets]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 2. 결과 수집 및 에러 처리
    all_records = []
    errors: List[str] = []

    for i, result in enumerate(results):
        market = markets[i]
        if isinstance(result, Exception):
            error_msg = f"{market}: 수집 실패 - {str(result)}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)
        else:
            all_records.extend(result)

    if not all_records:
        return {
            "success": False,
            "markets": markets,
            "uniqueSymbols": 0,
            "upserted": 0,
            "deactivated": 0,
            "errors": errors,
        }

    # 3. 중복 제거
    unique_records = _deduplicate_by_symbol(all_records)
    logger.info(f"중복 제거: {len(all_records)}개 → {len(unique_records)}개")

    # 4. 국가별 그룹핑
    partitioned = _partition_by_country(unique_records)

    # 5. 각 국가별로 upsert 및 비활성화 처리
    total_upserted = 0
    total_deactivated = 0

    for country, records in partitioned.items():
        try:
            # Upsert
            upserted, upsert_error = await upsert_stock_names(records)
            total_upserted += upserted
            if upsert_error:
                errors.append(f"{country}: {upsert_error}")

            # 비활성화 처리
            symbols = [r["symbol"] for r in records]
            deactivated = await deactivate_missing_stocks(symbols, country)
            total_deactivated += deactivated

        except Exception as e:
            error_msg = f"{country}: 처리 실패 - {str(e)}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

    return {
        "success": len(errors) == 0,
        "markets": markets,
        "uniqueSymbols": len(unique_records),
        "upserted": total_upserted,
        "deactivated": total_deactivated,
        "errors": errors,
    }
