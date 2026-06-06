---
title: Data Schema Reference
created: 2026-05-14
updated: 2026-06-05
type: reference
tags: [data, schema, parquet, contract]
confidence: high
---

# 数据 Schema 参考

本页说明 schema 归属和检查流程。它不是所有 Parquet 文件列定义的权威表。

## 权威来源

| 主题 | 来源 |
|---------|--------|
| 声明式数据维度 | `config/settings.yaml` → `data_registry` |
| 派生和显式数据契约 | `data/quality/contract.py` |
| 运行时 manifest schema hash | `var/store/_manifest/datasets.parquet` |
| 物理 Parquet 文件 | `var/store/` |
| Web/API schema 预期 | `web/api/schemas/*` 分域 schema、`web/api/models.py` 兼容聚合入口和路由 response models |

`data/quality/contract.py` 可以从 DataRegistry 派生契约，也可以为重要数据集叠加显式 schema 要求。数据集 schema 变化时，契约和测试必须在同一次改动里更新。

## 如何检查

列出已知契约：

```bash
python -c "from data.contract import derive_contracts_from_registry; print('\\n'.join(sorted(derive_contracts_from_registry())))"
```

查看单个契约：

```bash
python -c "from data.contract import derive_contracts_from_registry; c=derive_contracts_from_registry().get('sector_performance_snapshot'); print(c)"
```

运行契约测试：

```bash
pytest tests/test_datahub_contracts.py tests/test_sector_pipeline.py
```

## 稳定 schema 家族

| 家族 | 必要概念 |
|--------|----------------|
| OHLCV | symbol/date/open/high/low/close/volume 等字段；`PriceService` 显式声明 `raw` / `qfq` / `hfq`，DataHub manifest 记录 requested/actual price mode |
| 公司行动 | `corporate_actions` 标准事件：symbol/ex_date/cash_dividend_per_share/share_multiplier；从 `dividend` 等原始事件归一，供回测账本处理现金分红和送转/拆股 |
| 财务指标 | symbol/report date/period 字段，加财务比率或报表值 |
| PIT 特征 | symbol/date/month 特征，严格避免未来数据泄漏 |
| 策略信号 | symbol/date/strategy/score/signal/detail，供 Web、回测、broker 消费 |
| 行业快照 | sector_code/sector_name/date，加绩效、成员、信号或敞口字段 |
| 运维元数据 | path、row_count、schema_hash、producer、updated_at |

不要把上表当成完整 schema。精确列集合归属代码契约和测试。

## 变更规则

- 生产者必须通过 DataHub 写入，确保 schema hash 和 manifest 元数据更新。
- 消费者应在边界处校验必要列，避免缺列导致误导性结果。
- 被策略、Web API 或 broker 执行消费的数据集，测试必须覆盖必要列。
- 只有 schema 归属模型或数据集家族变化时，才需要更新 wiki。

## 相关

- [[data-dimensions]]
- [[datahub]]
- [[system-architecture]]
