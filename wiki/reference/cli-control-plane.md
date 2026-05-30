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
- 旧脚本仍可作为底层实现存在，但 agent-facing 示例统一写 `astroq`。

## 常用命令

```bash
astroq health --json
astroq config validate --json
astroq data status --json
astroq strategy catalog --json
astroq regime status --json
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
astroq strategy evidence multifactor --json
```

生产扫描只运行 `status=production` 的策略。候选策略如果没有 `--mode research` 应返回失败，防止研究候选误入生产信号。

## Regime 与回测

```bash
astroq regime status --json
astroq regime train-profit --dry-run --json
astroq backtest run --strategy multifactor --dry-run --json
astroq backtest check --json
```

`regime status` 读取当前生产检测链路。`train-profit` 和 `backtest run` 可能耗时，agent 默认先 dry-run。`backtest check` 运行可复现性、PIT 和管道合约测试。

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

返回多资产覆盖情况：资产类型、数据来源、研究就绪度、交易能力和 universe 大小。

## 执行

```bash
astroq execution dry-run --json
```

模拟执行 dry-run：加载信号、提议订单、检查风控、返回 JSON。不修改 broker 状态。

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
