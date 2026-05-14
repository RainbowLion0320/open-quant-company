#!/usr/bin/env python3
"""
LLM 因子假设生成器 — Phase 4.0 Research Engine

流程:
  1. LLM 生成候选因子假说 (基于金融文献知识)
  2. DSL 解析器计算因子值 (signals/dsl_parser.py)
  3. 用 PIT 特征数据评估 IC
  4. IC > 阈值 → 加入因子库

用法:
  python scripts/factor_hypothesis.py --n-candidates 10 --ic-threshold 0.02
"""
import os, sys, json, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dataclasses import dataclass
from typing import List, Dict, Optional

import pandas as pd
import numpy as np

from data.feature_store import FEATURES_DIR
from signals.dsl_parser import compute_formula
from data.fetcher import get_stock_daily


# ══════════════════════════════════════════════════════════
# 1. LLM 因子假说提示词
# ══════════════════════════════════════════════════════════

HYPOTHESIS_PROMPT = """You are a quantitative finance researcher specializing in alpha factor discovery for Chinese A-share markets.

Generate {n} novel alpha factor hypotheses. Each factor should:
1. Predict cross-sectional stock returns (next 20-day forward return)
2. Use only available price/volume data: close_t, close_t-5, high_t, low_t, volume_t, open_t
3. Support functions: MA(close,20), Std(close,20), Delta(close,5)
4. Be expressed as a mathematical formula using these exact variable names
5. Have clear economic intuition

Format each factor as JSON:
```json
{{
  "name": "factor_short_name",
  "formula": "(close_t - MA(close,20)) / Std(close,20)",
  "expected_sign": "positive or negative"
}}
```

Examples of good factors:
- "5-day momentum": (close_t / close_t-5 - 1)  → positive
- "Bollinger position": (close_t - MA(close,20)) / Std(close,20) → negative
- "Volume surge": volume_t / MA(volume,5) → negative

Existing factors we already have (DON'T duplicate):
{existing_factors}

Generate {n} novel, non-redundant factors."""


# ══════════════════════════════════════════════════════════

@dataclass
class FactorCandidate:
    name: str
    formula: str = ""
    description: str = ""
    expected_sign: str = ""
    ic: float = 0.0


def generate_via_llm(n: int = 10) -> List[FactorCandidate]:
    """调用 LLM 生成因子假说"""
    try:
        from openai import OpenAI
    except ImportError:
        print("openai not installed. pip install openai")
        return []
    
    # 读取 .env 获取 API key
    env_path = os.path.expanduser("~/.hermes/.env")
    api_key = ""
    if os.path.exists(env_path):
        for line in open(env_path):
            if line.startswith("DEEPSEEK_API_KEY="):
                api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    
    if not api_key:
        print("No DEEPSEEK_API_KEY in ~/.hermes/.env")
        return []
    
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
    
    # 读取已有因子
    existing = []
    for pq in sorted(FEATURES_DIR.glob("*.parquet")):
        df = pd.read_parquet(pq)
        existing = [c for c in df.columns if c not in ("symbol", "month", "ret_fwd_20d", "name")]
        break
    
    prompt = HYPOTHESIS_PROMPT.format(n=n, existing_factors=", ".join(existing[:30]))
    
    response = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
    )
    text = response.choices[0].message.content
    
    candidates = []
    json_blocks = re.findall(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    for block in json_blocks:
        try:
            items = json.loads(block)
            if isinstance(items, dict): items = [items]
            for item in items:
                c = FactorCandidate(
                    name=item.get("name", ""),
                    formula=item.get("formula", ""),
                    expected_sign=item.get("expected_sign", ""),
                    description=item.get("description", ""),
                )
                candidates.append(c)
        except json.JSONDecodeError:
            pass
    
    return candidates


def evaluate_factor(formula: str, features_df: pd.DataFrame) -> dict:
    """计算因子 IC — 用 DSL 解析器动态计算"""
    valid = features_df.dropna(subset=["ret_fwd_20d"])
    if len(valid) < 100:
        return {"ic": 0, "valid": False}
    
    syms = valid["symbol"].unique()[:80]
    factor_vals = []
    targets = []
    
    for sym in syms:
        try:
            df = get_stock_daily(sym)
            if df is None or len(df) < 60:
                continue
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            idx = len(df) - 1
            
            val = compute_formula(formula, df, idx)
            if not np.isnan(val) and abs(val) < 1e10:
                factor_vals.append(val)
                sym_data = valid[valid["symbol"] == sym]
                if len(sym_data) > 0:
                    targets.append(sym_data["ret_fwd_20d"].iloc[0])
        except Exception:
            pass
    
    if len(factor_vals) < 10:
        return {"ic": 0, "valid": False}
    
    from scipy.stats import spearmanr
    y = pd.Series(targets)
    fv = pd.Series(factor_vals)
    ic, _ = spearmanr(fv, y)
    ic = ic if not np.isnan(ic) else 0.0
    return {"ic": abs(ic), "valid": True}


def run_hypothesis_loop(n_candidates: int = 10, ic_threshold: float = 0.02):
    """完整因子发现循环"""
    print(f"🧪 Phase 4.0: LLM 因子假设生成器")
    print(f"   候选数: {n_candidates}, IC阈值: {ic_threshold}")
    print(f"   模型: deepseek-v4-pro")
    
    # 加载特征数据
    pq_files = sorted(FEATURES_DIR.glob("*.parquet"))
    if not pq_files:
        print("   ⚠️ 无 PIT 特征文件")
        return
    features = pd.concat([pd.read_parquet(pq) for pq in pq_files[-3:]], ignore_index=True)
    
    # 生成候选
    candidates = generate_via_llm(n=n_candidates)
    if not candidates:
        print("   ⚠️ LLM 未返回有效候选")
        return
    
    print(f"\n   {len(candidates)} 个候选因子:")
    
    accepted = []
    for c in candidates:
        result = evaluate_factor(c.formula, features)
        c.ic = result.get("ic", 0)
        status = "✅" if c.ic > ic_threshold and result.get("valid") else "❌"
        print(f"   {status} {c.name}: IC={c.ic:.4f} | {c.formula[:60]}")
        
        if c.ic > ic_threshold and result.get("valid"):
            accepted.append(c)
    
    print(f"\n   {'='*50}")
    print(f"   采纳: {len(accepted)}/{len(candidates)} (阈值={ic_threshold})")
    for c in accepted:
        print(f"   ✅ {c.name}: IC={c.ic:.4f}, 公式={c.formula}")
    
    return accepted


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-candidates", type=int, default=10)
    ap.add_argument("--ic-threshold", type=float, default=0.02)
    args = ap.parse_args()
    run_hypothesis_loop(n_candidates=args.n_candidates, ic_threshold=args.ic_threshold)
