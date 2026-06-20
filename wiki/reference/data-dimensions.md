---
title: Data Dimensions Reference
created: 2026-05-14
updated: 2026-06-05
type: reference
tags: [data, registry, datahub, parquet]
confidence: high
---

# 数据维度参考

本页说明数据维度在哪里定义、如何检查。它刻意不复制当前注册表全表或维度数量。

## 权威来源

| 主题 | 来源 |
|---------|--------|
| 维度列表、source、asset、status、freq、cache pattern | `config/settings.yaml` → `data_registry` |
| 注册表校验和元数据 | `data/storage/dimensions.py` |
| 路径展开和物理存储 | `data/storage/datahub.py` |
| 健康检查表映射 | `DataRegistry.health_metadata()` |
| 运行时目录和 manifest | `DataHub.catalog()` + `var/store/_manifest/datasets.parquet` |

注册表是数据维度的单一事实来源。Wiki 页面应该链接到注册表，不重复维护完整表格。

## 如何检查

列出启用维度：

```bash
python -c "from data.storage.dimensions import get_registry; print('\\n'.join(d.key for d in get_registry().get_enabled()))"
```

校验注册表契约：

```bash
python -c "from data.storage.dimensions import get_registry; print(get_registry().validate())"
```

查看健康检查元数据：

```bash
python -c "from data.storage.dimensions import get_registry; print(get_registry().health_metadata())"
```

查看 DataHub catalog：

```bash
python -c "from data.storage.datahub import get_datahub; print(get_datahub().catalog())"
```

## 路径规则

- cache pattern 指向具体文件时，使用 `DataHub.dimension_path(key, **values)`。
- cache pattern 指向快照目录或文件前缀时，使用 `DataHub.dimension_root(key)`。
- 策略、Web、研究代码不要硬编码 `var/store/sector/...` 这类深层路径。
- 所有写入应经过 `write_parquet()` 或 `append_parquet()`，确保 manifest 元数据持续更新。

## 重要维度家族

| 家族 | 示例 | 消费方 |
|--------|----------|----------|
| 股票市场数据 | OHLCV、复权因子、估值、资金流 | Signals、backtest、个股页 |
| 价格口径视图 | `ohlcv_daily`(qfq)、`ohlcv_daily_raw`(raw)、`ohlcv_daily_hfq`(hfq)、`adj_factor`、`corporate_actions` | `PriceService`、回测、估值、执行、公司行动账本 |
| 财报和财务指标 | financial summary、fina indicator、income/balance/cashflow | Buffett、多因子、ML 特征 |
| 宏观数据 | GDP、CPI、PMI、SHIBOR、黄金 | 市场总览、regime context |
| 行业数据 | 行业日线、成员映射、绩效、信号聚合、组合敞口 | 市场总览 Top5 热点、行业雷达、多因子行业动量；组合敞口在组合执行页承载 |
| 信号和特征 | 策略信号、PIT 特征切片 | Selection、backtest、PaperBroker |
| 运维元数据 | manifest、cron logs、健康扫描输出 | DB Health、System Settings status |

## 新增维度

1. 在 `config/settings.yaml` → `data_registry` 添加维度。
2. 确保 `source`、`asset`、`status`、`freq`、`enabled`、`label`、`cache` 满足 `DataRegistry.validate()`。
3. 下游 schema 重要时，在 `data/quality/contract.py` 添加或派生契约。
4. 生产代码使用 `DataHub.dimension_path()` 或 `dimension_root()`。
5. 补路径展开、契约形态和主要消费方测试。
6. 只有行为或契约变化时才更新 `docs/specs/01-data-pipeline.md`。

## 价格口径约定

股票 OHLCV 不再只依赖生产者口头说明。`PriceService` 按 use case 选择 `raw`、`qfq`、`hfq`：

- 研究、信号、回测默认使用 `qfq`，优先由 raw OHLCV + `adj_factor` 派生。
- 执行、估值、展示默认使用 `raw`，避免用复权价模拟真实成交价或当前市值。
- `corporate_actions` 是标准化公司行动事件层，独立于 OHLCV，用于现金分红、送转和拆股对账。

## 相关

- [[datahub]]
- [[data-schema]]
- [[system-architecture]]
