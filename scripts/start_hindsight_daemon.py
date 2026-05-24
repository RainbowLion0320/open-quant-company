#!/usr/bin/env python3
"""Start Hindsight embedded daemon for 星盘.

This script reads the API key from ~/.hermes/.env (DEEPSEEK_API_KEY),
constructs proper env vars for the daemon, and keeps it alive.

Usage:
  python scripts/start_hindsight_daemon.py
"""

import os
import sys
import time
import signal
from pathlib import Path


def load_env_value(env_path: Path, key: str) -> str:
    """Read a KEY=VALUE from a .env file."""
    if not env_path.exists():
        return ""
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{key}="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                return val
    return ""


def main():
    # HuggingFace is blocked by v2ray proxy. Models already cached locally.
    # Without these, SentenceTransformer init tries to reach huggingface.co → crash.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    hermes_env = Path.home() / ".hermes" / ".env"
    api_key = load_env_value(hermes_env, "DEEPSEEK_API_KEY")

    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not found in ~/.hermes/.env")
        sys.exit(1)

    # Set env vars that the daemon's MemoryEngine expects
    os.environ["HINDSIGHT_API_LLM_API_KEY"] = api_key
    os.environ["HINDSIGHT_API_LLM_PROVIDER"] = "openai"
    os.environ["HINDSIGHT_API_LLM_MODEL"] = "deepseek-v4-flash"
    os.environ["HINDSIGHT_API_LLM_BASE_URL"] = "https://api.deepseek.com/v1"

    from hindsight import start_server

    # Graceful shutdown
    running = True

    def handle_signal(signum, frame):
        nonlocal running
        print(f"\nReceived signal {signum}, shutting down...")
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    print("Starting 星盘 Hindsight embedded daemon (pg0 + deepseek-v4-flash)...")
    server = start_server(
        db_url="pg0",
        llm_provider="openai",
        llm_api_key=api_key,
        llm_model="deepseek-v4-flash",
        llm_base_url="https://api.deepseek.com/v1",
        host="127.0.0.1",
        port=9177,
        timeout=120.0,
    )
    print(f"READY URL={server.url}")
    sys.stdout.flush()

    # Keep alive — daemon runs in a background thread
    while running:
        time.sleep(5)

    print("Daemon stopped.")


if __name__ == "__main__":
    main()
