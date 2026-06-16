# Open Quant Company 文档目录规范

> 更新: 2026-06-14

本仓库的文档按读者和稳定性分层。根目录只保留第一次进入仓库时必须看到的入口，长期维护、产品、运维、质量和合规文档放进 `docs/` 的明确子目录。

## 根目录入口

| 文件 | 用途 |
| --- | --- |
| `README.md` / `README.en.md` | 面向人类读者的项目入口，说明项目定位、Web + CLI 双入口、快速开始和必要风险边界。 |
| `AGENTS.md` | 面向 Codex、Claude、自动化脚本和维护 agent 的执行入口。 |
| `CLAUDE.md` | Claude 专用薄入口，只指向当前权威文档和 agent 规则。 |
| `CONTRIBUTING.md` / `SECURITY.md` / `CODE_OF_CONDUCT.md` / `SUPPORT.md` | GitHub Community Standards 直接识别的一线协作文档。 |
| `CHANGELOG.md` | 发布变更记录。 |

`LICENSE`、`NOTICE`、`CITATION.cff` 不是 Markdown 文档，但继续留在根目录，方便开源平台和引用工具发现。

## docs 分层

| 目录 | 角色 |
| --- | --- |
| `docs/product/` | 产品范围、验收矩阵和读者理解项目边界所需的稳定说明。 |
| `docs/specs/` | 子系统行为契约，是代码行为的权威设计文档。 |
| `docs/strategies/` | 策略设计、策略族说明和研究到生产的边界。 |
| `docs/project/` | 文档治理、项目治理、维护者、路线图和发布流程。 |
| `docs/project/agent-company/` | Agent Company OS 长期路线图和仍未完成的 live execution 计划。 |
| `docs/project/compliance/` | 开源合规、隐私、安全、SBOM、无密钥入门等合规材料。 |
| `docs/operations/` | 本地运维、外部服务接入和可执行操作手册。 |
| `docs/quality/` | 测试、质量审计和验证体系说明。 |
| `docs/assets/` | README 和文档使用的静态素材。 |

`wiki/` 仍然独立保留，用于长期知识、概念解释、架构决策和操作索引；本次不把 wiki 合并进 `docs/`。

## 权威来源

| 主题 | 权威来源 | 文档规则 |
| --- | --- | --- |
| 产品范围和边界 | `docs/product/prd.md` | 保持稳定，不写 sprint 级状态。 |
| 模块行为和契约 | `docs/specs/*.md` | 行为变化时同提交更新。 |
| 当前实现状态 | 代码 + 测试 + `docs/product/acceptance-matrix.md` | 不在 wiki 重复维护状态表。 |
| 项目发布版本 | `pyproject.toml` → `[project].version` + `CHANGELOG.md` + `docs/project/release.md` | README badge 通过 `scripts/bump_version.py` 同步；配置文件不保存发布版本。 |
| 数据维度和路径 | `config/settings.yaml` + `data/storage/dimensions.py` + `data/storage/datahub.py` | 文档说明如何查询，不复制动态数量。 |
| 本地运行目录布局 | `config/settings.yaml` → `paths` | `data/` 是源码包，运行产物默认在 `var/`。 |
| 数据 schema | `data/quality/contract.py` + 必要时的显式 `_contracts/` 文件 | 文档说明契约归属和查询方法。 |
| 策略参数 | `config/settings.yaml` + 策略代码 | 文档描述设计意图，不固化易过期指标。 |
| 回测/锦标赛指标 | `var/artifacts/tournaments/` 和生成报告 | 除非明确标记为历史样本，否则不把 Sharpe/MaxDD 写进长期文档。 |
| Web 路由和 UI 模块 | `web/api/routes/` + `web/frontend/src/router` | spec 记录主要业务路由组，不追逐每个临时端点细节。 |
| Agent/cron/local 操作入口 | `astroq` CLI (`astrolabe_cli/`) | 新自动化优先调用 CLI；CLI 编排当前维护的底层模块。 |
| Agent Company OS 长期改造 | `docs/project/agent-company/00-master-roadmap.md` + `docs/specs/07-agent-company-os.md` | 路线图记录长期目标；spec 和验收矩阵记录当前 API/CLI/schema/approval/evidence 行为契约和实现状态。 |
| 操作历史 | git log | 仓库不保留历史计划归档；发布变更记录只写入 `CHANGELOG.md`。 |

## 更新规则

- 改动公开契约的代码提交，必须同步更新对应 `docs/specs/` 页面；必要时更新 `docs/product/acceptance-matrix.md`。
- 产品范围变化更新 `docs/product/prd.md`，不要把实施阶段清单塞进 PRD。
- Agent Company OS 方向变化必须同步更新 `docs/project/agent-company/00-master-roadmap.md` 和 `docs/specs/07-agent-company-os.md`，再按需要更新 PRD、Web spec 和验收矩阵；完成的阶段执行计划不保留在工作树。
- 项目维护规则写入 `docs/project/` 或根目录的 GitHub 标准文档，不塞回 README。
- 运维步骤写入 `docs/operations/`，测试和质量说明写入 `docs/quality/`。
- 合规和安全材料写入 `docs/project/compliance/`，根目录只保留 `SECURITY.md` 这类一线入口。
- wiki 页面保存推理、概念和方法论。动态值通过代码/配置链接查询，不复制数量、日期、回测结果。
- 完成或被取代的计划从工作树删除；需要追溯时使用 git log / git show。

## 漂移检查

文档类改动完成前运行：

```bash
astroq docs check --json
git diff --check
```

第一条命令只抓已经确认容易过期的短语和断链风险，不代表所有阶段或未来规划表述都有问题。
