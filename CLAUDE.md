# Quant Agent — 个人A股量化AI

## 项目概览
- 目的: 分阶段打造个人量化系统 (分析助手 → 信号系统 → 半自动交易)
- 频率: 日线级别, 低频
- 架构: 巴菲特价值投资 (决策约束层) + 钱学森控制论 (运行机制层), 正交不冲突
- 注意: 这两个原则已写入 ~/.hermes/SOUL.md，是 Hermes 本身的架构而非仅项目的。本项目是它们在量化领域的具体落地。

## 环境
- Python: `~/.hermes/hermes-agent/venv/bin/python3`
- 数据: AKShare 1.18.60, 优先用新浪源, 东方财富/腾讯作备选
- 回测: Backtrader 1.9.78
- 缓存: parquet (需 pyarrow)
- 代理: fetcher.py 会自动绕过 v2ray

## 数据源约定
- 个股日线: `stock_zh_a_daily` (新浪), 备选 `stock_zh_a_hist` (东财), `stock_zh_a_hist_tx` (腾讯)
- 指数日线: `stock_zh_index_daily` (通用), 备选 `stock_zh_index_daily_tx` (腾讯)
- 财务数据: `stock_financial_abstract_ths` (同花顺, 含ROE/毛利率/负债率)
- 请求频率: 3s间隔, 指数退避重试3次

## 记忆系统
- 已配置 Hindsight Local 模式 (deepseek-v4-flash, bank_id=quant-agent)
- 首次启动需 /reset, daemon 会自动拉起 (首次初始化约1分钟)

## 当前进度 (2026-05-10)
- [x] 环境搭建 + 数据源验证
- [x] fetcher 稳定性 (三源切换, 重试, 节流, 代理绕过)
- [x] 财务数据桥接 (同花顺 → ROE/毛利率/负债率, 万亿格式修复)
- [x] 巴菲特过滤器 (能力圈→护城河→安全边际, 板块感知)
- [x] 控制论框架 (市场状态, 反馈回路, 自适应, 真实数据接入)
- [x] Hindsight 记忆系统
- [x] 行业适配 (银行用净利率替代毛利率, D/E修复)
- [x] 全量巴菲特扫描 (25只→5只通过, 通过率20%)
- [x] 控制论层接入真实数据 (上证bull, 均线多头排列)
- [x] Backtrader 回测模板 (MA5/MA20金叉+止损, 5只精选池6.85% vs 基准35.48%)

## 巴菲特精选池 (2026-05-10扫描结果)
```
603288 海天味业  91分 (消费) ROE:23.8% 安全边际:56.7%
002415 海康威视  88分 (消费) ROE:20.2% 安全边际:80.0%
600036 招商银行  82分 (金融) ROE:15.6% 安全边际:98.0%
600030 中信证券  73分 (金融) ROE:9.4%  安全边际:92.9%
601318 中国平安  68分 (金融) ROE:12.1% 安全边际:96.4%
```

## 当前市场状态
- 状态: bull (多多头排列)
- 均线: MA5:4148 > MA20:4072 > MA60:4053
- 自适应: position 30%, stop -8%, max 8 positions

## 关键文件
```
~/quant-agent/
├── config/settings.yaml           # 全局配置（含行业阈值）
├── buffett/filters.py             # 巴菲特三重过滤器（板块感知）
├── cybernetics/orchestrator.py    # 控制论协调器（真实数据接入）
├── data/financials.py             # 财务数据提取（净利率+D/E）
├── data/symbols.py                # 股票池+板块分类
├── scripts/scan_all.py            # 全量扫描脚本
├── backtest/strategies/ma_cross.py # 均线金叉策略
├── backtest/run_ma_cross.py       # 回测运行脚本
└── main.py                        # CLI入口
```
