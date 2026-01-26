"""아파트 실거래가 수집 서비스"""

import asyncio
import hashlib
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests

from app.config import settings
from app.repositories.supabase_client import (
    get_bjd_codes,
    get_locatadd_nm,
    upsert_apt_sales,
)
from app.utils.logging_config import get_logger
from app.utils.slack_notifier import send_slack_error_log

logger = get_logger(__name__)


def get_target_months() -> List[str]:
    """
    이번 달과 지난달의 연월(YYYYMM)을 반환합니다.
    데이터 누락 방지를 위해 두 달치를 수집합니다.

    Returns:
        List[str]: 연월 리스트 (예: ["202412", "202501"])
    """
    now = datetime.now()

    # 이번 달
    current_month = now.strftime("%Y%m")

    # 지난달 (30일 전)
    last_month = (now - timedelta(days=30)).strftime("%Y%m")

    return [last_month, current_month]


def generate_apt_id(
    apt_name: str,
    deal_amount: int,
    area: float,
    floor: int,
    deal_date: str,
    lawd_code: str,
) -> str:
    """
    아파트 실거래 데이터의 고유 ID를 생성합니다.
    법정동코드+아파트명+금액+면적+층+거래일을 조합하여 MD5 해시를 생성합니다.

    Args:
        apt_name: 아파트명
        deal_amount: 거래금액 (만원)
        area: 전용면적 (㎡)
        floor: 층
        deal_date: 거래일 (YYYY-MM-DD)
        lawd_code: 법정동코드 (5자리)

    Returns:
        str: MD5 해시 문자열
    """
    # 고유 식별자 생성 (법정동코드 포함으로 지역별 중복 방지)
    unique_str = f"{lawd_code}_{apt_name}_{deal_amount}_{area}_{floor}_{deal_date}"

    # MD5 해시 생성
    hash_obj = hashlib.md5(unique_str.encode("utf-8"))
    return hash_obj.hexdigest()


def fetch_apt_sales_data(
    lawd_code: str, deal_ym: str, locatadd_nm: Optional[str] = None
) -> List[dict]:
    """
    공공데이터포털 API를 호출하여 아파트 실거래가 데이터를 가져옵니다.

    Args:
        lawd_code: 법정동코드 (5자리)
        deal_ym: 거래연월 (YYYYMM)
        locatadd_nm: 법정동명 (예: "서울특별시 종로구")

    Returns:
        List[dict]: 파싱된 실거래가 데이터 리스트

    Raises:
        Exception: API 호출 실패 또는 XML 파싱 오류
    """
    url = (
        f"https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
        f"?serviceKey={settings.data_go_api_key}"
        f"&LAWD_CD={lawd_code}"
        f"&DEAL_YMD={deal_ym}"
        f"&numOfRows=999"
    )

    try:
        logger.info(f"공공데이터 API 호출: lawd_code={lawd_code}, deal_ym={deal_ym}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # XML 파싱
        root = ET.fromstring(response.content)

        # 응답 코드 확인
        result_code = root.findtext(".//resultCode")
        result_msg = root.findtext(".//resultMsg")

        # 성공 코드: 00 또는 000
        if result_code not in ["00", "000"]:
            error_msg = f"API 오류: resultCode={result_code}, resultMsg={result_msg}"
            logger.warning(error_msg)
            raise Exception(error_msg)

        # 데이터 파싱
        data_list = []
        for item in root.findall(".//item"):
            try:
                # 필드 추출 및 trim
                apt_name = (
                    item.findtext("아파트") or item.findtext("aptNm") or ""
                ).strip()
                area_str = (
                    item.findtext("전용면적") or item.findtext("excluUseAr") or ""
                ).strip()
                floor_str = (
                    item.findtext("층") or item.findtext("floor") or ""
                ).strip()
                deal_amount_str = (
                    item.findtext("거래금액") or item.findtext("dealAmount") or ""
                ).strip()
                deal_year = (
                    item.findtext("거래년도") or item.findtext("dealYear") or ""
                ).strip()
                deal_month = (
                    (item.findtext("거래월") or item.findtext("dealMonth") or "")
                    .strip()
                    .zfill(2)
                )
                deal_day = (
                    (item.findtext("거래일") or item.findtext("dealDay") or "")
                    .strip()
                    .zfill(2)
                )

                # 필수 필드 검증
                if not all(
                    [apt_name, deal_amount_str, deal_year, deal_month, deal_day]
                ):
                    logger.warning(
                        f"필수 필드 누락: {ET.tostring(item, encoding='unicode')[:200]}"
                    )
                    continue

                # 데이터 타입 변환
                # 거래금액: 콤마 제거 후 정수 변환
                deal_amount = int(deal_amount_str.replace(",", "").replace(" ", ""))

                # 면적: 소수점 변환
                area = float(area_str) if area_str else None

                # 층: 정수 변환
                floor = int(floor_str) if floor_str else None

                # 거래일 생성 (YYYY-MM-DD)
                deal_date = f"{deal_year}-{deal_month}-{deal_day}"

                # 고유 ID 생성 (법정동코드 포함)
                apt_id = generate_apt_id(
                    apt_name=apt_name,
                    deal_amount=deal_amount,
                    area=area or 0.0,
                    floor=floor or 0,
                    deal_date=deal_date,
                    lawd_code=lawd_code,
                )

                data_list.append(
                    {
                        "id": apt_id,
                        "apt_name": apt_name,
                        "area": area,
                        "floor": floor,
                        "deal_amount": deal_amount,
                        "deal_date": deal_date,
                        "deal_year": deal_year,
                        "deal_month": deal_month,
                        "deal_day": deal_day,
                        "lawd_code": lawd_code,
                        "locatadd_nm": locatadd_nm,
                    }
                )

            except Exception as e:
                logger.warning(f"아이템 파싱 실패: {str(e)}", exc_info=True)
                continue

        # 중복 ID 제거 (같은 거래가 여러 번 포함된 경우 대비)
        unique_data = {}
        for item in data_list:
            item_id = item["id"]
            if item_id not in unique_data:
                unique_data[item_id] = item
            else:
                # 중복 발견 시 로그
                logger.debug(f"중복 ID 발견 및 제거: {item_id}")

        final_data = list(unique_data.values())
        logger.info(
            f"{lawd_code}/{deal_ym}: {len(data_list)}개 데이터 파싱 완료 (중복 제거 후 {len(final_data)}개)"
        )
        return final_data

    except ET.ParseError as e:
        error_msg = f"XML 파싱 오류 ({lawd_code}/{deal_ym}): {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg) from e
    except requests.RequestException as e:
        error_msg = f"API 호출 실패 ({lawd_code}/{deal_ym}): {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg) from e


async def sync_apt_sales(
    lawd_codes: Optional[List[str]] = None,
    deal_ym: Optional[str] = None,
    priority: Optional[int] = 1,
) -> Dict:
    """
    아파트 실거래가 데이터를 수집하여 Supabase에 저장합니다.

    Args:
        lawd_codes: 법정동코드 리스트 (지정 시 priority 무시)
        deal_ym: 거래연월 (None이면 이번 달과 지난달)
        priority: 우선순위 필터 (1=최우선만, 2=중요까지, 3=일반까지, None=전체)
                 기본값 1 (API 할당량 보호)

    Returns:
        Dict: 처리 결과 (success, total, upserted, errors)
    """
    try:
        # 1. 법정동코드 목록 결정
        target_lawd_codes = await get_bjd_codes(
            lawd_codes=lawd_codes, priority=priority
        )

        if lawd_codes:
            logger.info(f"명시적으로 지정된 법정동코드 {len(target_lawd_codes)}개 사용")
        else:
            logger.info(
                f"DB에서 법정동코드 {len(target_lawd_codes)}개 조회 (priority<={priority})"
            )

        # 1.5. 법정동명 캐시 생성 (효율적인 조회를 위해)
        locatadd_nm_cache: Dict[str, Optional[str]] = {}
        for code in target_lawd_codes:
            locatadd_nm_cache[code] = await get_locatadd_nm(code)
        logger.info(f"법정동명 캐시 생성 완료: {len(locatadd_nm_cache)}개")

        # 2. 거래연월 목록 결정
        if deal_ym is None:
            target_months = get_target_months()
            logger.info(f"자동 생성된 연월: {target_months}")
        else:
            target_months = [deal_ym]
            logger.info(f"지정된 연월: {target_months}")

        # 3. 수집 시작 - 모든 데이터를 먼저 수집
        all_records: List[dict] = []
        errors: List[str] = []

        # 법정동코드 × 연월 조합으로 처리
        async def process_combination(code: str, ym: str) -> List[dict]:
            try:
                # Rate Limiting: 랜덤 딜레이 (0.5~2초)
                delay = random.uniform(0.5, 2.0)
                await asyncio.sleep(delay)
                logger.debug(f"{code}/{ym}: {delay:.2f}초 대기 후 API 호출")

                # 법정동명 가져오기
                locatadd_nm = locatadd_nm_cache.get(code)

                # API 호출 (동기 함수를 비동기로 실행)
                records = await asyncio.to_thread(
                    fetch_apt_sales_data, code, ym, locatadd_nm
                )

                if not records:
                    logger.info(f"{code}/{ym}: 데이터 없음")
                    return []

                logger.info(f"{code}/{ym}: {len(records)}개 데이터 수집 완료")
                return records

            except Exception as e:
                error_msg = f"{code}/{ym}: 수집 실패 - {str(e)}"
                logger.error(error_msg, exc_info=True)
                send_slack_error_log(None, e)
                errors.append(error_msg)
                return []

        # 병렬 처리 (모든 조합에 대해)
        tasks = [
            process_combination(code, ym)
            for code in target_lawd_codes
            for ym in target_months
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 4. 모든 데이터 모으기
        for result in results:
            if isinstance(result, list):
                all_records.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"수집 중 예외 발생: {str(result)}", exc_info=result)

        total_records = len(all_records)
        logger.info(f"총 {total_records}개 레코드 수집 완료")

        # 5. 전역 중복 제거 (ID 기준)
        unique_records = {}
        duplicate_count = 0
        for record in all_records:
            record_id = record["id"]
            if record_id not in unique_records:
                unique_records[record_id] = record
            else:
                duplicate_count += 1
                logger.debug(
                    f"중복 ID 발견 및 제거: {record_id} "
                    f"(기존: {unique_records[record_id]['lawd_code']}, "
                    f"중복: {record['lawd_code']})"
                )

        final_records = list(unique_records.values())
        logger.info(
            f"중복 제거 완료: {total_records}개 → {len(final_records)}개 "
            f"(중복 {duplicate_count}개 제거)"
        )

        # 6. 한 번에 Upsert
        upsert_total = 0
        if final_records:
            upserted, upsert_error = await upsert_apt_sales(final_records)
            upsert_total = upserted

            if upsert_error:
                errors.append(f"Upsert 실패: {upsert_error}")
            else:
                logger.info(f"{upserted}개 레코드 Upsert 완료")
        else:
            logger.warning("저장할 데이터가 없습니다")

        # 결과 반환
        return {
            "success": len(errors) == 0,
            "total": total_records,
            "upserted": upsert_total,
            "lawd_codes": target_lawd_codes,
            "deal_months": target_months,
            "errors": errors,
        }

    except Exception as e:
        error_msg = f"아파트 실거래가 동기화 실패: {str(e)}"
        logger.error(error_msg, exc_info=True)
        send_slack_error_log(None, e)
        raise Exception(error_msg) from e
