---
title: CLI Control Plane
created: 2026-05-29
updated: 2026-05-29
type: reference
tags: [cli, automation, operations]
---

# CLI Control Plane

`astroq` 是星盘 / Astrolabe Quant OS 的本地控制平面，给 agent、cron 和人工维护使用。它不是新的业务实现层，只负责把命令路由到现有模块。

## 使用原则

- 机器调用优先加 `--json`，读取 `ok`、`command`、`data`、`message`、`errors`。
- 会写数据、跑长任务或触发研究流程的命令，先用 `--dry-run` 确认。
- 策略运行默认是 `production`；candidate / research 策略必须显式 `--mode research`。
- agent-facing 示例统一写 `astroq` 或明确的 `python -m ...` 模块入口；脚本只作为当前受维护的批处理命令使用。

## 常用命令

```bash
astroq health --json
astroq config validate --json
astroq data status --json
astroq strategy catalog --json
astroq regime status --json
astroq test check --suite quick --json
astroq docs check --json
```

## 数据维护

```bash
astroq data repair stock_valuation --dry-run --json
astroq data repair stock_valuation --limit 100 --days 365 --json
```

`data repair` 只允许修复 `scripts.repair_table.REPAIR_MAP` 中声明的逻辑表。dry-run 必须不调用真实 repair 函数。

## 策略运行

```bash
astroq strategy run all --mode production --json
astroq strategy run trend_following --mode research --dry-run --json
astroq strategy compete --json
astroq strategy evidence --json
astroq strategy evidence multifactor --json
```

生产扫描只运行 `status=production` 的策略。候选策略如果没有 `--mode research` 应返回失败，防止研究候选误入生产信号。
`strategy compete` 读取 canonical backtest artifacts，按同一 OOS 窗口生成 12 策略公平竞赛排名和 production/paper 推荐，不直接改写策略注册表。
`strategy evidence` 不带名称时返回所有策略的 evidence 状态，带名称时返回单策略 detail；缺失报告返回结构化 `exists=false`，不作为 CLI 执行失败。

## Regime 与回测

```bash
astroq regime status --json
astroq regime train-profit --dry-run --json
astroq backtest run --strategy multifactor --dry-run --json
astroq backtest check --json
```

`regime status` 读取当前生产检测链路。`train-profit` 和 `backtest run` 可能耗时，agent 默认先 dry-run。`backtest check` 运行可复现性、PIT 和管道合约测试。

## 测试系统

```bash
astroq test check --suite quick --json
astroq test check --suite full --json
astroq test design --json
astroq architecture ast --json
```

`test check` 运行 `config/test_system.yaml` 声明的固定测试 suite。`test design` 使用确定性 AST 规则生成 `var/artifacts/tests/design/latest.json`。Web 的 `/system?tab=tests` 只读取测试设计产物，展示风险矩阵、测试图谱、用例审查器和异味诊断，不直接触发 pytest。

`architecture ast` 使用确定性 Python/TS/Vue/CSS AST 规则生成 `var/artifacts/architecture/ast/latest.json`。Web 的 `/system?tab=ast` 只读取该产物，展示重复风险分、clone groups、模块热力和重复实现诊断，不在 API 请求时扫描仓库。

## Pipeline

```bash
astroq pipeline list --json
astroq pipeline show market_regime --json
astroq pipeline show data_quality --json
```

`pipeline list` 返回所有可用管道。`pipeline show` 返回指定管道的节点、边和摘要。

## 资产概览

```bash
astroq assets overview --json
```

返回多资产覆盖情况：资产类型、启用状态、数据来源、研究就绪度、交易能力和 universe 大小。`enabled` 必须来自 `config/settings.yaml`，不能用 adapter 能力硬编码。

## 执行

```bash
astroq execution dry-run --json
```

模拟执行 dry-run：加载信号、检查数据 freshness gate、提议订单、检查风控、返回 JSON。不修改 broker 状态；数据门禁失败时拒绝新买单。

## Web 运维

```bash
astroq web build --json
astroq web serve --host 0.0.0.0 --port 8501
```

`web build` 委托 `web/frontend` 下的 Vite build。`web serve` 委托 `uvicorn web.api.app:create_app --factory`。

## 安装与入口

开发环境可以直接使用模块入口：

```bash
PYTHONPATH=. .venv/bin/python -m astrolabe_cli.main health --json
```

安装 editable 包后使用 console script：

```bash
uv pip install -e . --python .venv/bin/python
PATH="$PWD/.venv/bin:$PATH" astroq health --json
```
