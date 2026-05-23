---
title: Hindsight Knowledge Graph (记忆知识图谱)
created: 2026-05-17
updated: 2026-05-17
type: concept
tags: [web, hindsight, knowledge-graph, three.js, 3d]
---

# Hindsight Knowledge Graph

Hindsight 持久化记忆的交互式知识图谱可视化。**Three.js WebGL 3D 星空图** + Quantum Terminal 风格，独立 Web 页面。

2026-05-17: 从 Canvas 2D 迁移到 Three.js 3D (commit 9c3bac9)。

## 数据来源

```
Hindsight REST API (localhost:9177)
  ├── /memories/list    → 全部记忆节点 (id, text, type, entities[], tags[], document_id)
  ├── /stats            → 图谱元数据 (total_nodes, total_links, links_by_type)
  └── /memories/recall  → 搜索 + source_fact_ids
```

## 3D 架构

### 场景组件

| 组件 | 技术 | 细节 |
|------|------|------|
| 星空背景 | `THREE.Points` + `AdditiveBlending` | 600 粒子，深蓝 #334466，`depthWrite: false` |
| 节点球体 | `THREE.SphereGeometry(1, 24, 16)` 复用 | `MeshStandardMaterial` + emissive 发光 |
| 边 | `THREE.BufferGeometry` + `vertexColors` | 单次 draw call，逐边颜色控制 |
| 光源 | `AmbientLight` + `PointLight` | 环境光 #334466 + 点光源 #00d4ff |
| 相机 | `PerspectiveCamera(55°)` | 初始距离 160，OrbitControls |
| 交互 | `Raycaster` | 替代 Canvas 2D hit-test |

### 力模拟 (3D)

```
tick() 每帧:
  repulsion=400,  inverse-square 3D 斥力
  centering=0.003, 原点引力
  damping=0.85,    15% 能量衰减/帧
  springLen=45,  springK=0.003
  → 收敛: max_velocity < 0.08 持续 60 帧 → stop
```

### 节点类型与颜色 (色轮等边三角: 195°-270°-40°)

| 类型 | 颜色 | 语义 |
|------|------|------|
| Observation | 青色 #00d4ff | 「刚发生的」对话碎片 |
| Experience  | 紫色 #7c3aed | 「学到的」精炼知识 |
| World       | 金色 #e8a840 | 「本来如此的」通用知识 |

节点大小按 `degree` 动态缩放: `scale = 1.8 + (degree/maxDegree) * 4.5`

### 点击高亮 (逐边 vertexColors)

所有边存为单一 `BufferGeometry`，`edgeMeta[]` 并行记录每条边 `{srcId, tgtId, type}`。点击节点时：

- 关联边顶点颜色 → 白色 `#ffffff`
- 非关联边顶点颜色 → `#111122`（几乎隐身）
- `geometry.attributes.color.needsUpdate = true`

### 交互 (Three.js)

| 操作 | 效果 |
|------|------|
| 左键拖拽 | 旋转视角 (OrbitControls) |
| 滚轮 | 缩放 (30~600 距离) |
| 右键拖拽 | 平移 |
| 悬停节点 | 放大 1.3x + tooltip + cursor:pointer |
| 点击节点 | 选中高亮+详情面板展开 |
| 点击空白 | 取消选中，边恢复原色 |
| 自动旋转 | `autoRotate=true`, speed=0.15 |

### 性能特征

- **单次 draw call**: 所有边一个 BufferGeometry
- **GPU 渲染**: Three.js WebGL，59 节点 ~0.5ms/frame
- **收敛停止**: 节点稳定后停 requestAnimationFrame
- **闲置渲染**: `renderLoop()` 保持 controls.update + 重绘
- **Three.js 体积**: ~135KB gzipped (约 Vue 3 + ECharts 已完成)

## 关键文件

| 文件 | 角色 |
|------|------|
| `web/api/routes/hindsight.py` | 后端端点 + 图谱构建逻辑 |
| `web/frontend/src/views/HindsightGraph.vue` | 3D 渲染 + 物理模拟 + 交互 (~820行) |
| `web/frontend/src/router/index.ts` | 路由注册 |
| `web/frontend/package.json` | 依赖: three@latest |

## 设计约束

- **Three.js 是唯一 3D 依赖**: 零外部图谱库
- **自建力模拟**: 不依赖 D3-force/cytoscape 等
- **vertexColors 逐边控制**: 避免分组 material 的全局变色
- **无实时轮询**: 数据变化慢，手动 Load Graph 触发

## See Also

- [[hindsight-architecture]] — Hindsight 引擎深层架构 + 配置详解
- [[web-architecture]] — Web 整体架构 + 6 个一级入口
- [[system-architecture]] — 系统分层 + 关键模块表
