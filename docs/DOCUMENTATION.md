# 星盘 / Astrolabe Quant OS 文档治理

> 更新: 2026-05-29

本仓库保留三类文档层。它们不是同一种东西，每一层只负责自己的边界。

## 阅读顺序

1. `docs/PRD.md` — 产品意图、范围、用户能力和非功能需求。
2. `docs/specs/` — 子系统实现契约，是代码行为的权威设计文档。
3. `docs/acceptance-matrix.md` — PRD/spec 到代码、测试、API/Web、手工验收的追踪矩阵。
4. `wiki/` — 长期知识：概念、架构决策、对比分析、操作方法。
5. `docs/development-plan.md` — 当前唯一活跃开发计划。完成或被取代的计划从工作树删除，历史从 git 恢复。

## 权威来源

| 主题 | 权威来源 | 文档规则 |
|---------|----------------------|--------------------|
| 产品范围和边界 | `docs/PRD.md` | 保持稳定，不写 sprint 级状态。 |
| 模块行为和契约 | `docs/specs/*.md` | 行为变化时同提交更新。 |
| 当前实现状态 | 代码 + 测试 + `docs/acceptance-matrix.md` | 不在 wiki 重复维护状态表。 |
| 项目发布版本 | `pyproject.toml` → `[project].version` | README badge 通过 `scripts/bump_version.py` 同步；配置文件不保存发布版本。 |
| 数据维度和路径 | `config/settings.yaml` + `data/data_registry.py` + `data/datahub.py` | 文档说明如何查询，不复制动态数量。 |
| 数据 schema | `data/contract.py` + 必要时的显式 `_contracts/` 文件 | 文档说明契约归属和查询方法。 |
| 策略参数 | `config/settings.yaml` + 策略代码 | 文档描述设计意图，不固化易过期指标。 |
| 回测/锦标赛指标 | `data/tournament/` 和生成报告 | 除非明确标记为历史样本，否则不把 Sharpe/MaxDD 写进长期文档。 |
| Web 路由和 UI 模块 | `web/api/routes/` + `web/frontend/src/router` | spec 记录主要业务路由组，不追逐每个临时端点细节。 |
| Agent/cron/local 操作入口 | `astroq` CLI (`astrolabe_cli/`) | 新自动化优先调用 CLI；旧脚本作为底层实现或兼容入口。 |
| 操作历史 | git log | 仓库不再保留 append-only changelog 或历史计划归档。 |

## 更新规则

- 改动公开契约的代码提交，必须同步更新对应 `docs/specs/` 页面；必要时更新验收矩阵。
- 产品范围变化更新 `docs/PRD.md`，不要把实施阶段清单塞进 PRD。
- wiki 页面保存推理、概念和方法论。动态值通过代码/配置链接查询，不复制数量、日期、回测结果。
- 完成或被取代的计划从工作树删除；需要追溯时使用 git log / git show。
- 当前活跃计划只放在 `docs/development-plan.md`；已完成或被替换的计划依靠 git 历史追溯。
- 不在 wiki 保留大型历史日志。当前活动由 git commit 追溯。

## 漂移检查

文档类改动完成前运行：

```bash
rg -n "34 维度|34维度|四维加权|多因子四维|9 页|9页|FastAPI（9|3页|3 页|5517|全局 ticker|底部 ticker|点位与日涨跌|Regime Score" README.md CLAUDE.md docs wiki -g '!docs/DOCUMENTATION.md' -g '!docs/development-plan.md'
git diff --check
```

第一条命令故意保持窄范围，只抓已经确认容易过期的短语，不代表所有阶段或未来规划表述都有问题。
