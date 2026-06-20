"""LLM prompt, usage logging, and response parsing for factor discovery."""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from data.storage.dimensions import get_registry
from data.llm.usage import append_llm_usage, load_provider_api_key, resolve_llm_use_case
from research.factors.hypothesis.candidates import FactorCandidate

def _log_llm_usage(source: str, usage, provider: str, model: str):
    """Record provider response usage in the canonical local LLM ledger."""
    try:
        append_llm_usage(provider, model, usage, source=source)
    except Exception:
        pass

# ══════════════════════════════════════════════════════════
# 1. 扩展 LLM 提示词 — 暴露全部可用数据维度
# ══════════════════════════════════════════════════════════

def build_hypothesis_prompt(n: int, existing: List[str],
                            importance_hints: Optional[Dict[str, float]] = None) -> str:
    """
    Build LLM prompt with full data vocabulary from the data registry.

    importance_hints: {factor_name: importance_score} from previous model training.
    LLM uses these to avoid overfit patterns and explore underserved areas.
    """
    reg = get_registry()
    available = reg.get_available()

    # Build data vocabulary for the LLM
    vocab_lines = []
    for d in available:
        vocab_lines.append(f"  {d.key}: {d.label} [{d.freq}] — {d.description or d.label}")
    vocab = "\n".join(vocab_lines)

    # Build importance feedback
    importance_section = ""
    if importance_hints:
        top_factors = sorted(importance_hints.items(), key=lambda x: -x[1])[:10]
        bottom_factors = sorted(importance_hints.items(), key=lambda x: x[1])[:5]
        importance_section = f"""
Model feature importance from last training:
  Top factors (overfit risk — find alternatives to reduce reliance):
    {chr(10).join(f'    {name}: {score:.4f}' for name, score in top_factors)}
  Weak factors (underserved — try complementary patterns):
    {chr(10).join(f'    {name}: {score:.4f}' for name, score in bottom_factors)}
"""

    return f"""You are a quantitative finance researcher specializing in alpha factor discovery for Chinese A-share markets.

GENERATE {n} NOVEL alpha factor hypotheses for cross-sectional stock return prediction (next 20-day forward return).

AVAILABLE DATA DIMENSIONS (use these in your formulas):
{vocab}

CRITICAL RULE — Cross-Sectional Discrimination:
  • MACRO variables (PMI, SHIBOR, M2, CPI, etc.) are the SAME for ALL stocks on a given date.
  • ❌ FAILED EXAMPLES (these were REJECTED — do NOT propose anything similar):
      - `pmi_conditional_value = (1 / val_pe_ttm) * max(Delta(MACRO_PMI, 3), 0)`
      - `shibor_value_yield = (1 / val_pe_ttm) / MACRO_SHIBOR_3M`
    These failed because MACRO_PMI and MACRO_SHIBOR_3M are identical for all stocks,
    so multiplying/dividing them with stock-level PE still produces near-constant values.
  • ✅ WORKING PATTERNS — macro used as interaction/condition, not direct multiplication:
      - `stock_growth = Delta(close,60) / close * (1.5 if MACRO_PMI > 50 else 0.5)`
      - `liquidity_adj = volume / MA(volume,20) / MACRO_SHIBOR_3M`
    Key insight: macro should MODIFY or CONDITION a stock-level signal, not BE the signal.
  • RULE OF THUMB: If you remove all stock-level terms from the formula and the remaining
    expression still produces a number, it's a cross-sectional constant → WILL BE REJECTED.

SUPPORTED FORMULA FUNCTIONS:
  Price: close_t, close_t-N, open_t, high_t, low_t, volume_t
  Aggregations: MA(col,window), Std(col,window), Delta(col,window)
  Fund flow: MF_MAIN_NET — main force net flow (亿元), MF_SMART — smart money ratio (-1 to 1)
  Holders: HOLDER_CHANGE — holder count change %, HOLDER_CONC — concentration score
  Macro: MACRO_PMI — PMI, MACRO_M2_YOY — M2 YoY%, MACRO_SHIBOR_3M — 3M Shibor

FORMAT each factor as JSON:
```json
{{
  "name": "short_name",
  "formula": "mathematical expression using above variables",
  "expected_sign": "positive or negative"
}}
```

ECONOMIC RATIONALE required. Don't just tweak existing factors — propose genuinely new patterns.
{importance_section}

Existing factors (DO NOT duplicate):
{', '.join(existing[:40])}

Generate {n} novel, non-redundant, economically-motivated factors."""


# ══════════════════════════════════════════════════════════
# 2. LLM 生成
# ══════════════════════════════════════════════════════════

def generate_via_llm(n: int, existing: List[str],
                     importance_hints: Optional[Dict[str, float]] = None) -> List[FactorCandidate]:
    """Call LLM to generate factor hypotheses."""
    try:
        from openai import OpenAI
    except ImportError:
        print("openai not installed. pip install openai")
        return []

    runtime = resolve_llm_use_case("factor_hypothesis")
    provider = runtime["provider"]
    model = runtime["model"]
    api_key = load_provider_api_key(provider)
    if not api_key:
        print("Missing LLM provider credential; configure the provider API key environment variable.")
        return []

    client_kwargs = {"api_key": api_key}
    if runtime.get("base_url"):
        client_kwargs["base_url"] = runtime["base_url"]
    client = OpenAI(**client_kwargs)
    prompt = build_hypothesis_prompt(n, existing, importance_hints)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
    )
    text = response.choices[0].message.content

    # 记录 provider response usage 到本地 LLM usage ledger。
    if hasattr(response, 'usage') and response.usage:
        _log_llm_usage("factor_hypothesis", response.usage, provider, model)

    return _parse_llm_candidates(text)

def _parse_llm_candidates(text: str) -> List[FactorCandidate]:
    """Parse factor candidates from fenced or plain JSON LLM output."""
    candidates = []
    blocks = re.findall(r'```(?:json)?\s*(.*?)\s*```', text or "", re.DOTALL)
    if not blocks:
        blocks = _extract_json_fragments(text or "")

    for block in blocks:
        try:
            items = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            formula = str(item.get("formula", "")).strip()
            if not name or not formula:
                continue
            candidates.append(FactorCandidate(
                name=name,
                formula=formula,
                expected_sign=str(item.get("expected_sign", "")).strip(),
                description=str(item.get("description", "")).strip(),
            ))

    return candidates

def _extract_json_fragments(text: str) -> List[str]:
    """Extract top-level JSON object/array fragments from free-form text."""
    fragments = []
    stack = []
    start = None
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch in "[{":
            if not stack:
                start = i
            stack.append(ch)
            continue
        if ch not in "]}":
            continue
        if not stack:
            continue
        opener = stack.pop()
        if (opener, ch) not in {("[", "]"), ("{", "}")}:
            stack.clear()
            start = None
            continue
        if not stack and start is not None:
            fragments.append(text[start : i + 1])
            start = None
    return fragments
