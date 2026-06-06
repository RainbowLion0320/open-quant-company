#!/usr/bin/env python3
"""Start Hindsight embedded daemon for 星盘.

This script reads API credentials from process environment only and keeps the
daemon alive.

Usage:
  python scripts/start_hindsight_daemon.py
"""

import os
import sys
import time
import signal


def main():
    # HuggingFace is blocked by v2ray proxy. Models already cached locally.
    # Without these, SentenceTransformer init tries to reach huggingface.co → crash.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY is not configured in the process environment")
        sys.exit(1)

    os.environ.setdefault("HINDSIGHT_API_LLM_PROVIDER", "openai")
    os.environ.setdefault("HINDSIGHT_API_LLM_MODEL", "deepseek-v4-flash")
    os.environ.setdefault("HINDSIGHT_API_LLM_BASE_URL", "https://api.deepseek.com/v1")

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
        llm_provider=os.environ["HINDSIGHT_API_LLM_PROVIDER"],
        llm_api_key=api_key,
        llm_model=os.environ["HINDSIGHT_API_LLM_MODEL"],
        llm_base_url=os.environ["HINDSIGHT_API_LLM_BASE_URL"],
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
