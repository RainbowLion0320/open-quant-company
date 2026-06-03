"""Factor hypothesis candidate models and DSL conversion."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

@dataclass
class FactorCandidate:
    name: str
    formula: str = ""
    description: str = ""
    expected_sign: str = ""
    ic: float = 0.0
    icir: float = 0.0
    ic_rolling: List[float] = field(default_factory=list)
    ic_std: float = 0.0
    oos_ic: float = 0.0
    passed_oos: bool = False
    round_num: int = 0


# ══════════════════════════════════════════════════════════
# 3. LLM 生成
# ══════════════════════════════════════════════════════════

def _formula_to_dsl(formula: str, name: str) -> str:
    """
    Convert LLM formula to Factor DSL expression.
    Simplified mapping for common patterns.
    """
    # Common replacements
    f = formula
    f = f.replace("close_t", "Ref('close')")
    f = f.replace("open_t", "Ref('open')")
    f = f.replace("high_t", "Ref('high')")
    f = f.replace("low_t", "Ref('low')")
    f = f.replace("volume_t", "Ref('volume')")

    # MA(col, N) → MA("col", N)
    f = re.sub(r'MA\((\w+),\s*(\d+)\)', r'MA("\1", \2)', f)

    # Std(col, N) → Std("col", N)
    f = re.sub(r'Std\((\w+),\s*(\d+)\)', r'Std("\1", \2)', f)

    # Delta(col, N) → Delta(Ref("col"), N)
    f = re.sub(r'Delta\((\w+),\s*(\d+)\)', r'Delta(Ref("\1"), \2)', f)

    # close_t-N → Ref("close", -N)
    f = re.sub(r'(\w+)_t-(\d+)', r'Ref("\1", -\2)', f)

    # Safety: wrap division denominator
    return f


# ══════════════════════════════════════════════════════════
# 7. 主循环 — 多轮迭代
# ══════════════════════════════════════════════════════════
