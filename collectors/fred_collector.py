from __future__ import annotations
"""
FRED API Data Collector
========================
FRED(Federal Reserve Economic Data)에서 경제 지표 시계열 수집
- 증분 수집: 마지막 수집 날짜 이후 데이터만 가져옴
- Rate limit 준수: 120 requests/minute
- 에러 핸들링 + 재시도 로직
"""

import time
from datetime import datetime, date, timedelta

import pandas as pd
from fredapi import Fred
from loguru import logger

from config.indicators import Indicator, FRED_INDICATORS
from db.database import DatabaseManager


class FredCollector:
    """FRED API에서 경제 지표 데이터를 수집"""

    # FRED API rate limit: 120 requests/min → ~0.5초 간격
    REQUEST_DELAY = 0.55

    def __init__(self, api_key: str, db: DatabaseManager):
        self.fred = Fred(api_key=api_key)
        self.db = db
        self._request_count = 0
        self._last_request_time = 0.0

    def _rate_limit(self):
        """Rate limit 준수"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()
        self._request_count += 1

    def fetch_series(self, series_code: str, start_date: date | None = None,
                     observation_start: str = "2000-01-01") -> pd.DataFrame | None:
        """
        단일 FRED 시리즈 데이터 수집

        Args:
            series_code: FRED series ID (e.g. "INDPRO")
            start_date: 이 날짜 이후 데이터만 (증분 수집)
            observation_start: 최초 수집 시 시작일

        Returns:
            DataFrame with columns [date, value] or None on error
        """
        self._rate_limit()

        try:
            if start_date:
                # 증분: 마지막 날짜 다음날부터
                obs_start = (start_date + timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                obs_start = observation_start

            data = self.fred.get_series(
                series_code,
                observation_start=obs_start,
            )

            if data is None or data.empty:
                logger.debug(f"  {series_code}: no new data since {obs_start}")
                return None

            # NaN 제거 후 DataFrame 변환
            data = data.dropna()
            df = pd.DataFrame({
                "date": data.index.date,
                "value": data.values,
            })

            logger.debug(f"  {series_code}: fetched {len(df)} records")
            return df

        except Exception as e:
            logger.error(f"  {series_code}: FRED fetch error — {e}")
            return None

    def collect_indicator(self, indicator: Indicator) -> dict:
        """
        하나의 지표에 속한 모든 FRED 시리즈를 수집하여 DB에 저장

        Returns:
            {"indicator_id": str, "series_results": [{"code": str, "added": int, "status": str}]}
        """
        results = []
        started_at = datetime.utcnow()

        logger.info(f"Collecting: {indicator.id} — {indicator.name}")
        logger.info(f"  Series count: {len(indicator.fred_series)}")

        for series in indicator.fred_series:
            series_start = datetime.utcnow()

            # 마지막 수집 날짜 확인 (증분 수집)
            latest_date = self.db.get_latest_date(series.code)

            # FRED에서 데이터 가져오기
            df = self.fetch_series(series.code, start_date=latest_date)

            if df is None or df.empty:
                status = "no_update"
                added = 0
            else:
                # DB에 저장
                records = [
                    {
                        "indicator_id": indicator.id,
                        "series_code": series.code,
                        "date": row["date"],
                        "value": float(row["value"]),
                        "source_type": "fred",
                    }
                    for _, row in df.iterrows()
                ]
                added = self.db.insert_timeseries(records)
                status = "success" if added > 0 else "no_update"

            # 수집 로그
            self.db.log_collection(
                indicator_id=indicator.id,
                series_code=series.code,
                source_type="fred",
                status=status,
                records_added=added,
                started_at=series_start,
            )

            results.append({"code": series.code, "added": added, "status": status})

        total_added = sum(r["added"] for r in results)
        logger.info(f"  → Total new records: {total_added}")

        return {"indicator_id": indicator.id, "series_results": results}

    def collect_all(self, indicators: list[Indicator] | None = None) -> list[dict]:
        """
        모든 FRED 기반 지표 수집 (전체 또는 선택)

        Args:
            indicators: 수집할 지표 리스트 (None이면 FRED_INDICATORS 전체)
        """
        targets = indicators or FRED_INDICATORS
        total_series = sum(len(ind.fred_series) for ind in targets)

        logger.info("=" * 60)
        logger.info(f"FRED Collection Start")
        logger.info(f"  Indicators: {len(targets)} | Series: {total_series}")
        logger.info("=" * 60)

        all_results = []
        start_time = time.time()

        for i, indicator in enumerate(targets, 1):
            logger.info(f"[{i}/{len(targets)}] {indicator.id}")
            result = self.collect_indicator(indicator)
            all_results.append(result)

        elapsed = time.time() - start_time
        total_added = sum(
            sum(r["added"] for r in res["series_results"])
            for res in all_results
        )

        logger.info("=" * 60)
        logger.info(f"FRED Collection Complete")
        logger.info(f"  Time: {elapsed:.1f}s | New records: {total_added}")
        logger.info(f"  API calls: {self._request_count}")
        logger.info("=" * 60)

        return all_results

    def get_series_info(self, series_code: str) -> dict | None:
        """FRED 시리즈 메타데이터 조회 (디버깅/확인용)"""
        self._rate_limit()
        try:
            info = self.fred.get_series_info(series_code)
            return {
                "id": info["id"],
                "title": info["title"],
                "frequency": info["frequency_short"],
                "units": info["units"],
                "seasonal_adjustment": info["seasonal_adjustment_short"],
                "last_updated": str(info["last_updated"]),
            }
        except Exception as e:
            logger.error(f"Series info error for {series_code}: {e}")
            return None

    def validate_all_series(self) -> dict:
        """모든 FRED 시리즈 코드가 유효한지 확인"""
        from config.indicators import get_all_fred_series

        all_series = get_all_fred_series()
        valid, invalid = [], []

        logger.info(f"Validating {len(all_series)} FRED series codes...")

        for ind_id, code, name in all_series:
            info = self.get_series_info(code)
            if info:
                valid.append({"indicator": ind_id, "code": code, "title": info["title"]})
            else:
                invalid.append({"indicator": ind_id, "code": code, "expected": name})

        logger.info(f"Valid: {len(valid)} | Invalid: {len(invalid)}")
        if invalid:
            logger.warning(f"Invalid series: {[i['code'] for i in invalid]}")

        return {"valid": valid, "invalid": invalid}
