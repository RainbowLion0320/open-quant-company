#!/usr/bin/env python3
"""从 Hindsight /metrics 提取 LLM token 统计"""
import re, urllib.request, json, os, sys
from datetime import datetime

OUT = "/Users/fushao/quant-agent/data/cache/hindsight_tokens.json"


def parse_metrics(text: str) -> dict:
    inputs, outputs, calls = {}, {}, {}
    for m in re.finditer(r'hindsight_llm_tokens_input_tokens_total\{[^}]*scope="([^"]+)"[^}]*\}\s+([\d.]+)', text):
        inputs[m.group(1)] = inputs.get(m.group(1), 0) + int(float(m.group(2)))
    for m in re.finditer(r'hindsight_llm_tokens_output_tokens_total\{[^}]*scope="([^"]+)"[^}]*\}\s+([\d.]+)', text):
        outputs[m.group(1)] = outputs.get(m.group(1), 0) + int(float(m.group(2)))
    for m in re.finditer(r'hindsight_llm_calls_total\{[^}]*scope="([^"]+)"[^}]*\}\s+([\d.]+)', text):
        calls[m.group(1)] = calls.get(m.group(1), 0) + int(float(m.group(2)))
    return {
        "input_tokens": sum(inputs.values()),
        "output_tokens": sum(outputs.values()),
        "total_tokens": sum(inputs.values()) + sum(outputs.values()),
        "calls": sum(calls.values()),
        "cost_usd": round(sum(inputs.values()) / 1_000_000 * 0.27 + sum(outputs.values()) / 1_000_000 * 1.10, 6),
        "scopes": list(inputs.keys()),
        "updated_at": datetime.now().isoformat(),
    }


def collect():
    try:
        resp = urllib.request.urlopen("http://localhost:8888/metrics", timeout=5)
        text = resp.read().decode()
        data = parse_metrics(text)
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w") as f:
            json.dump(data, f)
        print(f"Hindsight: {data['input_tokens']:,} in / {data['output_tokens']:,} out "
              f"= ${data['cost_usd']:.6f} ({data['calls']} calls)")
    except Exception as e:
        print(f"Hindsight fetch failed: {e}")


if __name__ == "__main__":
    collect()
