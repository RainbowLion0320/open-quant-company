#!/usr/bin/env python3
"""
LLM 因子假设生成器 — Phase 4.0 Research Engine

流程:
  1. LLM 生成候选因子假说 (基于金融文献知识)
  2. 翻译为 Factor DSL 表达式
  3. 用现有 PIT 特征数据计算 IC
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
from scipy.stats import spearmanr

from data.feature_store import FEATURES_DIR
from models import prepare_xy


# ══════════════════════════════════════════════════════════
# 1. LLM 因子假说提示词模板
# ══════════════════════════════════════════════════════════

HYPOTHESIS_PROMPT = """You are a quantitative finance researcher specializing in alpha factor discovery for Chinese A-share markets.

Generate {n} novel alpha factor hypotheses. Each factor should:
1. Predict cross-sectional stock returns (next 20-day forward return)
2. Use only available price/volume data: close, open, high, low, volume
3. Be expressed as a mathematical formula
4. Have economic intuition behind it

Format each factor as JSON:
```json
{{
  "name": "factor_short_name",
  "description": "Economic intuition in one sentence",
  "formula": "mathematical expression using close_t, close_t-5, volume_t, etc.",
  "expected_sign": "positive or negative"
}}
```

Examples of good factors:
- "5-day momentum": (close_t / close_t-5 - 1)  → positive
- "Volume surge": volume_t / mean(volume_t-20..t-1) → negative (mean-reversion)
- "Intraday reversal": (close_t - open_t) / (high_t - low_t + 0.01) → negative

Existing factors we already have (DON'T duplicate):
{existing_factors}

Generate {n} novel, non-redundant factors.
"""


# ══════════════════════════════════════════════════════════
# 2. Factor DSL 翻译器
# ══════════════════════════════════════════════════════════

@dataclass
class FactorCandidate:
    name: str
    description: str
    formula: str
    expected_sign: str
    ic: float = 0.0
    icir: float = 0.0
    dsl_expression: str = ""


def translate_to_dsl(formula: str) -> str:
    """将自然语言公式翻译为 Factor DSL 表达式
    
    Examples:
      "close_t / close_t-5 - 1" → "Ref('close',0) / Ref('close',-5) - 1"
      "mean(close_t-20..t-1)" → "MA('close',20)"
    """
    # 简单替换规则
    replacements = [
        (r'\bclose_t\b(?!-)', "Ref('close',0)"),
        (r'\bclose_t-(\d+)\b', r"Ref('close',-\1)"),
        (r'\bopen_t\b', "Ref('open',0)"),
        (r'\bhigh_t\b', "Ref('high',0)"),
        (r'\blow_t\b', "Ref('low',0)"),
        (r'\bvolume_t\b', "Ref('volume',0)"),
        (r'\bvolume_t-(\d+)\b', r"Ref('volume',-\1)"),
        (r'std\(.*?,\s*(\d+)\)', r"Std(..., \1)"),
        (r'mean\(.*?,\s*(\d+)\)', r"MA(..., \1)"),
        (r'max\(.*?,\s*(\d+)\)', r"Max(..., \1)"),
        (r'min\(.*?,\s*(\d+)\)', r"Min(..., \1)"),
    ]
    result = formula
    for pattern, repl in replacements:
        result = re.sub(pattern, repl, result)
    return result


# ══════════════════════════════════════════════════════════
# 3. IC 评估
# ══════════════════════════════════════════════════════════

def evaluate_factor(name: str, dsl_expr: str, features_df: pd.DataFrame) -> Dict:
    """计算因子 IC"""
    valid = features_df.dropna(subset=["ret_fwd_20d"])
    if len(valid) < 100:
        return {"ic": 0, "valid": False}

    # 计算因子值
    try:
        # 安全 eval DSL 表达式
        col_map = {}
        for col in ["close", "open", "high", "low", "volume"]:
            if col in valid.columns:
                col_map[col] = valid[col]
        # 简化: 直接用现有列名
        if name in valid.columns:
            factor_vals = valid[name].fillna(0)
        else:
            return {"ic": 0, "valid": False}
    except Exception:
        return {"ic": 0, "valid": False}

    y = valid["ret_fwd_20d"].fillna(0)
    ic, _ = spearmanr(factor_vals, y)
    ic = ic if not np.isnan(ic) else 0.0

    # ICIR (按月分组)
    monthly_ic = []
    for month in valid["month"].unique():
        mask = valid["month"] == month
        if mask.sum() >= 5:
            ic_m, _ = spearmanr(factor_vals[mask], y[mask])
            if not np.isnan(ic_m):
                monthly_ic.append(ic_m)
    icir = np.mean(monthly_ic) / (np.std(monthly_ic) + 1e-9) if monthly_ic else 0.0

    return {"ic": abs(ic), "icir": icir, "valid": True}


# ══════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════

def generate_via_llm(n: int = 10, api_key: str = "", base_url: str = "") -> List[FactorCandidate]:
    """调用 LLM 生成因子假说"""
    try:
        from openai import OpenAI
    except ImportError:
        print("openai not installed. Run: pip install openai")
        return []

    client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
                    base_url=base_url or None)
    if not client.api_key:
        print("No API key. Set OPENAI_API_KEY or pass --api-key")
        return []

    # 读取已有因子列表
    existing = []
    for pq in sorted(FEATURES_DIR.glob("*.parquet")):
        df = pd.read_parquet(pq)
        cols = [c for c in df.columns if c not in ("symbol", "month", "ret_fwd_20d", "name")]
        existing = cols
        break

    prompt = HYPOTHESIS_PROMPT.format(n=n, existing_factors=", ".join(existing[:30]))

    response = client.chat.completions.create(
        model=os.environ.get("LLM_MODEL", "deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
    )
    text = response.choices[0].message.content

    # 解析 JSON
    candidates = []
    json_blocks = re.findall(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    for block in json_blocks:
        try:
            items = json.loads(block)
            if isinstance(items, dict):
                items = [items]
            for item in items:
                c = FactorCandidate(
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    formula=item.get("formula", ""),
                    expected_sign=item.get("expected_sign", ""),
                    dsl_expression=translate_to_dsl(item.get("formula", "")),
                )
                candidates.append(c)
        except json.JSONDecodeError:
            pass

    return candidates


def run_hypothesis_loop(n_candidates: int = 10, ic_threshold: float = 0.02):
    """完整因子发现循环"""
    print(f"🧪 Phase 4.0: LLM 因子假设生成器")
    print(f"   候选数: {n_candidates}, IC阈值: {ic_threshold}")

    # 加载特征数据
    pq_files = sorted(FEATURES_DIR.glob("*.parquet"))
    if not pq_files:
        print("   ⚠️ 无 PIT 特征文件")
        return
    features = pd.concat([pd.read_parquet(pq) for pq in pq_files[-3:]], ignore_index=True)

    # 生成候选
    candidates = generate_via_llm(n=n_candidates)
    if not candidates:
        print("   ⚠️ LLM 未返回有效候选, 使用内置示例")
        # 内置示例因子
        candidates = [
            FactorCandidate("gap_reversal", "Gap opening tends to reverse intraday",
                          "(open_t - close_t-1) / close_t-1", "negative",
                          "(Ref('open',0) / Ref('close',-1) - 1)"),
            FactorCandidate("volume_price_trend", "Volume × price trend divergence",
                          "volume_t / MA(volume,20) * Ret('close')", "positive", ""),
            FactorCandidate("high_low_pressure", "High-low range expansion",
                          "(high_t - low_t) / Std(high_t - low_t, 20)", "negative", ""),
        ]

    print(f"\n   生成 {len(candidates)} 个候选因子:")

    # 评估每个因子
    accepted = []
    for c in candidates:
        result = evaluate_factor(c.name, c.dsl_expression, features)
        c.ic = result["ic"]
        c.icir = result["icir"]
        status = "✅" if result["ic"] > ic_threshold and result["valid"] else "❌"
        print(f"   {status} {c.name}: IC={c.ic:.4f} | {c.description[:60]}")

        if result["ic"] > ic_threshold and result["valid"]:
            accepted.append(c)

    # 报告
    print(f"\n   {'='*50}")
    print(f"   采纳: {len(accepted)}/{len(candidates)} (阈值={ic_threshold})")
    for c in accepted:
        print(f"   ✅ {c.name}: IC={c.ic:.4f}, 表达式={c.dsl_expression}")

    return accepted


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-candidates", type=int, default=10)
    ap.add_argument("--ic-threshold", type=float, default=0.02)
    ap.add_argument("--api-key", default="")
    args = ap.parse_args()
    run_hypothesis_loop(n_candidates=args.n_candidates, ic_threshold=args.ic_threshold)
