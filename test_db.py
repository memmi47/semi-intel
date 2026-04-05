from db.database import DatabaseManager
import os
from sqlalchemy import text
db = DatabaseManager(os.getenv("DB_PATH", "sqlite:///./data/semi_intel.db"))
session = db.get_session()
try:
    res = session.execute(text("SELECT product, metric, reference_date, value FROM omdia_reference ORDER BY reference_date LIMIT 5"))
    print([dict(r._mapping) for r in res])
except Exception as e:
    print("ERROR:", e)
