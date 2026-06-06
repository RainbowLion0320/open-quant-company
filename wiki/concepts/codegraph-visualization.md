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
| `POST /api/codegraph/sync` | 显式触发 `sync` 或 `rebuild` |

## 交互模型

- 默认展示模块级总览，避免一次性渲染 6000+ 符号。
- 点击模块下钻到文件级；点击文件下钻到符号级；点击符号进入邻域图。
- 边类型筛选支持 `imports / calls / instantiates / references / extends`。
- 选中节点时，流入边和流出边使用不同颜色并做轻量脉冲动画。
- Sync/Rebuild 由用户显式点击，不在页面加载时自动改写 `.codegraph/`。

## 3D 架构

前端继续使用 Three.js WebGL：节点为复用 `SphereGeometry`，边为单个 `BufferGeometry + vertexColors`，交互基于 `Raycaster` 和 `OrbitControls`。

核心文件：

| 文件 | 角色 |
|------|------|
| `web/api/routes/codegraph.py` | CodeGraph API route |
| `web/api/services/codegraph.py` | SQLite 读取、图谱聚合、CLI 同步 |
| `web/frontend/src/views/CodeGraph.vue` | 页面工具栏、搜索、详情面板 |
| `web/frontend/src/composables/useCodeGraph.ts` | 加载、同步、下钻、交互状态 |
| `web/frontend/src/composables/codegraph/*` | Three.js 场景、图构建、物理模拟、拾取交互 |

## 设计约束

- `.codegraph/` 是本地忽略产物，不提交仓库。
- 普通图谱请求只读 SQLite，不调用 CLI。
- `POST /api/codegraph/sync` 使用固定命令数组，不接收路径参数。
- Hindsight 仍是后台记忆服务，但不再提供 Web 图谱页面。

## See Also

- [[system-architecture]] — 系统分层 + 关键模块表
- [[web-architecture]] — Web 整体架构
- [[hindsight-architecture]] — 后台记忆服务
