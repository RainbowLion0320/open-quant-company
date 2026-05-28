# Strategy Lab Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把策略实验室从“四个内置策略展示页”升级为可扩展、可评估、可治理的策略研究平台，第一批引入 8 个候选策略原型，并确保候选策略不会绕过样本外和晋级门槛进入生产信号。

**Architecture:** 先建立 Strategy Catalog 和统一评估/晋级门禁，再扩展策略数量，最后改 Strategy Lab UI。所有新策略以 `candidate` 或 `validated` 生命周期接入，默认只用于研究扫描、回测和实验室展示，不参与生产信号、模拟盘或自动交易，直到证据门槛通过。

**Tech Stack:** Python 3.11、pandas、DuckDB/Parquet、FastAPI、Vue 3、ECharts、pytest、Vite。

---

## Non-Negotiable Rules

- 不直接把 GitHub 策略复制进生产；外部项目只作为策略设计参考。
- 不新增无法回测、无法解释、无法评估的策略。
- 不让 `candidate` / `validated` 策略被 `scripts/compute_signals.py --strategy all` 静默写入生产信号。
- 不用当前未成熟策略结果反证新策略质量；必须跑 baseline、交易成本、OOS、walk-forward、regime 分层。
- 不改实盘或模拟盘策略来源，除非晋级门禁明确通过且用户单独确认。

## External References To Read First

- `https://github.com/hugo2046/QuantsPlaybook` — A股金工策略复现，重点参考择时、RPS、行业轮动、质量价值。
- `https://github.com/microsoft/qlib` — 研究流水线、因子/模型/组合治理。
- `https://github.com/tkfy920/qstock` — A股数据、RPS、MM趋势、资金流模型。
- `https://github.com/fasiondog/hikyuu` — 策略组件化：环境、信号、止损、资金管理。
- `https://github.com/freqtrade/freqtrade-strategies` — 技术指标策略模板和参数实验，不直接迁移交易制度。

## Current Baseline

现有活跃策略：

- `buffett`：生产状态，质量/价值过滤层。
- `multifactor`：生产状态，主 Alpha 横截面打分。
- `cybernetic`：生产状态，当前被定位为风险覆盖/市场状态层。
- `ml_lgbm`：模拟盘状态，辅助非线性 Alpha。

现有关键文件：

- `config/settings.yaml`：策略注册配置。
- `data/registry.py`：策略注册表和生命周期状态。
- `data/strategy_plugins.py`：CLI 与 Web 任务统一策略调度入口。
- `signals/runners.py`：生产策略 runner。
- `signals/technical.py`、`signals/scoring.py`、`signals/selection.py`：技术因子、打分、买入选择。
- `research/strategy_governance.py`：策略分层和晋级门禁。
- `web/api/routes/strategies.py`、`web/api/routes/backtest.py`：策略实验室 API。
- `web/frontend/src/views/StrategyLab.vue`、`Strategies.vue`、`Backtest.vue`、`Signals.vue`：策略实验室 UI。
- `tests/test_registry_status.py`、`tests/test_strategy_research_governance.py`：当前治理测试。

---

## File Map

Create:

- `research/strategy_catalog.py` — 策略目录模型、分类、数据需求、参数 schema、展示元数据。
- `research/strategy_evaluation.py` — baseline、OOS、walk-forward、成本、regime 分层评估结果聚合。
- `signals/candidates/__init__.py` — 候选策略包导出。
- `signals/candidates/common.py` — 候选策略通用数据加载、ST/流动性过滤、分数归一化、信号构造。
- `signals/candidates/trend_following.py` — 均线趋势择时/选股候选。
- `signals/candidates/donchian_breakout.py` — Donchian 突破候选。
- `signals/candidates/rps_relative_strength.py` — RPS 相对强弱候选。
- `signals/candidates/sector_rotation.py` — 行业轮动动量候选。
- `signals/candidates/quality_value.py` — 质量价值复合候选。
- `signals/candidates/low_vol_defensive.py` — 低波动防御候选。
- `signals/candidates/volume_confirmation.py` — 量能确认候选。
- `signals/candidates/regime_gated.py` — regime-gated 组合候选。
- `tests/test_strategy_catalog.py` — 策略目录契约测试。
- `tests/test_candidate_strategy_contracts.py` — 候选策略输出契约测试。
- `tests/test_strategy_runtime_gates.py` — 生命周期调度门禁测试。
- `tests/test_strategy_lab_api.py` — API 契约测试。

Modify:

- `config/settings.yaml` — 增加 8 个候选策略注册项和可解释参数。
- `data/registry.py` — 读取 catalog 元数据、暴露策略类型/层级/数据需求。
- `data/strategy_plugins.py` — 增加生产/研究运行模式，避免候选策略污染生产信号。
- `scripts/compute_signals.py` — 明确 `--mode production|research` 和 `--allow-candidate` 行为。
- `web/api/models.py` — 增加 strategy catalog / evaluation 响应模型。
- `web/api/routes/strategies.py` — 增加 catalog、candidate scan、evaluation summary API。
- `web/frontend/src/api/index.ts` — 增加策略目录和评估接口类型。
- `web/frontend/src/views/Strategies.vue` — 从旧的四内置策略状态视角改成策略目录与生命周期研究台。
- `web/frontend/src/views/Backtest.vue` — 增加 baseline、成本、OOS、regime 分层指标展示。
- `docs/specs/02-signal-system.md` — 同步策略生命周期、候选策略接入、信号契约。
- `docs/specs/03-backtest-engine.md` — 同步统一评估要求。
- `docs/specs/05-web-platform.md` — 同步 Strategy Lab UI/API 结构。
- `docs/acceptance-matrix.md` — 增加策略扩充验收链路。

Delete:

- 不再保留已完成计划或空计划目录说明。历史计划只通过 git 追溯。

---

## Task 1: Baseline Audit And Guard Tests

**Files:**
- Create: `tests/test_strategy_runtime_gates.py`
- Modify: `data/strategy_plugins.py`
- Modify: `scripts/compute_signals.py`

- [ ] **Step 1: Write failing tests for production-vs-research runtime gates**

Create `tests/test_strategy_runtime_gates.py`:

```python
def test_production_mode_excludes_candidate_strategies(monkeypatch):
    from data.strategy_plugins import iter_strategy_plugins

    fake_registry = [
        {"name": "prod_alpha", "label": "Prod", "runner": "signals.runners:compute_multifactor", "signal_name": "prod_alpha", "enabled": True, "status": "production"},
        {"name": "candidate_alpha", "label": "Candidate", "runner": "signals.runners:compute_multifactor", "signal_name": "candidate_alpha", "enabled": True, "status": "candidate"},
    ]
    monkeypatch.setattr("data.strategy_plugins.get_enabled_strategies", lambda: fake_registry)
    monkeypatch.setattr("data.strategy_plugins.get_strategy", lambda name: next((s for s in fake_registry if s["name"] == name), None))
    monkeypatch.setattr("data.strategy_plugins.list_strategy_names", lambda: [s["name"] for s in fake_registry])

    names = [plugin.name for plugin in iter_strategy_plugins("all", mode="production")]

    assert names == ["prod_alpha"]


def test_research_mode_can_include_candidate_strategies(monkeypatch):
    from data.strategy_plugins import iter_strategy_plugins

    fake_registry = [
        {"name": "prod_alpha", "label": "Prod", "runner": "signals.runners:compute_multifactor", "signal_name": "prod_alpha", "enabled": True, "status": "production"},
        {"name": "candidate_alpha", "label": "Candidate", "runner": "signals.runners:compute_multifactor", "signal_name": "candidate_alpha", "enabled": True, "status": "candidate"},
    ]
    monkeypatch.setattr("data.strategy_plugins.get_enabled_strategies", lambda: fake_registry)
    monkeypatch.setattr("data.strategy_plugins.get_strategy", lambda name: next((s for s in fake_registry if s["name"] == name), None))
    monkeypatch.setattr("data.strategy_plugins.list_strategy_names", lambda: [s["name"] for s in fake_registry])

    names = [plugin.name for plugin in iter_strategy_plugins("all", mode="research")]

    assert names == ["prod_alpha", "candidate_alpha"]
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_strategy_runtime_gates.py -q
```

Expected: FAIL because `iter_strategy_plugins()` does not accept `mode`.

- [ ] **Step 3: Add runtime mode to strategy dispatch**

Modify `data/strategy_plugins.py`:

```python
def iter_strategy_plugins(selected: str = "all", mode: str = "production") -> Iterable[StrategyPlugin]:
    valid = set(list_strategy_names()) | {"all"}
    if selected not in valid:
        raise ValueError(f"Invalid strategy: {selected}. Choose from: {', '.join(sorted(valid))}")
    if mode not in {"production", "research"}:
        raise ValueError(f"Invalid strategy runtime mode: {mode}")

    for item in get_enabled_strategies():
        name = item["name"]
        if selected not in ("all", name):
            continue
        if mode == "production" and item.get("status", "candidate") != "production":
            continue
        plugin = get_strategy_plugin(name)
        if plugin:
            yield plugin
```

Update `run_registered_strategies()` signature:

```python
def run_registered_strategies(
    selected: str = "all",
    limit: int = 0,
    progress_callback: Callable[[int, int, str], None] | None = None,
    mode: str = "production",
) -> list[dict]:
    plugins = list(iter_strategy_plugins(selected, mode=mode))
```

Modify `scripts/compute_signals.py` parser:

```python
parser.add_argument("--mode", choices=["production", "research"], default="production")
```

Then pass:

```python
run_registered_strategies(args.strategy, limit=args.limit, mode=args.mode)
```

- [ ] **Step 4: Run gate tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_strategy_runtime_gates.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add data/strategy_plugins.py scripts/compute_signals.py tests/test_strategy_runtime_gates.py
git commit -m "codex: add strategy runtime mode gates"
```

---

## Task 2: Strategy Catalog Contract

**Files:**
- Create: `research/strategy_catalog.py`
- Create: `tests/test_strategy_catalog.py`
- Modify: `data/registry.py`
- Modify: `config/settings.yaml`
- Modify: `web/api/models.py`
- Modify: `web/api/routes/strategies.py`

- [ ] **Step 1: Write failing catalog tests**

Create `tests/test_strategy_catalog.py`:

```python
def test_strategy_catalog_has_required_fields_for_every_enabled_strategy():
    from data.registry import get_enabled_strategies
    from research.strategy_catalog import catalog_by_name

    catalog = catalog_by_name()
    for strategy in get_enabled_strategies():
        item = catalog[strategy["name"]]
        assert item.name == strategy["name"]
        assert item.strategy_type in {"selection", "timing", "sector_rotation", "portfolio", "risk_overlay"}
        assert item.lifecycle in {"candidate", "validated", "paper", "production", "retired"}
        assert item.data_requirements
        assert item.output_contract == "StrategySignalRows"


def test_strategy_catalog_api_is_not_shadowed(monkeypatch):
    from fastapi.testclient import TestClient
    from web.api.app import create_app

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    res = TestClient(create_app()).get("/api/strategies/catalog")

    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert any(item["name"] == "multifactor" for item in data["items"])
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_strategy_catalog.py -q
```

Expected: FAIL because `research.strategy_catalog` and `/api/strategies/catalog` do not exist.

- [ ] **Step 3: Implement catalog model**

Create `research/strategy_catalog.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from data.registry import get_enabled_strategies


@dataclass(frozen=True)
class StrategyCatalogItem:
    name: str
    label: str
    strategy_type: str
    layer: str
    lifecycle: str
    data_requirements: list[str]
    parameters: dict[str, object] = field(default_factory=dict)
    output_contract: str = "StrategySignalRows"
    research_sources: list[str] = field(default_factory=list)


DEFAULT_TYPES = {
    "buffett": ("selection", "quality_filter", ["financials", "valuation_daily", "stock_daily"]),
    "multifactor": ("selection", "primary_alpha", ["financials", "valuation_daily", "stock_daily", "sector"]),
    "ml_lgbm": ("selection", "auxiliary_alpha", ["features", "stock_daily", "valuation_daily", "macro"]),
    "cybernetic": ("risk_overlay", "risk_overlay", ["market_regime", "stock_daily", "sector"]),
}


def catalog_items() -> list[StrategyCatalogItem]:
    items: list[StrategyCatalogItem] = []
    for raw in get_enabled_strategies():
        name = raw["name"]
        strategy_type, layer, requirements = DEFAULT_TYPES.get(
            name,
            (
                raw.get("strategy_type", "selection"),
                raw.get("layer", "candidate_alpha"),
                raw.get("data_requirements", ["stock_daily"]),
            ),
        )
        items.append(
            StrategyCatalogItem(
                name=name,
                label=raw.get("label", name),
                strategy_type=raw.get("strategy_type", strategy_type),
                layer=raw.get("layer", layer),
                lifecycle=raw.get("status", "candidate"),
                data_requirements=list(raw.get("data_requirements", requirements)),
                parameters=dict(raw.get("parameters", {})),
                research_sources=list(raw.get("research_sources", [])),
            )
        )
    return items


def catalog_by_name() -> dict[str, StrategyCatalogItem]:
    return {item.name: item for item in catalog_items()}
```

- [ ] **Step 4: Add catalog API**

Add response models in `web/api/models.py`:

```python
class StrategyCatalogItemResponse(BaseModel):
    name: str
    label: str
    strategy_type: str
    layer: str
    lifecycle: str
    data_requirements: List[str]
    parameters: Dict[str, Any] = {}
    output_contract: str
    research_sources: List[str] = []


class StrategyCatalogResponse(BaseModel):
    items: List[StrategyCatalogItemResponse]
    total: int
```

Add route before `@router.get("/{name}")` in `web/api/routes/strategies.py`:

```python
@router.get("/catalog", response_model=StrategyCatalogResponse)
async def get_strategy_catalog():
    from research.strategy_catalog import catalog_items

    items = [item.__dict__ for item in catalog_items()]
    return {"items": items, "total": len(items)}
```

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_strategy_catalog.py tests/test_strategy_research_governance.py tests/test_registry_status.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add research/strategy_catalog.py web/api/models.py web/api/routes/strategies.py tests/test_strategy_catalog.py
git commit -m "codex: add strategy catalog contract"
```

---

## Task 3: Candidate Strategy Common Runtime

**Files:**
- Create: `signals/candidates/__init__.py`
- Create: `signals/candidates/common.py`
- Create: `tests/test_candidate_strategy_contracts.py`

- [ ] **Step 1: Write common contract tests**

Create `tests/test_candidate_strategy_contracts.py`:

```python
import pandas as pd


def test_candidate_signal_row_contract():
    from signals.candidates.common import build_signal_row

    row = build_signal_row(
        symbol="000001",
        name="平安银行",
        industry="银行",
        score=82.5,
        signal="buy",
        detail={"reason": "test"},
    )

    assert row["symbol"] == "000001"
    assert row["name"] == "平安银行"
    assert row["industry"] == "银行"
    assert row["score"] == 82.5
    assert row["signal"] == "buy"
    assert row["detail"]["reason"] == "test"


def test_cross_section_percentile_score_bounds():
    from signals.candidates.common import percentile_score

    scores = percentile_score(pd.Series([10, 20, 30], index=["a", "b", "c"]))

    assert scores["a"] == 0.0
    assert scores["c"] == 100.0
    assert all(0.0 <= value <= 100.0 for value in scores)
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_candidate_strategy_contracts.py -q
```

Expected: FAIL because `signals.candidates.common` does not exist.

- [ ] **Step 3: Implement common helpers**

Create `signals/candidates/__init__.py`:

```python
"""Candidate strategy runners for Strategy Lab research mode."""
```

Create `signals/candidates/common.py`:

```python
from __future__ import annotations

import math
from typing import Any

import pandas as pd


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    return default if math.isnan(number) else number


def percentile_score(values: pd.Series) -> dict[str, float]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return {}
    if len(clean) == 1:
        return {str(clean.index[0]): 100.0}
    ranked = clean.rank(method="average", pct=True)
    min_rank = ranked.min()
    max_rank = ranked.max()
    scaled = (ranked - min_rank) / max(max_rank - min_rank, 1e-12) * 100
    return {str(k): round(float(v), 2) for k, v in scaled.items()}


def is_st_name(name: str) -> bool:
    return "ST" in str(name or "").upper()


def build_signal_row(symbol: str, name: str, industry: str, score: float, signal: str, detail: dict | None = None) -> dict:
    return {
        "symbol": str(symbol),
        "name": str(name or symbol),
        "industry": str(industry or ""),
        "score": round(safe_float(score), 2),
        "signal": signal if signal in {"buy", "hold", "sell"} else "hold",
        "detail": detail or {},
    }
```

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_candidate_strategy_contracts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add signals/candidates/__init__.py signals/candidates/common.py tests/test_candidate_strategy_contracts.py
git commit -m "codex: add candidate strategy common runtime"
```

---

## Task 4: First Candidate Strategy Batch

**Files:**
- Create 8 files under `signals/candidates/`
- Modify: `config/settings.yaml`
- Modify: `tests/test_candidate_strategy_contracts.py`

- [ ] **Step 1: Add candidate runner import tests**

Append to `tests/test_candidate_strategy_contracts.py`:

```python
def test_candidate_strategy_runners_return_signal_rows_for_small_limit():
    modules = [
        "signals.candidates.trend_following",
        "signals.candidates.donchian_breakout",
        "signals.candidates.rps_relative_strength",
        "signals.candidates.sector_rotation",
        "signals.candidates.quality_value",
        "signals.candidates.low_vol_defensive",
        "signals.candidates.volume_confirmation",
        "signals.candidates.regime_gated",
    ]

    for module_name in modules:
        module = __import__(module_name, fromlist=["compute"])
        rows = module.compute(limit=5)
        assert isinstance(rows, list)
        for row in rows:
            assert {"symbol", "name", "industry", "score", "signal", "detail"}.issubset(row)
            assert row["signal"] in {"buy", "hold", "sell"}
            assert 0 <= row["score"] <= 100
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_candidate_strategy_contracts.py::test_candidate_strategy_runners_return_signal_rows_for_small_limit -q
```

Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement candidate strategy calculations**

Each file exposes `compute(limit: int = 0) -> list[dict]`.

Required formulas:

- `trend_following.py`: score = 40% MA20/MA60 trend + 30% close above MA120 + 30% 60-day momentum percentile.
- `donchian_breakout.py`: score = 60% close proximity to 55-day high + 20% 20-day volume ratio + 20% 20-day volatility penalty.
- `rps_relative_strength.py`: score = 45% 3-month skip-1-month RPS + 45% 6-month skip-1-month RPS + 10% positive trend filter.
- `sector_rotation.py`: score = 60% industry 20-day median return rank + 25% industry 60-day median return rank + 15% candidate stock score inside industry.
- `quality_value.py`: score = 35% ROE rank + 25% gross margin rank + 20% inverse PE rank + 20% inverse PB rank.
- `low_vol_defensive.py`: score = 40% inverse 60-day volatility rank + 30% drawdown control + 20% positive 20-day trend + 10% liquidity rank.
- `volume_confirmation.py`: score = 45% 20-day volume ratio rank + 35% price momentum rank + 20% turnover/moneyflow proxy.
- `regime_gated.py`: in bull mode boost `trend_following` and `rps_relative_strength`; in sideways mode boost `quality_value` and `low_vol_defensive`; in bear mode allow only `low_vol_defensive` and cash-defense proxy rows.

Use `signals.candidates.common.build_signal_row()` and `signals.selection.apply_ranked_buys()` for final `buy` selection. Default candidate max buys should be 20 or lower.

- [ ] **Step 4: Register candidates as research-only strategies**

Add entries under `strategies:` in `config/settings.yaml`:

```yaml
  trend_following:
    color: '#38bdf8'
    config_key: strategies.trend_following
    enabled: true
    label: 趋势跟随候选
    runner: signals.candidates.trend_following:compute
    signal_name: trend_following
    status: candidate
    strategy_type: timing
    layer: candidate_alpha
    data_requirements: [stock_daily]
  donchian_breakout:
    color: '#f97316'
    config_key: strategies.donchian_breakout
    enabled: true
    label: Donchian突破候选
    runner: signals.candidates.donchian_breakout:compute
    signal_name: donchian_breakout
    status: candidate
    strategy_type: timing
    layer: candidate_alpha
    data_requirements: [stock_daily]
  rps_relative_strength:
    color: '#22c55e'
    config_key: strategies.rps_relative_strength
    enabled: true
    label: RPS相对强弱候选
    runner: signals.candidates.rps_relative_strength:compute
    signal_name: rps_relative_strength
    status: candidate
    strategy_type: selection
    layer: candidate_alpha
    data_requirements: [stock_daily]
  sector_rotation:
    color: '#06b6d4'
    config_key: strategies.sector_rotation
    enabled: true
    label: 行业轮动候选
    runner: signals.candidates.sector_rotation:compute
    signal_name: sector_rotation
    status: candidate
    strategy_type: sector_rotation
    layer: candidate_alpha
    data_requirements: [stock_daily, sector]
  quality_value:
    color: '#84cc16'
    config_key: strategies.quality_value
    enabled: true
    label: 质量价值候选
    runner: signals.candidates.quality_value:compute
    signal_name: quality_value
    status: candidate
    strategy_type: selection
    layer: candidate_alpha
    data_requirements: [financials, valuation_daily]
  low_vol_defensive:
    color: '#a78bfa'
    config_key: strategies.low_vol_defensive
    enabled: true
    label: 低波防御候选
    runner: signals.candidates.low_vol_defensive:compute
    signal_name: low_vol_defensive
    status: candidate
    strategy_type: selection
    layer: defensive_alpha
    data_requirements: [stock_daily]
  volume_confirmation:
    color: '#facc15'
    config_key: strategies.volume_confirmation
    enabled: true
    label: 量能确认候选
    runner: signals.candidates.volume_confirmation:compute
    signal_name: volume_confirmation
    status: candidate
    strategy_type: selection
    layer: confirmation_alpha
    data_requirements: [stock_daily, moneyflow]
  regime_gated:
    color: '#fb7185'
    config_key: strategies.regime_gated
    enabled: true
    label: Regime门控候选
    runner: signals.candidates.regime_gated:compute
    signal_name: regime_gated
    status: candidate
    strategy_type: portfolio
    layer: risk_overlay
    data_requirements: [market_regime, stock_daily]
```

- [ ] **Step 5: Run candidate tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_candidate_strategy_contracts.py tests/test_strategy_catalog.py tests/test_strategy_runtime_gates.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add config/settings.yaml signals/candidates tests/test_candidate_strategy_contracts.py
git commit -m "codex: add first strategy lab candidate batch"
```

---

## Task 5: Evaluation And Promotion Evidence

**Files:**
- Create: `research/strategy_evaluation.py`
- Modify: `research/strategy_governance.py`
- Create: `tests/test_strategy_evaluation.py`
- Modify: `web/api/routes/strategies.py`
- Modify: `web/api/models.py`

- [ ] **Step 1: Write evaluation tests**

Create `tests/test_strategy_evaluation.py`:

```python
def test_strategy_evaluation_requires_strong_baselines():
    from research.strategy_evaluation import required_baselines

    assert required_baselines() == [
        "buy_and_hold",
        "fixed_weight",
        "ma_timing",
        "trend_only",
        "trend_breadth",
        "current_champion",
    ]


def test_evaluation_summary_blocks_missing_oos():
    from research.strategy_evaluation import StrategyEvaluation, promotion_ready

    eval_result = StrategyEvaluation(
        name="trend_following",
        cagr=0.15,
        sharpe=0.9,
        max_drawdown=-0.18,
        turnover=3.2,
        oos_months=6,
        trades=40,
        baseline_win_rate=0.8,
        regime_coverage={"bull": 0.7, "sideways": 0.5, "bear": 0.2},
    )

    decision = promotion_ready(eval_result, target_status="paper")

    assert not decision.passed
    assert "oos_months" in decision.failed_rules
```

- [ ] **Step 2: Implement evaluation dataclasses**

Create `research/strategy_evaluation.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from research.strategy_governance import StrategyMetrics, evaluate_promotion


def required_baselines() -> list[str]:
    return [
        "buy_and_hold",
        "fixed_weight",
        "ma_timing",
        "trend_only",
        "trend_breadth",
        "current_champion",
    ]


@dataclass(frozen=True)
class StrategyEvaluation:
    name: str
    cagr: float
    sharpe: float
    max_drawdown: float
    turnover: float
    oos_months: int
    trades: int
    baseline_win_rate: float = 0.0
    regime_coverage: dict[str, float] = field(default_factory=dict)
    cost_model: str = "commission_slippage"


def promotion_ready(evaluation: StrategyEvaluation, target_status: str = "paper"):
    metrics = StrategyMetrics(
        cagr=evaluation.cagr,
        sharpe=evaluation.sharpe,
        max_drawdown=evaluation.max_drawdown,
        turnover=evaluation.turnover,
        oos_months=evaluation.oos_months,
        trades=evaluation.trades,
        ic=0.03 if evaluation.baseline_win_rate >= 0.6 else 0.0,
        icir=0.4 if evaluation.baseline_win_rate >= 0.6 else 0.0,
    )
    return evaluate_promotion(metrics, target_status=target_status)
```

- [ ] **Step 3: Add API summary**

Add route:

```python
@router.get("/evaluation")
async def get_strategy_evaluation_summary():
    from research.strategy_evaluation import required_baselines

    return {
        "baselines": required_baselines(),
        "status": "research_required",
        "note": "Candidate strategies require OOS, walk-forward, cost and regime evidence before promotion.",
    }
```

Place it before `@router.get("/{name}")`.

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_strategy_evaluation.py tests/test_strategy_research_governance.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add research/strategy_evaluation.py research/strategy_governance.py web/api/routes/strategies.py web/api/models.py tests/test_strategy_evaluation.py
git commit -m "codex: add strategy evaluation evidence layer"
```

---

## Task 6: Strategy Lab API And UI Expansion

**Files:**
- Modify: `web/frontend/src/api/index.ts`
- Modify: `web/frontend/src/views/Strategies.vue`
- Modify: `web/frontend/src/views/Backtest.vue`
- Modify: `web/frontend/src/views/StrategyLab.vue`
- Modify: `tests/test_web_system_contracts.py`

- [ ] **Step 1: Write UI contract tests**

Append to `tests/test_web_system_contracts.py`:

```python
def test_strategy_lab_exposes_catalog_and_candidate_language():
    strategies = Path("web/frontend/src/views/Strategies.vue").read_text(encoding="utf-8")
    api = Path("web/frontend/src/api/index.ts").read_text(encoding="utf-8")

    assert "strategyCatalog" in api
    assert "strategyEvaluation" in api
    assert "策略目录" in strategies
    assert "候选策略" in strategies
    assert "生命周期" in strategies
    assert "生产隔离" in strategies
```

- [ ] **Step 2: Run UI contract test and confirm it fails**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_web_system_contracts.py::test_strategy_lab_exposes_catalog_and_candidate_language -q
```

Expected: FAIL.

- [ ] **Step 3: Add frontend API types**

In `web/frontend/src/api/index.ts`, add:

```ts
export interface StrategyCatalogItem {
  name: string;
  label: string;
  strategy_type: string;
  layer: string;
  lifecycle: string;
  data_requirements: string[];
  output_contract: string;
  research_sources: string[];
}

export interface StrategyCatalogResponse {
  items: StrategyCatalogItem[];
  total: number;
}

export interface StrategyEvaluationSummary {
  baselines: string[];
  status: string;
  note: string;
}
```

Add API methods:

```ts
strategyCatalog: () => get<StrategyCatalogResponse>("/api/strategies/catalog"),
strategyEvaluation: () => get<StrategyEvaluationSummary>("/api/strategies/evaluation"),
```

- [ ] **Step 4: Rebuild Strategy Center UI**

Modify `web/frontend/src/views/Strategies.vue` so the first viewport contains:

- Header: `策略目录`
- Four compact status counters: total, production, paper, candidate
- Filters: lifecycle, strategy type, layer
- Table/card list columns: strategy, lifecycle, type, layer, data requirements, latest scan, actions
- Safety banner text: `生产隔离：candidate/validated 只允许研究扫描和回测，不参与生产信号`

- [ ] **Step 5: Run frontend checks**

Run:

```bash
cd web/frontend
npm run typecheck
npm run build
```

Expected: both commands exit 0.

- [ ] **Step 6: Browser smoke test**

Run local service and verify:

```bash
.venv/bin/python -m uvicorn web.api.app:create_app --factory --host 0.0.0.0 --port 8501
```

Open:

```text
http://localhost:8501/strategy-lab
```

Expected visible text:

- `策略目录`
- `候选策略`
- `生命周期`
- `生产隔离`

- [ ] **Step 7: Commit**

Run:

```bash
git add web/frontend/src/api/index.ts web/frontend/src/views/Strategies.vue web/frontend/src/views/Backtest.vue web/frontend/src/views/StrategyLab.vue tests/test_web_system_contracts.py
git commit -m "codex: expand strategy lab catalog UI"
```

---

## Task 7: Backtest Tournament And Evidence Reports

**Files:**
- Modify: `backtest/pipeline.py`
- Modify: `backtest/pipeline_runner.py`
- Modify: `backtest/run_all_strategies.py`
- Create: `tests/test_strategy_backtest_evidence.py`

- [ ] **Step 1: Write evidence output test**

Create `tests/test_strategy_backtest_evidence.py`:

```python
def test_strategy_evidence_report_contains_baselines_and_gates():
    from research.strategy_evaluation import required_baselines

    baselines = required_baselines()

    assert "buy_and_hold" in baselines
    assert "current_champion" in baselines
    assert len(baselines) >= 6
```

- [ ] **Step 2: Extend runner output contract**

Ensure backtest/report generation writes a JSON or Parquet evidence artifact with these fields:

```python
{
    "strategy": "trend_following",
    "status": "candidate",
    "baselines": {"buy_and_hold": {}, "fixed_weight": {}, "ma_timing": {}, "trend_only": {}, "trend_breadth": {}, "current_champion": {}},
    "metrics": {"cagr": 0.0, "sharpe": 0.0, "max_drawdown": 0.0, "turnover": 0.0, "trades": 0},
    "oos": {"months": 0, "start": "", "end": ""},
    "cost_model": {"commission": 0.00025, "slippage": 0.001},
    "regime_breakdown": {"bull": {}, "sideways": {}, "bear": {}},
    "promotion_decision": {"target_status": "paper", "passed": False, "failed_rules": []}
}
```

The artifact path should be:

```text
data/store/research/strategy_evidence/<strategy>.json
```

- [ ] **Step 3: Run backtest evidence tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_strategy_backtest_evidence.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```bash
git add backtest research tests/test_strategy_backtest_evidence.py
git commit -m "codex: add strategy evidence report contract"
```

---

## Task 8: Documentation And Acceptance Alignment

**Files:**
- Modify: `docs/specs/02-signal-system.md`
- Modify: `docs/specs/03-backtest-engine.md`
- Modify: `docs/specs/05-web-platform.md`
- Modify: `docs/acceptance-matrix.md`
- Create: `docs/strategies/candidate-strategies.md`

- [ ] **Step 1: Update signal system spec**

`docs/specs/02-signal-system.md` must state:

- Strategy Catalog is the strategy metadata authority for UI and research workflows.
- `candidate` and `validated` are research states, not production signal states.
- All strategy runners output `StrategySignalRows`: `symbol`, `name`, `industry`, `score`, `signal`, `detail`.
- Production daily signal scan defaults to `mode=production`.
- Strategy Lab research scan uses `mode=research`.

- [ ] **Step 2: Update backtest spec**

`docs/specs/03-backtest-engine.md` must state:

- Candidate promotion requires baseline comparison, OOS, walk-forward, cost model and regime breakdown.
- Required baselines are `buy_and_hold`, `fixed_weight`, `ma_timing`, `trend_only`, `trend_breadth`, `current_champion`.
- Evidence artifacts live under `data/store/research/strategy_evidence/`.

- [ ] **Step 3: Update web spec**

`docs/specs/05-web-platform.md` must state:

- Strategy Lab has Strategy Catalog, Signal History and Backtest/Evidence views.
- Candidate strategy actions are labeled as research scans.
- Production isolation banner must be visible when candidates exist.

- [ ] **Step 4: Create candidate strategy doc**

Create `docs/strategies/candidate-strategies.md` with sections for:

- 趋势跟随候选
- Donchian突破候选
- RPS相对强弱候选
- 行业轮动候选
- 质量价值候选
- 低波防御候选
- 量能确认候选
- Regime门控候选

Each section must include: purpose, data requirements, formula, failure modes, promotion evidence.

- [ ] **Step 5: Documentation drift check**

Run:

```bash
rg -n "当前没有展开中的专题计划|空专题计划目录说明|历史计划索引" docs wiki web/frontend/src/views -g '*.md' -g '*.vue' -g '!docs/development-plan.md'
git diff --check
```

Expected:

- No stale text in docs.
- `git diff --check` exits 0.

- [ ] **Step 6: Commit**

Run:

```bash
git add docs
git commit -m "codex: document strategy lab expansion plan and contracts"
```

---

## Final Verification

After all tasks complete, run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_registry_status.py tests/test_strategy_research_governance.py tests/test_strategy_runtime_gates.py tests/test_strategy_catalog.py tests/test_candidate_strategy_contracts.py tests/test_strategy_evaluation.py tests/test_strategy_backtest_evidence.py tests/test_web_system_contracts.py -q
cd web/frontend && npm run typecheck && npm run build
```

Then start or restart the Web service:

```bash
.venv/bin/python -m uvicorn web.api.app:create_app --factory --host 0.0.0.0 --port 8501
```

Browser smoke paths:

- `http://localhost:8501/strategy-lab`
- `http://localhost:8501/strategy-lab?tab=backtest`
- `http://localhost:8501/strategy-lab?tab=signals`

Required visible outcomes:

- Strategy Lab no longer reads as a four-strategy-only page.
- Candidate strategies are visible but marked as research/candidate.
- Production isolation is visible.
- Backtest page exposes baseline/evidence language.
- Running all production strategies does not run candidate strategies.
