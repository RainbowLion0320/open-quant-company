---
title: CodeGraph Visualization (代码图谱可视化)
created: 2026-06-06
updated: 2026-06-06
type: concept
tags: [web, codegraph, architecture, three.js, 3d]
---

# CodeGraph Visualization

CodeGraph 可视化是 `/system?tab=codegraph` 的代码结构探索页。它读取本地 `.codegraph/codegraph.db`，把项目的模块、文件、符号和调用/引用关系渲染成 Three.js 3D 图谱。

## 数据来源

```
.codegraph/codegraph.db
  ├── files  → 文件路径、语言、符号数、索引时间
  ├── nodes  → file/class/function/method/component/route/interface
  └── edges  → contains/imports/calls/instantiates/references/extends
```

Web API 固定服务当前仓库，不接受任意项目路径：

| Endpoint | 用途 |
|----------|------|
| `GET /api/codegraph/status` | 索引状态、统计、pending changes |
| `GET /api/codegraph/graph` | module/file/symbol 三层图谱 |
| `GET /api/codegraph/search` | 文件和符号搜索 |
| `GET /api/codegraph/neighborhood` | 单节点调用/引用邻域 |
| `GET /api/codegraph/diagnostics` | 确定性架构诊断和风险叠加 |
| `POST /api/codegraph/sync` | 显式触发 `sync` 或 `rebuild` |

## 交互模型

- 默认展示模块级总览，避免一次性渲染 6000+ 符号。
- 点击模块下钻到文件级；点击文件下钻到符号级；点击符号进入邻域图。
- 边类型筛选支持 `imports / calls / instantiates / references / extends`。
- 选中节点时，流入边和流出边使用不同颜色并做轻量脉冲动画。
- 架构诊断面板异步加载；节点保留类型颜色，同时按风险分增强发光和缩放。
- Sync/Rebuild 由用户显式点击，不在页面加载时自动改写 `.codegraph/`。

## 架构诊断

CodeGraph 诊断层是确定性 architecture smell detector，不调用大模型，不做主观代码评审。所有诊断都必须能从 `.codegraph/codegraph.db`、文件行数/符号数和 90 天 git churn 复现。

首批规则：

- `cycle`: 模块/文件依赖循环。
- `cross_layer`: 违反分层的直接调用，例如 route 直接依赖 data 内部层。
- `hotspot`: 高 fan-in/fan-out，或高连接度叠加高 git churn。
- `orphan`: 生产目录中没有可见调用/引用边的孤岛候选。
- `internal_api_leak`: 内部文件被多个外部模块直接依赖。
- `large_connected_file`: 大文件同时拥有较高连接度。

诊断结果分为两类语气：`Violation` 表示明确违反规则，`Risk/Candidate` 表示需要人工确认的结构风险。普通图谱请求不执行诊断；前端单独请求 `/api/codegraph/diagnostics` 并把结果叠加到当前图。

## 3D 架构

前端继续使用 Three.js WebGL：节点为复用 `SphereGeometry`，边为单个 `BufferGeometry + vertexColors`，交互基于 `Raycaster` 和 `OrbitControls`。

核心文件：

| 文件 | 角色 |
|------|------|
| `web/api/routes/codegraph.py` | CodeGraph API route |
| `web/api/services/codegraph.py` | SQLite 读取、图谱聚合、CLI 同步 |
| `web/api/services/codegraph_diagnostics.py` | 确定性架构诊断 |
| `web/frontend/src/views/CodeGraph.vue` | 页面工具栏、搜索、详情面板 |
| `web/frontend/src/composables/useCodeGraph.ts` | 加载、同步、下钻、交互状态 |
| `web/frontend/src/composables/useCodeGraphDiagnostics.ts` | 诊断加载、过滤和风险叠加 |
| `web/frontend/src/composables/codegraph/*` | Three.js 场景、图构建、物理模拟、拾取交互 |

## 设计约束

- `.codegraph/` 是本地忽略产物，不提交仓库。
- 普通图谱请求只读 SQLite，不调用 CLI。
- 诊断层只读 SQLite + git log，失败时降级为无 git churn，不影响图谱加载。
- `POST /api/codegraph/sync` 使用固定命令数组，不接收路径参数。
- Hindsight 仍是后台记忆服务，但不再提供 Web 图谱页面。

## See Also

- [[system-architecture]] — 系统分层 + 关键模块表
- [[web-architecture]] — Web 整体架构
- [[hindsight-architecture]] — 后台记忆服务
