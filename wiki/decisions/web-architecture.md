---
title: Web Architecture (Vue 3 + FastAPI)
created: 2026-05-12
updated: 2026-06-02
type: decision
tags: [architecture, frontend, backend, vue3, fastapi, websocket, ADR, command-center, monitor]
---

# Decision: Open Quant Company Console Web SPA

- **Date**: 2026-05-12 (initial), 2026-05-16 (command center upgrade), 2026-05-23 (refresh), 2026-05-27 (doc/code alignment), 2026-06-02 (doc/wiki/spec/code alignment)
- **Status**: Implemented
- **Author**: Open Quant Company + Codex

## Stack

| Layer      | Choice                               | 说明                                     |
| ---------- | ------------------------------------ | -------------------------------------- |
| Frontend   | Vue 3 (Composition API)              | SPA, 响应式                               |
| State      | Pinia                                | 类型安全 store                             |
| Charts     | ECharts 5                            | Canvas 渲染，万点级流畅                        |
| Styling    | Tailwind CSS + CSS custom properties | 暗色主题，Linear-inspired design tokens     |
| Typography | Inter (Google Fonts)                 | `font-feature-settings: "cv01","ss03"` |
| Build      | Vite                                 | ESM 原生 HMR                             |
| Backend    | FastAPI                              | 异步原生，Pydantic 校验                       |
| Real-time  | WebSocket                            | 扫描进度推送                                 |

## 设计系统

基于 Linear.app 设计语言适配量化终端场景：
- 侧栏：72px 极窄图标列，hover tooltip, SVG 图标
- 配色：青色主调 (#06b6d4)，翠绿/琥珀策略分色
- 卡片：暗色表面 + 半透明白边框 (`rgba(255,255,255,0.05)`)
- 滑块：青色渐变轨道 + 光环 thumb
- Regime 球体：CSS 动画光晕, 评分环形进度
- 预警面板：多级颜色 (success/warning/danger/info)

## 页面结构 (7 个一级入口)

| 页面 | 路由 | 功能 |
|------|------|------|
| 市场总览 | `/` | Regime 球体 + 核心指数相对强弱图 + 宏观快照 + 热门行业脉冲 |
| 市场研究 | `/research` | 二级 tab: 行业雷达 + 个股搜索；行业雷达以行业资金方块矩阵为主视图，`/stocks/:code` 保留为隐藏详情路由 |
| 策略实验室 | `/strategy-lab` | 二级 tab: 策略目录 + 信号历史 + 回测分析 + 证据面板 |
| 组合执行 | `/portfolio` | ★ PaperBroker 日频模拟: NAV权益曲线 + 持仓 + 交易记录 + 手动下单 |
| 流程图 | `/pipeline` | 关键参数计算透明度入口；四条关键链路 + Market Regime 细粒度 DAG |
| 数据中台 | `/datahub` | DataRegistry 健康扫描 + 全量大小统计 + 按时间分段 + 单表修复 |
| 系统控制 | `/system` | 二级 tab: 系统设置 + 配置中心 + CodeGraph 代码图谱 |

旧一级页面 redirect 已移除，避免隐藏入口继续影响导航编排。除 `/stocks/:code` 个股详情外，模块入口以七个一级路由、二级 tab 和 Pipeline 透明度页为准。

### Pipeline 透明度页 (2026-06-02)

`/pipeline` 展示 `market_regime`、`data_quality`、`strategy_evidence`、`portfolio_execution` 四条关键链路。后端 `GET /api/pipeline/{pipeline_key}` 复用生产服务和研究治理模块，统一返回 `summary` / `nodes` / `edges` / `warnings`。Market Regime 流程拆成市场输入、benchmark/breadth/volume 快照、规则评分、HMM 特征与推断、engine/hybrid/置信度决策分支、raw regime、dwell gate 和下游输出等细粒度节点。前端使用 `elkjs` layered + orthogonal routing，节点高度按内容测量自适应；节点点击后在右侧展示输入、输出和全部关键指标，选中节点时关联边显示流动高亮。该页面解释关键参数形成过程，不替代 Market 页面。

### 指挥中心 (2026-05-16 Codex 升级)

Market API 新增字段：
- `multi_asset[]` — 上证综指/沪深300/创业板指/科创50 核心指数序列；市场页用于相对强弱图，不再复制为全局行情 ticker
- `macro[]` — GDP/PMI/CPI/SHIBOR 宏观快照
- `alerts[]` — 智能预警 (regime/PMI偏离/黄金波动/策略完成)
- `freshness` — 数据新鲜度时间戳

前端 Market.vue 采用 Command Center 布局，含 animated regime orb、居中纯数字 regime score、4 个核心小仪表盘（Risk Buffer / A-share Breadth / Index Trend / Above MA20）、Confirmed / Raw / Pending / Dwell 紧凑状态卡、核心指数相对强弱图、宏观快照行和热门行业脉冲。大图展示上证综指/沪深300/创业板指/科创50 的归一化强弱对比；全局页脚只显示 REGIME / FRESH、CEO 会话模型上下文与三态纯色系统健康灯，不再展示行情 ticker 或文字健康状态；策略明细归属策略实验室，行业页承载完整排名与信号分布，市场总览只保留 Top5 热点概览，避免重复缩略看板。

### 行业雷达方块矩阵 (2026-05-27)

Sectors.vue 在行业排名表上方增加行业资金方块矩阵。每个申万一级行业是独立方块，边长按 `amount_5d_avg`（近 5 日平均成交额）开方映射，保持方形且让面积近似表达资金量；颜色可在资金热力（5日涨跌幅）、动量热力（20日涨跌幅）、信号热力（策略买入集中度）之间切换。`data/market/sectors.py` 从申万行业指数成交额或成员股 OHLCV `amount` 聚合资金字段。行业方块内部不展示具体股票，避免行业雷达变成个股看板；点击行业方块沿用原行业级信号详情展开，不把方块矩阵当作精确数值表替代品。

### 系统设置顶部状态 (2026-06-20 精简)

系统设置页顶部只保留对运行决策有直接价值的集成状态：
- API: `/api/system/api-health` (AKShare/Tushare/LLM providers/Telegram 配置状态)
- API: `/api/system/cron-jobs` (cron job 状态)
- 前端: `Settings.vue` 展示 API Health + Cron Jobs，不展示本机硬件资源、资源历史或进程表。
- **职责边界:** Settings 顶部承载只读运行状态，下方管理认证、通知、数据源、策略状态、风控和审计；Config Center 继续承担可调参数 schema 编辑。

### 代码图谱 (2026-06-06 对齐)

CodeGraph 使用 Three.js WebGL 3D 星空图，零外部图谱库依赖。直接从 `GET /api/codegraph/graph` 拉取模块、文件、符号和调用关系，渲染为交互式代码图谱。节点按代码类型分色，链接按 `imports / calls / instantiates / references / extends` 区分；悬浮显示 tooltip，点击模块/文件/符号逐级下钻，选中节点时高亮流入和流出边。

`GET /api/codegraph/diagnostics` 提供确定性架构诊断：循环依赖、跨层调用、热点耦合、孤岛候选、内部 API 泄漏和大文件高连接。诊断结果异步叠加到图谱节点和面板中，不调用大模型，不阻塞首屏图谱加载。

物理模拟：节点间 3D 斥力（inverse-square）+ 图中心引力 + 链接弹簧力 + 阻尼。Three.js 负责 WebGL 渲染和 OrbitControls 交互。页面只读展示当前 `.codegraph/`，索引同步必须由用户显式点击 Sync/Rebuild。

详见 [[codegraph-visualization]]。

## DuckDB 读写分离

Web 以 DuckDB `:memory:` 注册 Parquet 视图，只读查询不持有单文件数据库写锁。数据写入统一通过 DataHub 的 Parquet 原子写入和 manifest 记录完成，Web 查询层只读消费当前落盘数据。见 [[duckdb-migration]] 与 [[datahub]]。

## 相关

- [[duckdb-migration]] — Web 查询 DuckDB
- [[tushare-mcp]] — Token 管理: 环境变量优先, 统一由 data/ingestion/tushare_utils.py 获取
- [[strategy-evolution]] — 回测页展示多策略对比
- [[system-architecture]] — 完整系统分层
