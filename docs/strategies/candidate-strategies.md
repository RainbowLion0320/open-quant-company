# Candidate Strategies

> 状态: research-only | 更新: 2026-05-29 | 权威注册: `config/settings.yaml` → `strategies`

候选策略用于 Strategy Lab 研究扫描和回测，不直接参与默认生产信号。所有 runner 位于 `signals/candidates/`，输出统一 `StrategySignalRows`：`symbol`、`name`、`industry`、`score`、`signal`、`detail`。晋级前必须输出 `data/store/research/strategy_evidence/<strategy>.json` 并通过 OOS、强基准、成本和 regime 分解证据。

## 趋势跟随候选

- Purpose: 捕捉中期趋势延续，作为牛市或强趋势环境的 timing/selection 候选。
- Data requirements: `stock_daily`
- Formula: `40% MA20/MA60 趋势结构 + 30% close > MA120 + 30% 60D 动量横截面百分位`
- Failure modes: 震荡市追高回撤、均线信号滞后、强势股尾段拥挤。
- Promotion evidence: 与 trend-only、trend+breadth、current_champion 比较 OOS Sharpe/MaxDD，按 bull/sideways/bear 分解趋势环境贡献。

## Donchian突破候选

- Purpose: 捕捉接近 55 日高点且量能确认的突破标的。
- Data requirements: `stock_daily`
- Formula: `60% close / 55D high + 20% 20D volume ratio rank + 20% inverse 20D volatility rank`
- Failure modes: 假突破、缩量新高、财报或事件驱动缺口导致不可持续。
- Promotion evidence: 需要突破后持有期收益分布、失败突破回撤、成交量过滤增益和成本后换手评估。

## RPS相对强弱候选

- Purpose: 用相对强弱筛选 3-6 个月中期领先标的，避免只看绝对涨跌。
- Data requirements: `stock_daily`
- Formula: `45% 3M skip-1M RPS + 45% 6M skip-1M RPS + 10% close > MA120`
- Failure modes: 反转行情滞后、热门行业过度集中、skip window 不适合极端短趋势。
- Promotion evidence: 横截面 IC/ICIR、分组收益单调性、行业集中度约束和 OOS 基准胜率。

## 行业轮动候选

- Purpose: 先识别强势行业，再在行业内部选择相对强的股票。
- Data requirements: `stock_daily`, `sector`
- Formula: `60% 行业 20D 中位收益 rank + 25% 行业 60D 中位收益 rank + 15% 行业内个股 20D rank`
- Failure modes: 行业成员映射滞后、强行业内部弱股拖累、行业动量反转。
- Promotion evidence: 行业层收益贡献、行业切换频率、行业暴露上限和与市场研究行业雷达的一致性。

## 质量价值候选

- Purpose: 捕捉基本面质量和相对低估的组合候选，补充纯动量策略。
- Data requirements: `financials`, `valuation_daily`
- Formula: `35% ROE rank + 25% gross margin rank + 20% inverse PE rank + 20% inverse PB rank`
- Failure modes: 财报滞后、低估值陷阱、金融行业毛利率不可比、估值数据缺失。
- Promotion evidence: PIT 财务数据验证、估值分位稳定性、行业中性收益和价值陷阱过滤效果。

## 低波防御候选

- Purpose: 在弱市或高波动环境提供防御型股票候选。
- Data requirements: `stock_daily`
- Formula: `40% inverse 60D volatility rank + 30% drawdown control + 20% positive 20D trend + 10% liquidity rank`
- Failure modes: 低波拥挤、行情反弹时收益弹性不足、流动性代理不充分。
- Promotion evidence: bear/sideways regime 下的回撤控制、反弹期机会成本、换手和流动性冲击。

## 量能确认候选

- Purpose: 用成交量和价格动量共同确认短中期信号，作为 alpha confirmation 层。
- Data requirements: `stock_daily`, `moneyflow`
- Formula: `45% 20D volume ratio rank + 35% 20D price momentum rank + 20% turnover/moneyflow proxy rank`
- Failure modes: 放量出货、单日异常成交、moneyflow 缺失时代理口径偏弱。
- Promotion evidence: 量价背离样本诊断、成交量过滤前后收益对比、交易成本后净贡献。

## Regime门控候选

- Purpose: 根据当前 market regime 组合不同候选策略，作为 portfolio/risk overlay 研究候选。
- Data requirements: `market_regime`, `stock_daily`
- Formula: bull 偏向 `trend_following` + `rps_relative_strength`；sideways 偏向 `quality_value` + `low_vol_defensive`；bear 仅保留低波防御并加入现金防御代理。
- Failure modes: regime 误判导致错误风格暴露、门控切换过频、现金代理不能直接映射真实交易资产。
- Promotion evidence: risk-on/risk-off OOS 收益回撤比、regime 分解、与当前 champion 的换手和净收益对比。
