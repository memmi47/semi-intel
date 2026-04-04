from __future__ import annotations
"""
Manual Data Collector
======================
FRED/Yahoo에 없는 반도체 특화 지표를 수동 입력하는 인터페이스
- DRAM/NAND 가격 (TrendForce)
- SEMI Book-to-Bill Ratio
- WSTS Global Semiconductor Sales

사용법:
    python -m collectors.manual_collector add DRAM_SPOT DDR5_8Gb_SPOT 2025-01-15 3.45
    python -m collectors.manual_collector add SEMI_BB SEMI_BB_RATIO 2025-01-15 1.05
    python -m collectors.manual_collector import DRAM_SPOT ./data/manual/dram_prices.csv
"""

import csv
from datetime import datetime, date
from pathlib import Path

from loguru import logger
from db.database import DatabaseManager


class ManualCollector:
    """수동 데이터 입력/CSV 임포트"""

    # 지원하는 수동 입력 시리즈 정의
    MANUAL_SERIES = {
        "DRAM_SPOT": {
            "codes": [
                "DDR5_8Gb_SPOT",      # DDR5 8Gb spot price (USD)
                "DDR5_8Gb_CONTRACT",   # DDR5 8Gb contract price
                "DDR4_8Gb_SPOT",      # DDR4 8Gb spot price
                "NAND_128L_SPOT",     # 128L TLC NAND spot
                "NAND_128L_CONTRACT", # 128L TLC NAND contract
                "HBM3E_PRICE",        # HBM3E estimated ASP
            ],
            "unit": "USD",
        },
        "SEMI_BB": {
            "codes": [
                "SEMI_BB_RATIO",       # Global B/B ratio
                "SEMI_BB_BILLINGS",    # Billings (USD millions)
                "SEMI_BB_BOOKINGS",    # Bookings (USD millions)
            ],
            "unit": "ratio / USD millions",
        },
        "WSTS": {
            "codes": [
                "WSTS_GLOBAL_TOTAL",   # Total global semi sales (USD millions)
                "WSTS_MEMORY",         # Memory segment
                "WSTS_LOGIC",          # Logic segment
                "WSTS_ANALOG",         # Analog segment
                "WSTS_AMERICAS",       # Americas region
                "WSTS_ASIA_PAC",       # Asia Pacific region
            ],
            "unit": "USD millions",
        },
    }

    def __init__(self, db: DatabaseManager):
        self.db = db

    def add_single(self, indicator_id: str, series_code: str,
                   data_date: date, value: float) -> bool:
        """단일 데이터 포인트 추가"""
        if indicator_id not in self.MANUAL_SERIES:
            logger.error(f"Unknown indicator: {indicator_id}")
            logger.info(f"Available: {list(self.MANUAL_SERIES.keys())}")
            return False

        valid_codes = self.MANUAL_SERIES[indicator_id]["codes"]
        if series_code not in valid_codes:
            logger.error(f"Unknown series: {series_code}")
            logger.info(f"Available for {indicator_id}: {valid_codes}")
            return False

        record = {
            "indicator_id": indicator_id,
            "series_code": series_code,
            "date": data_date,
            "value": value,
            "source_type": "manual",
        }

        added = self.db.insert_timeseries([record])
        if added > 0:
            logger.info(f"Added: {indicator_id}/{series_code} = {value} on {data_date}")
            self.db.log_collection(
                indicator_id=indicator_id,
                series_code=series_code,
                source_type="manual",
                status="success",
                records_added=1,
                started_at=datetime.utcnow(),
            )
            return True
        else:
            logger.warning(f"Duplicate or failed: {indicator_id}/{series_code} on {data_date}")
            return False

    def import_csv(self, indicator_id: str, csv_path: str) -> int:
        """
        CSV 파일에서 데이터 임포트

        CSV 형식:
            date,series_code,value
            2025-01-15,DDR5_8Gb_SPOT,3.45
            2025-01-15,DDR5_8Gb_CONTRACT,3.20
        """
        csv_file = Path(csv_path)
        if not csv_file.exists():
            logger.error(f"File not found: {csv_path}")
            return 0

        records = []
        with open(csv_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    records.append({
                        "indicator_id": indicator_id,
                        "series_code": row["series_code"],
                        "date": datetime.strptime(row["date"], "%Y-%m-%d").date(),
                        "value": float(row["value"]),
                        "source_type": "manual",
                    })
                except (KeyError, ValueError) as e:
                    logger.warning(f"Skipping row: {row} — {e}")

        added = self.db.insert_timeseries(records)
        logger.info(f"Imported {added}/{len(records)} records from {csv_path}")

        self.db.log_collection(
            indicator_id=indicator_id,
            series_code="csv_import",
            source_type="manual",
            status="success",
            records_added=added,
            started_at=datetime.utcnow(),
        )

        return added

    def create_csv_template(self, indicator_id: str, output_dir: str = "./data/manual"):
        """CSV 입력 템플릿 생성"""
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        if indicator_id not in self.MANUAL_SERIES:
            logger.error(f"Unknown indicator: {indicator_id}")
            return

        series_info = self.MANUAL_SERIES[indicator_id]
        filepath = Path(output_dir) / f"{indicator_id.lower()}_template.csv"

        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "series_code", "value"])
            # 샘플 행
            for code in series_info["codes"]:
                writer.writerow(["2025-01-15", code, "0.00"])

        logger.info(f"Template created: {filepath}")
        logger.info(f"  Unit: {series_info['unit']}")
        logger.info(f"  Series: {series_info['codes']}")

    def list_available_series(self):
        """사용 가능한 수동 입력 시리즈 출력"""
        print("\n=== Manual Input Series ===\n")
        for ind_id, info in self.MANUAL_SERIES.items():
            print(f"  {ind_id} ({info['unit']})")
            for code in info["codes"]:
                print(f"    - {code}")
            print()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m collectors.manual_collector list")
        print("  python -m collectors.manual_collector template <INDICATOR_ID>")
        print("  python -m collectors.manual_collector add <INDICATOR_ID> <SERIES_CODE> <DATE> <VALUE>")
        print("  python -m collectors.manual_collector import <INDICATOR_ID> <CSV_PATH>")
        sys.exit(1)

    from dotenv import load_dotenv
    import os
    load_dotenv()

    db = DatabaseManager(
        db_type=os.getenv("DB_TYPE", "sqlite"),
        db_path=os.getenv("DB_PATH", "./data/semi_intel.db"),
    )
    db.create_tables()
    collector = ManualCollector(db)

    cmd = sys.argv[1]

    if cmd == "list":
        collector.list_available_series()
    elif cmd == "template" and len(sys.argv) >= 3:
        collector.create_csv_template(sys.argv[2])
    elif cmd == "add" and len(sys.argv) >= 6:
        collector.add_single(
            indicator_id=sys.argv[2],
            series_code=sys.argv[3],
            data_date=datetime.strptime(sys.argv[4], "%Y-%m-%d").date(),
            value=float(sys.argv[5]),
        )
    elif cmd == "import" and len(sys.argv) >= 4:
        collector.import_csv(sys.argv[2], sys.argv[3])
    else:
        print("Invalid command. Run without arguments for usage.")
