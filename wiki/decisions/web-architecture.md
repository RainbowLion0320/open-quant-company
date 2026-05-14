---
title: Web Architecture (Vue 3 + FastAPI)
created: 2026-05-12
updated: 2026-05-12
type: decision
tags: [architecture, frontend, backend, vue3, fastapi, websocket, ADR]
---

# Decision: Refactor Web UI to Vue 3 + FastAPI

- **Date**: 2026-05-12
- **Status**: Implemented
- **Author**: Quant Agent

## Stack

| Layer | Choice | 说明 |
|-------|--------|------|
| Frontend | Vue 3 (Composition API) | SPA, 响应式 |
| State | Pinia | 类型安全 store |
| Charts | ECharts 5 | Canvas 渲染，万点级流畅 |
| Styling | Tailwind CSS + CSS custom properties | 暗色主题，Linear-inspired design tokens |
| Typography | Inter (Google Fonts) | `font-feature-settings: "cv01","ss03"` |
| Build | Vite | ESM 原生 HMR |
| Backend | FastAPI | 异步原生，Pydantic 校验 |
| Real-time | WebSocket | 扫描进度推送 |

## 设计系统

基于 Linear.app 设计语言适配量化终端场景：
- 侧栏：72px 极窄图标列，hover tooltip
- 配色：青色主调 (#06b6d4)，翠绿/琥珀策略分色
- 卡片：暗色表面 + 半透明白边框 (`rgba(255,255,255,0.05)`)
- 滑块：青色渐变轨道 + 光环 thumb

## 页面结构 (8 页)

| 页面 | 路由 | 功能 |
|------|------|------|
| 市场总览 | `/` | Regime 卡片 + 三策略参数可调滑块 + 保存/重跑 |
| 策略中心 | `/strategies` | 信号表格 + WebSocket 进度 |
| 模拟交易 | `/portfolio` | PaperBroker 仓位/委托 |
| 个股搜索 | `/stocks` | 搜索入口 |
| 个股深挖 | `/stocks/:code` | K线 + DCF计算器 + 巴菲特评分 + 策略信号 |
| 回测分析 | `/backtest` | **N策略同屏叠加曲线 + 点击高亮 + 基准参照** |
| 信号历史 | `/signals` | 信号变更追踪 |
| 系统设置 | `/settings` | 通知开关 + 数据源状态 |

## DuckDB 读写分离

Web 以 `get_db(read_only=True)` 连接 DuckDB。注意 macOS 不支持真正的并发读写——扫描和 Web 需串行执行。见 [[duckdb-migration]]。

## 相关

- [[duckdb-migration]] — Web 查询 DuckDB
- [[tushare-mcp]] — 设置页配置 Tushare token
- [[strategy-evolution]] — 回测页展示三策略对比
- [[system-architecture]] — 完整系统分层
