"""
数据获取层 — 基于 AKShare 的A股数据接口
支持：指数行情、个股日线、财务指标、实时快照

稳定性机制：
- 直连境内数据源（绕过代理，避免 v2ray/clash 拦截）
- 指数退避重试（2s → 4s → 8s，最多3次）
- 请求节流（全局最小间隔3秒，批量模式下避免触发反爬）
- Parquet本地缓存（24小时内直接命中）
"""
import os
import time
import random
import hashlib
import functools
import threading
import socket
from datetime import datetime, timedelta
from typing import Optional, Callable
import pandas as pd

# SSL hang prevention: AKShare drops connections after ~100 sustained requests
from core.settings import get_section as _get_section
socket.setdefaulttimeout(int((_get_section("data.fetcher", {}) or {}).get("socket_timeout", 30)))

from data.datahub import get_datahub

_HUB = get_datahub()

# ============================================================
# 代理绕过 — 境内数据源直连，不走 v2ray/clash
# ============================================================

# 必须在 requests 和 akshare 导入之前设置
EASTMONEY_DOMAINS = (
    "eastmoney.com",
    "10jqka.com.cn",   # 同花顺
    "sina.com.cn",     # 新浪财经
    "qianlong.com",    # 乾隆
)

_no_proxy = os.environ.get("no_proxy", "") or os.environ.get("NO_PROXY", "")
_existing = set(_no_proxy.split(",")) if _no_proxy else set()
for domain in EASTMONEY_DOMAINS:
    _existing.add(f".{domain}")
os.environ["no_proxy"] = ",".join(_existing)
os.environ["NO_PROXY"] = os.environ["no_proxy"]

# 显式清空代理（防御性编程）
for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(key, None)

# ============================================================
# 基础设施
# ============================================================

CACHE_DIR = str(_HUB.cache_root / "api")


# ============================================================
# 配置读取 — data.fetcher section
# ============================================================

def _fetcher_cfg() -> dict:
    from core.settings import get_section
    return get_section("data.fetcher", {}) or {}


# ============================================================
# 请求节流 — 全局最小间隔，避免触发反爬
# ============================================================

_throttle_lock = threading.Lock()
_last_request_time: float = 0.0


def _get_min_interval() -> float:
    return float(_fetcher_cfg().get("min_interval", 3.0))


def _get_jitter_max() -> float:
    return float(_fetcher_cfg().get("jitter_max", 0.5))


def _throttle():
    """节流：确保两次请求之间至少间隔 min_interval 秒"""
    global _last_request_time
    min_interval = _get_min_interval()
    jitter_max = _get_jitter_max()
    with _throttle_lock:
        now = time.monotonic()
        elapsed = now - _last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed + random.uniform(0, jitter_max))
        _last_request_time = time.monotonic()


# ============================================================
# 重试机制 — 指数退避 + 抖动
# ============================================================

import requests  # 仅用于异常类型

RETRYABLE_ERRORS = (
    ConnectionError,
    ConnectionResetError,
    ConnectionAbortedError,
    TimeoutError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
    OSError,  # RemoteDisconnected 等
)


def retry_with_backoff(
    max_retries: int | None = None,
    base_delay: float | None = None,
    backoff_factor: float | None = None,
    jitter: bool = True,
):
    """
    装饰器：带指数退避和随机抖动的重试
    间隔: base * factor^attempt + random jitter
    例: 2s → 4s → 8s（加随机抖动避免惊群）
    参数默认值从 data.fetcher 配置读取。
    """
    cfg = _fetcher_cfg()
    _max_retries = max_retries if max_retries is not None else int(cfg.get("max_retries", 3))
    _base_delay = base_delay if base_delay is not None else float(cfg.get("base_delay", 2.0))
    _backoff_factor = backoff_factor if backoff_factor is not None else float(cfg.get("backoff_factor", 2.0))
    _jitter_ratio = float(cfg.get("jitter_ratio", 0.3))

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(_max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except RETRYABLE_ERRORS as e:
                    last_error = e
                    if attempt < _max_retries:
                        delay = _base_delay * (_backoff_factor ** attempt)
                        if jitter:
                            delay += random.uniform(0, delay * _jitter_ratio)
                        print(
                            f"  [RETRY] {func.__name__} 第{attempt+1}次失败: {type(e).__name__}, "
                            f"{delay:.1f}s后重试..."
                        )
                        time.sleep(delay)
                    else:
                        print(f"  [FAIL] {func.__name__} 已重试{_max_retries}次，放弃")
            raise last_error  # type: ignore
        return wrapper
    return decorator


# ============================================================
# 缓存层 — 两层：磁盘(parquet,跨会话) + 内存(dict,会话内)
# ============================================================

# 内存缓存 — 同一会话内避免重复磁盘读取
_mem_cache: dict = {}


def _get_mem_cache_max() -> int:
    return int(_fetcher_cfg().get("mem_cache_max", 64))


def _cache_path(key: str) -> str:
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return os.path.join(CACHE_DIR, f"{h}.parquet")


def _mem_get(key: str) -> Optional[pd.DataFrame]:
    """从内存缓存读取"""
    return _mem_cache.get(key)


def _mem_set(key: str, df: pd.DataFrame):
    """写入内存缓存，维护上限"""
    if len(_mem_cache) >= _get_mem_cache_max():
        # 淘汰最旧的
        oldest = next(iter(_mem_cache))
        del _mem_cache[oldest]
    _mem_cache[key] = df


def _read_cache(key: str, max_age_hours: int = 24) -> Optional[pd.DataFrame]:
    """读缓存：先内存 → 再磁盘。max_age_hours=0 表示永不过期。"""
    # 1. 内存命中
    df = _mem_get(key)
    if df is not None:
        return df

    # 2. 磁盘命中
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    if max_age_hours > 0:
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        if datetime.now() - mtime > timedelta(hours=max_age_hours):
            return None
    df = _HUB.read_parquet(path)
    _mem_set(key, df)
    return df


def _write_cache(key: str, df: pd.DataFrame):
    """写缓存：同时写内存和磁盘"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    _HUB.write_parquet(df, _cache_path(key))
    _mem_set(key, df)


# TTL 常量——分三级
def _get_ttl_forever() -> int:
    return int(_fetcher_cfg().get("ttl_forever_hours", 8760))


def _get_ttl_daily() -> int:
    return int(_fetcher_cfg().get("ttl_daily_hours", 24))


def _get_ttl_realtime() -> int:
    return int(_fetcher_cfg().get("ttl_realtime_hours", 1))


def _allow_api_fallback() -> bool:
    return os.environ.get("QUANT_ALLOW_API_FALLBACK", "").lower() in {"1", "true", "yes", "on"}


# ============================================================
# 数据获取 — 核心接口
# ============================================================

@retry_with_backoff(max_retries=3, base_delay=2.0)
def get_index_daily(
    symbol: str = "sh000001",
    force_refresh: bool = False,
    source: str = "default",  # default / tx / em
) -> pd.DataFrame:
    """
    获取指数日线数据
    symbol: sh000001(上证), sz399001(深证), sh000300(沪深300)
    source: default(akshare通用), tx(腾讯), em(东方财富)
    """
    cache_key = f"index_daily_{symbol}_{source}"
    if not force_refresh:
        cached = _read_cache(cache_key, max_age_hours=_get_ttl_daily())
        if cached is not None:
            return cached

    import akshare as ak

    _throttle()  # API调用前节流
    if source == "tx":
        df = ak.stock_zh_index_daily_tx(symbol=symbol)
    elif source == "em":
        df = ak.stock_zh_index_daily_em(symbol=symbol)
    else:
        df = ak.stock_zh_index_daily(symbol=symbol)

    df.columns = [c.lower() for c in df.columns]
    _write_cache(cache_key, df)
    return df


@retry_with_backoff(max_retries=3, base_delay=2.0)
def get_stock_daily(
    symbol: str,
    adjust: str = "qfq",
    force_refresh: bool = False,
    source: str = "sina",
) -> pd.DataFrame:
    """
    获取个股日线（前复权）— 默认只读本地 parquet。

    外部 API 拉取只在 force_refresh=True 或显式设置
    QUANT_ALLOW_API_FALLBACK=1 时发生，避免研究/回测路径隐式触网。
    """
    from data.fetchers.stock_daily import read_one, fetch_one

    if not force_refresh:
        df = read_one(symbol)
        if df is not None and len(df) > 0:
            return df
        if not _allow_api_fallback():
            return pd.DataFrame()

    # Fallback: 本地无数据，从 API 拉取
    df = fetch_one(symbol, source=source, adjust=adjust, force=True)
    if df is not None and len(df) > 0:
        return df
    return pd.DataFrame()


@retry_with_backoff(max_retries=3, base_delay=2.0)
def get_financial_indicator(
    symbol: str,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    获取财务指标（ROE、毛利率、资产负债率等）
    数据来源：同花顺 → 本地 parquet
    """
    from data.fetchers.financial import read_financial_summary, fetch_financial_summary

    if not force_refresh:
        df = read_financial_summary(symbol)
        if df is not None and len(df) > 0:
            return df
        if not _allow_api_fallback():
            return pd.DataFrame()

    df = fetch_financial_summary(symbol)
    if df is not None and len(df) > 0:
        return df
    return pd.DataFrame()


@retry_with_backoff(max_retries=2, base_delay=3.0)
def get_stock_spot(
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    获取全市场实时行情快照
    注意：东方财富实时接口不稳定，失败返回空DataFrame
    """
    cache_key = "spot_all"
    if not force_refresh:
        cached = _read_cache(cache_key, max_age_hours=1)
        if cached is not None:
            return cached

    import akshare as ak
    _throttle()
    df = ak.stock_zh_a_spot_em()
    _write_cache(cache_key, df)
    return df


# ============================================================
# 批量获取 — 带进度和容错
# ============================================================

def fetch_all_stocks(
    symbols: list,
    force_refresh: bool = False,
    on_error: str = "skip",  # skip / raise
) -> dict:
    """
    批量获取个股日线
    返回 {symbol: DataFrame}，失败的 symbol 会打印警告但不中断
    """
    results = {}
    n = len(symbols)
    for i, sym in enumerate(symbols, 1):
        print(f"  [{i}/{n}] {sym}...", end=" ", flush=True)
        try:
            results[sym] = get_stock_daily(sym, force_refresh=force_refresh)
            print(f"✓ {len(results[sym])}条")
        except Exception as e:
            print(f"✗ {e}")
            if on_error == "raise":
                raise
    return results


def fetch_all_indices(
    symbols: dict = None,
    force_refresh: bool = False,
) -> dict:
    """
    批量获取指数日线
    symbols: {"上证指数": "sh000001", ...}，默认三大指数
    """
    if symbols is None:
        symbols = {
            "上证指数": "sh000001",
            "深证成指": "sz399001",
            "沪深300": "sh000300",
        }
    results = {}
    for name, code in symbols.items():
        print(f"  指数 {name} ({code})...", end=" ", flush=True)
        try:
            results[code] = get_index_daily(code, force_refresh=force_refresh)
            print(f"✓ {len(results[code])}条")
        except Exception as e:
            print(f"✗ {e}")
    return results
