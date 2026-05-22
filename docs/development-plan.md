# Quant Agent 下一阶段开发计划

> 日期: 2026-05-22
> 来源: Codex 对当前 Git、Wiki、PRD/spec、Web UI 的复核
> 目的: 给后续 agent 提供可直接执行的计划。上一版架构计划的大部分 P0/P1/P2 已落地，本文件替代旧计划。

## 当前判断

上一轮架构改造已基本完成，代表性提交包括:

- `8af94b3` 到 `44bae92`: 依赖入口、PRD/spec 验收矩阵、API 合约、ResearchRun、PIT、PortfolioTarget、订单账本、Provider/DataContract、质量门禁、前端拆包、Settings 安全边界、策略晋级、多资产契约。
- `9e7f8ff codex: harden Claude rollout regressions`: 修复 Claude rollout 后的 provider 路由、数据契约、质量门禁、认证、PIT 检查、账本并发和前端构建问题。

下一阶段重点不再是继续铺底层骨架，而是把 Web UI 和数据中台的展示能力从“功能集合”升级成“研究终端”:

- 补齐行业/板块作为一级研究对象。
- 收敛系统信息和系统设置的职责边界。
- 刷新已过期的验收矩阵和 Web 架构文档。
- 给关键 Web 页面补自动化 smoke/e2e，减少后续 agent 每次重复肉眼检查。

## 旧计划已完成或需要改写的部分

这些内容不应再作为下一阶段主计划重复执行，只需要补文档状态或小范围修正。

| 旧计划项 | 当前状态 | 后续动作 |
|---|---|---|
| P0-1 统一依赖、Makefile、CI | 已落地，已补 `requirements-dev.txt` | 只需在验收矩阵中更新状态 |
| P0-2 PRD/spec 验收矩阵 | 已有 `docs/acceptance-matrix.md` | 需要刷新过期缺口 |
| P0-3 API 合约统一 | 已部分落地，核心异常处理和多端点 response_model 已增强 | 需要重新审计真实剩余缺口，不要沿用旧结论 |
| P0-4 ResearchRun / ExperimentRegistry | 已有 `research/runs.py` | 可追加 Web 查询入口，但不是本阶段主线 |
| P0-5 PIT 数据视图 / lookahead check | 已有 `MarketDataView` 和 `scripts/lookahead_check.py`，并补回归测试 | 后续扩大覆盖到更多策略 |
| P1-6 PortfolioTarget 流水线 | 已落地 | 只补使用文档和策略接入一致性 |
| P1-7 执行层订单状态机和事件账本 | 已落地，并修复 parent event 链 | 后续补部分成交/拒单场景测试 |
| P1-8 ProviderAdapter / DataContract / BackfillLedger | 已落地，并修复多处 provider/contract 错配 | 本阶段要在行业数据上继续扩展 |
| P1-9 数据质量门禁 | 已落地，并修复 `schema_mismatch` 被覆盖问题 | 新增行业维度质量规则 |
| P1-10 前端 chunk 优化 | 已落地，`npm run build` 当前无大 chunk 警告 | 更新验收矩阵 |
| P1-11 Settings 安全边界 | 已落地 API Key、audit、run mode | 下一阶段重构页面职责 |
| P2-12 策略晋级制度 | 已有策略卡片和生命周期 | 后续接行业暴露和 OOS 门槛 |
| P2-13 多资产真实数据契约 | 已有 data_source 元数据和 Web 可视化 | 后续继续减少 proxy，但非本阶段第一优先级 |

## 已确认的遗漏、错误和文档漂移

### 1. 行业/板块缺少一级页面

PRD 写了“A 股全量 + 申万 31 行业”，策略文档也多次提到板块轮动、行业白名单、行业特殊处理，但 Web 目前只在个股、策略表里零散展示 `industry` 字段。

影响:

- 无法快速判断当前强势行业、弱势行业和行业扩散。
- 无法看到策略信号是否集中在少数行业。
- 无法看到组合持仓是否有行业暴露过度。
- 控制论策略的板块轮动缺少可解释的 Web 展示。

### 2. 行业行情数据链路不完整

`data/provider.py` 已有 `sw_daily` 的 Tushare dispatch，但 `config/settings.yaml` 的 `data_registry` 里没有正式行业行情维度，DataContract、DataHub 路径、质量门禁、repair/backfill 也未形成闭环。

本阶段应补:

- `sector_sw_daily`: 申万行业指数日行情。
- `sector_membership`: 股票到申万行业映射快照。
- `sector_signal_snapshot`: 策略信号按行业聚合快照。
- `sector_exposure_snapshot`: 组合持仓按行业暴露快照。

### 3. 系统信息和系统设置内容重复

当前 `ActivityMonitor.vue` 展示 Telegram、Data Sources、System Info，并且可以直接 toggle 通知；`Settings.vue` 也展示 Telegram、Data Sources、System Info。

问题:

- 两个页面都在展示同一类系统配置摘要，后续很容易样式和逻辑漂移。
- Monitor 页面混入写配置操作，和“系统观测”职责不一致。
- Settings 页面又包含很多只读系统信息，和“配置管理”职责不一致。

目标边界:

- `/monitor`: 只读观测。资源、DeepSeek 用量、API Health、Services、Cron Jobs、最近错误、数据新鲜度。
- `/settings`: 配置和安全边界。运行模式、API Key、通知配置、数据源开关、策略参数、风险参数、审计日志。

### 4. 文档与代码状态不一致

需要刷新:

- `docs/acceptance-matrix.md`: 仍把前端 chunk 和 Settings 安全边界标为旧缺口，且 API 合约缺口描述可能不再准确。
- `wiki/decisions/web-architecture.md`: 页面数量、`/settings` 是否独立、系统信息页面职责需要和当前代码重新对齐。
- `docs/specs/05-web-platform.md`: Settings/System 的职责描述需要根据重构结果更新。

### 5. Web 自动化验收不足

现在主要依赖后端 pytest 和 `npm run build`。缺少针对真实页面渲染的 smoke/e2e:

- 市场总览。
- 新增行业页面。
- 系统信息。
- 系统设置。
- 数据库健康。
- 策略中心。

### 6. 策略的行业逻辑还偏静态

`cybernetic` 和 `multifactor` 都提到行业/板块，但目前更多依赖静态 favored sectors 或信号表字段，缺少行业指数、行业动量、行业资金、行业信号强度共同驱动。

## 下一阶段目标

交付一个“行业雷达 + 清晰系统后台 + 文档验收同步”的版本。

完成后应达到:

- Web 导航新增行业/板块一级入口。
- 行业行情、信号、持仓暴露能在同一页面解释。
- `/monitor` 和 `/settings` 无重复写操作，边界清晰。
- 文档能准确告诉后续 agent 当前完成了什么、还缺什么。
- 核心 Web 页面有自动化 smoke/e2e，避免 UI 回归靠人工反复检查。

## P0: 文档和验收状态收口

### P0-1 刷新验收矩阵

文件:

- `docs/acceptance-matrix.md`

任务:

- 重新核对 6 个能力域当前状态。
- 更新已完成项: 前端 chunk、Settings 安全边界、ResearchRun、PIT、Provider/DataContract、质量门禁、多资产契约。
- 把旧的“P0-3/P1-10 将增强”描述改成当前真实状态。
- 对仍缺测试的条目保留“待补测试”，不要虚假标 OK。

验收:

- 矩阵中的“关键缺口”只列当前真实缺口。
- 每条 Web 相关能力至少有手工验收命令或待补自动化测试说明。

### P0-2 刷新 Web 架构文档

文件:

- `wiki/decisions/web-architecture.md`
- `docs/specs/05-web-platform.md`

任务:

- 更新当前页面结构。
- 明确 `/monitor` 和 `/settings` 的职责边界。
- 加入行业/板块页面规划。
- 删除或改写已经不准确的“Settings 已合并/移除”类描述。

验收:

- 文档页面列表和 `web/frontend/src/router/index.ts` 一致。
- 文档中的 API 列表和 `web/api/routes/*` 一致。

## P1: 系统信息和系统设置边界重构

### P1-1 重构 `/monitor` 为只读观测页

文件:

- `web/frontend/src/views/ActivityMonitor.vue`
- `web/frontend/src/api/index.ts`
- `web/api/routes/system.py`

任务:

- 移除 Monitor 页里直接写配置的操作，例如 Telegram toggle。
- 保留只读状态: Telegram enabled/disabled、Data Sources、API Health、Services、Cron Jobs、System Info。
- 对需要修改的地方提供“去设置”入口，而不是在 Monitor 内保存配置。
- 增加“最近错误/异常”区: API health error、cron last_status、服务异常、数据质量异常。

验收:

- Monitor 页面不调用 `api.saveSettings()`。
- Monitor 页面刷新不会修改 `config/settings.yaml`。
- `npm run build` 通过。

### P1-2 重构 `/settings` 为配置管理页

文件:

- `web/frontend/src/views/Settings.vue`
- `web/api/routes/settings.py`
- `web/api/auth.py`

任务:

- 移除 Settings 页里重复的只读系统信息网格，保留必要摘要即可。
- 配置分组建议:
  - 运行模式和认证: research/paper/live, API Key status。
  - 通知: Telegram 开关、signal_change_only。
  - 数据源: AKShare/Tushare/paid/future 维度开关和修复策略。
  - 策略: 启用状态、晋级状态、风险提示。
  - 风控: 最大仓位、最大回撤、交易频率、live mode 禁写规则。
  - 审计: 最近配置变更。
- 敏感写入继续走确认弹窗和 audit ledger。

验收:

- Settings 页面仍可保存合法配置。
- live mode 下禁止写入的行为保持不变。
- API Key 不自动写回 tracked `config/settings.yaml`。

## P2: 行业/板块数据中台

### P2-1 增加行业数据维度

文件:

- `config/settings.yaml`
- `data/data_registry.py`
- `data/contract.py`
- `data/provider.py`
- `data/datahub.py` 或相关路径 helper

新增维度建议:

| key | 来源 | 频率 | 说明 |
|---|---|---|---|
| `sector_sw_daily` | tushare_free | daily | 申万行业指数日行情，来自 `sw_daily` |
| `sector_membership` | tushare_free/local | event | 股票到申万一/二级行业映射 |
| `sector_signal_snapshot` | computed | daily | 各策略信号按行业聚合 |
| `sector_exposure_snapshot` | computed | daily | Paper/Portfolio 持仓按行业暴露 |

要求:

- 每个维度必须有 cache 路径、label、SLA、DataContract。
- 如果 `sw_daily` 不可用，允许用个股 OHLCV 按行业聚合生成 proxy，但必须标记 `data_source="proxy"`。
- Web 不允许在页面请求时触网，只读缓存。

验收:

- `DataRegistry.validate()` 通过。
- `DataQualityGate.check_dimension()` 能识别行业维度 missing/stale/schema_mismatch。
- Provider 能正确路由 `sector_sw_daily` 到 Tushare `sw_daily` 或显式 fallback。

### P2-2 增加行业快照计算脚本

建议新增:

- `scripts/build_sector_snapshots.py`
- 或放入 `data/sectors.py` + 脚本入口。

计算内容:

- 行业最近 1D/5D/20D/60D 涨跌幅。
- 行业波动率和量能变化。
- 行业内股票数量、可用数据数量、数据新鲜度。
- 策略信号按行业聚合: total、buy_count、buy_ratio、avg_score、top_symbol。
- 组合持仓按行业聚合: weight、market_value、position_count。

验收:

- 生成 `data/store/sector/*.parquet` 或约定路径。
- 空数据时脚本不崩溃，并产出清晰 warning。
- 有单元测试覆盖行业聚合逻辑。

### P2-3 行业 API

建议新增:

- `web/api/routes/sectors.py`

端点:

- `GET /api/sectors/overview`
- `GET /api/sectors/{industry}`
- `GET /api/sectors/{industry}/stocks`
- `GET /api/sectors/exposure`

返回字段建议:

- 行业名称、行业代码、rank、returns、momentum、volatility、turnover/volume。
- signal summary: buy_ratio、avg_score、top picks。
- exposure summary: portfolio_weight、overweight/underweight。
- series: 行业指数走势。
- `data_source`: real/proxy/missing。
- freshness: 最新日期。

验收:

- 端点有 Pydantic response model 或 contract test。
- 缺缓存时返回空结构和明确状态，不返回 500。
- API 不触发外部网络。

## P3: 行业/板块 Web UI

### P3-1 新增行业雷达页面

文件:

- `web/frontend/src/views/Sectors.vue`
- `web/frontend/src/router/index.ts`
- `web/frontend/src/App.vue`
- `web/frontend/src/api/index.ts`

布局建议:

- 顶部摘要: 强势行业、弱势行业、行业扩散、信号集中度、组合行业集中度。
- 左侧/主区域: 31 行业热力图或矩阵。
- 右侧: 行业排名表，支持按 1D/5D/20D/信号强度/持仓权重排序。
- 下方: 策略信号行业分布、持仓行业暴露。

交互:

- 点击行业进入详情视图或详情面板。
- 从策略中心、个股详情跳转到对应行业。
- 所有图表加载空数据态，不能白屏。

验收:

- `npm run build` 通过。
- 页面在无行业数据时有专业空态。
- 页面在移动/窄屏下不出现表头和列错位。

### P3-2 行业详情视图

详情内容:

- 行业指数 K 线或趋势线。
- 成分股表格: symbol、name、signal、score、return、market cap。
- 行业策略信号: 各策略 buy/hold/sell 分布。
- 行业基本面摘要: 可先用已有信号/财务字段聚合，后续再接完整财务。
- 行业风险: 波动率、回撤、数据新鲜度。

验收:

- 任一行业点击后可稳定展示。
- 行业名称包含中文时路由和 API 参数编码正常。

## P4: 策略和组合联动

### P4-1 行业强弱进入策略解释层

涉及:

- `signals/multifactor.py`
- `cybernetics/orchestrator.py`
- `scripts/compute_signals.py`
- `docs/strategies/*.md`

任务:

- 多因子 Market 维度接入行业动量/行业信号强度。
- 控制论策略的 favored sectors 从纯静态列表升级为“regime base + sector momentum overlay”。
- 信号输出增加 sector_reason 或 industry_reason，便于 Web 解释。

验收:

- 行业数据缺失时策略能降级，不崩溃。
- 策略信号 detail 能说明行业加分/减分来源。

### P4-2 组合行业暴露和风险提醒

涉及:

- `broker/portfolio_target.py`
- `broker/risk.py`
- `web/frontend/src/views/Portfolio.vue`
- `web/api/routes/portfolio.py`

任务:

- Portfolio 页面增加行业暴露分布。
- 增加行业集中度预警，例如单行业权重 > 配置阈值。
- Risk 层可选支持行业上限，不默认强制阻断。

验收:

- Paper 持仓能按行业汇总。
- 无行业映射的持仓归入“待分类”。
- 行业风险提醒不影响当前交易流程，除非配置显式启用。

## P5: 自动化测试和质量门禁

### P5-1 前端 smoke/e2e

建议:

- 优先使用已有 Browser/Playwright 能力。
- 新增最小 smoke 脚本，覆盖:
  - `/`
  - `/sectors`
  - `/monitor`
  - `/settings`
  - `/db-health`
  - `/strategies`

验收:

- 启动本地 API + 前端后，所有核心页面无 console error。
- 截图或 DOM 检查确认关键区域非空。
- 表格表头和列对齐检查至少覆盖行业页和 DB Health。

### P5-2 后端合约测试

新增测试建议:

- `tests/test_sector_api.py`
- `tests/test_sector_snapshots.py`
- `tests/test_web_information_architecture.py`

覆盖:

- 行业 API 缺数据不 500。
- 行业聚合数值正确。
- Monitor 不调用 settings write。
- Settings live mode 禁写保持有效。
- `sector_sw_daily` contract 缺必需列时报 `schema_mismatch`。

验收:

- `/Users/fushao/.hermes/hermes-agent/venv/bin/python3 -m pytest -q` 通过。
- `npm run build` 通过。
- `scripts/lookahead_check.py --quick --n 5` 通过。

## P6: 文档收尾

完成代码后必须同步:

- `docs/acceptance-matrix.md`: 更新行业页面、行业 API、系统页边界、测试状态。
- `docs/specs/01-data-pipeline.md`: 增加行业数据维度。
- `docs/specs/02-signal-system.md`: 增加行业强弱如何参与策略解释。
- `docs/specs/05-web-platform.md`: 增加行业页面，更新 Monitor/Settings。
- `wiki/decisions/web-architecture.md`: 更新页面结构。
- `wiki/reference/data-dimensions.md`: 增加行业维度。
- `wiki/reference/data-schema.md`: 增加行业快照 schema。

验收:

- 文档中的路由、API、文件路径和代码一致。
- 新增计划完成后，本文件应再次更新: 已完成项移到“当前状态”，不要无限累积旧任务。

## 推荐执行顺序

1. P0: 先刷新验收矩阵和 Web 架构文档，避免后续 agent 依据旧文档误判。
2. P1: 重构 `/monitor` 和 `/settings` 的职责边界，先解决重复和误写配置问题。
3. P2: 补行业数据维度、契约、快照脚本和行业 API。
4. P3: 新增行业雷达 Web 页面。
5. P4: 把行业强弱接入策略解释和组合暴露。
6. P5: 补 Web smoke/e2e 和后端合约测试。
7. P6: 同步 PRD/spec/wiki/reference。

## Agent 拆分建议

- Agent A: 文档同步。负责 P0 和 P6，不改业务代码。
- Agent B: 数据中台。负责 P2 的 registry、contract、snapshot、quality gate。
- Agent C: Web UI。负责 P1 和 P3，重点检查布局、表格对齐、空态、响应式。
- Agent D: 策略/组合。负责 P4，避免直接改数据抓取和 UI。
- Agent E: 测试。负责 P5，可在 B/C/D 并行后统一补合约和 smoke。

## 非目标和约束

- 不要在 Web 页面加载时触发外部行情 API 请求，Web 只读本地缓存。
- 不要把系统信息和系统设置合并成一个大页面；应通过职责边界减少重复。
- 不要静默使用 proxy 数据；任何 proxy 必须在 API 和 Web 明确标记。
- 不要为了行业页面重写整个 Market 页面；行业是一级新模块，不是 Market 的附属卡片。
- 不要为了视觉效果牺牲表格可读性；行业排名、成分股、暴露表必须列宽稳定、表头对齐。
- 不要删除历史文档中的有效上下文；如内容过期，应改写或标注 superseded。
