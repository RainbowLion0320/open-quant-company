# 盈利策略发现目标

> 更新: 2026-07-01

Open Quant Company 下一阶段的核心目标不是继续扩展功能面，而是先找到至少一条可以被证据支持的正期望策略链路。这里的“盈利”不指承诺收益，也不指样本内曲线好看；它指在真实数据、真实成本、样本外检验和可复现 evidence 下，仍然有资格进入 paper 或小规模实盘验证的策略。

## 北极星目标

在继续扩大资产、数据源、Agent、Web 页面之前，先完成一条最小但正式的投资闭环：

```text
可用环境 -> 新鲜数据 -> 策略信号 -> score panel -> 回测 evidence
-> OOS / IC / ICIR 或 overlay evidence -> 组合建议 -> 风控 -> paper 验证
```

只有这条链路跑通，项目才算从“量化操作系统外壳”进入“可验证研究系统”。

## 当前判断

当前仓库已经有丰富的 Web UI、CLI、Agent、数据源治理、AST/测试设计诊断和多资产展示，但策略收益这条主线仍未闭环。

- 策略目录已有 13 个策略，但当前不能把任何一个策略视为已经通过正式盈利验证。
- 生命周期检查仍有数据 stale、缺 backtest artifact、缺策略 evidence、缺 crypto 历史数据、部分 Tushare 权限不可用等 blocker。
- 多资产链路目前是“启用 + 研究/展示可用”，不是五类资产全部交易化完成。
- 数据源能力发现很宽，但项目正式接入和策略实际消费的数据维度仍然有限。

因此下一阶段不再以“又支持了多少模块”为成功标准，而以“是否产出可复现、可比较、可晋级的策略 evidence”为标准。

## 盈利策略定义

一个策略只有同时满足下面条件，才可以被称为“盈利候选”：

| 维度 | 最低要求 |
| --- | --- |
| 数据 | 所有必需数据维度 fresh，缺失、权限不足、stale 必须阻断。 |
| 回测 | 使用正式 PipelineBacktest，保存 trade log、score panel、成本、复权口径、benchmark 和配置快照。 |
| 样本外 | 明确 OOS 区间，不允许只看全样本或样本内优化结果。 |
| 成本 | 手续费、印花税、滑点、换手和交易单位必须计入。 |
| 证据 | 选股类策略必须有 IC / ICIR / 分组收益等 alpha evidence；风险覆盖类策略必须有回撤降低、尾部风险、参与率、错失上涨等 overlay evidence。 |
| 稳健性 | 至少跨牛、熊、震荡或不同年份分段仍然不崩。 |
| 可执行性 | 输出能转成组合目标或 paper order，不依赖无法交易的数据或假价格。 |

未满足这些条件的策略可以继续研究，但不能标记为 production。

## 收敛优先级

### P0：修通证据链

目标：让 `astroq lifecycle check --json` 不再因为系统自身设计残留或缺失 artifact 阻断。

必须处理：

- 清理已经删除模块留下的 blocker，例如 `system_llm_usage` 不应继续阻断生命周期。
- 解决当前环境变量和旧 artifact 状态不一致的问题，尤其是 `TUSHARE_TOKEN`、数据源审计时间和 Web 健康状态。
- 补齐或明确阻断 stale 数据：`stock_valuation`、`fund_daily`、`fund_nav`、`futures_daily`、债券利率、行业快照、宏观 GDP。
- 对无权限接口保持 `no_permission`，不要伪造数据，也不要把无权限维度算成可用。
- 重新生成正式 backtest artifact、score panel 和 strategy competition evidence。

验收：

```bash
astroq lifecycle check --json
astroq strategy compete --json
astroq strategy data-coverage --json
```

结果必须能清楚说明每个策略是 pass、blocked、insufficient evidence 还是 killed。

### P1：公平比较 13 个策略

目标：让所有策略在同一套 universe、时间区间、成本、benchmark、复权口径和 OOS 规则下比较。

要求：

- 先以 A 股和 ETF 为主战场，不把期货、债券、加密硬塞进策略竞赛。
- 股票策略继续只跑股票；跨资产配置只有在 crypto/futures/bond 数据满足 freshness 和交易语义后再纳入正式排名。
- 每个策略必须输出同一类 evidence schema，不能有的只有收益、有的只有信号、有的只有说明。
- 候选策略如果长期没有 alpha evidence，应降级为 research archived 或删除，不继续占据 Web 与配置中心注意力。

验收：

- 至少能列出每个策略的净收益、Sharpe、最大回撤、换手、命中率、IC、ICIR、样本数和 blocker。
- 对风险覆盖策略使用 overlay evidence，不强行要求 IC。
- 对 ML 策略明确训练窗口、特征覆盖、OOS 切分和模型版本。

### P2：集中优化少数候选

目标：不要 13 个策略一起平均用力。先筛出 2 到 3 个最有希望的方向做深入研究。

优先方向：

- `multifactor`：作为主 alpha，检查因子有效性、因子相关性、行业暴露和换手成本。
- `quality_value` / `buffett`：作为低频质量价值方向，重点看长期稳定性和估值陷阱。
- `trend_following` / `rps_relative_strength`：作为趋势动量方向，重点看市场状态过滤和回撤控制。
- `ml_lgbm`：只有在特征覆盖和 OOS 训练闭环稳定后继续推进，不允许为了跑通而填 0 或降低证据门槛。

不优先：

- 为了页面完整继续新增策略。
- 为了多资产叙事强行扩展加密或期货交易策略。
- 为了让指标好看调低门槛或删除真实阻断。

### P3：paper 验证

目标：只有 evidence 达标的策略进入 paper，不让 paper 成为“什么都能跑”的展示层。

要求：

- paper 订单必须能追溯到 strategy evidence、组合目标、风控结果和价格来源。
- paper 期间记录信号是否延续有效、实际可成交性、换手、滑点假设偏差。
- paper 不是最终成功标准，只是 live 前的运行验证。

### P4：再考虑扩展系统面

只有当至少一条策略进入 paper 并稳定产出 evidence 后，才继续考虑：

- 更完整的期货/加密 live adapter。
- 更多外部数据源接入。
- 更复杂的 Agent 协作。
- 新策略族和更多 Web 可视化。

## 决策规则

| 结果 | 处理 |
| --- | --- |
| 数据缺失或无权限 | blocked，先修数据或降级需求，不进入策略排名。 |
| 样本内好、OOS 差 | 不晋级，记录过拟合风险。 |
| 收益可看但换手过高 | 优先调组合/交易约束，不直接宣传盈利。 |
| IC/ICIR 长期接近 0 | 降级或删除，不继续消耗主线注意力。 |
| 风控 overlay 降低回撤但显著错失上涨 | 作为风险工具保留，不当作 alpha 策略。 |
| 连续两轮正式竞赛无改进 | 归档策略或降级为 research。 |

## 成功标准

项目下一阶段的成功不是“页面更多”，而是至少达到以下状态：

1. 生命周期检查能区分真实阻断和可运行链路，不再混入废弃模块。
2. 13 个策略都有统一、可复现的 evidence 状态。
3. 至少 1 个策略满足盈利候选定义，并进入 paper 验证。
4. CEO Office 能回答“当前最值得关注的策略是什么、为什么、证据在哪里、还缺什么”，而不是展示工程步骤。
5. 文档、Web、CLI 对策略状态的描述一致。

## 非目标

- 不承诺任何收益。
- 不用假数据补缺口。
- 不把“发现了很多数据源能力”当作策略有效性的证据。
- 不为了让系统看起来完备而隐藏 blocker。
- 不继续无限新增模块来绕开“策略不赚钱”这个核心问题。
