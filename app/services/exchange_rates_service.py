from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import FinanceDataReader as fdr
import pandas as pd

from app.repositories.supabase_client import (
    get_max_date,
    upsert_exchange_rates,
    get_active_exchange_rate_symbols,
    get_symbol_metadata,
    resolve_symbol_from_cache,
)
from app.utils.logging_config import get_logger
from app.utils.rate_limiter import request_queue
from app.utils.slack_notifier import send_slack_error_log

logger = get_logger(__name__)


def resolve_symbol(name_or_symbol: str) -> str:
    """
    한국어 이름 또는 심볼을 심볼로 변환합니다.
    DB 캐시를 사용합니다.
    """
    return resolve_symbol_from_cache(name_or_symbol)


def fetch_exchange_rate_data(symbol: str, start_date: Optional[str] = None) -> pd.DataFrame:
    """
    동기 함수: FinanceDataReader.DataReader 호출.
    (네트워크/파싱이 있을 수 있어 비동기에서는 to_thread로 감쌉니다.)
    """
    if start_date:
        return fdr.DataReader(symbol, start=start_date)
    else:
        # 첫 수집: 최근 1년 데이터
        one_year_ago = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
        return fdr.DataReader(symbol, start=one_year_ago)


async def normalize_exchange_rate_data(symbol: str, df: pd.DataFrame) -> list[dict]:
    """
    FDR DataReader 결과를 exchange_rates upsert용 레코드로 변환합니다.
    Close와 Adj Close 둘 다 추출하고, DB에서 메타데이터를 조회합니다.
    """
    if df is None or df.empty:
        return []

    # DB에서 메타데이터 가져오기
    meta = await get_symbol_metadata(symbol)
    name = meta.get("name") if meta else None
    currency = meta.get("currency") if meta else None

    records: list[dict] = []

    # Date 인덱스가 DatetimeIndex가 아니면 Date 컬럼을 인덱스로 설정
    if not isinstance(df.index, pd.DatetimeIndex):
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date")
        else:
            logger.warning(f"{symbol}: Date 컬럼이나 인덱스를 찾을 수 없습니다. columns={list(df.columns)}")
            return []

    # Close와 Adj Close 컬럼 찾기
    close_col = None
    adj_close_col = None

    for col in df.columns:
        col_lower = str(col).lower()
        if col_lower == "close":
            close_col = col
        elif "adj" in col_lower and "close" in col_lower:
            adj_close_col = col

    if not close_col:
        logger.warning(f"{symbol}: Close 컬럼을 찾을 수 없습니다. columns={list(df.columns)}")
        return []

    for idx, row in df.iterrows():
        # 날짜 추출
        if isinstance(idx, pd.Timestamp):
            date_str = idx.strftime("%Y-%m-%d")
        else:
            date_str = str(idx)

        close_price = row.get(close_col)
        adj_close_price = row.get(adj_close_col) if adj_close_col else close_price

        if close_price is None or pd.isna(close_price):
            continue

        records.append(
            {
                "symbol": symbol,
                "date": date_str,
                "close_price": float(close_price),
                "adj_close_price": float(adj_close_price) if adj_close_price is not None and not pd.isna(adj_close_price) else None,
                "currency": currency,
                "name": name,
            }
        )

    return records


async def sync_exchange_rates(symbols: Optional[List[str]] = None) -> Dict:
    """
    FDR DataReader로 exchange_rates 테이블을 동기화합니다.
    MAX(date) 기반 증분 수집으로 최적화되어 있습니다.

    정책:
    - 각 심볼별로 가장 최근 날짜 조회
    - last_date 이후 데이터만 FDR에서 요청
    - Python 필터링 없이 DB upsert에 위임
    - symbols가 없으면 DB에서 활성화된 환율/인덱스 심볼을 자동 조회
    """
    if symbols is None:
        # DB에서 활성화된 환율/인덱스 심볼 조회
        target_symbols = await get_active_exchange_rate_symbols()
        logger.info(f"DB에서 활성화된 환율/인덱스 심볼 {len(target_symbols)}개 조회: {target_symbols}")
    else:
        target_symbols = symbols

    # 한국어 이름을 심볼로 변환
    resolved_symbols = [resolve_symbol(s) for s in target_symbols]

    upsert_total = 0
    errors: list[str] = []

    # 심볼별로 병렬 처리
    async def process_symbol(symbol: str):
        nonlocal upsert_total
        try:
            # 1) 가장 최근 날짜 조회
            last_date = await get_max_date(symbol)
            logger.info(f"{symbol}: 최근 날짜 조회 완료 - last_date={last_date}")

            # 2) FDR DataReader 호출 (last_date 이후만)
            async def fetch_data():
                return await asyncio.to_thread(fetch_exchange_rate_data, symbol, last_date)

            df = await request_queue.add(fetch_data)

            if df is None or df.empty:
                logger.warning(f"{symbol}: FDR DataReader 결과가 비어있습니다")
                return

            # 3) 정규화
            records = await normalize_exchange_rate_data(symbol, df)
            if not records:
                logger.warning(f"{symbol}: 정규화된 레코드가 없습니다")
                return

            logger.info(f"{symbol}: {len(records)}개 레코드 정규화 완료")

            # 4) Upsert (Python 필터링 없이 DB에 위임)
            upserted, upsert_error = await upsert_exchange_rates(records)
            upsert_total += upserted
            if upsert_error:
                errors.append(f"{symbol}: {upsert_error}")
            else:
                logger.info(f"{symbol}: {upserted}개 레코드 upsert 완료")

        except Exception as e:
            error_msg = f"{symbol}: 수집 실패 - {str(e)}"
            logger.error(error_msg, exc_info=True)
            send_slack_error_log(None, e)
            errors.append(error_msg)

    # 병렬 처리
    tasks = [process_symbol(s) for s in resolved_symbols]
    await asyncio.gather(*tasks, return_exceptions=True)

    return {
        "success": len(errors) == 0,
        "symbols": resolved_symbols,
        "upserted": upsert_total,
        "errors": errors,
    }
