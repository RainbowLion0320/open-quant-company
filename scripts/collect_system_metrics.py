#!/usr/bin/env python3
"""系统监控数据采集 —— 每分钟写入 SQLite (WAL 模式)"""
import os, sys, time, json, sqlite3
from datetime import datetime
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.datahub import get_datahub

HUB = get_datahub()
DB = HUB.system_monitor_path()
TOKEN_CACHE = HUB.token_usage_path()


def init_db(conn):
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            ts          TEXT    PRIMARY KEY,   -- ISO timestamp
            cpu_pct     REAL,                  -- CPU 使用率 %
            mem_pct     REAL,                  -- 内存使用率 %
            mem_used_gb REAL,                  -- 已用内存 GB
            disk_pct    REAL,                  -- 磁盘使用率 %
            load_1m     REAL,                  -- 1分钟负载
            load_5m     REAL,
            load_15m    REAL,
            bat_pct     REAL,                  -- 电池 %
            bat_charge  INTEGER,               -- 1=充电中
            token_hermes_in  INTEGER,           -- Hermes 输入 token
            token_hermes_out INTEGER,           -- Hermes 输出 token
            token_ext_in     INTEGER,           -- 外部输入 token
            token_ext_out    INTEGER,           -- 外部输出 token
            token_total_cost REAL               -- 总费用 $
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS top_processes (
            ts       TEXT,
            rank     INTEGER,
            pid      INTEGER,
            name     TEXT,
            cpu_pct  REAL,
            mem_pct  REAL,
            PRIMARY KEY (ts, rank)
        )
    """)


def collect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB))
    init_db(conn)

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # System
    cpu = psutil.cpu_percent(interval=0.05)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load = psutil.getloadavg()
    bat = psutil.sensors_battery()

    # Token
    token = {"hermes": {}, "external": {}, "total": {}}
    try:
        if TOKEN_CACHE.exists():
            with open(TOKEN_CACHE) as f:
                token = json.load(f)
    except Exception:
        pass

    conn.execute("""
        INSERT OR REPLACE INTO metrics
        (ts, cpu_pct, mem_pct, mem_used_gb, disk_pct, load_1m, load_5m, load_15m,
         bat_pct, bat_charge, token_hermes_in, token_hermes_out,
         token_ext_in, token_ext_out, token_total_cost)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now,
        round(cpu, 1),
        round(mem.used / mem.total * 100, 1),
        round(mem.used / 1024**3, 1),
        round(disk.percent, 1),
        round(load[0], 2),
        round(load[1], 2),
        round(load[2], 2),
        round(bat.percent, 1) if bat else None,
        1 if (bat and bat.power_plugged) else 0,
        token.get("hermes", {}).get("input_tokens", 0),
        token.get("hermes", {}).get("output_tokens", 0),
        token.get("external", {}).get("input_tokens", 0),
        token.get("external", {}).get("output_tokens", 0),
        round(token.get("total", {}).get("cost_usd", 0), 6),
    ))

    # Top processes
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            pi = p.info
            procs.append(pi)
            if len(procs) > 200:
                break
        except Exception:
            pass
    procs.sort(key=lambda x: -(x.get("cpu_percent") or 0))
    for rank, p in enumerate(procs[:10]):
        if (p.get("cpu_percent") or 0) <= 0:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO top_processes (ts, rank, pid, name, cpu_pct, mem_pct) VALUES (?,?,?,?,?,?)",
            (now, rank, p["pid"], p["name"],
             round(p.get("cpu_percent") or 0, 1),
             round(p.get("memory_percent") or 0, 1))
        )

    conn.commit()
    conn.close()

    # 清理旧数据 (保留 30 天)
    _cleanup()


def _cleanup():
    """保留最近365天数据"""
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        conn = sqlite3.connect(str(DB))
        conn.execute("DELETE FROM metrics WHERE ts < ?", (cutoff,))
        conn.execute("DELETE FROM top_processes WHERE ts < ?", (cutoff,))
        conn.commit()
        conn.close()
    except Exception:
        pass


if __name__ == "__main__":
    collect()
