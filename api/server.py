from __future__ import annotations
"""
Semi-Intel API Server
======================
FastAPI 기반 REST API + HTML 대시보드

실행:
    python3 -m api.server
    브라우저에서 http://localhost:8000 접속
"""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    from db.database import DatabaseManager
    from config.indicators import ALL_INDICATORS

    db_type = os.getenv("DB_TYPE", "sqlite")
    db_path = os.getenv("DB_PATH", "./data/semi_intel.db")
    db_url = os.getenv("DB_URL")

    app.state.db = DatabaseManager(db_type=db_type, db_path=db_path, db_url=db_url)
    app.state.db.create_tables()
    app.state.db.sync_indicator_meta(ALL_INDICATORS)

    # Initialize Automation Pipeline
    from utils.automation import BackgroundPipeline
    app.state.pipeline = BackgroundPipeline(app.state.db)
    app.state.pipeline.start()

    # 데이터가 하나도 없다면 서버 시작 시 즉시 첫 수집 실행 (비동기 백그라운드)
    stats = app.state.db.get_collection_stats()
    if stats.get("total_records", 0) == 0:
        logger.info("Empty database detected. Triggering initial data collection...")
        import threading
        threading.Thread(target=app.state.pipeline.run_full_pipeline).start()

    yield

    app.state.pipeline.stop()


app = FastAPI(
    title="Semi-Intel API",
    description="Semiconductor Investment Intelligence",
    version="3.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes
from api.routes import router
app.include_router(router, prefix="/api")


# Dashboard: serve index.html at root
@app.get("/")
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


# Static files fallback
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    # Railway 등 클라우드 환경은 PORT 환경변수를 사용함
    port = int(os.getenv("PORT", 8000))
    print(f"\n  Semi-Intel Dashboard")
    print(f"  Running on port: {port}\n")
    uvicorn.run("api.server:app", host="0.0.0.0", port=port, reload=False)
