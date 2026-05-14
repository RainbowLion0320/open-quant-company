# Wiki Schema

## Domain
A股量化交易系统 — 巴菲特价值投资哲学 + 钱学森控制论的工程落地。
覆盖: 策略设计、数据架构、技术选型、因子工程、回测方法论。

## Architecture: Three Layers

```
wiki/
├── SCHEMA.md           # 本文件 — 结构约定、标签分类
├── index.md            # 内容目录，分区 + 一句话摘要
├── log.md              # 按时间追加的操作日志 (append-only)
├── raw/                # Layer 1: 不可变原始素材
│   ├── articles/       # 网页文章、AI对话摘要
│   ├── papers/         # 研报PDF、论文
│   ├── transcripts/    # 会议记录、讨论摘要
│   └── assets/         # 图片、图表引用
├── entities/           # Layer 2: 实体页 (数据源、工具、交易所)
├── concepts/           # Layer 2: 概念/专题页 (策略、因子、架构)
├── decisions/          # Layer 2: 架构决策记录 (ADR)
├── comparisons/        # Layer 2: 对比分析页
├── queries/            # Layer 2: 归档的问答结果
└── _archive/           # 已取代的页面存档
```

**Layer 1 — Raw:** 不可变。Agent 可读但绝不修改。
**Layer 2 — Wiki:** Agent 创建、更新、交叉引用的 markdown 页面。
**Layer 3 — Schema:** SCHEMA.md 定义结构和约定。

## Conventions
- 文件名: lowercase-hyphens.md
- 每页必须有 YAML frontmatter (title, created, updated, type, tags)
- raw/ 下的素材也有 frontmatter (source_url, ingested, sha256)
- 使用 `[[page-name]]` wikilink 语法链接其它页面，至少2个出站链接
- 更新时修改 `updated` 日期
- 新页面加入 `index.md` 对应分区，按字母序
- 所有操作追加到 `log.md`

## Frontmatter

### Wiki 页面
```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: concept | entity | comparison | decision | query
tags: [from taxonomy]
confidence: high | medium | low
---
```

### raw/ 素材
```yaml
---
source_url: https://example.com/article
ingested: YYYY-MM-DD
sha256: <hex digest>
---
```

## Tag Taxonomy
- strategy: buffett, multifactor, cybernetic, ml-lgbm
- data: akshare, tushare, duckdb, sqlite, parquet, pit
- architecture: web, api, database, broker, pipeline, registry, strategy-interface
- finance: roe, dcf, margin-of-safety, moat, regime
- ml: factor-dsl, lightgbm, optuna, tournament, llm, factor-discovery, feature-store
- meta: decision, comparison, pitfall, roadmap

## Page Thresholds
- Create page: 主题在2+处被提及 OR 对系统架构有关键影响
- Split page: 超过200行
- Archive: 内容完全被替代 → `_archive/`
