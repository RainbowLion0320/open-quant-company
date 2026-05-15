#!/usr/bin/env python3
"""
统一工作流执行器 — 对标 Qlib `qrun`

读取 config/workflows/{name}.yaml，按顺序执行 steps。
每个 step 是一个独立脚本，带超时和重试。

用法:
  python scripts/run_workflow.py research_pipeline
  python scripts/run_workflow.py factor_discovery
  python scripts/run_workflow.py --list     # 列出所有可用工作流
"""
import sys
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

import yaml

PROJECT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = PROJECT / "config" / "workflows"
VENV_PYTHON = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3"


def load_workflow(name: str) -> Optional[Dict]:
    """Load workflow YAML definition."""
    wf_path = WORKFLOW_DIR / f"{name}.yaml"
    if not wf_path.exists():
        print(f"✗ Workflow not found: {name}")
        print(f"  Available:")
        for wf in sorted(WORKFLOW_DIR.glob("*.yaml")):
            print(f"    - {wf.stem}")
        return None
    with open(wf_path) as f:
        return yaml.safe_load(f)


def run_step(step: Dict, step_index: int, total_steps: int) -> bool:
    """Execute one workflow step. Returns True on success."""
    name = step["name"]
    script = step["script"]
    args = step.get("args", [])
    timeout = step.get("timeout_minutes", 30) * 60
    max_retries = step.get("retry", 0)
    on_fail = step.get("on_fail", "abort")

    script_path = PROJECT / script
    if not script_path.exists():
        print(f"  ✗ Script not found: {script}")
        return on_fail != "abort"

    for attempt in range(max_retries + 1):
        label = f"[{step_index}/{total_steps}] {name}"
        if attempt > 0:
            label += f" (retry {attempt}/{max_retries})"

        print(f"\n{'─'*60}")
        print(f"  {label}")
        print(f"  {'─'*60}")

        cmd = [str(VENV_PYTHON), str(script_path)] + args
        print(f"  → {' '.join(cmd)}")

        t0 = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=str(PROJECT),
                timeout=timeout,
                capture_output=True,
                text=True,
            )
            elapsed = time.time() - t0

            # Print output
            if result.stdout:
                for line in result.stdout.strip().split("\n")[-20:]:
                    print(f"    {line}")

            if result.returncode == 0:
                print(f"  ✓ {name} completed in {elapsed:.0f}s")
                return True
            else:
                print(f"  ✗ {name} failed (exit={result.returncode}) in {elapsed:.0f}s")
                if result.stderr:
                    for line in result.stderr.strip().split("\n")[-5:]:
                        print(f"    [stderr] {line}")

        except subprocess.TimeoutExpired:
            elapsed = time.time() - t0
            print(f"  ✗ {name} timeout after {elapsed:.0f}s (limit: {timeout}s)")

        except Exception as e:
            print(f"  ✗ {name} error: {e}")

        if attempt < max_retries:
            print(f"  ↻ Retrying...")

    # All retries exhausted
    if on_fail == "abort":
        print(f"\n  ⏹ Aborting workflow (on_fail=abort)")
        return False
    elif on_fail == "warn":
        print(f"\n  ⚠ Step failed but continuing (on_fail=warn)")
        return True
    else:  # continue
        return True


def run_workflow(name: str) -> bool:
    """Execute a complete workflow."""
    wf = load_workflow(name)
    if wf is None:
        return False

    steps = wf.get("steps", [])
    total = len(steps)

    print(f"{'='*60}")
    print(f"🚀 Workflow: {wf.get('name', name)}")
    print(f"   {wf.get('description', '')}")
    print(f"   Steps: {total}")
    print(f"{'='*60}")

    t_start = time.time()
    for i, step in enumerate(steps, 1):
        ok = run_step(step, i, total)
        if not ok:
            elapsed = time.time() - t_start
            print(f"\n{'='*60}")
            print(f"✗ Workflow FAILED after {elapsed:.0f}s")
            print(f"{'='*60}")
            return False

    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"✓ Workflow COMPLETE — {elapsed/60:.1f} minutes")
    print(f"{'='*60}")
    return True


def list_workflows():
    """List all available workflows."""
    print("Available workflows:")
    for wf in sorted(WORKFLOW_DIR.glob("*.yaml")):
        with open(wf) as f:
            cfg = yaml.safe_load(f)
        steps = len(cfg.get("steps", []))
        print(f"  {wf.stem:30s} {steps} steps — {cfg.get('description', '')}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Workflow Runner (qrun-style)")
    ap.add_argument("workflow", nargs="?", help="Workflow name")
    ap.add_argument("--list", action="store_true", help="List available workflows")
    args = ap.parse_args()

    if args.list or not args.workflow:
        list_workflows()
    else:
        run_workflow(args.workflow)
