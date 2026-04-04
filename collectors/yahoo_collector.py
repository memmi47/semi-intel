from __future__ import annotations
"""
Yahoo Finance Data Collector
==============================
반도체 섹터 지수(SOX, SOXX, SMH) + Hyperscaler 주가/CapEx 추적
"""

import time
from datetime import datetime, date, timedelta

import yfinance as yf
import pandas as pd
from loguru import logger

from config.indicators import Indicator, YAHOO_INDICATORS
from db.database import DatabaseManager


class YahooCollector:
    """Yahoo Finance에서 주가/지수 데이터 수집"""

    REQUEST_DELAY = 1.0  # yahoo는 rate limit이 더 엄격

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._request_count = 0

    def _rate_limit(self):
        time.sleep(self.REQUEST_DELAY)
        self._request_count += 1

    def fetch_symbol(self, symbol: str, indicator_id: str,
                     period: str = "max", start_date: date | None = None) -> pd.DataFrame | None:
        """
        단일 Yahoo Finance 심볼 수집

        Args:
            symbol: Yahoo ticker (e.g. "^SOX", "MSFT")
            indicator_id: 매핑할 indicator ID
            period: 최초 수집 시 기간 ("max", "5y", "1y" 등)
            start_date: 증분 수집 시 시작일
        """
        self._rate_limit()

        try:
            ticker = yf.Ticker(symbol)

            if start_date:
                start_str = (start_date + timedelta(days=1)).strftime("%Y-%m-%d")
                hist = ticker.history(start=start_str)
            else:
                hist = ticker.history(period=period)

            if hist is None or hist.empty:
                logger.debug(f"  {symbol}: no new data")
                return None

            # Close price를 주 데이터로 사용
            df = pd.DataFrame({
                "date": hist.index.date,
                "close": hist["Close"].values,
                "volume": hist["Volume"].values if "Volume" in hist.columns else 0,
            })
            df = df.dropna(subset=["close"])

            logger.debug(f"  {symbol}: fetched {len(df)} records")
            return df

        except Exception as e:
            logger.error(f"  {symbol}: Yahoo fetch error — {e}")
            return None

    def collect_indicator(self, indicator: Indicator) -> dict:
        """하나의 지표에 속한 모든 Yahoo 심볼 수집"""
        results = []
        started_at = datetime.utcnow()

        logger.info(f"Collecting Yahoo: {indicator.id} — {indicator.name}")

        for symbol in indicator.yahoo_symbols:
            # 증분 수집
            latest_date = self.db.get_latest_date(symbol)
            df = self.fetch_symbol(symbol, indicator.id, start_date=latest_date)

            if df is None or df.empty:
                status = "no_update"
                added = 0
            else:
                records = [
                    {
                        "indicator_id": indicator.id,
                        "series_code": symbol,
                        "date": row["date"],
                        "value": float(row["close"]),
                        "source_type": "yahoo",
                    }
                    for _, row in df.iterrows()
                ]
                added = self.db.insert_timeseries(records)
                status = "success" if added > 0 else "no_update"

            self.db.log_collection(
                indicator_id=indicator.id,
                series_code=symbol,
                source_type="yahoo",
                status=status,
                records_added=added,
                started_at=started_at,
            )

            results.append({"symbol": symbol, "added": added, "status": status})

        total_added = sum(r["added"] for r in results)
        logger.info(f"  → Yahoo total new records: {total_added}")

        return {"indicator_id": indicator.id, "symbol_results": results}

    def collect_all(self, indicators: list[Indicator] | None = None) -> list[dict]:
        """모든 Yahoo 기반 지표 수집"""
        targets = indicators or YAHOO_INDICATORS

        logger.info("=" * 60)
        logger.info(f"Yahoo Finance Collection Start — {len(targets)} indicators")
        logger.info("=" * 60)

        all_results = []
        for i, indicator in enumerate(targets, 1):
            logger.info(f"[{i}/{len(targets)}] {indicator.id}")
            result = self.collect_indicator(indicator)
            all_results.append(result)

        return all_results

    def fetch_hyperscaler_financials(self) -> dict:
        """
        Hyperscaler(MSFT, GOOGL, AMZN, META) 재무 데이터 수집
        - CapEx (Capital Expenditure)
        - Revenue
        주의: yfinance의 재무 데이터는 분기별, 지연 있음
        """
        symbols = ["MSFT", "GOOGL", "AMZN", "META"]
        results = {}

        for symbol in symbols:
            self._rate_limit()
            try:
                ticker = yf.Ticker(symbol)
                quarterly = ticker.quarterly_financials

                if quarterly is not None and not quarterly.empty:
                    # Capital Expenditure 추출 (음수로 표시됨)
                    cf = ticker.quarterly_cashflow
                    if cf is not None and "Capital Expenditure" in cf.index:
                        capex = cf.loc["Capital Expenditure"]
                        results[symbol] = {
                            "capex": {str(d.date()): abs(float(v)) for d, v in capex.items() if pd.notna(v)},
                        }
                        logger.info(f"  {symbol} CapEx: {len(results[symbol]['capex'])} quarters")

                        # DB에 저장
                        records = [
                            {
                                "indicator_id": "HYPERSCALER_CAPEX",
                                "series_code": f"{symbol}_CAPEX",
                                "date": datetime.strptime(d, "%Y-%m-%d").date(),
                                "value": v,
                                "source_type": "yahoo",
                            }
                            for d, v in results[symbol]["capex"].items()
                        ]
                        added = self.db.insert_timeseries(records)
                        logger.info(f"  {symbol} CapEx → {added} new records to DB")

            except Exception as e:
                logger.error(f"  {symbol} financials error: {e}")
                results[symbol] = {"error": str(e)}

        return results
