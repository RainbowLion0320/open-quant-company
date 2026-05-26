"""
数据库抽象层 — DuckDB 只做查询引擎，Parquet 做存储

设计理念:
  存储层: Parquet 文件 (无锁, 多进程安全, 按策略分区)
  查询层: DuckDB 只读连接 + CREATE VIEW FROM read_parquet()
  写入层: pd.DataFrame.to_parquet() (永不锁库)

架构:
  data/store/signals/{strategy}.parquet  — 策略信号
  data/store/scan_meta.parquet           — 扫描元数据
  DuckDB 文件仅存轻量视图定义, 不存数据
"""

import os
from pathlib import Path
from typing import Optional

from data.datahub import get_datahub

_DB_DIR = Path(__file__).resolve().parent
_HUB = get_datahub()
_STORE_DIR = _HUB.store_dir()
_DUCKDB_PATH = _DB_DIR / "quant_results.duckdb"
_SQLITE_PATH = _DB_DIR / "quant_results.db"

# 确保 store 目录存在
for _sub in ["signals", "equity", "financials"]:
    _HUB.store_dir(_sub) if _sub != "signals" else _HUB.signals_dir().mkdir(parents=True, exist_ok=True)


class Column:
    def __init__(self, keys, values):
        self._keys = list(keys)
        self._values = list(values)
    def keys(self): return self._keys
    def __getitem__(self, key):
        if isinstance(key, int): return self._values[key]
        return self._values[self._keys.index(key)]
    def __repr__(self): return dict(zip(self._keys, self._values)).__repr__()


class Database:
    def __init__(self, backend: str = "duckdb", path: Optional[Path] = None):
        self.backend = backend
        self._conn = None
        if backend == "duckdb":
            self.path = path or _DUCKDB_PATH
        elif backend == "sqlite":
            self.path = path or _SQLITE_PATH
        else:
            raise ValueError(f"Unknown backend: {backend}")

    def connect(self, read_only: bool = True):
        if self.backend == "duckdb":
            import duckdb
            if read_only:
                # 只读 → 内存数据库 (永不锁文件, 映射 Parquet 视图)
                self._conn = duckdb.connect(":memory:")
                self._conn.execute("SET enable_progress_bar=false")
                self._row_factory = True
                _register_views(self)
            else:
                # 读写 → 持久化文件 (仅 compute_signals 使用)
                self._conn = duckdb.connect(str(self.path))
                self._conn.execute("SET memory_limit='4GB'")
                self._conn.execute("SET threads=4")
                self._conn.execute("SET enable_progress_bar=false")
                self._row_factory = True
        elif self.backend == "sqlite":
            import sqlite3
            self._conn = sqlite3.connect(str(self.path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @property
    def conn(self):
        if self._conn is None: self.connect()
        return self._conn

    def _wrap_rows(self, rows, columns):
        return [Column(columns, row) for row in rows]

    def execute(self, sql: str, params=None):
        return self.conn.execute(sql, params) if params else self.conn.execute(sql)

    def executescript(self, sql: str):
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            self.conn.execute(stmt)

    def fetchall(self, sql: str, params=None) -> list:
        cur = self.execute(sql, params)
        if self.backend == "duckdb":
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            return self._wrap_rows(rows, cols)
        return cur.fetchall()

    def fetchone(self, sql: str, params=None):
        cur = self.execute(sql, params)
        if self.backend == "duckdb":
            rows = cur.fetchall()
            if not rows: return None
            cols = [d[0] for d in cur.description] if cur.description else []
            return self._wrap_rows(rows[:1], cols)[0]
        return cur.fetchone()

    def commit(self): self.conn.commit()

    def close(self):
        if self._conn: self._conn.close(); self._conn = None

    def __enter__(self): self.connect(); return self
    def __exit__(self, *args): self.close()

    def table_exists(self, table_name: str) -> bool:
        try: self.execute(f"SELECT 1 FROM {table_name} LIMIT 1"); return True
        except Exception: return False


# ── Parquet 视图注册 ──

def _register_views(db: Database):
    """将 data/store/ 下所有 Parquet 文件映射为 DuckDB 视图。

    视图命名:
      signals/{name}.parquet → {name}_signals  (策略信号)
      signals/buffett_scan.parquet → buffett_scan
      scan_meta.parquet       → scan_meta
    """
    if db.backend != "duckdb":
        return

    # 策略信号视图
    sig_dir = _HUB.signals_dir()
    for pq in sorted(sig_dir.glob("*.parquet")):
        name = pq.stem
        # buffett_scan.parquet → buffett_scan 视图 (财务详情)
        if name == "buffett_scan":
            db.execute(
                f"CREATE OR REPLACE VIEW buffett_scan AS "
                f"SELECT symbol, name, industry, sector, verdict, score, "
                f"  COALESCE(avg_roe_5y, 0) AS avg_roe_5y, "
                f"  COALESCE(avg_gross_margin_5y, 0) AS avg_gross_margin_5y, "
                f"  COALESCE(avg_net_margin_5y, 0) AS avg_net_margin_5y, "
                f"  COALESCE(debt_equity_ratio, 0) AS debt_equity_ratio, "
                f"  COALESCE(safety_margin_pct, 0) AS safety_margin_pct, "
                f"  COALESCE(dcf_value, 0) AS dcf_value, "
                f"  COALESCE(current_price, 0) AS current_price, "
                f"  COALESCE(updated_at, '') AS updated_at "
                f"FROM read_parquet('{pq}')"
            )
            continue

        # {name}.parquet → {name}_signals 视图 (策略信号)
        db.execute(
            f"CREATE OR REPLACE VIEW {name}_signals AS "
            f"SELECT * FROM read_parquet('{pq}')"
        )

    # 元数据视图
    meta_pq = _HUB.scan_meta_path()
    if meta_pq.exists():
        db.execute(
            f"CREATE OR REPLACE VIEW scan_meta AS "
            f"SELECT * FROM read_parquet('{meta_pq}')"
        )

    # 盘后数据缓存视图 under data/cache/api/
    api_cache_dir = _HUB.cache_root / "api"
    if api_cache_dir.exists():
        for pq in sorted(api_cache_dir.glob("*.parquet")):
            vname = "cache_" + pq.stem.replace("-", "_").replace(".", "_")
            try:
                db.execute(
                    f"CREATE OR REPLACE VIEW {vname} AS "
                    f"SELECT * FROM read_parquet('{pq}')"
                )
            except Exception:
                pass

    # ── 多资产存储视图 (Phase 4.1) ──
    # 扫描 data/store/{asset_type}/signals/ 下的信号文件
    for asset_dir in sorted(_STORE_DIR.glob("*/")):
        atype = asset_dir.name
        if atype in ("signals", "features"):
            continue
        atype_sig_dir = asset_dir / "signals"
        if atype_sig_dir.exists():
            for pq in sorted(atype_sig_dir.glob("*.parquet")):
                vname = f"{atype}_{pq.stem}_signals"
                try:
                    db.execute(
                        f"CREATE OR REPLACE VIEW {vname} AS "
                        f"SELECT * FROM read_parquet('{pq}')"
                    )
                except Exception:
                    pass


# ── 全局单例 ──
_db: Optional[Database] = None


def get_db(backend: str = "duckdb", read_only: bool = True) -> Database:
    """获取数据库实例。默认只读（Web安全），写操作需显式传 read_only=False。"""
    global _db
    if _db is not None:
        return _db
    _db = Database(backend=backend)
    _db.connect(read_only=read_only)
    return _db


def reset_db():
    global _db
    if _db: _db.close(); _db = None


def get_backend() -> str:
    return get_db().backend


def get_store_dir(asset_type: Optional[str] = None) -> Path:
    """获取存储目录。asset_type=None → 返回根目录。"""
    return _HUB.store_dir(asset_type)
