import os
import csv
from datetime import datetime
from db.database import DatabaseManager

def import_dramexchange_tsv(db, file_path, indicator_id, series_code, date_col='Date', value_col='Avg', date_fmt='%Y-%m-%d'):
    print(f"Importing {file_path} for {series_code}...")
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    records = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            try:
                d_str = row.get(date_col)
                v_str = row.get(value_col)
                if not d_str or not v_str: continue
                
                v_str = v_str.replace(',', '').split()[0]
                records.append({
                    "indicator_id": indicator_id, "series_code": series_code,
                    "date": datetime.strptime(d_str, date_fmt).date(),
                    "value": float(v_str), "source_type": "dramexchange",
                })
            except Exception as e:
                print(f"Skipping row {row}: {e}")
    added = db.insert_timeseries(records)
    print(f"Successfully added {added} records for {series_code}.")

def import_manual_points(db, indicator_id, series_code, points):
    print(f"Importing manual points for {series_code}...")
    records = []
    for d_str, val in points:
        records.append({
            "indicator_id": indicator_id, "series_code": series_code,
            "date": datetime.strptime(d_str, "%Y-%m-%d").date(),
            "value": float(val), "source_type": "manual_calibration",
        })
    added = db.insert_timeseries(records)
    print(f"Successfully added {added} manual points for {series_code}.")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    db = DatabaseManager(
        db_type=os.getenv("DB_TYPE", "sqlite"),
        db_path=os.getenv("DB_PATH", "./data/semi_intel.db")
    )
    db.create_tables()
    base_dir = "/Users/jungdo/Desktop/semi-intel/data/manual"

    # 1. DDR5 & DXI (From Files)
    import_dramexchange_tsv(db, os.path.join(base_dir, "DDR5_16Gb_(2Gx8)_4800_5600.xls"), "DRAM_SPOT", "DDR5_16G_SPOT")
    import_dramexchange_tsv(db, os.path.join(base_dir, "DXI_Historical_Price_2025-1-1_TO_2026-4-5.xls"), "DXI", "DXI_INDEX", date_col='LastUpdate', value_col='Value', date_fmt='%Y/%m/%d')
    
    # 2. NAND Wafer (User Provided 11 Points - LOW)
    nand_512g_points = [
        ("2023-04-03", 1.35), ("2023-05-08", 1.33), ("2023-11-13", 2.45),
        ("2024-02-19", 3.25), ("2024-07-08", 2.7), ("2024-11-25", 2.3),
        ("2025-04-14", 2.55), ("2025-09-01", 2.7), ("2026-01-19", 13),
        ("2026-03-23", 18.5), ("2026-03-30", 17)
    ]
    import_manual_points(db, "NAND_SPOT", "NAND_512G_WAFER_LOW", nand_512g_points)

    nand_1t_points = [
        ("2023-04-03", 2.8), ("2023-05-08", 2.75), ("2023-11-13", 4.8),
        ("2024-02-19", 5.7), ("2024-07-08", 5.7), ("2024-11-25", 3.7),
        ("2025-04-14", 4.8), ("2025-09-01", 4.85), ("2026-01-19", 16),
        ("2026-03-23", 22.5), ("2026-03-30", 21)
    ]
    import_manual_points(db, "NAND_SPOT", "NAND_1T_WAFER_LOW", nand_1t_points)
