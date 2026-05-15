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
from datetime import datetime, timedelta
from typing import Optional, Callable
import pandas as pd

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

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")


# ============================================================
# 请求节流 — 全局最小间隔，避免触发反爬
# ============================================================

_throttle_lock = threading.Lock()
_last_request_time: float = 0.0
MIN_INTERVAL: float = 3.0  # 每次请求最小间隔（秒），批量模式避免触发反爬


def _throttle():
    """节流：确保两次请求之间至少间隔 MIN_INTERVAL 秒"""
    global _last_request_time
    with _throttle_lock:
        now = time.monotonic()
        elapsed = now - _last_request_time
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed + random.uniform(0, 0.5))
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
    max_retries: int = 3,
    base_delay: float = 2.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
):
    """
    装饰器：带指数退避和随机抖动的重试
    间隔: base * factor^attempt + random jitter
    例: 2s → 4s → 8s（加随机抖动避免惊群）
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except RETRYABLE_ERRORS as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = base_delay * (backoff_factor ** attempt)
                        if jitter:
                            delay += random.uniform(0, delay * 0.3)
                        print(
                            f"  [RETRY] {func.__name__} 第{attempt+1}次失败: {type(e).__name__}, "
                            f"{delay:.1f}s后重试..."
                        )
                        time.sleep(delay)
                    else:
                        print(f"  [FAIL] {func.__name__} 已重试{max_retries}次，放弃")
            raise last_error  # type: ignore
        return wrapper
    return decorator


# ============================================================
# 缓存层 — 两层：磁盘(parquet,跨会话) + 内存(dict,会话内)
# ============================================================

# 内存缓存 — 同一会话内避免重复磁盘读取
_mem_cache: dict = {}
_MEM_CACHE_MAX = 64  # 最多缓存 64 个 DataFrame


def _cache_path(key: str) -> str:
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return os.path.join(CACHE_DIR, f"{h}.parquet")


def _mem_get(key: str) -> Optional[pd.DataFrame]:
    """从内存缓存读取"""
    return _mem_cache.get(key)


def _mem_set(key: str, df: pd.DataFrame):
    """写入内存缓存，维护上限"""
    if len(_mem_cache) >= _MEM_CACHE_MAX:
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
    df = pd.read_parquet(path)
    _mem_set(key, df)
    return df


def _write_cache(key: str, df: pd.DataFrame):
    """写缓存：同时写内存和磁盘"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    df.to_parquet(_cache_path(key), index=False)
    _mem_set(key, df)


# TTL 常量——分三级
TTL_FOREVER = 365 * 24       # 历史数据：永不失效（annual: 365天 ≈ 永久）
TTL_DAILY = 24               # 日线数据：建议日常 force_refresh=True
TTL_REALTIME = 1             # 实时数据：1h


def refresh_stock_daily(symbol: str, adjust: str = "qfq", source: str = "sina") -> pd.DataFrame:
    """强制刷新个股日线（追加模式：缓存+新数据合并）"""
    cache_key = f"stock_daily_{symbol}_{adjust}_{source}"

    # 读已有缓存，获取最后日期
    old = _read_cache(cache_key, max_age_hours=0)
    last_date = None
    if old is not None and len(old) > 0:
        last_date = old["date"].iloc[-1] if "date" in old.columns else None

    # 拉全量（AKShare 不支持增量接口）
    import akshare as ak
    _throttle()  # API调用前节流
    if source == "sina":
        df = ak.stock_zh_a_daily(symbol=_to_sina_symbol(symbol), adjust=adjust)
        col_map = {
            "date": "date", "open": "open", "close": "close", "high": "high", "low": "low",
            "volume": "volume", "amount": "amount",
            "outstanding_share": "outstanding_share", "turnover": "turnover",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    elif source == "tx":
        import datetime as dt_mod
        df = ak.stock_zh_a_hist_tx(
            symbol=_to_sina_symbol(symbol),
            start_date="19900101",
            end_date=dt_mod.date.today().strftime("%Y%m%d"),
        )
        df = df.rename(columns={"date": "date", "open": "open", "close": "close",
                                "high": "high", "low": "low", "amount": "volume"})
    else:
        df = ak.stock_zh_a_hist(symbol=_to_plain_code(symbol), period="daily", adjust=adjust)
        col_map = {
            "日期": "date", "开盘": "open", "收盘": "close", "最高": "high", "最低": "low",
            "成交量": "volume", "成交额": "amount",
            "振幅": "amplitude", "涨跌幅": "pct_change", "涨跌额": "change", "换手率": "turnover",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # 和新数据合并
    if old is not None and len(old) > 0:
        existing_dates = set(old["date"].tolist()) if "date" in old.columns else set()
        new_rows = df[~df["date"].isin(existing_dates)]
        df = pd.concat([old, new_rows], ignore_index=True)
        df = df.sort_values("date").reset_index(drop=True)

    _write_cache(cache_key, df)
    return df


def refresh_index_daily(symbol: str = "sh000001", source: str = "default") -> pd.DataFrame:
    """强制刷新指数日线（追加模式）"""
    cache_key = f"index_daily_{symbol}_{source}"

    old = _read_cache(cache_key, max_age_hours=0)
    last_date = None
    if old is not None and len(old) > 0:
        col = "date" if "date" in old.columns else old.columns[0]
        last_date = old[col].iloc[-1]

    import akshare as ak
    _throttle()  # API调用前节流
    if source == "tx":
        df = ak.stock_zh_index_daily_tx(symbol=symbol)
    elif source == "em":
        df = ak.stock_zh_index_daily_em(symbol=symbol)
    else:
        df = ak.stock_zh_index_daily(symbol=symbol)

    df.columns = [c.lower() for c in df.columns]

    if old is not None and len(old) > 0:
        date_col = "date" if "date" in df.columns else df.columns[0]
        existing_dates = set(old[date_col].tolist())
        new_rows = df[~df[date_col].isin(existing_dates)]
        df = pd.concat([old, new_rows], ignore_index=True)
        df = df.sort_values(date_col).reset_index(drop=True)

    _write_cache(cache_key, df)
    return df


# ============================================================
# 数据源适配 — 多源切换 + 符号格式转换
# ============================================================

def _to_eastmoney_symbol(code: str) -> str:
    """纯数字代码 → 东方财富格式"""
    if code.startswith(("sh", "sz")):
        return code
    if code.startswith(("60", "68")):
        return f"sh{code}"
    return f"sz{code}"


def _to_sina_symbol(code: str) -> str:
    """纯数字代码 → 新浪格式 (sh600519)"""
    if code.startswith(("sh", "sz")):
        return code
    if code.startswith(("60", "68")):
        return f"sh{code}"
    return f"sz{code}"


def _to_plain_code(code: str) -> str:
    """去掉前缀, 返回纯数字"""
    return code.replace("sh", "").replace("sz", "")

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
        cached = _read_cache(cache_key, max_age_hours=TTL_DAILY)
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
    source: str = "sina",  # sina / em / tx
) -> pd.DataFrame:
    """
    获取个股日线（前复权）
    symbol: 如 '600519' 或 'sh600519'（自动适配格式）
    adjust: qfq(前复权), hfq(后复权), ''(不复权)
    source: sina(新浪,推荐), em(东方财富), tx(腾讯)
    """
    cache_key = f"stock_daily_{symbol}_{adjust}_{source}"
    if not force_refresh:
        cached = _read_cache(cache_key, max_age_hours=TTL_DAILY)
        if cached is not None:
            return cached

    import akshare as ak

    _throttle()  # API调用前节流
    if source == "sina":
        df = ak.stock_zh_a_daily(symbol=_to_sina_symbol(symbol), adjust=adjust)
        col_map = {
            "date": "date",
            "open": "open", "close": "close", "high": "high", "low": "low",
            "volume": "volume", "amount": "amount",
            "outstanding_share": "outstanding_share",
            "turnover": "turnover",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    elif source == "tx":
        import datetime
        df = ak.stock_zh_a_hist_tx(
            symbol=_to_sina_symbol(symbol),
            start_date="19900101",
            end_date=datetime.date.today().strftime("%Y%m%d"),
        )
        col_map = {
            "date": "date",
            "open": "open", "close": "close", "high": "high", "low": "low",
            "amount": "volume",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    else:  # em (东方财富)
        df = ak.stock_zh_a_hist(symbol=_to_plain_code(symbol), period="daily", adjust=adjust)
        col_map = {
            "日期": "date", "股票代码": "symbol",
            "开盘": "open", "收盘": "close", "最高": "high", "最低": "low",
            "成交量": "volume", "成交额": "amount",
            "振幅": "amplitude", "涨跌幅": "pct_change",
            "涨跌额": "change", "换手率": "turnover",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    _write_cache(cache_key, df)
    return df


@retry_with_backoff(max_retries=3, base_delay=2.0)
def get_financial_indicator(
    symbol: str,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    获取财务指标（ROE、毛利率、资产负债率等）
    数据来源：同花顺
    """
    cache_key = f"financial_{symbol}"
    if not force_refresh:
        cached = _read_cache(cache_key, max_age_hours=720)  # 30天，季度财报更新周期
        if cached is not None:
            return cached

    import akshare as ak
    _throttle()
    df = ak.stock_financial_abstract_ths(symbol=symbol, indicator="按报告期")
    _write_cache(cache_key, df)
    return df


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
