from __future__ import annotations
"""
Data Transforms
================
시계열 데이터 변환 함수들
- 변화율 (MoM%, YoY%, QoQ%)
- 이동평균 (SMA, EMA)
- 정규화 (Z-score, Min-Max, Percentile Rank)
- 모멘텀 / 방향성 판별
"""

import numpy as np
import pandas as pd
from typing import Literal


# ============================================================
# 변화율 계산
# ============================================================

def pct_change(series: pd.Series, periods: int = 1) -> pd.Series:
    """단순 변화율 (%)"""
    return series.pct_change(periods=periods) * 100


def mom_pct(series: pd.Series) -> pd.Series:
    """전월 대비 변화율 (Month-over-Month %)"""
    return pct_change(series, 1)


def qoq_pct(series: pd.Series) -> pd.Series:
    """전분기 대비 변화율"""
    return pct_change(series, 1)


def yoy_pct(series: pd.Series, frequency: str = "monthly") -> pd.Series:
    """전년 동기 대비 변화율 (Year-over-Year %)"""
    periods = {"daily": 252, "weekly": 52, "monthly": 12, "quarterly": 4}
    p = periods.get(frequency, 12)
    return pct_change(series, p)


def annualized_rate(series: pd.Series, periods_per_year: int = 12) -> pd.Series:
    """연율화 변화율 (SAAR 방식)"""
    mom = series.pct_change()
    return ((1 + mom) ** periods_per_year - 1) * 100


def diff(series: pd.Series, periods: int = 1) -> pd.Series:
    """단순 차분 (레벨 변화)"""
    return series.diff(periods=periods)


# ============================================================
# 이동평균
# ============================================================

def sma(series: pd.Series, window: int) -> pd.Series:
    """단순 이동평균 (Simple Moving Average)"""
    return series.rolling(window=window, min_periods=1).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    """지수 이동평균 (Exponential Moving Average)"""
    return series.ewm(span=span, adjust=False).mean()


def sma_crossover(series: pd.Series, short: int = 3, long: int = 6) -> pd.Series:
    """
    이동평균 크로스오버 신호
    Returns: 1 (골든크로스), -1 (데드크로스), 0 (중립)
    """
    short_ma = sma(series, short)
    long_ma = sma(series, long)
    signal = pd.Series(0, index=series.index)
    signal[short_ma > long_ma] = 1
    signal[short_ma < long_ma] = -1
    return signal


# ============================================================
# 정규화 / 표준화
# ============================================================

def z_score(series: pd.Series, window: int | None = None) -> pd.Series:
    """
    Z-score 정규화
    window=None → 전체 기간 기준
    window=N → 롤링 N기간 기준
    """
    if window:
        rolling_mean = series.rolling(window=window, min_periods=max(1, window // 2)).mean()
        rolling_std = series.rolling(window=window, min_periods=max(1, window // 2)).std()
        return (series - rolling_mean) / rolling_std.replace(0, np.nan)
    else:
        mean = series.mean()
        std = series.std()
        if std == 0:
            return pd.Series(0, index=series.index)
        return (series - mean) / std


def min_max_normalize(series: pd.Series, window: int | None = None) -> pd.Series:
    """
    Min-Max 정규화 → 0~1 범위
    window=None → 전체 기간
    window=N → 롤링 N기간
    """
    if window:
        rolling_min = series.rolling(window=window, min_periods=1).min()
        rolling_max = series.rolling(window=window, min_periods=1).max()
        range_ = rolling_max - rolling_min
        return (series - rolling_min) / range_.replace(0, np.nan)
    else:
        min_val = series.min()
        max_val = series.max()
        if max_val == min_val:
            return pd.Series(0.5, index=series.index)
        return (series - min_val) / (max_val - min_val)


def percentile_rank(series: pd.Series, window: int | None = None) -> pd.Series:
    """
    백분위 순위 (0~100)
    가장 최근 값이 과거 분포에서 몇 번째 위치인지
    """
    if window:
        def _rank(x):
            if len(x) < 2:
                return 50.0
            return (x.values[:-1] < x.values[-1]).sum() / (len(x) - 1) * 100
        return series.rolling(window=window, min_periods=2).apply(_rank, raw=False)
    else:
        return series.rank(pct=True) * 100


def to_score_0_100(series: pd.Series, window: int = 60,
                   invert: bool = False) -> pd.Series:
    """
    시리즈를 0-100 스코어로 변환 (Composite Score 산출용)

    Args:
        window: 백분위 계산 기간 (기본 60개월 = 5년)
        invert: True면 높을수록 bearish (CPI 등에 사용)
    """
    score = percentile_rank(series, window=window)
    if invert:
        score = 100 - score
    return score.clip(0, 100)


# ============================================================
# 모멘텀 / 방향성
# ============================================================

def momentum(series: pd.Series, periods: int = 3) -> pd.Series:
    """모멘텀: 현재값 - N기간 전 값"""
    return series - series.shift(periods)


def direction(series: pd.Series, periods: int = 3,
              threshold: float = 0.0) -> pd.Series:
    """
    방향성 판별

    Returns:
        1  → 상승 추세 (change > threshold)
        -1 → 하락 추세 (change < -threshold)
        0  → 횡보
    """
    change = pct_change(series, periods)
    result = pd.Series(0, index=series.index)
    result[change > threshold] = 1
    result[change < -threshold] = -1
    return result


def consecutive_direction(series: pd.Series) -> pd.Series:
    """
    연속 방향 카운트
    양수: N개월 연속 상승, 음수: N개월 연속 하락
    """
    changes = series.diff()
    signs = np.sign(changes)

    counts = pd.Series(0, index=series.index)
    for i in range(1, len(series)):
        if signs.iloc[i] == signs.iloc[i - 1] and signs.iloc[i] != 0:
            counts.iloc[i] = counts.iloc[i - 1] + signs.iloc[i]
        elif signs.iloc[i] != 0:
            counts.iloc[i] = signs.iloc[i]
    return counts


def rate_of_change(series: pd.Series, periods: int = 6) -> pd.Series:
    """ROC: (현재 - N기간전) / N기간전 * 100"""
    shifted = series.shift(periods)
    return ((series - shifted) / shifted.abs().replace(0, np.nan)) * 100


# ============================================================
# 임계값 기반 신호
# ============================================================

def threshold_signal(series: pd.Series,
                     bullish_above: float | None = None,
                     bearish_below: float | None = None) -> pd.Series:
    """
    임계값 기반 신호 생성

    Args:
        bullish_above: 이 값 이상이면 bullish (1)
        bearish_below: 이 값 이하면 bearish (-1)

    Returns:
        1 (bullish), -1 (bearish), 0 (neutral)
    """
    signal = pd.Series(0, index=series.index, dtype=int)
    if bullish_above is not None:
        signal[series >= bullish_above] = 1
    if bearish_below is not None:
        signal[series <= bearish_below] = -1
    return signal


def spread_signal(series_a: pd.Series, series_b: pd.Series,
                  bullish_positive: bool = True) -> pd.Series:
    """
    두 시리즈 간 스프레드 기반 신호
    예: New Orders - Inventories spread
    """
    spread = series_a - series_b
    signal = pd.Series(0, index=spread.index, dtype=int)
    if bullish_positive:
        signal[spread > 0] = 1
        signal[spread < 0] = -1
    else:
        signal[spread > 0] = -1
        signal[spread < 0] = 1
    return signal


# ============================================================
# 유틸리티
# ============================================================

def align_series(*series_list: pd.Series,
                 method: str = "ffill") -> list[pd.Series]:
    """여러 시리즈의 날짜를 정렬 (빈도가 다른 시리즈 결합 시)"""
    df = pd.concat(series_list, axis=1)
    if method == "ffill":
        df = df.fillna(method="ffill")
    elif method == "interpolate":
        df = df.interpolate(method="time")
    return [df.iloc[:, i] for i in range(len(series_list))]


def resample_to_monthly(series: pd.Series, agg: str = "last") -> pd.Series:
    """일간/주간 데이터를 월간으로 리샘플링"""
    series.index = pd.DatetimeIndex(series.index)
    if agg == "last":
        return series.resample("ME").last()
    elif agg == "mean":
        return series.resample("ME").mean()
    elif agg == "first":
        return series.resample("ME").first()
    return series.resample("ME").last()


def fill_gaps(series: pd.Series, max_gap: int = 3) -> pd.Series:
    """최대 max_gap 기간까지 전방 채우기"""
    return series.fillna(method="ffill", limit=max_gap)
