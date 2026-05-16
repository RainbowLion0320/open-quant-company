---
title: Hindsight Knowledge Graph (记忆知识图谱)
created: 2026-05-17
updated: 2026-05-17
type: concept
tags: [web, hindsight, knowledge-graph, visualization, canvas]
---

# Hindsight Knowledge Graph

Hindsight 持久化记忆的交互式知识图谱可视化。Canvas 力导向图 + Quantum Terminal 风格，独立 Web 页面。

## 数据来源

```
Hindsight REST API (localhost:8888)
  ├── /memories/list    → 全部记忆节点 (id, text, type, entities[], tags[], document_id)
  ├── /stats            → 图谱元数据 (total_nodes, total_links, links_by_type)
  └── /memories/recall  → 搜索 + source_fact_ids
```

## 图谱构建

后端 `web/api/routes/hindsight.py` 的 `/api/hindsight/graph` 端点从 Hindsight API 拉取原始数据，构建 `{nodes, links}` 结构：

**节点**：每条记忆一个节点。属性包括 id、标签（截断80字符）、类型（observation/experience）、entities、tags、时间戳。

**链接（4种）**：
1. **Entity 共享** — 两个节点有相同 entity（如「AKShare」→ 语义链接
2. **Document 聚合** — 同一 document_id 下的节点互连 → 时序链接
3. **Consolidation** — observation 被合并为 experience → 提炼关系
4. **Tag 共享** — 两个节点有相同 tag

## 前端渲染

Canvas 自建力导向图，不依赖第三方图谱库。

**物理模拟**（`HindsightGraph.vue → tick()`）：
- 节点间斥力（inverse-square）
- 图中心引力
- 链接弹簧力
- 速度阻尼衰减

**渲染**：Canvas 2D，Device Pixel Ratio 适配视网膜屏。

**节点区分**：
- Observation → 青色 (#00d4ff) 小圆点，径向渐变光晕
- Experience → 紫色 (#7c3aed) 大圆点，径向渐变光晕  
- 悬浮/选中 → 阴影发光 + 放大

**链接区分**：
- Semantic → 青色虚线
- Temporal → 白色细线
- Consolidation → 绿色虚线
- Tag → 紫色点线

**无文字标签**：节点不显示文字，保持图谱干净。文字信息通过悬浮 tooltip 和点击详情面板获取。

## 交互

| 操作 | 效果 |
|------|------|
| 悬浮节点 | 固定定位 tooltip: 类型徽章 + 全文 + entities |
| 点击节点 | 右侧详情面板弹出: 完整文字 + entities列表 + tags + 日期 |
| 拖拽节点 | 固定节点位置 |
| 拖拽空白 | 平移画布 |
| 滚轮 | 缩放 (0.2x ~ 3x) |
| 底部图例 | 标注四种节点/链接类型的颜色 |

## 集成

- **路由**: `/hindsight`（Vue Router）
- **侧栏入口**: 记忆图谱 SVG 图标
- **加载方式**: 页面打开自动加载，也支持手动点击「LOAD GRAPH」按钮刷新
- **非实时**: 不轮询，数据在点击载入时拉取一次

## 关键文件

| 文件 | 角色 |
|------|------|
| `web/api/routes/hindsight.py` | 后端端点 + 图谱构建逻辑 |
| `web/frontend/src/views/HindsightGraph.vue` | Canvas 力导向图渲染 + 交互 (650行) |
| `web/frontend/src/router/index.ts` | 路由注册 |

## 设计约束

- **零外部图谱库依赖**：自建物理模拟，避免引入 cytoscape/vis/d3-force 等重依赖
- **Canvas 非 SVG**：节点数可能增长到数百，Canvas 比 SVG DOM 更高效
- **无实时轮询**：数据变化慢（每轮对话才增量），无需 WebSocket 推送

## See Also

- [[web-architecture]] — Web 整体架构 + 10 页结构
- [[system-architecture]] — 系统分层 + 关键模块表
