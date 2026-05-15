# 多资产扩展计划

## 目标
从单资产(A股) → 可开关的多资产综合量化系统，核心价值在跨资产动态分配。

## 开关控制模型
```yaml
# config/settings.yaml
assets:
  stock:
    enabled: true
    alloc_weight: 0.50        # 资产分配权重(可被Allocator覆盖)
  etf:
    enabled: true
    alloc_weight: 0.30
  bond:
    enabled: false
    alloc_weight: 0.00
  futures:
    enabled: false
    alloc_weight: 0.00
  crypto:
    enabled: false
    alloc_weight: 0.00
```

## Phase 5.0 — 多资产基础设施

### 5.0-1: MultiAssetExchange 🆕
**文件**: `broker/exchange.py` → 多态化
- 当前: AShareExchange (A股硬编码)
- 目标: MultiAssetExchange 按 asset_type 分发费率
- ETF: T+0, 佣金0.005%, 无印花税, 无涨跌停
- 债券: T+0/T+1, 佣金0.002%, 净价交易

### 5.0-2: ETFAsset adapter 🆕
**文件**: `data/assets/etf.py`
- AKShare `fund_etf_spot_em` (实时行情) + Tushare `etf_basic` (基础信息)
- 200+ ETF universe (宽基/行业/债券/黄金/QDII)
- 因子: 折溢价率、跟踪误差、规模增长、份额变动

### 5.0-3: AssetAllocator 🆕
**文件**: `broker/allocator.py`
- 核心价值: regime → 动态权重 → 跨资产下单
- bull: stock↑ etf↑ bond↓
- bear: stock↓ bond↑ gold_etf↑
- 每个资产内部: 按各自策略评分选标的

### 5.0-4: 配置开关 + 集成
**文件**: `config/settings.yaml`, `scripts/compute_signals.py`
- AssetRegistry 按 enabled flag 实例化
- MultiAssetExchange 替换 AShareExchange
- Allocator 接入 cron 日频扫描

## Phase 5.1 — 更多资产类型 (按需)

### 5.1-1: BondAsset adapter
**文件**: `data/assets/bond.py`
- AKShare `bond_zh_us_rate` (国债收益率曲线)
- Tushare `cb_basic` (可转债)
- 因子: 久期/凸性/信用利差/YTM

### 5.1-2: FuturesAsset adapter
**文件**: `data/assets/futures.py`
- AKShare `futures_zh_daily_sina` + Tushare `fut_daily`
- 主力合约: IF/IC/IH(股指), T/TF/TS(国债), RB/I/CU(商品)
- 因子: 基差/期限结构/持仓量变化/波动率曲面

### 5.1-3: CryptoAsset adapter
**文件**: `data/assets/crypto.py`
- CCXT 统一接口 (Binance/OKX)
- BTC/ETH 现货 + 永续合约
- 因子: funding rate/open interest/whale flow

## 执行顺序
1. ✅ 设计 AssetAdapter ABC (已有)
2. 🆕 ETFAsset + ETF基金池
3. 🆕 MultiAssetExchange (费率多态)
4. 🆕 AssetAllocator (regime→weights)
5. 🆕 配置开关集成
6. 🆕 锦标赛扩展 (多资产对比)
7. 🔜 BondAsset (Phase 5.1)
