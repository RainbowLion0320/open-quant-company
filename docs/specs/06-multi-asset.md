# Spec: 多资产架构 (Multi-Asset Architecture)

> 版本: 1.0 | 日期: 2026-05-21 | 关联: [[PRD.md]] [[04-execution-layer.md]]

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
│   get_enabled() / get("stock") / list_all()           │
└──────────────────────┬──────────────────────────────┘
                       │
       ┌───────────────┼───────────────┬───────────────┐
       │               │               │               │
┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
│ StockAsset  │ │ ETFAsset    │ │ BondAsset   │ │FuturesAsset │
│ A股股票      │ │ 场内ETF     │ │ 债券/国债    │ │ 期货 (planned)
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │               │
       └───────────────┼───────────────┴───────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                AssetAllocator                         │
│   detect_regime(index_data) → get_weights(regime)     │
│   allocate(capital, regime, scores) → PortfolioAlloc  │
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
    def universe(self) → list[str]
    @abstractmethod
    def metadata(self, symbol) → dict

    # 可选
    def build_features(self, symbol, date) → dict   # PIT 特征
    def validate_symbol(self, symbol) → bool
```

### 2.2 已实现资产类型

| 资产 | 类 | 数据源 | 状态 |
|------|-----|--------|------|
| Stock | `StockAsset` | AKShare(新浪) + Tushare(财务) | available |
| ETF | `ETFAsset` | AKShare `fund_etf_hist_em` (网络不稳定) | rate_limited |
| Bond | 待实现 | — | planned |
| Futures | 待实现 | — | planned |
| Crypto | 待实现 | — | planned |

### 2.3 AssetAllocator — 动态权重分配

**Regime → Weight Matrix（可配置）：**

| Regime | Stock | ETF | Bond | Cash |
|--------|-------|-----|------|------|
| Bull | 60% | 25% | 5% | 10% |
| Sideways | 35% | 25% | 20% | 20% |
| Bear | 10% | 10% | 40% | 40% |
| Unknown | 20% | 15% | 30% | 35% |

**分配流程：**
1. `detect_regime(index_data)` → `"bull" | "bear" | "sideways"`
2. `get_weights(regime)` → `{"stock": 0.60, "etf": 0.25, ...}`
3. 按权重分割资金 → 各资产内独立选标的（动量/多因子评分）
4. 每月再平衡

**配置覆盖：** `settings.yaml` → `asset_allocation.regime_weights` 可覆盖默认权重矩阵，使用 `copy.deepcopy` 防止 mutation。

### 2.4 Multi-Asset Exchange — 差异化费率

```python
# 各资产交易成本不同
AShareExchange:  佣金 0.03% + 印花税 0.1%(卖) + 滑点 0.1%
ETFExchange:     佣金 0.01% + 印花税 0%(免)  + 滑点 0.05%
BondExchange:    佣金 0.001% + 无印花税      + 滑点 0.02%
```

### 2.5 ETF 代理价格 — 短期方案

由于 AKShare ETF 历史行情接口（`fund_etf_hist_em`）网络不稳定，`multi_asset_tournament.py` 中使用 proxy 构造 ETF 近似价格：

| ETF | Proxy | 方法 |
|-----|-------|------|
| 510050 (上证50) | sh000016 | 指数收盘价 × 0.001 |
| 510300 (沪深300) | sh000300 | 指数收盘价 × 0.001 |
| 510500 (中证500) | sh000905 | 指数收盘价 × 0.001 |
| 518880 (黄金ETF) | SGE 金价 | 晚盘价 × 0.01 |
| 511010 (国债ETF) | 10Y 收益率 | 价格变化 ≈ -久期 × 收益率变化 |
| 511880 (货币ETF) | Shibor 隔夜 | 日复利累积 |

**长期方案：** 等 AKShare `fund_etf_hist_em` 接口恢复后切换为真实 ETF 行情，或接入 Wind/Tushare ETF 数据。

## 3. 数据流

```
Market Index Data (sh000001)
       │
       ▼
  detect_regime(close) → "bull" / "bear" / "sideways"
       │
       ▼
  AssetAllocator.get_weights(regime)
       │ {stock: 0.6, etf: 0.25, bond: 0.05, cash: 0.10}
       ▼
  ┌─────────────────────────────────────┐
  │  For each enabled asset type:        │
  │    budget = total_capital × weight   │
  │    symbols = asset.universe()        │
  │    scores = score_symbols(symbols)   │
  │    selected = top_n(scores, budget)  │
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

    def universe(self) → list[str]:
        """返回可交易标的列表"""

    def metadata(self, symbol) → dict:
        """返回 {name, exchange, multiplier, ...}"""
```

### AssetAllocator 接口

```python
allocator = AssetAllocator()

# 基于历史数据检测 regime（无前视偏差）
regime = allocator.detect_regime(index_close, date)

# 获取权重
weights = allocator.get_weights(regime)  # {"stock": 0.6, "etf": 0.25, ...}

# 完整分配
portfolio = allocator.allocate(
    capital=1_000_000,
    regime="bull",
    stock_scores={...},
    etf_scores={...},
)
# → PortfolioAllocation(allocations=[...], cash_reserve=...)
```

## 6. 错误处理

- **资产类型未启用：** `get_enabled()` 过滤，不会加载未启用的适配器
- **ETF 真实数据不可用：** 回退到 Proxy（`multi_asset_tournament.py` 中实现）
- **Regime 检测数据不足：** 返回 "unknown"，使用保守权重
- **权重配置缺失：** `AssetAllocator.__init__` 中 `copy.deepcopy(REGIME_WEIGHTS_DEFAULT)` 保证始终有默认值
- **单资产类型失败：** 不影响其他资产类型的分配和执行

## 7. 测试策略

- **合约测试：** StockAsset/ETFAsset 实现 AssetAdapter ABC 所有抽象方法
- **分配器测试：** 固定 regime → 验证权重总和 = 1.0
- **Regime 检测测试：** 构造 bull/bear/sideways 价格序列 → 验证检测结果
- **多资产回测测试：** `multi_asset_tournament.py` 成功运行 stock-only vs ETF-only vs multi 三组对比
- **边界测试：** 所有资产未启用 → 100% 现金、单一资产启用 → 权重正确

## 8. 已知限制 & 未来方向

- **ETF 真实行情缺失：** 当前使用 proxy 方案，收益计算有偏差（见 2.5 节）
- **Bond/Futures/Crypto 未实现：** 框架已就绪，需要数据源接入
- **无跨资产对冲：** 当前各资产独立选标的，未考虑资产间相关性
- **无动态风险预算：** 当前 regime 权重是静态矩阵，未来可基于波动率动态调整
- **未来：** Phase 5 实盘中多资产联合执行、T+0 ETF 日内轮动
