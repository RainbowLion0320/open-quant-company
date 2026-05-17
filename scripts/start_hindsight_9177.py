#!/usr/bin/env python3
"""Start Hindsight daemon connecting to existing pg0 hindsight DB on port 9177."""

import os, sys, time, signal
from pathlib import Path

def load_env_value(env_path: Path, key: str) -> str:
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
    hermes_env = Path.home() / ".hermes" / ".env"
    api_key = load_env_value(hermes_env, "DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not found")
        sys.exit(1)

    os.environ["HINDSIGHT_API_LLM_API_KEY"] = api_key
    os.environ["HINDSIGHT_LLM_API_KEY"] = api_key

    from hindsight import start_server

    running = [True]
    def handle_signal(signum, frame):
        print(f"\nSignal {signum}, shutting down...")
        running[0] = False
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    print("Starting Hindsight daemon on port 9177 (pg0 localhost:5432)...")
    server = start_server(
        db_url="postgresql://localhost:5432/hindsight",
        llm_provider="openai",
        llm_api_key=api_key,
        llm_model="deepseek-v4-flash",
        llm_base_url="https://api.deepseek.com/v1",
        host="127.0.0.1",
        port=9177,
    )
    print(f"READY URL={server.url}")
    sys.stdout.flush()

    while running[0]:
        time.sleep(5)
    print("Daemon stopped.")

if __name__ == "__main__":
    main()
