from __future__ import annotations
"""
Semi-Intel Database Layer
==========================
SQLite 기본, PostgreSQL 전환 가능 구조
시계열 데이터 저장 + 메타데이터 관리
"""

import os
from datetime import datetime, date
from pathlib import Path

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime,
    Text, JSON, Index, ForeignKey, Enum as SAEnum, UniqueConstraint,
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from loguru import logger

Base = declarative_base()


# ============================================================
# ORM Models
# ============================================================

class IndicatorMeta(Base):
    """지표 메타데이터 (config/indicators.py 기반 동기화)"""
    __tablename__ = "indicator_meta"

    id = Column(String(30), primary_key=True)           # e.g. "DGORDER"
    name = Column(String(200), nullable=False)
    tier = Column(String(5), nullable=False)             # "1", "2", "3", "S"
    category = Column(String(50))
    source = Column(String(100))
    frequency = Column(String(20))
    dimension = Column(String(30))
    book_chapter = Column(String(30))
    semi_relevance = Column(Text)
    signal_logic = Column(Text)
    fred_series_codes = Column(JSON)                     # ["DGORDER", "NEWORDER", ...]
    yahoo_symbols = Column(JSON)                         # ["^SOX", "SOXX"]
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TimeSeriesData(Base):
    """시계열 데이터 (핵심 테이블)"""
    __tablename__ = "timeseries_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator_id = Column(String(30), ForeignKey("indicator_meta.id"), nullable=False)
    series_code = Column(String(50), nullable=False)     # FRED code or yahoo symbol
    date = Column(Date, nullable=False)
    value = Column(Float)
    source_type = Column(String(10), default="fred")     # fred, yahoo, manual
    revision_num = Column(Integer, default=0)            # 개정 번호 (FRED 데이터 개정 추적)
    collected_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("indicator_id", "series_code", "date", "revision_num",
                         name="uq_series_date_rev"),
        Index("ix_indicator_date", "indicator_id", "date"),
        Index("ix_series_date", "series_code", "date"),
    )


class CollectionLog(Base):
    """데이터 수집 로그"""
    __tablename__ = "collection_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator_id = Column(String(30))
    series_code = Column(String(50))
    source_type = Column(String(10))
    status = Column(String(10))                          # success, error, no_update
    records_added = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime, default=datetime.utcnow)


class Signal(Base):
    """생성된 시그널 (Phase 2에서 사용)"""
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator_id = Column(String(30), ForeignKey("indicator_meta.id"))
    date = Column(Date, nullable=False)
    signal_type = Column(String(10))                     # bullish, bearish, neutral
    strength = Column(Float)                             # 0.0 ~ 1.0
    dimension = Column(String(30))
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class CompositeScore(Base):
    """복합 사이클 스코어 (Phase 2에서 사용)"""
    __tablename__ = "composite_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True)
    total_score = Column(Float)
    demand_score = Column(Float)
    supply_score = Column(Float)
    price_score = Column(Float)
    macro_score = Column(Float)
    global_score = Column(Float)
    regime = Column(String(20))                          # expansion, late_cycle, contraction, recovery
    investment_action = Column(Text)
    trend_alert = Column(String(100))                    # Momentum/Divergence Alert
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# Database Manager
# ============================================================

class DatabaseManager:
    """DB 연결 및 세션 관리"""

    def __init__(self, db_type: str = "sqlite", db_path: str = "./data/semi_intel.db",
                 db_url: str | None = None):
        if db_type == "postgresql" and db_url:
            self.engine = create_engine(db_url, echo=False)
        else:
            # SQLite
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(f"sqlite:///{db_path}", echo=False)

        self.SessionLocal = sessionmaker(bind=self.engine)
        logger.info(f"Database initialized: {db_type}")

    def create_tables(self):
        """테이블 생성 (없으면 생성, 있으면 무시)"""
        Base.metadata.create_all(self.engine)
        logger.info("All tables created/verified")

    def get_session(self) -> Session:
        return self.SessionLocal()

    def sync_indicator_meta(self, indicators):
        """config/indicators.py의 지표 정의를 DB에 동기화"""
        session = self.get_session()
        try:
            for ind in indicators:
                existing = session.query(IndicatorMeta).filter_by(id=ind.id).first()
                meta = {
                    "id": ind.id,
                    "name": ind.name,
                    "tier": str(ind.tier.value),
                    "category": ind.category,
                    "source": ind.source,
                    "frequency": ind.frequency.value,
                    "dimension": ind.dimension.value,
                    "book_chapter": ind.book_chapter,
                    "semi_relevance": ind.semi_relevance,
                    "signal_logic": ind.signal_logic,
                    "fred_series_codes": [s.code for s in ind.fred_series],
                    "yahoo_symbols": ind.yahoo_symbols,
                }
                if existing:
                    for key, val in meta.items():
                        setattr(existing, key, val)
                else:
                    session.add(IndicatorMeta(**meta))

            session.commit()
            logger.info(f"Synced {len(indicators)} indicators to DB")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to sync indicators: {e}")
            raise
        finally:
            session.close()

    def get_latest_date(self, series_code: str) -> date | None:
        """특정 시리즈의 최신 데이터 날짜 조회 (증분 수집용)"""
        session = self.get_session()
        try:
            result = (session.query(TimeSeriesData.date)
                      .filter_by(series_code=series_code)
                      .order_by(TimeSeriesData.date.desc())
                      .first())
            return result[0] if result else None
        finally:
            session.close()

    def insert_timeseries(self, records: list[dict]) -> int:
        """시계열 데이터 벌크 삽입 (중복 무시)"""
        if not records:
            return 0

        session = self.get_session()
        added = 0
        try:
            for rec in records:
                exists = (session.query(TimeSeriesData)
                          .filter_by(
                              indicator_id=rec["indicator_id"],
                              series_code=rec["series_code"],
                              date=rec["date"],
                              revision_num=rec.get("revision_num", 0)
                          ).first())
                if not exists:
                    session.add(TimeSeriesData(**rec))
                    added += 1

            session.commit()
            return added
        except Exception as e:
            session.rollback()
            logger.error(f"Insert failed: {e}")
            raise
        finally:
            session.close()

    def log_collection(self, indicator_id: str, series_code: str,
                       source_type: str, status: str,
                       records_added: int = 0, error_message: str = None,
                       started_at: datetime = None):
        """수집 로그 기록"""
        session = self.get_session()
        try:
            log = CollectionLog(
                indicator_id=indicator_id,
                series_code=series_code,
                source_type=source_type,
                status=status,
                records_added=records_added,
                error_message=error_message,
                started_at=started_at,
            )
            session.add(log)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Log failed: {e}")
        finally:
            session.close()

    def get_series_data(self, series_code: str, start_date: date = None,
                        end_date: date = None) -> list[dict]:
        """시리즈 데이터 조회"""
        session = self.get_session()
        try:
            query = (session.query(TimeSeriesData)
                     .filter_by(series_code=series_code)
                     .order_by(TimeSeriesData.date))
            if start_date:
                query = query.filter(TimeSeriesData.date >= start_date)
            if end_date:
                query = query.filter(TimeSeriesData.date <= end_date)

            return [{"date": r.date, "value": r.value} for r in query.all()]
        finally:
            session.close()

    def get_collection_stats(self) -> dict:
        """수집 현황 통계"""
        session = self.get_session()
        try:
            total_records = session.query(TimeSeriesData).count()
            series_count = session.query(TimeSeriesData.series_code).distinct().count()
            latest_collection = (session.query(CollectionLog.completed_at)
                                 .order_by(CollectionLog.completed_at.desc())
                                 .first())

            return {
                "total_records": total_records,
                "series_count": series_count,
                "latest_collection": latest_collection[0] if latest_collection else None,
            }
        finally:
            session.close()
