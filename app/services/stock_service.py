"""주식 가격 업데이트 비즈니스 로직"""

import traceback
from typing import List, Optional, Dict
from app.config import get_stock_symbols_override
from app.repositories.supabase_client import (
    get_managed_stocks,
    get_today_stock_prices,
    save_stock_price_to_db,
)
from app.services.yahoo_finance import get_quote_data
from app.utils.logging_config import get_logger
from app.exceptions import StockPriceUpdaterException

logger = get_logger(__name__)


class SymbolResult:
    """심볼 처리 결과"""

    def __init__(self, symbol: str, success: bool, error: Optional[str] = None):
        self.symbol = symbol
        self.success = success
        self.error = error

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        result = {
            "symbol": self.symbol,
            "success": self.success,
        }
        if self.error:
            result["error"] = self.error
        return result


async def determine_symbols(
    request_symbols: Optional[List[str]] = None,
    country: Optional[str] = None,
) -> List[str]:
    """
    심볼 목록 결정 (우선순위: request body > 환경변수 > DB)

    Args:
        request_symbols: 요청 본문의 심볼 목록
        country: 국가 필터

    Returns:
        List[str]: 결정된 심볼 목록
    """
    symbols: List[str] = []

    if request_symbols:
        symbols = [s.strip().upper() for s in request_symbols if s.strip()]
        logger.info(f"Request body에서 {len(symbols)}개 심볼 받음: {symbols}")
    else:
        # 환경변수 오버라이드 확인
        env_symbols = get_stock_symbols_override()
        if env_symbols:
            symbols = env_symbols
            logger.info(f"환경변수에서 {len(symbols)}개 심볼 로드: {symbols}")
        else:
            # DB에서 활성화된 종목 조회
            symbols = await get_managed_stocks(country=country)
            logger.info(f"DB에서 {len(symbols)}개 활성화된 종목 조회: {symbols}")

    return symbols


async def filter_symbols_to_fetch(
    symbols: List[str],
) -> tuple[List[str], Dict[str, dict]]:
    """
    실제 API 호출이 필요한 심볼만 필터링 (N+1 문제 방지)

    Args:
        symbols: 전체 심볼 목록

    Returns:
        tuple[List[str], Dict[str, dict]]: (API 호출 필요한 심볼 목록, 이미 존재하는 가격 데이터)
    """
    if not symbols:
        return [], {}

    # 오늘 날짜 데이터를 한 번에 조회 (N+1 문제 방지)
    existing_prices = await get_today_stock_prices(symbols)
    existing_symbols = set(existing_prices.keys())
    all_symbols = set(s.upper() for s in symbols)

    # 메모리에서 비교: 수집해야 할 목록 - 이미 있는 목록 = API 호출할 목록
    symbols_to_fetch = list(all_symbols - existing_symbols)

    logger.info(
        f"배치 작업 시작: 전체 {len(all_symbols)}개, "
        f"이미 있음 {len(existing_symbols)}개, "
        f"API 호출 필요 {len(symbols_to_fetch)}개"
    )

    return symbols_to_fetch, existing_prices


async def update_stock_prices(
    request_symbols: Optional[List[str]] = None,
    country: Optional[str] = None,
) -> Dict:
    """
    주식 가격을 업데이트하는 메인 비즈니스 로직

    성능 최적화:
    1. managed_stocks에서 활성화된 심볼 목록 조회 (쿼리 1번)
    2. stock_prices에서 오늘 날짜 데이터를 한 번에 조회 (쿼리 1번)
    3. 메모리에서 비교하여 실제 API 호출이 필요한 심볼만 필터링
    4. 각 심볼에 대해 개별 try-except로 실패 격리

    Args:
        request_symbols: 요청 본문의 심볼 목록
        country: 국가 필터

    Returns:
        Dict: 업데이트 결과 (success, total, successCount, failureCount, results)
    """
    try:
        # 1. 심볼 목록 결정
        symbols = await determine_symbols(request_symbols, country)

        if not symbols:
            return {
                "success": True,
                "total": 0,
                "successCount": 0,
                "failureCount": 0,
                "results": [],
            }

        # 2. API 호출이 필요한 심볼 필터링
        symbols_to_fetch, existing_prices = await filter_symbols_to_fetch(symbols)

        # 전체 업데이트 대상 종목 수 계산
        total_symbols = len(symbols_to_fetch) + len(existing_prices)

        # 🚀 시작 로그
        logger.info(f"🚀 배치 작업 시작 - 업데이트 대상: {total_symbols}개 종목")

        # 3. 각 심볼에 대해 개별 try-except로 실패 격리
        results: List[SymbolResult] = []
        failed_symbols: List[str] = []  # 실패한 종목 리스트

        # 이미 있는 종목은 성공으로 처리
        for idx, symbol in enumerate(existing_prices.keys(), start=1):
            results.append(SymbolResult(symbol=symbol, success=True))
            logger.info(f"[{idx}/{total_symbols}] '{symbol}' - 이미 DB에 존재하여 스킵")

        # API 호출이 필요한 종목 처리
        processed_count = len(existing_prices)
        for symbol in symbols_to_fetch:
            processed_count += 1
            try:
                # 진행 상황 로그: 시작
                logger.info(
                    f"[{processed_count}/{total_symbols}] '{symbol}' 데이터 업데이트 시도..."
                )

                # Yahoo Finance API에서 데이터 가져오기
                quote_data, error_reason = await get_quote_data(symbol)

                if not quote_data:
                    # error_reason이 있으면 구체적인 원인 사용, 없으면 기본 메시지
                    error_msg = error_reason or "가격 정보를 찾을 수 없습니다."
                    results.append(
                        SymbolResult(
                            symbol=symbol,
                            success=False,
                            error=error_msg,
                        )
                    )
                    failed_symbols.append(symbol)
                    logger.error(f"🚨 '{symbol}' 업데이트 실패 - {error_msg}")
                    continue

                # Supabase에 저장
                saved = await save_stock_price_to_db(symbol, quote_data)

                if saved:
                    results.append(SymbolResult(symbol=symbol, success=True))
                    logger.info(f"✅ '{symbol}' 업데이트 성공")
                else:
                    error_msg = "Supabase 저장 실패"
                    results.append(
                        SymbolResult(
                            symbol=symbol,
                            success=False,
                            error=error_msg,
                        )
                    )
                    failed_symbols.append(symbol)
                    logger.error(f"🚨 '{symbol}' 업데이트 실패 - {error_msg}")

            except Exception as e:
                # 실패 격리: 한 종목 실패가 전체를 중단시키지 않음
                error_message = str(e)
                results.append(
                    SymbolResult(symbol=symbol, success=False, error=error_message)
                )
                failed_symbols.append(symbol)

                # 상세 에러 로그 (traceback 포함)
                error_traceback = traceback.format_exc()
                logger.error(
                    f"🚨 '{symbol}' 업데이트 실패 - {error_message}\n"
                    f"Traceback:\n{error_traceback}"
                )

        # 통계 계산
        success_count = sum(1 for r in results if r.success)
        failure_count = sum(1 for r in results if not r.success)

        # 🏁 최종 요약 로그
        if failed_symbols:
            logger.info(
                f"🏁 배치 작업 종료 - 전체: {total_symbols}, "
                f"성공: {success_count}, 실패: {failure_count} "
                f"(실패 종목: {', '.join(failed_symbols)})"
            )
        else:
            logger.info(
                f"🏁 배치 작업 종료 - 전체: {total_symbols}, "
                f"성공: {success_count}, 실패: {failure_count}"
            )

        return {
            "success": True,
            "total": len(results),
            "successCount": success_count,
            "failureCount": failure_count,
            "results": [r.to_dict() for r in results],
        }

    except Exception as e:
        logger.error(f"배치 작업 중 오류 발생: {str(e)}", exc_info=True)
        raise StockPriceUpdaterException(
            f"배치 작업 중 오류가 발생했습니다: {str(e)}"
        ) from e
