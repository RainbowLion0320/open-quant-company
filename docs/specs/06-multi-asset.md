# Spec: 多资产架构 (Multi-Asset Architecture)

> 版本: 1.1 | 日期: 2026-06-03 | 关联: [PRD](../product/prd.md) [Execution Layer](04-execution-layer.md)

## 1. 概述

多资产架构支持 Stock/ETF/Bond/Futures/Crypto 五类资产统一管理和交易。通过 AssetAdapter ABC 接口统一数据获取，AssetAllocator 按市场 regime 动态分配权重，各资产类型可在 `config/settings.yaml` 中独立启用/禁用。

**设计原则：**
- **统一接口，多种适配器** — 不硬编码 "if stock elif fund"
- **Regime 驱动分配** — 牛市多股权，熊市多债券，波动市多现金
- **可开关扩展** — 每种资产类型独立配置，未启用的不加载

## 2. 组件架构

```
┌─────────────────────────────────────────────────────┐
│              config/settings.yaml                     │
│   assets: {stock, etf, bond, futures, crypto}        │
│   asset_allocation.regime_weights: {bull, bear, ...}  │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  AssetRegistry                        │
│   注册所有已启用资产类型 → AssetAdapter 实例            │
│   get("stock") / asset_types / all / get_universe()   │
└──────────────────────┬──────────────────────────────┘
                       │
       ┌───────────────┼───────────────┬───────────────┐
       │               │               │               │
┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
│ StockAsset  │ │ ETFAsset    │ │ BondAsset   │ │FuturesAsset │
│ A股股票      │ │ 场内ETF     │ │ 债券/国债    │ │ 期货真实适配   │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │               │
       └───────────────┼───────────────┴───────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                AssetAllocator                         │
│   get_weights(regime[, probs])                        │
│   allocate(regime, enabled_assets, asset_signals, ...)│
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              Multi-Asset Exchange                      │
│   AShareExchange / ETFExchange / BondExchange         │
│   各资产独立的费率结构 + 交易规则                        │
└─────────────────────────────────────────────────────┘
```

### 2.1 AssetAdapter ABC — 统一接口

```python
class AssetAdapter(ABC):
    asset_type: str      # "stock", "etf", "bond", "futures", "crypto"
    label: str           # "A股股票"
    description: str

    @abstractmethod
    def fetch_daily(self, symbol, start_date, end_date) → pd.DataFrame | None
    @abstractmethod
    def get_universe(self) → list[str]
    @abstractmethod
    def get_metadata(self, symbol) → dict

    # 可选
    def fetch_fundamentals(self, symbol) → dict
    def fetch_valuation(self, symbol, date=None) → dict
    def fetch_factor_data(self, symbol, factor_name, date=None) → float | None
    def get_data_source(self, symbol="") → dict
```

### 2.2 已实现资产类型

| 资产 | 类 | 数据源 | 状态 |
|------|-----|--------|------|
| Stock | `StockAsset` | AKShare 日线 + Tushare 财务补充 | production-ready adapter |
| ETF | `ETFAsset` | AKShare `fund_etf_hist_em`; tournament 可显式降级到指数代理 | production adapter with fallback marking |
| Bond | `BondAsset` | 国债收益率价格代理 + 可转债快照真实数据 | 代理数据 + 部分真实快照 |
| Futures | `FuturesAsset` | AKShare 主力连续合约行情 | 真实行情适配，当前尚未深度接入配置研究 |
| Crypto | `CryptoAsset` | 默认禁用；未接入 CCXT 真实行情 | disabled adapter |

### 2.3 AssetAllocator — 动态权重分配

**Regime → Raw Weight Matrix（可配置，分配时归一化）：**

| Regime | Stock | ETF | Bond | Cash | 说明 |
|--------|-------|-----|------|------|------|
| Bull | 60% | 30% | 5% | 10% | 当前 settings 覆盖 stock/ETF/cash，bond 沿用模块默认 |
| Sideways | 35% | 35% | 20% | 30% | allocate 时按启用资产归一到 `1 - cash` |
| Bear | 15% | 15% | 40% | 70% | 高现金配置，未启用资产不会进入分配 |
| Unknown | 20% | 15% | 30% | 35% | 模块默认保守权重 |

**分配流程：**
1. Market Regime 由 `cybernetics` 当前检测或回测的 `backtest.regime_replay` 提供；`AssetAllocator` 不自行检测 regime
2. `get_weights(regime, probs=None)` → `{"stock": 0.60, "etf": 0.30, ...}`，传入 HMM/Hybrid 概率时可做概率加权
3. `allocate(regime, enabled_assets, asset_signals, total_capital, max_positions_per_asset)` 按启用资产归一权重
4. 各资产内按 score 排序选 Top-N，资产内等权，缺信号的权重并入现金

**配置覆盖：** `settings.yaml` → `asset_allocation.regime_weights` 可覆盖默认权重矩阵，使用 `copy.deepcopy` 防止 mutation。未写入配置的资产键保留 `REGIME_WEIGHTS_DEFAULT` 默认值。

### 2.4 Multi-Asset Exchange — 差异化费率

```python
# 各资产交易成本不同，默认值来自 config/settings.yaml → trading.exchange
AShareExchange:  佣金 0.025% + 印花税 0.05%(卖) + 过户费 0.001%
ETFExchange:     佣金 0.005% + 无印花税
BondExchange:    佣金 0.002% + 无印花税
```

### 2.5 ETF 价格 fallback

ETF 适配器优先使用 AKShare `fund_etf_hist_em` 真实行情。`scripts/multi_asset_tournament.py` 在缺少本地 ETF 缓存或接口不可用时，可使用 proxy 构造近似价格，并必须在结果中保留 `data_source` 标识：

| ETF | Proxy | 方法 |
|-----|-------|------|
| 510050 (上证50) | sh000016 | 指数收盘价 × 0.001 |
| 510300 (沪深300) | sh000300 | 指数收盘价 × 0.001 |
| 510500 (中证500) | sh000905 | 指数收盘价 × 0.001 |
| 518880 (黄金ETF) | SGE 金价 | 晚盘价 × 0.01 |
| 511010 (国债ETF) | 10Y 收益率 | 价格变化 ≈ -久期 × 收益率变化 |
| 511880 (货币ETF) | Shibor 隔夜 | 日复利累积 |

**长期方案：** 多资产回测应默认优先真实 ETF 行情，并把 proxy 场景作为显式降级路径；后续可接入 Wind/Tushare ETF 数据作为补充。

## 3. 数据流

```
Market Regime Snapshot
       │
       ▼
  regime + optional regime_probs
       │
       ▼
  AssetAllocator.get_weights(regime)
       │ raw weights, then normalize enabled assets to 1 - cash
       ▼
  ┌─────────────────────────────────────┐
  │  For each enabled asset type:        │
  │    budget = total_capital × weight   │
  │    symbols = asset.get_universe()    │
  │    signals = asset_signals[type]     │
  │    selected = top_n(signals, score)  │
  └─────────────────────────────────────┘
       │
       ▼
  PortfolioAllocation:
    allocations: [AssetAllocation(stock, 0.6, [...]), ...]
    cash_reserve: ¥100,000
       │
       ▼
  Multi-Asset Exchange → execute orders
```

## 4. 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| AssetAdapter ABC | 统一接口 | 新增资产类型只需实现接口，分配器/交易所无需改动 |
| 配置驱动启用 | `assets.{type}.enabled: true/false` | 未实现的资产保持 enabled=false |
| Regime 权重矩阵 | `copy.deepcopy` 防御 | 防止运行时修改污染模块级默认常量 |
| ETF Proxy 方案 | 短期 workaround | AKShare 接口不稳定，Proxy 保证回测可运行 |
| 每月再平衡 | 月初统一调仓 | 与股票策略调仓周期一致 |

## 5. 接口合约

### AssetAdapter 接口

```python
class MyAsset(AssetAdapter):
    asset_type = "futures"
    label = "期货"

    def fetch_daily(self, symbol, start, end) → pd.DataFrame:
        """返回 OHLCV DataFrame，无数据返回 None"""

    def get_universe(self) → list[str]:
        """返回可交易标的列表"""

    def get_metadata(self, symbol) → dict:
        """返回 {name, exchange, multiplier, ...}"""
```

### AssetAllocator 接口

```python
allocator = AssetAllocator()

# 获取权重
weights = allocator.get_weights(regime)  # {"stock": 0.6, "etf": 0.25, ...}

# 完整分配
portfolio = allocator.allocate(
    regime="bull",
    enabled_assets={"stock": True, "etf": True, "bond": False},
    asset_signals={
        "stock": [{"symbol": "000001", "score": 82.0}],
        "etf": [{"symbol": "510300", "score": 74.0}],
    },
    total_capital=1_000_000,
    max_positions_per_asset=8,
)
# → PortfolioAllocation(allocations=[...], cash_reserve=...)
```

## 6. 错误处理

- **资产类型未启用：** `enabled_assets` 过滤，不进入 allocation
- **ETF 真实数据不可用：** 回退到 Proxy（`scripts/multi_asset_tournament.py` 中实现）
- **Regime 缺失或未知：** `normalize_regime(..., default="unknown")` 后使用保守权重
- **权重配置缺失：** `AssetAllocator.__init__` 中 `copy.deepcopy(REGIME_WEIGHTS_DEFAULT)` 保证始终有默认值
- **单资产类型失败：** 不影响其他资产类型的分配和执行

## 7. 测试策略

- **合约测试：** StockAsset/ETFAsset 实现 AssetAdapter ABC 所有抽象方法
- **分配器测试：** 固定 regime → 验证权重总和 = 1.0
- **Regime 权重测试：** 固定 bull/bear/sideways/unknown → 验证归一化和现金保留
- **多资产回测测试：** `scripts/multi_asset_tournament.py` 成功运行 stock-only vs ETF-only vs multi 三组对比
- **边界测试：** 所有资产未启用 → 100% 现金、单一资产启用 → 权重正确

## 8. 已知限制 & 未来方向

- **ETF proxy fallback：** ETF 适配器已有真实行情路径，但多资产回测在缺少本地缓存时仍可能回退 proxy，收益计算需标注 data_source
- **Bond/Futures/Crypto 边界：** Bond 当前是国债收益率价格代理 + 可转债快照，Futures 有真实日线适配器但未形成完整研究/交易闭环，Crypto 默认禁用且未接入 CCXT。所有收益、回测和 Web 展示必须保留 `data_source` provenance。
- **无跨资产对冲：** 当前各资产独立选标的，未考虑资产间相关性
- **无动态风险预算：** 当前 regime 权重是静态矩阵，未来可基于波动率动态调整
- **未来：** 半自动实盘中多资产联合执行、T+0 ETF 日内轮动
