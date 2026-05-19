---
title: Hindsight Architecture (记忆引擎深层架构)
created: 2026-05-17
updated: 2026-05-17
type: concept
tags: [hindsight, memory, architecture, infrastructure, pg0]
---

# Hindsight Architecture

Hindsight 是 Quant Agent 的唯一记忆系统。Hermes 内置 MEMORY 已禁用（`memory_enabled: false`），所有跨会话知识存储由 Hindsight 接管。

## 系统定位

```
Hermes Agent (deepseek-v4-pro)
  └── Hindsight (deepseek-v4-flash, local embedded mode)
        ├── 存储: 事实提取 → 知识图谱
        ├── 检索: 语义搜索 + 图谱遍历 + 重排序
        └── 综合: 跨记忆推理 (reflect)
```

## 基础设施

| 组件 | 值 |
|------|-----|
| 模式 | Local Embedded |
| LLM | deepseek-v4-flash (via DeepSeek API) |
| 向量引擎 | pg0 v18.1.0 (嵌入式 PostgreSQL + pgvector) |
| 嵌入模型 | sentence-transformers |
| 活跃端口 | **9177** |
| Bank ID | `quant-agent` |
| 召回预算 | mid |

## 关键配置

### Hermes 端 (`~/.hermes/config.yaml`)

```yaml
memory:
  memory_enabled: false      # 禁用内置 MEMORY，仅用 Hindsight
  user_profile_enabled: true
  memory_char_limit: 8000
  user_char_limit: 1375
  provider: hindsight
  flush_min_turns: 1         # 每轮对话都 flush (之前是6，导致短会话丢失)
```

### Hindsight 端 (`~/.hermes/hindsight/config.json`)

```json
{
  "mode": "local",
  "llm_model": "deepseek-v4-flash",
  "bank_id": "quant-agent",
  "auto_recall": true,
  "auto_retain": true,
  "memory_mode": "hybrid",
  "recall_budget": "mid"
}
```

## 环境变量

两个 env var 必须设置（都在 `~/.hermes/.env`）：

- `HINDSIGHT_API_LLM_API_KEY` — Hindsight 调用 LLM 的 key
- `HINDSIGHT_LLM_API_KEY` — 同上（向后兼容）

## 端口陷阱 (⚠️ 已修复)

**问题**: 系统中存在两个 Hindsight daemon 实例：

| 端口 | PID | 状态 | 数据 |
|------|-----|------|------|
| 8888 | (已关闭) | 历史遗留 (脚本已修复至 9177) | 仅14个自指节点 (空壳) |
| **9177** | 活跃 | 由 `start_hindsight_daemon.py` 启动 | **~100+ 节点** (活跃增长中) |

**根因**: `start_hindsight_daemon.py` 硬编码了 `port=8888`，但 Hermes 的 Hindsight 插件在 auto-start 时用了默认端口 9177。Web API 路由 (`web/api/routes/hindsight.py`) 原来 hardcode 了 `localhost:8888`，导致图谱只显示 14 个节点。

**修复**: 2026-05-17 将 Web API 的 `HINDSIGHT` 常量改为 `http://localhost:9177`。

## 记忆生命周期

```
用户对话 → auto_retain (每轮 flush) 
  → Hindsight API POST /memories/retain (raw text)
  → LLM 事实提取 (deepseek-v4-flash)
  → 消歧 + 实体解析
  → 知识图谱节点 (observation / experience / world)
  → Consolidation (observation → experience 精炼)
  → 索引构建 (pgvector + FTS5)
  → 可召回 (auto_recall / recall / reflect)
```

## 记忆类型 (3 层事实模型)

Hindsight 的 LLM 事实提取不只记录对话，它同时提取三种不同层级的知识：

| 类型 | 颜色 | 语义 | 时间性 | 可替代 |
|------|------|------|--------|--------|
| **Observation** | 青色 #00d4ff | 「刚发生的」对话原始碎片 | 绑定对话轮次 | 被 experience 取代 |
| **Experience** | 紫色 #7c3aed | 「学到的」精炼知识 | 弱绑定 | 被更新的 experience 取代 |
| **World** | 金色 #e8a840 | 「本来如此的」通用客观知识 | 无时间性 | 被更新的 world 取代 |

- **Observation**: 一次性的原子事实，关联到具体 conversation turn（如"助手创建了 cron job"）
- **Experience**: Consolidation 合并多个 observation 后的精炼知识（如"Web UI 图谱 bug 根因是边按类型分组共用 material"）
- **World**: 脱人脱时的纯客观知识（如"两层架构的原因：只有 Observation 会导致碎片化"），不绑定人物和时间

Consolidation 做四件事：消歧、合并、抽象、实体解析。Observation → Experience 通过 `caused_by` 链接保持溯源性。

边类型同样分三层，各有独立的 entity/semantic/temporal/caused_by 链接矩阵。

当前分布 (2026-05-17):
- Observation: 114 | Experience: 129 | World: 111
- 总节点: 354 | 总链接: 14,399+

## 四种检索策略 (recall)

1. **语义搜索** — pgvector 余弦相似度 (`<=>` 操作符)
2. **关键词匹配** — FTS5 BM25 全文搜索
3. **实体图谱遍历** — 知识图谱关联节点跳跃
4. **时间衰减** — 最近记忆权重更高

## Daemon 管理

### 启动
```bash
python scripts/start_hindsight_daemon.py
# 首次初始化约 60 秒 (pg0 安装 + schema 构建)
```

### 健康检查
```bash
curl localhost:9177/health
# → {"status":"healthy","database":"connected"}
```

### 统计
```bash
curl localhost:9177/v1/default/banks/quant-agent/stats
# → total_nodes, total_links, nodes_by_fact_type, links_by_link_type
```

### 可能的问题

- **daemon 不自动启动**: status 显示 "available" 不等于在跑。Hermes 采用 lazy-start，需要手动触发。
- **端口冲突**: 不要同时跑两个 daemon 实例。
- **pg0 数据目录**: `/Users/fushao/.pg0/instances/hindsight/data` (端口 5432)

## 当前状态 (2026-05-17)

> 注: 以下为历史快照，当前实时数据请查看 Web UI 记忆图谱页面或 `/api/hindsight/graph`。

| 指标 | 值 |
|------|-----|
| 总节点 | ~100+ (增长中) |
| Observations | ~70+ |
| Experiences / World | ~30+ |
| 总链接 | 3000+ |
| 文档 | 15 |
| 最后合并 | 2026-05-17T03:06 UTC |

## 与 Hermes 工具的对应

| Hermes 工具 | Hindsight API |
|------------|---------------|
| `hindsight_retain` | POST /memories/retain |
| `hindsight_recall` | POST /memories/recall |
| `hindsight_reflect` | POST /memories/reflect |
| (auto) | GET /memories/list, GET /stats |

## See Also

- [[hindsight-graph]] — Web 端知识图谱可视化
- [[system-architecture]] — 系统整体架构
- [[web-architecture]] — Web 前端架构
