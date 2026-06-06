"""
Experiment Registry — 追踪研究/训练/回测的完整生命周期。

每次 workflow / tune_model / tournament 生成 run_id，记录:
  - git commit + config hash + DataHub manifest snapshot
  - model name/version/params
  - metrics (tournament/backtest)
  - artifact paths
  - status: scheduled → running → finished / failed

Persisted to var/store/runs.parquet via DataHub.
"""

import os
import json
import hashlib
import subprocess
import traceback
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent


def _git_commit() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT), capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip()[:8] if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _config_hash() -> str:
    cfg = PROJECT / "config" / "settings.yaml"
    if not cfg.exists():
        return "no_config"
    return hashlib.sha256(cfg.read_bytes()).hexdigest()[:12]


def _manifest_snapshot() -> Dict[str, str]:
    """Snapshot of DataHub manifest (key → schema_hash)."""
    manifest = PROJECT / "data" / "store" / "_manifest" / "datasets.parquet"
    if not manifest.exists():
        return {}
    try:
        df = pd.read_parquet(manifest)
        snap = {}
        for _, row in df.iterrows():
            key = row.get("key", row.get("path", ""))
            sha = row.get("schema_hash", "")
            if key:
                snap[str(key)] = str(sha)
        return snap
    except Exception:
        return {}


def _run_id(prefix: str = "run") -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}_{uuid.uuid4().hex[:6]}"


def _store() -> Path:
    d = PROJECT / "data" / "store"
    d.mkdir(parents=True, exist_ok=True)
    return d


class RunTracker:
    """Manages the lifecycle of a single experiment run."""

    def __init__(self, run_type: str, label: str = "", params: Optional[Dict] = None):
        self.run_id = _run_id(run_type)
        self.run_type = run_type
        self.label = label or run_type
        self.params = params or {}

        self._status = "scheduled"
        self._started = None
        self._finished = None
        self._metrics: Dict[str, Any] = {}
        self._artifacts: List[str] = []
        self._error: Optional[str] = None
        self._steps: List[Dict[str, Any]] = []
        self._record = None  # snapshot at start

    # ── lifecycle ──

    def start(self):
        self._status = "running"
        self._started = datetime.now(timezone.utc).isoformat()
        self._record = {
            "git_commit": _git_commit(),
            "config_hash": _config_hash(),
            "manifest_snapshot": json.dumps(_manifest_snapshot(), ensure_ascii=False),
        }
        self._persist()

    def log_step(self, name: str, status: str = "done", detail: str = ""):
        self._steps.append({
            "step": name, "status": status, "detail": detail,
            "at": datetime.now(timezone.utc).isoformat(),
        })

    def add_metric(self, key: str, value):
        self._metrics[key] = value

    def add_artifact(self, path: str):
        self._artifacts.append(path)

    def finish(self):
        self._status = "finished"
        self._finished = datetime.now(timezone.utc).isoformat()
        self._persist()

    def fail(self, error: str = ""):
        self._status = "failed"
        self._finished = datetime.now(timezone.utc).isoformat()
        self._error = error
        self._persist()

    # ── persistence ──

    def _persist(self):
        row = {
            "run_id": self.run_id,
            "run_type": self.run_type,
            "label": self.label,
            "status": self._status,
            "started_at": self._started,
            "finished_at": self._finished,
            "git_commit": self._record.get("git_commit", "") if self._record else "",
            "config_hash": self._record.get("config_hash", "") if self._record else "",
            "manifest_snapshot": self._record.get("manifest_snapshot", "") if self._record else "",
            "params": json.dumps(self.params, ensure_ascii=False),
            "metrics": json.dumps(self._metrics, ensure_ascii=False),
            "artifacts": json.dumps(self._artifacts, ensure_ascii=False),
            "steps": json.dumps(self._steps, ensure_ascii=False),
            "error": self._error or "",
        }
        from data.storage.datahub import get_datahub
        hub = get_datahub()
        hub.append_parquet(str(_store() / "runs.parquet"), row, dedupe_subset=["run_id"])

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "run_type": self.run_type,
            "label": self.label,
            "status": self._status,
            "started_at": self._started,
            "finished_at": self._finished,
            "git_commit": self._record.get("git_commit", "") if self._record else "",
            "config_hash": self._record.get("config_hash", "") if self._record else "",
            "params": self.params,
            "metrics": self._metrics,
            "artifacts": self._artifacts,
            "steps": self._steps,
            "error": self._error or "",
        }


# ── query API ──

def list_runs(limit: int = 20, run_type: str = "") -> List[Dict]:
    """List recent runs, optionally filtered by type."""
    pq = _store() / "runs.parquet"
    if not pq.exists():
        return []
    df = pd.read_parquet(pq)
    if run_type:
        df = df[df["run_type"] == run_type]
    df = df.sort_values("started_at", ascending=False).head(limit)
    records = df.to_dict(orient="records")
    for r in records:
        for col in ("params", "metrics", "artifacts", "steps"):
            if col in r and isinstance(r[col], str):
                try:
                    r[col] = json.loads(r[col])
                except (json.JSONDecodeError, TypeError):
                    pass
    return records


def get_run(run_id: str) -> Optional[Dict]:
    pq = _store() / "runs.parquet"
    if not pq.exists():
        return None
    df = pd.read_parquet(pq)
    rows = df[df["run_id"] == run_id]
    if rows.empty:
        return None
    r = rows.iloc[0].to_dict()
    for col in ("params", "metrics", "artifacts", "steps"):
        if col in r and isinstance(r[col], str):
            try:
                r[col] = json.loads(r[col])
            except (json.JSONDecodeError, TypeError):
                pass
    return r


def recent_error_runs(limit: int = 5) -> List[Dict]:
    """Return recent failed runs for debugging."""
    pq = _store() / "runs.parquet"
    if not pq.exists():
        return []
    df = pd.read_parquet(pq)
    failed = df[df["status"] == "failed"].sort_values("finished_at", ascending=False).head(limit)
    records = failed.to_dict(orient="records")
    for r in records:
        for col in ("params", "metrics", "steps"):
            if col in r and isinstance(r[col], str):
                try:
                    r[col] = json.loads(r[col])
                except (json.JSONDecodeError, TypeError):
                    pass
    return records
