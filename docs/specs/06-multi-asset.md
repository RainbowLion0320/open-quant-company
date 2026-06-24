# Spec: 多资产架构 (Multi-Asset Architecture)

> 版本: 1.2 | 日期: 2026-06-24 | 关联: [PRD](../product/prd.md) [Execution Layer](04-execution-layer.md)

## 1. 概述

多资产架构支持 Stock/ETF/Bond/Futures/Crypto 五类资产统一管理。`assets.*.enabled` 只表示资产开关，不等于策略、回测、paper 或 live 已可用。正式链路以 `asset_type` 一等字段贯穿数据、信号、组合、回测、paper/live 执行和 evidence；缺数据、缺合约语义、缺交易适配或缺权限必须显示 `blocked`，不能用股票逻辑硬套。

**设计原则：**
- **统一接口，多种适配器** — 不硬编码 "if stock elif fund"
- **Regime 驱动分配** — 牛市多股权，熊市多债券，波动市多现金
- **可开关扩展** — 每种资产类型独立配置，未启用的不加载
- **链路分段验收** — 数据、策略、回测、paper、live 五段分别可用或阻断
- **Live 分资产适配** — 股票/ETF/可转债优先 QMT/MiniQMT，期货走 CTP/配置化 futures gateway，加密走 CCXT-compatible adapter，未配置即 fail-closed

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
┌──────────────────────▼──────────────────────────────┐
│         AssetInstrument / AssetPricePanel             │
│   asset_type + symbol + currency + multiplier + status │
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
│ AShare / ETF / Bond / Futures / Crypto Exchange        │
│   各资产独立费率、交易单位、保证金和成交规则                │
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
| Futures | `FuturesAsset` | AKShare 主力连续合约行情 | 真实行情适配；研究链路启用，交易链路未接入 |
| Crypto | `CryptoAsset` | AKShare `crypto_js_spot` 最新现货快照 | 当前快照源 stale 时必须阻断策略/交易；完整历史 K 线未接入 |

### 2.3 资产链路状态

`astroq assets overview --json` 和 `/datahub?tab=assets` 必须展示每类资产的五段状态：

| 阶段 | 含义 | 阻断示例 |
|------|------|----------|
| data | 本地数据/源适配是否足以研究 | `research_data_not_ready`, `crypto_data_stale_until_fresh_source` |
| strategy | 是否可被策略正式消费 | 缺必需价格、连续合约、复权/币种口径 |
| backtest | 是否可进入正式 PIT 回测 | 缺历史 bars、样本不足、benchmark 缺失 |
| paper | 是否可模拟下单和对账 | 不可交易代理数据、交易单位未知 |
| live | 是否有实盘 adapter 与账户能力 | `live_adapter_not_configured`, `exchange_secret_missing` |

启用资产开关只影响是否纳入链路检查；不改变任何阶段的真实 ready/block 状态。

### 2.4 AssetAllocator — 动态权重分配

**Regime → Raw Weight Matrix（可配置，分配时归一化）：**

| Regime | Stock | ETF | Bond | Futures | Crypto | Cash | 说明 |
|--------|-------|-----|------|---------|--------|------|------|
| Bull | 55% | 25% | 5% | 3% | 2% | 10% | 股票/ETF 为主，保留小比例跨资产研究仓位 |
| Sideways | 30% | 25% | 20% | 5% | 3% | 17% | 均衡配置，allocate 时按启用资产归一到 `1 - cash` |
| Bear | 10% | 10% | 40% | 3% | 2% | 35% | 防御资产和现金优先 |
| Unknown | 20% | 15% | 30% | 3% | 2% | 30% | 模块默认保守权重 |

**分配流程：**
1. Market Regime 由 `cybernetics` 当前检测或回测的 `backtest.regime_replay` 提供；`AssetAllocator` 不自行检测 regime
2. `get_weights(regime, probs=None)` → `{"stock": 0.60, "etf": 0.30, ...}`，传入 HMM/Hybrid 概率时可做概率加权
3. `allocate(regime, enabled_assets, asset_signals, total_capital, max_positions_per_asset)` 按启用资产归一权重
4. 各资产内按 score 排序选 Top-N，资产内等权，缺信号的权重并入现金

**配置覆盖：** `settings.yaml` → `asset_allocation.regime_weights` 可覆盖默认权重矩阵，使用 `copy.deepcopy` 防止 mutation。未写入配置的资产键保留 `REGIME_WEIGHTS_DEFAULT` 默认值。

### 2.5 Multi-Asset Exchange — 差异化费率

```python
# 各资产交易成本不同，默认值来自 config/settings.yaml → trading.exchange
AShareExchange:  佣金 0.025% + 印花税 0.05%(卖) + 过户费 0.001%
ETFExchange:     佣金 0.005% + 无印花税
BondExchange:    佣金 0.002% + 无印花税
FuturesExchange: 按手收佣 + 保证金参数
CryptoExchange:  现货 taker/maker 风格费率，默认 0.1%
```

`ExecutionRouter` 按 `OrderIntent.asset_type` 分发到对应 exchange。缺 exchange 注册时阻断，不允许回退股票费率。

### 2.6 Live adapter registry

| 资产 | 默认 live adapter | 当前状态 |
|------|-------------------|----------|
| stock | QMT/MiniQMT | 合约存在，仍受 `execution.live.enabled`、SDK、账号和权限控制 |
| etf | QMT/MiniQMT | 同 stock，需券商端支持 |
| bond | QMT/MiniQMT 条件支持 | 仅可转债可尝试，国债收益率代理不可交易 |
| futures | CTP 或配置化 futures gateway | 默认 `live_adapter_not_configured` |
| crypto | CCXT-compatible exchange | 默认 `live_adapter_not_configured` / `exchange_secret_missing` |
| cash | 非交易桶 | `not_applicable` |

Live 路径不得回退 PaperBroker；未配置或失败只写 blocked evidence。

### 2.7 ETF 价格 fallback

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
PipelineBacktest / PaperBroker / LiveAdapterRegistry
  → asset_type-aware evidence and blockers
```

## 4. 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| AssetAdapter ABC | 统一接口 | 新增资产类型只需实现接口，分配器/交易所无需改动 |
| 配置驱动启用 | `assets.{type}.enabled: true/false` | 当前五类资产默认启用；开关不代表全链路 ready |
| `asset_type` 一等字段 | Signal/Target/Order/Fill/Position 全部携带 | 避免把期货/ETF/加密误当股票 |
| Live 分资产 registry | 未配置即阻断 | 防止期货/加密实盘被 Paper 或股票 broker 假冒 |
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
    enabled_assets={"stock": True, "etf": True, "bond": True, "futures": True, "crypto": True},
    asset_signals={
        "stock": [{"symbol": "000001", "score": 82.0}],
        "etf": [{"symbol": "510300", "score": 74.0}],
        # 缺少信号的资产不会生成假标的，其权重会进入现金。
        "futures": [],
        "crypto": [],
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

- **合约测试：** Signal/Target/Order/Fill/Position 均携带 `asset_type`
- **价格测试：** `get_asset_price_panel()` 对缺 adapter、空价格和正常 adapter 输出明确 status/blockers
- **分配器测试：** 固定 regime → 验证权重总和 = 1.0
- **Regime 权重测试：** 固定 bull/bear/sideways/unknown → 验证归一化和现金保留
- **PipelineBacktest 测试：** trade log、score panel、final holdings 均包含资产类型
- **Paper/Live 测试：** PaperBroker 按资产持仓；futures/crypto live adapter 默认 fail-closed
- **边界测试：** 所有资产未启用 → 100% 现金、单一资产启用 → 权重正确

## 8. 已知限制 & 未来方向

- **ETF proxy fallback：** ETF 适配器已有真实行情路径，但降级 proxy 必须标注 `data_source`
- **Bond/Futures/Crypto 边界：** Bond 当前是国债收益率价格代理 + 可转债快照，Futures 有真实主力合约行情适配器，Crypto 当前 AKShare snapshot 源可能 stale；三者缺失条件必须阻断，不得填默认值。
- **Live adapter 缺口：** Futures 需要 CTP/配置化 futures gateway，Crypto 需要 CCXT-compatible exchange 和 API key；未配置前均不可实盘。
- **无跨资产对冲：** 当前各资产独立选标的，未考虑资产间相关性
- **无动态风险预算：** 当前 regime 权重是静态矩阵，未来可基于波动率动态调整
- **未来：** 实盘环境中完成 ETF/可转债/QMT、期货/CTP、加密/交易所三类 adapter 的真实账户验收
