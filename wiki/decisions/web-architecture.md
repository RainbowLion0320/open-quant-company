---
title: Web Architecture (Vue 3 + FastAPI)
created: 2026-05-12
updated: 2026-05-23
type: decision
tags: [architecture, frontend, backend, vue3, fastapi, websocket, ADR, command-center, monitor]
---

# Decision: Quantum Terminal Web SPA

- **Date**: 2026-05-12 (initial), 2026-05-16 (command center upgrade), 2026-05-23 (refresh)
- **Status**: Implemented
- **Author**: Quant Agent + Codex

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

## 页面结构 (12 页)

| 页面 | 路由 | 功能 |
|------|------|------|
| 市场总览 | `/` | Regime 球体 + 多资产跟踪器 (data_source 标识) + 宏观快照 + 策略矩阵 + 智能预警 |
| 策略中心 | `/strategies` | 策略生命周期状态徽章 + 信号表格 + WebSocket 进度 |
| 模拟交易 | `/portfolio` | ★ PaperBroker 日频模拟: NAV权益曲线 + 持仓 + 交易记录 + 手动下单 |
| 个股搜索 | `/stocks` | 搜索入口 |
| 个股深挖 | `/stocks/:code` | K线 + DCF计算器 + 巴菲特评分 + 策略信号 |
| 回测分析 | `/backtest` | N策略同屏叠加曲线 + 点击高亮 + 基准参照 |
| 行业雷达 | `/sectors` | 申万31行业排名表 + 1/5/20/60日动量 + 信号分布 + 组合敞口 |
| 信号历史 | `/signals` | 信号变更追踪 (含 strategy/old_signal/new_signal) |
| 系统信息 | `/monitor` | 只读观测: CPU/MEM/DISK + DeepSeek 用量 + Top 进程 + API Health + Services + Cron Jobs (不写配置) |
| 数据库健康 | `/db-health` | 34 维度健康扫描 + 全量大小统计 + 按时间分段 + 单表修复 |
| 记忆图谱 | `/hindsight` | Hindsight 知识图谱 — Canvas 力导向图, 悬浮/点击探索节点关系 |
| 系统设置 | `/settings` | 配置管理: 运行模式 + API Key + Telegram 通知 + 数据源 + 策略/风控参数 + 审计日志 |

### 指挥中心 (2026-05-16 Codex 升级)

Market API 新增字段：
- `multi_asset[]` — A股/黄金ETF/10Y国债/SHIBOR 实时卡片+42日趋势线
- `macro[]` — GDP/PMI/CPI/SHIBOR 宏观快照
- `strategy_matrix[]` — 已注册策略的买比/评分/Top1标的
- `alerts[]` — 智能预警 (regime/PMI偏离/黄金波动/策略完成)
- `freshness` — 数据新鲜度时间戳

前端 Market.vue 完全重写：从4张简单卡片升级为 Command Center 布局，含 animated regime orb、4资产跟踪器、宏观快照行、策略矩阵卡片、预警面板。仅读 Parquet 缓存，无网络阻塞。

### 系统信息 (2026-05-21 升级, 2026-05-23 边界明确)

独立 SQLite WAL 时序库 `system_monitor.db`：
- API: `/api/system/monitor` (实时快照) + `/api/system/history` (趋势)
- 新增: `/api/system/api-health` (AKShare/Tushare/DeepSeek/Hindsight/Telegram 配置状态)
- 新增: `/api/system/cron-jobs` (cron job 状态, 读 ~/.hermes/cron/jobs.json)
- 新增: `/api/system/service-status` (Chrome CDP + DeepSeek cookie 倒计时)
- 新增: `/api/system/deepseek-usage` (CDP 日度 Token 用量)
- 前端: ActivityMonitor.vue, CPU/MEM/DISK + DeepSeek 用量 + Top 进程 + API Health + Services + Cron Jobs
- Token 三来源覆盖: Hermes state.db + factor_hypothesis log + Hindsight /metrics
- **职责边界 (2026-05-23):** Monitor 为只读观测页，不调用 `api.saveSettings()`。配置操作通过"去设置"入口引导到 `/settings`。

### 记忆图谱 (2026-05-17)

Canvas 自建力导向图，零外部图谱库依赖。直接从 Hindsight REST API 拉取节点和链接数据，渲染为交互式知识图谱。节点按类型分色（青色 observation / 紫色 experience），链接按来源区分（entity共享/同轮对话/合并提炼/tag共享）。不支持节点文字标签——悬浮显示 tooltip，点击展开详情面板。缩放、拖拽、平移全支持。

物理模拟：节点间斥力（inverse-square）+ 图中心引力 + 链接弹簧力 + 阻尼。Canvas 2D 渲染，DPR 适配视网膜屏。数据非实时——页面加载时拉取一次，手动按钮可刷新。

详见 [[hindsight-graph]]。

## DuckDB 读写分离

Web 以 `get_db(read_only=True)` 连接 DuckDB。注意 macOS 不支持真正的并发读写——扫描和 Web 需串行执行。见 [[duckdb-migration]]。

## 相关

- [[duckdb-migration]] — Web 查询 DuckDB
- [[tushare-mcp]] — Token 管理: 环境变量优先, 统一由 data/tushare_utils.py 获取
- [[strategy-evolution]] — 回测页展示四策略对比
- [[system-architecture]] — 完整系统分层
