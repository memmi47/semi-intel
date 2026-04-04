import os
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from collectors.fred_collector import FredCollector
from collectors.yahoo_collector import YahooCollector
from analysis.composite_score import CompositeScoreCalculator
from analysis.signal_generator import SignalGenerator

class BackgroundPipeline:
    """
    백그라운드 스케줄러를 통해 전체 데이터 파이프라인(수집 -> 분석 -> 스코어링)을 자동화하는 클래스
    FastAPI 서버 구동 시 라이프사이클에 통합되어 실행됨.
    """
    def __init__(self, db):
        self.db = db
        self.scheduler = BackgroundScheduler()
        self.is_running = False
        self.last_run_time = None
        self.next_run_time = None

    def run_full_pipeline(self):
        """전체 파이프라인 수동/예약 실행"""
        logger.info("=== 백그라운드 자동화 파이프라인 시작 ===")
        
        # 1. 데이터 수집
        fred_key = os.getenv("FRED_API_KEY", "")
        if fred_key and fred_key != "your_fred_api_key_here":
            logger.info("[자동화] 1. FRED 데이터 수집 중...")
            try:
                fred = FredCollector(fred_key, self.db)
                fred.collect_all()
            except Exception as e:
                logger.error(f"[자동화] FRED 수집 실패: {e}")
        else:
            logger.warning("[자동화] FRED_API_KEY가 없어 수집을 생략합니다.")

        logger.info("[자동화] 2. Yahoo Finance 데이터 수집 중...")
        try:
            yahoo = YahooCollector(self.db)
            yahoo.collect_all()
        except Exception as e:
            logger.error(f"[자동화] Yahoo 수집 실패: {e}")

        # 2. 분석 및 스코어 계산
        logger.info("[자동화] 3. 시그널 생성 및 Composite Score 계산 중...")
        try:
            calc = CompositeScoreCalculator(self.db)
            result = calc.calculate()
            calc.save_to_db(result)
            
            # 모든 시그널도 저장 (추가 모니터링 목적)
            all_signals = calc.signal_gen.generate_all()
            calc.save_signals_to_db(all_signals)
            
            logger.info(f"[자동화] Score 갱신 완료: {result.total_score} ({result.regime})")
        except Exception as e:
            logger.error(f"[자동화] Score 계산 실패: {e}")

        self.last_run_time = datetime.now()
        
        # 다음 실행 시간 갱신을 위해 스케줄러 직업 정보 가져오기
        job = self.scheduler.get_job('daily_pipeline')
        if job:
            self.next_run_time = job.next_run_time
            
        logger.info("=== 백그라운드 자동화 파이프라인 종료 ===")

    def start(self):
        """스케줄러 시작"""
        if self.is_running:
            return
            
        # 매일 평일(월-금) 오후 6시 30분에 실행 (미국 시장 마감 및 FRED 오후 업데이트 반영)
        self.scheduler.add_job(
            self.run_full_pipeline, 
            'cron', 
            day_of_week='mon-fri', 
            hour=18, 
            minute=30, 
            id='daily_pipeline',
            replace_existing=True
        )
        self.scheduler.start()
        self.is_running = True
        
        # 초기 next_run_time 설정
        job = self.scheduler.get_job('daily_pipeline')
        if job:
            self.next_run_time = job.next_run_time
            
        logger.info("Background Auto-Pipeline Scheduler started (Runs Mon-Fri at 18:30)")

    def stop(self):
        """스케줄러 정지"""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("Background Auto-Pipeline Scheduler stopped")
