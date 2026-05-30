# System Gap Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining production-readiness gaps in Astrolabe Quant OS across data reliability, research governance, backtest evidence, multi-asset expansion, Web contracts, Pipeline transparency, and execution observability.

**Architecture:** Do not rewrite the system. Treat DataHub, Strategy Catalog, Hybrid Market Regime, `astroq` CLI, and the Web shell as stable anchors, then extend missing contract surfaces around them with small services, tests, and UI panels. Every new feature must be traceable through doc/spec/wiki/code and must have either an automated test or a precise manual acceptance command.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, pandas/Parquet/DataHub, pytest, Vue 3, TypeScript, Vite, ECharts, `astroq` CLI.

---

## Current Gap Inventory

The current system has broad feature coverage, but several modules are still not production-complete. The acceptance matrix marks 73/73 items as `OK`, while also listing 23 test or quality debts. Treat those debts as real work, not cosmetic documentation noise.

| Area | Current State | Missing Work | Priority |
|---|---|---|---|
| Documentation truth | `docs/DOCUMENTATION.md` defines clean doc roles; `docs/specs/06-multi-asset.md` still says Bond/Futures/Crypto are planned while code has Bond/Futures adapters and Crypto disabled | Align stale specs and make acceptance matrix distinguish feature availability from quality debt | P0 |
| Data pipeline | DataHub, registry, manifest, API safety valve exist | Automated tests for fetch fallback/backoff/throttle, cleaner rules, cron log rotation, and freshness gates are incomplete | P0 |
| Strategy research | Candidate strategies, catalog, governance, evidence report builders exist | Strategy Lab lacks evidence artifact drilldown and promotion workflow visibility; candidate strategies still need real OOS evidence runs | P0 |
| Backtest engine | Tournament, analytics, regime replay, and pipeline abstractions exist | Reproducibility regression, PIT lookahead test, pluggable pipeline test, and evidence baseline integration are incomplete | P0 |
| Multi-asset | Stock/ETF real adapters, Bond proxy, Futures real adapter, Crypto disabled adapter exist | Multi-asset data provenance is not visible enough in Web/API; tournament still relies on explicit fallback paths; Crypto has no optional real adapter path | P1 |
| Web platform | Main pages are feature-rich; `/pipeline` v1 shows Market Regime | WebSocket contract tests, response models on critical endpoints, browser smoke coverage, and Pipeline v2 for other key flows are missing | P1 |
| Execution layer | Paper broker, risk, persistence, exchange costs, cron scripts exist | End-to-end paper trading dry-run ledger, run audit surface, and freshness-blocking behavior are not fully tested | P1 |
| Agent control plane | `astroq` covers health/config/data/strategy/regime/backtest/docs/web | CLI does not yet expose every long-running workflow, evidence artifact readout, pipeline introspection, or execution dry-run as stable JSON | P2 |

## File Ownership Map

Use these file boundaries when implementing. Avoid spreading a single concern across unrelated modules.

| Concern | Primary Files | Test Files |
|---|---|---|
| Documentation governance | `docs/acceptance-matrix.md`, `docs/specs/*.md`, `wiki/reference/*.md`, `wiki/concepts/*.md` | `tests/test_documentation_contracts.py` if needed |
| Data reliability | `data/fetcher.py`, `data/cleaner.py`, `data/cron_logger.py`, `data/data_registry.py`, `data/datahub.py` | `tests/test_data_fetcher_resilience.py`, `tests/test_data_cleaner_contracts.py`, `tests/test_cron_logger_contracts.py` |
| Strategy evidence | `research/strategy_evaluation.py`, `web/api/routes/strategies.py`, `web/api/models.py`, `web/frontend/src/views/StrategyLab.vue`, `web/frontend/src/api/index.ts` | `tests/test_strategy_evaluation.py`, `tests/test_strategy_backtest_evidence.py`, `tests/test_web_system_contracts.py` |
| Backtest correctness | `backtest/run_all_strategies.py`, `backtest/pipeline.py`, `backtest/pipeline_runner.py`, `scripts/lookahead_check.py` | `tests/test_backtest_reproducibility.py`, `tests/test_backtest_pit_contracts.py`, `tests/test_backtest_pipeline_contracts.py` |
| Multi-asset | `data/assets/*.py`, `broker/allocator.py`, `broker/exchange.py`, `backtest/multi_asset_tournament.py`, `scripts/multi_asset_tournament.py` | `tests/test_asset_contracts.py`, `tests/test_multi_asset_tournament.py` |
| Web API contracts | `web/api/routes/*.py`, `web/api/models.py`, `web/api/errors.py`, `web/api/ws.py` | `tests/test_web_system_contracts.py`, `tests/test_pipeline_route_contracts.py`, `tests/test_websocket_contracts.py` |
| Web frontend | `web/frontend/src/views/*.vue`, `web/frontend/src/api/index.ts`, `web/frontend/src/router/index.ts`, `web/frontend/src/assets/*.css` | `npm run typecheck`, `npm run build`, browser smoke |
| CLI control plane | `astrolabe_cli/main.py`, `astrolabe_cli/commands/*.py` | `tests/test_cli_*.py` |

## Execution Rules

- [ ] Work in small commits. One workstream should usually be one commit.
- [ ] Do not delete generated historical data unless the task explicitly says to remove a tracked generated artifact.
- [ ] If a spec changes behavior, update `docs/acceptance-matrix.md` in the same commit.
- [ ] Use deterministic fixtures and monkeypatches for tests that describe network behavior. Do not require live AKShare, Tushare, CCXT, or browser sessions for CI-style tests.
- [ ] Before final handoff, run the verification suite in the final checklist and report any command that could not run.

---

## Phase 1: Documentation Truth And Acceptance Semantics

**Objective:** Make docs/spec/wiki accurately describe what exists and what is still quality debt.

**Files:**
- Modify: `docs/specs/06-multi-asset.md`
- Modify: `docs/acceptance-matrix.md`
- Modify: `docs/specs/05-web-platform.md`
- Modify: `wiki/reference/data-dimensions.md`
- Modify: `wiki/concepts/system-architecture.md`

- [ ] **Step 1: Confirm current multi-asset implementation from code**

Run:

```bash
PYTHONPATH=. .venv/bin/python - <<'PY'
from data.assets.stock import StockAsset
from data.assets.etf import ETFAsset
from data.assets.bond import BondAsset
from data.assets.futures import FuturesAsset
from data.assets.crypto import CryptoAsset

for cls in (StockAsset, ETFAsset, BondAsset, FuturesAsset, CryptoAsset):
    item = cls()
    print(cls.__name__, item.asset_type, item.DATA_SOURCE, len(item.universe()))
PY
```

Expected: each adapter imports successfully. Bond reports proxy provenance, Futures reports real provenance, and Crypto reports disabled or non-production provenance.

- [ ] **Step 2: Update `docs/specs/06-multi-asset.md` status table**

Replace the existing "已实现资产类型" table with:

```markdown
| 资产 | 类 | 数据源 | 状态 |
|------|-----|--------|------|
| Stock | `StockAsset` | AKShare 日线 + Tushare 财务补充 | production-ready adapter |
| ETF | `ETFAsset` | AKShare `fund_etf_hist_em`; tournament 可显式降级到指数代理 | production adapter with fallback marking |
| Bond | `BondAsset` | 国债收益率价格代理 + 可转债快照真实数据 | proxy/partial-real adapter |
| Futures | `FuturesAsset` | AKShare 主力连续合约行情 | real adapter, not yet deeply integrated into allocation research |
| Crypto | `CryptoAsset` | 默认禁用；未接入 CCXT 真实行情 | disabled adapter |
```

Also replace "Bond/Futures/Crypto 未实现" in section 8 with:

```markdown
- **Bond/Futures/Crypto 边界：** Bond 当前是国债收益率价格代理 + 可转债快照，Futures 有真实日线适配器但未形成完整研究/交易闭环，Crypto 默认禁用且未接入 CCXT。所有收益、回测和 Web 展示必须保留 `data_source` provenance。
```

- [ ] **Step 3: Update acceptance matrix semantics**

In `docs/acceptance-matrix.md`, keep the current PRD/spec mapping, but change the summary table from "有缺口" to "质量债". The summary should make this explicit:

```markdown
| 能力域 | 总条目 | 功能可验收 | 质量债条目 | 待补自动化测试 |
|--------|-------|------------|------------|----------------|
```

Rules:
- `功能可验收` means the feature has a usable code path.
- `质量债条目` counts rows whose "缺口" cell is not `—`.
- Do not write `有缺口 0` while rows still contain missing tests or evidence work.

- [ ] **Step 4: Align Web and architecture docs**

Update `docs/specs/05-web-platform.md` and `wiki/concepts/system-architecture.md` with two statements:

```markdown
- Pipeline 页面当前 v1 只覆盖 Market Regime。后续 Pipeline v2 应扩展到 Data Quality、Strategy Evidence、Portfolio/Execution 三条关键链路。
- Web API 的稳定契约以 Pydantic `response_model` 和前端 TypeScript 类型共同约束；新关键端点必须同时补齐后端模型、前端类型和合约测试。
```

- [ ] **Step 5: Verify docs**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main docs check --json
git diff --check
```

Expected: docs check returns JSON with `"ok": true`; `git diff --check` emits no whitespace errors.

---

## Phase 2: Data Reliability Contract Tests And Freshness Gates

**Objective:** Convert manual data reliability claims into automated tests and a reusable freshness gate.

**Files:**
- Create: `tests/test_data_fetcher_resilience.py`
- Create: `tests/test_data_cleaner_contracts.py`
- Create: `tests/test_cron_logger_contracts.py`
- Modify: `data/fetcher.py`
- Modify: `data/cleaner.py`
- Modify: `data/cron_logger.py`
- Modify: `data/data_registry.py`
- Modify: `astrolabe_cli/commands/data.py` or the current data CLI command file

- [ ] **Step 1: Add fetch retry/backoff tests**

Create tests that monkeypatch `time.sleep` and `random.uniform`, then wrap a local function with `retry_with_backoff(max_retries=2, base_delay=1.0, backoff_factor=2.0, jitter=False)`.

Acceptance:
- A function failing twice then succeeding is called three times.
- Sleep delays are `[1.0, 2.0]`.
- A function failing three times raises the final retryable error.

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_data_fetcher_resilience.py -q
```

- [ ] **Step 2: Add throttle test**

In the same test file, monkeypatch `data.fetcher.time.monotonic`, `data.fetcher.time.sleep`, and `data.fetcher.random.uniform`.

Acceptance:
- First `_throttle()` call does not sleep when `_last_request_time` is old.
- Second call sleeps for the remaining interval when elapsed time is below `MIN_INTERVAL`.
- Test resets `data.fetcher._last_request_time = 0.0` at start and end.

- [ ] **Step 3: Add cleaner rule contract tests**

Create `tests/test_data_cleaner_contracts.py` with deterministic OHLCV and factor frames.

Acceptance:
- `OHLCVIntegrityRule` swaps `high`/`low`, clamps `close`, removes non-positive `close`, and replaces non-positive `open` with `close`.
- `OutlierDetectionRule` caps non-limit extreme returns while preserving 10%, 20%, and 30% limit-like moves.
- `SuspendedDetectionRule` removes rows after `max_flat_days`.
- `MissingValueRule` forward-fills only within limit and removes rows still missing `close`.
- `FinancialValidationRule` caps financial columns inside configured ranges.
- `WinsorizeRule` caps numeric feature tails without altering date/symbol columns.

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_data_cleaner_contracts.py -q
```

- [ ] **Step 4: Add cron logger rotation tests**

Create `tests/test_cron_logger_contracts.py` and monkeypatch `data.cron_logger._LOG_DIR` to `tmp_path`.

Acceptance:
- `log_cron_success()` writes one JSONL row with `status="ok"`.
- `log_cron_error()` truncates `error` and `traceback` to documented limits.
- `_rotate_if_needed(path, max_lines=3)` keeps exactly the last three lines and preserves trailing newline.
- `cron_run()` logs error and re-raises the original exception.

- [ ] **Step 5: Add a reusable freshness gate**

Add a small helper close to the existing registry/health code:

```python
def freshness_gate(audit_rows: list[dict], *, required: list[str] | None = None) -> dict:
    required_keys = set(required or [])
    stale = []
    missing = []
    for row in audit_rows:
        key = str(row.get("key") or row.get("dimension") or "")
        status = str(row.get("status") or "").lower()
        if required_keys and key not in required_keys:
            continue
        if status == "missing":
            missing.append(key)
        elif status in {"stale", "error"}:
            stale.append(key)
    return {"ok": not stale and not missing, "stale": stale, "missing": missing}
```

Wire it into `astroq data status --json` as an additional stable field:

```json
{
  "freshness_gate": {
    "ok": true,
    "stale": [],
    "missing": []
  }
}
```

- [ ] **Step 6: Verify data reliability suite**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_data_fetcher_resilience.py tests/test_data_cleaner_contracts.py tests/test_cron_logger_contracts.py tests/test_datahub_contracts.py -q
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main data status --json
```

Expected: pytest passes; CLI JSON includes `freshness_gate`.

---

## Phase 3: Strategy Evidence Drilldown And Promotion Visibility

**Objective:** Make Strategy Lab show whether a candidate has real evidence, where the artifact is, and why it can or cannot be promoted.

**Files:**
- Modify: `research/strategy_evaluation.py`
- Modify: `web/api/models.py`
- Modify: `web/api/routes/strategies.py`
- Modify: `web/frontend/src/api/index.ts`
- Modify: `web/frontend/src/views/StrategyLab.vue`
- Modify: `docs/strategies/research-governance.md`
- Test: `tests/test_strategy_evaluation.py`
- Test: `tests/test_web_system_contracts.py`

- [ ] **Step 1: Add evidence artifact listing service**

Extend `research/strategy_evaluation.py` with functions that read `data/store/research/strategy_evidence/*.json` without creating files:

```python
def list_evidence_artifacts(root: str | Path = "data/store/research/strategy_evidence") -> list[dict]:
    ...

def load_evidence_artifact(strategy: str, root: str | Path = "data/store/research/strategy_evidence") -> dict:
    ...
```

Acceptance:
- Listing returns stable fields: `strategy`, `path`, `updated`, `exists`, `promotion_decision`, `oos_status`, `baseline_count`.
- Loading an absent strategy returns a structured "missing" payload, not a traceback.
- Loading invalid JSON returns `exists=true`, `parse_error`, and no process crash.

- [ ] **Step 2: Add API response models and routes**

Add Pydantic models in `web/api/models.py`:

```python
class StrategyEvidenceItem(BaseModel):
    strategy: str
    path: str
    updated: str | None = None
    exists: bool
    promotion_decision: str | None = None
    oos_status: str | None = None
    baseline_count: int = 0
    parse_error: str | None = None

class StrategyEvidenceListResponse(BaseModel):
    items: list[StrategyEvidenceItem]
    total: int

class StrategyEvidenceDetailResponse(BaseModel):
    strategy: str
    exists: bool
    path: str | None = None
    summary: dict = Field(default_factory=dict)
    artifact: dict = Field(default_factory=dict)
    parse_error: str | None = None
```

Add routes:

```python
@router.get("/evidence", response_model=StrategyEvidenceListResponse)
async def list_strategy_evidence():
    ...

@router.get("/evidence/{strategy}", response_model=StrategyEvidenceDetailResponse)
async def get_strategy_evidence(strategy: str):
    ...
```

- [ ] **Step 3: Add Strategy Lab evidence panel**

In `StrategyLab.vue`, add an evidence area under the strategy catalog:
- Show all strategies with status badges: `missing`, `available`, `parse_error`, `promotion_ready`, `blocked`.
- Selecting a row opens a detail panel with baselines, OOS, cost, regime breakdown, and promotion decision.
- Empty state says: `No evidence artifact generated yet. Run research backtest before promotion.`

Do not use large marketing cards. Keep the panel compact and aligned with the existing cyberpunk dashboard style.

- [ ] **Step 4: Verify strategy evidence**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_strategy_evaluation.py tests/test_strategy_backtest_evidence.py tests/test_web_system_contracts.py -q
cd web/frontend && npm run typecheck && npm run build
```

Expected: all commands pass. Web build must not introduce chunk warnings.

---

## Phase 4: Backtest Reproducibility, PIT Guard, And Pipeline Contracts

**Objective:** Make the backtest layer trustworthy enough to evaluate strategy and regime changes.

**Files:**
- Create: `tests/test_backtest_reproducibility.py`
- Create: `tests/test_backtest_pit_contracts.py`
- Create: `tests/test_backtest_pipeline_contracts.py`
- Modify: `backtest/run_all_strategies.py`
- Modify: `backtest/pipeline.py`
- Modify: `backtest/pipeline_runner.py`
- Modify: `scripts/lookahead_check.py`
- Modify: `docs/specs/03-backtest-engine.md`

- [ ] **Step 1: Add deterministic tournament regression**

Create a tiny fixture with fixed daily prices and fixed strategy signals. Run the same backtest twice in one test process.

Acceptance:
- Total return, max drawdown, trade count, and ranking order are byte-stable or rounded-stable.
- Test does not fetch network data.
- If production code uses current date, inject a fixed date in the test.

- [ ] **Step 2: Add PIT lookahead regression**

Build a fixture where a stock has a future price spike after the decision date.

Acceptance:
- Feature generation on date `T` cannot see price or financial fields from `T+1` or later.
- The strategy cannot buy solely because of a return that has not occurred yet.
- `scripts/lookahead_check.py` returns non-zero or structured failure when a deliberately contaminated feature is injected.

- [ ] **Step 3: Add pluggable pipeline contract**

Create a test pipeline with four fake stages:
- Data stage returns two symbols and deterministic prices.
- Alpha stage emits scores.
- Portfolio stage applies max single-name and total exposure caps.
- Execution stage records orders without mutating external state.

Acceptance:
- Stages run in order.
- Stage payloads use the shared pipeline types.
- Risk rejection is visible in output, not swallowed.

- [ ] **Step 4: Expose backtest quality through CLI**

Add or extend a JSON command:

```bash
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main backtest check --json
```

Expected JSON fields:

```json
{
  "ok": true,
  "reproducibility": {"ok": true},
  "pit": {"ok": true},
  "pipeline_contract": {"ok": true}
}
```

If adding a new CLI subcommand is too invasive, expose the same checks through an existing `backtest` command group and document the exact command in `wiki/reference/cli-control-plane.md`.

- [ ] **Step 5: Verify backtest trust suite**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_backtest_reproducibility.py tests/test_backtest_pit_contracts.py tests/test_backtest_pipeline_contracts.py tests/test_architecture_contracts.py -q
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main backtest run --strategy multifactor --dry-run --json
```

Expected: pytest passes; dry-run returns valid JSON.

---

## Phase 5: Multi-Asset Production Readiness

**Objective:** Make multi-asset support explicit, observable, and hard to misuse.

**Files:**
- Modify: `data/assets/base.py`
- Modify: `data/assets/bond.py`
- Modify: `data/assets/futures.py`
- Modify: `data/assets/crypto.py`
- Modify: `backtest/multi_asset_tournament.py`
- Modify: `scripts/multi_asset_tournament.py`
- Modify: `web/api/models.py`
- Create or modify: `web/api/routes/assets.py` if no existing asset overview route is suitable
- Modify: `web/api/app.py`
- Modify: `web/frontend/src/api/index.ts`
- Modify: `web/frontend/src/views/Portfolio.vue` or `web/frontend/src/views/DataHub.vue`
- Test: `tests/test_asset_contracts.py`
- Create: `tests/test_multi_asset_tournament.py`

- [ ] **Step 1: Standardize asset provenance**

Every adapter metadata payload should expose:

```python
{
    "asset_type": "stock",
    "data_source": "real",
    "data_source_detail": "AKShare stock_zh_a_hist + local cache",
    "tradable": True,
    "research_ready": True,
}
```

Acceptance:
- Stock and ETF are `tradable=True`.
- Bond is `tradable=True` only for instruments actually supported by the broker/exchange layer; treasury yield proxy is `research_ready=True`, `tradable=False`.
- Futures is `research_ready=True`; execution readiness must reflect actual broker support.
- Crypto is `research_ready=False`, `tradable=False` until CCXT is implemented and tested.

- [ ] **Step 2: Add multi-asset tournament tests**

Create `tests/test_multi_asset_tournament.py` with local fixtures.

Acceptance:
- Stock-only, ETF-only, and multi portfolios all produce result rows.
- Any generated fallback series includes `data_source` in the result.
- If ETF real data fixture exists, fallback is not used.
- If an asset is disabled in config, it is excluded from allocation and results.

- [ ] **Step 3: Add asset overview API**

Expose a compact API response for Web and agents:

```json
{
  "items": [
    {
      "asset_type": "etf",
      "label": "ETF",
      "enabled": true,
      "data_source": "real",
      "research_ready": true,
      "tradable": true,
      "universe_size": 6
    }
  ],
  "total": 5
}
```

Prefer `/api/assets/overview`. If the project already has a better route group, use that and document it.

- [ ] **Step 4: Add Web visibility**

Add a compact "Asset Coverage" section to `DataHub.vue` or the portfolio execution page:
- Asset type.
- Enabled/disabled.
- Data provenance.
- Research readiness.
- Trading readiness.
- Universe size.

The UI must not imply Crypto or treasury yield proxies are fully tradable.

- [ ] **Step 5: Verify multi-asset suite**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_asset_contracts.py tests/test_multi_asset_tournament.py -q
cd web/frontend && npm run typecheck && npm run build
```

---

## Phase 6: Web API Contracts, WebSocket Tests, And Browser Smoke

**Objective:** Reduce repeated UI regressions by making backend/frontend contracts explicit.

**Files:**
- Modify: `web/api/models.py`
- Modify: `web/api/routes/market.py`
- Modify: `web/api/routes/pipeline.py`
- Modify: `web/api/routes/sectors.py`
- Modify: `web/api/routes/system.py`
- Modify: `web/api/ws.py`
- Modify: `web/frontend/src/api/index.ts`
- Create: `tests/test_websocket_contracts.py`
- Modify: `tests/test_market_route_contracts.py`
- Modify: `tests/test_pipeline_route_contracts.py`
- Modify: `tests/test_web_system_contracts.py`

- [ ] **Step 1: Add response models for critical successful endpoints**

Add or expand Pydantic models for:
- `GET /api/market/regime`
- `GET /api/market/overview` or the current market overview endpoint
- `GET /api/pipeline/market-regime`
- `GET /api/sectors/overview`
- `GET /api/system/health`
- `GET /api/system/cron-log`

Acceptance:
- Route decorators include `response_model=...`.
- Tests call each endpoint and validate stable keys.
- Frontend TypeScript interfaces match the Pydantic field names.

- [ ] **Step 2: Add WebSocket contract test**

Create a test that uses FastAPI `TestClient.websocket_connect()` against `/api/strategies/ws/{job_id}`.

Acceptance:
- Unknown job returns a structured status message or closes predictably.
- Known job sends progress fields: `job_id`, `status`, `progress`, `message`.
- The test has a bounded timeout and cannot hang.

- [ ] **Step 3: Add browser smoke script**

Add a lightweight smoke command to project docs and, if practical, a script:

```bash
cd web/frontend && npm run build
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main web serve --host 127.0.0.1 --port 8501
```

Manual browser smoke pages:
- `/market`
- `/research?tab=sectors`
- `/strategy-lab?tab=strategies`
- `/pipeline`
- `/system`

Acceptance:
- No blank pages.
- No obvious text overlap at desktop width.
- `/pipeline` node click still opens details.

- [ ] **Step 4: Verify Web contracts**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_market_route_contracts.py tests/test_pipeline_route_contracts.py tests/test_web_system_contracts.py tests/test_websocket_contracts.py -q
cd web/frontend && npm run typecheck && npm run build
```

---

## Phase 7: Pipeline V2 For Key System Flows

**Objective:** Extend Pipeline from a Market Regime explainer into a general key-parameter transparency surface.

**Files:**
- Modify: `web/api/services/pipeline.py`
- Modify: `web/api/routes/pipeline.py`
- Modify: `web/api/models.py`
- Modify: `web/frontend/src/views/Pipeline.vue`
- Modify: `web/frontend/src/api/index.ts`
- Modify: `docs/specs/05-web-platform.md`
- Modify: `wiki/concepts/system-architecture.md`
- Test: `tests/test_pipeline_route_contracts.py`

- [ ] **Step 1: Add pipeline registry endpoint**

Add:

```http
GET /api/pipeline
```

Response:

```json
{
  "items": [
    {"key": "market_regime", "label": "Market Regime", "status": "available"},
    {"key": "data_quality", "label": "Data Quality", "status": "available"},
    {"key": "strategy_evidence", "label": "Strategy Evidence", "status": "available"},
    {"key": "portfolio_execution", "label": "Portfolio Execution", "status": "available"}
  ],
  "total": 4
}
```

- [ ] **Step 2: Add three additional pipeline payloads**

Each payload must use the same shape as Market Regime: `pipeline_key`, `updated`, `summary`, `nodes`, `edges`, `warnings`.

Data Quality nodes:
1. Registry dimensions
2. Cache discovery
3. Manifest audit
4. Freshness gate
5. Repair actions
6. Downstream readiness

Strategy Evidence nodes:
1. Strategy catalog
2. Research scan
3. Backtest tournament
4. Baseline comparison
5. OOS and cost diagnostics
6. Promotion decision

Portfolio Execution nodes:
1. Signals
2. Regime overlay
3. Asset allocation
4. Risk checks
5. Paper order simulation
6. Persistence and audit

- [ ] **Step 3: Update Pipeline UI selector**

In `Pipeline.vue`:
- Add a compact segmented selector at the top.
- Reuse the existing graph/card visual language.
- Keep node detail panel behavior.
- Bottom output band should adapt to each pipeline and show no empty labels.

- [ ] **Step 4: Verify Pipeline V2**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_pipeline_route_contracts.py -q
cd web/frontend && npm run typecheck && npm run build
```

Manual browser check: open `/pipeline`, switch all four pipelines, click at least one node per pipeline.

---

## Phase 8: Execution Observability And Agent-Ready Operations

**Objective:** Let agents safely inspect and dry-run operational workflows without reading logs manually.

**Files:**
- Modify: `scripts/compute_signals.py`
- Modify: `scripts/execute_paper_trades.py`
- Modify: `broker/persistence.py`
- Modify: `web/api/routes/portfolio.py`
- Modify: `web/api/routes/system.py`
- Modify: `astrolabe_cli/commands/*.py`
- Modify: `wiki/reference/cli-control-plane.md`
- Test: `tests/test_broker_risk_persistence_allocator.py`
- Create: `tests/test_execution_observability.py`

- [ ] **Step 1: Add paper execution dry-run report**

Expose a JSON dry-run command:

```bash
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main execution dry-run --json
```

Expected JSON:

```json
{
  "ok": true,
  "signals_loaded": 0,
  "orders_proposed": 0,
  "orders_rejected": 0,
  "risk_rejections": [],
  "cash_after": 0.0,
  "warnings": []
}
```

The command must not mutate broker state.

- [ ] **Step 2: Add execution run ledger**

Create a small append-only Parquet or JSONL ledger under DataHub store:
- `run_id`
- `ts`
- `mode`: `dry_run` or `paper`
- `signals_loaded`
- `orders_proposed`
- `orders_submitted`
- `orders_rejected`
- `risk_rejections`
- `data_freshness_ok`

Acceptance:
- Dry-run can be configured not to persist, but live paper execution must persist.
- System Web page can show the latest run summary.

- [ ] **Step 3: Wire freshness gate into execution**

Before paper execution, check the data freshness gate from Phase 2.

Acceptance:
- If required dimensions are stale or missing, execution refuses new buy orders and records the refusal.
- Sell or risk-reduction orders may still be allowed if the current broker/risk design supports that distinction; if not, document that all new orders are blocked.

- [ ] **Step 4: Verify execution observability**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_broker_risk_persistence_allocator.py tests/test_execution_observability.py -q
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main execution dry-run --json
```

---

## Phase 9: CLI Coverage Expansion

**Objective:** Make agent operations depend on `astroq` instead of bespoke shell commands.

**Files:**
- Modify: `astrolabe_cli/main.py`
- Modify: `astrolabe_cli/commands/*.py`
- Modify: `wiki/reference/cli-control-plane.md`
- Modify: `docs/DOCUMENTATION.md`
- Test: `tests/test_cli_*.py`

- [ ] **Step 1: Add stable JSON commands for missing workflows**

Add commands if absent:
- `astroq strategy evidence --json`
- `astroq pipeline list --json`
- `astroq pipeline show market_regime --json`
- `astroq assets overview --json`
- `astroq execution dry-run --json`
- `astroq backtest check --json`

Each command must return:

```json
{
  "ok": true,
  "command": "pipeline.show",
  "data": {},
  "message": "",
  "errors": []
}
```

- [ ] **Step 2: Add CLI tests**

Acceptance:
- Every command supports `--json`.
- Every command exits with code 0 on dry-run or read-only paths.
- Errors use `ok=false` and structured `errors`, not raw tracebacks.

- [ ] **Step 3: Update CLI docs**

Update `wiki/reference/cli-control-plane.md` with the new commands and one example output per group.

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_cli_*.py -q
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main docs check --json
```

---

## Final Verification Checklist

Run this before handing work back:

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/test_data_fetcher_resilience.py \
  tests/test_data_cleaner_contracts.py \
  tests/test_cron_logger_contracts.py \
  tests/test_datahub_contracts.py \
  tests/test_strategy_evaluation.py \
  tests/test_strategy_backtest_evidence.py \
  tests/test_backtest_reproducibility.py \
  tests/test_backtest_pit_contracts.py \
  tests/test_backtest_pipeline_contracts.py \
  tests/test_asset_contracts.py \
  tests/test_multi_asset_tournament.py \
  tests/test_market_route_contracts.py \
  tests/test_pipeline_route_contracts.py \
  tests/test_web_system_contracts.py \
  tests/test_websocket_contracts.py \
  tests/test_cli_*.py \
  -q

cd web/frontend && npm run typecheck && npm run build

PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main docs check --json
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main health --json
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main data status --json
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main strategy catalog --json
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main regime status --json
git diff --check
```

Expected:
- All pytest targets pass.
- Frontend typecheck and build pass.
- CLI commands return valid JSON.
- Docs check returns `ok=true`.
- No whitespace errors.

## Completion Criteria

- [ ] `docs/specs/06-multi-asset.md` no longer contradicts current Bond/Futures/Crypto code.
- [ ] `docs/acceptance-matrix.md` no longer reports zero gaps while listing quality debt.
- [ ] Data reliability claims have automated tests.
- [ ] Strategy Lab can show evidence artifacts and promotion reasons.
- [ ] Backtest reproducibility, PIT, and pipeline behavior have regression tests.
- [ ] Multi-asset provenance is visible through API/Web and tested.
- [ ] Critical Web endpoints have response models and matching frontend types.
- [ ] WebSocket progress has a bounded contract test.
- [ ] Pipeline page supports Market Regime plus Data Quality, Strategy Evidence, and Portfolio Execution.
- [ ] Execution dry-run is agent-readable through `astroq`.
- [ ] Doc/spec/wiki/code are aligned at the end of implementation.

