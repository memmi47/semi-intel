import os
import pandas as pd
import sqlite3
import warnings
warnings.filterwarnings("ignore")

def create_connection(db_path):
    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")
    return sqlite3.connect(db_path)

def process_omdia(file_path):
    print("Parsing Omdia Reference...")
    df = pd.read_excel(file_path, sheet_name="Omdia")
    
    # Extract only up to 4Q25
    keep_cols = ["Unnamed: 1", "Unnamed: 2"]
    for col in df.columns:
        if "Q" in col:
            year = int(col[-2:])
            if year <= 25: # Keep up to 2025
                keep_cols.append(col)
                
    df = df[keep_cols]
    df.rename(columns={"Unnamed: 1": "product", "Unnamed: 2": "metric"}, inplace=True)
    
    # Filter rows that have valid product/metric
    df = df.dropna(subset=["product", "metric"])
    
    # Melt
    melted = df.melt(id_vars=["product", "metric"], var_name="quarter", value_name="value")
    # Convert quarter string like 1Q11 to a date for sorting, assume end of quarter
    # 1Q -> 03-31, 2Q -> 06-30, 3Q -> 09-30, 4Q -> 12-31
    def quarter_to_date(q_str):
        q, y = q_str[0], q_str[2:]
        year = 2000 + int(y)
        month = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}[q]
        return f"{year}-{month}"
        
    melted["reference_date"] = melted["quarter"].apply(quarter_to_date)
    return melted

def process_wsts(file_path):
    print("Parsing WSTS Reference...")
    df = pd.read_excel(file_path, sheet_name="WSTS")
    
    keep_cols = ["Unnamed: 1", "Unnamed: 2"]
    for col in df.columns:
        # Ignore Unnamed columns for dates
        if isinstance(col, str) and col.startswith("Unnamed"):
            continue
            
        try:
            dt = pd.to_datetime(col)
            if dt.year <= 2025:
                keep_cols.append(col)
        except Exception:
            pass
                
    df = df[keep_cols]
    df.rename(columns={"Unnamed: 1": "product", "Unnamed: 2": "metric"}, inplace=True)
    df = df.dropna(subset=["product", "metric"])
    
    melted = df.melt(id_vars=["product", "metric"], var_name="reference_date", value_name="value")
    melted["reference_date"] = pd.to_datetime(melted["reference_date"]).dt.strftime("%Y-%m-%d")
    return melted

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    file_path = os.path.join(os.path.dirname(__file__), "../data/manual/Historical_Data_Upload.xlsx")
    db_path = os.getenv("DB_PATH", "./data/semi_intel.db")
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        exit(1)
        
    omdia_df = process_omdia(file_path)
    wsts_df = process_wsts(file_path)
    
    # Store to database
    conn = create_connection(db_path)
    print(f"Writing {len(omdia_df)} Omdia records to reference db...")
    omdia_df.to_sql("omdia_reference", conn, if_exists="replace", index=False)
    
    print(f"Writing {len(wsts_df)} WSTS records to reference db...")
    wsts_df.to_sql("wsts_reference", conn, if_exists="replace", index=False)
    
    conn.close()
    print("Reference Data Import Completed Successfully!")
