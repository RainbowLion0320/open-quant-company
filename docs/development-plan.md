# 当前开发计划

> 更新: 2026-05-26

## 当前焦点

本文件是唯一的活跃计划入口。已完成的执行计划不再保留在工作树，避免后续 agent 把历史任务误判为当前任务。

当前没有展开中的专题计划。本文件只保留下一步候选方向；已完成任务通过 git 追溯。

## 本轮交付项

| 事项 | 归属文档 | 状态 |
|------|----------------|--------|
| 历史执行计划退出工作树 | `docs/plans/` | 已完成 |
| wiki append-only 历史日志退出工作树 | `wiki/` | 已完成 |
| 旧 DataHub sector flat-file fallback 移除 | `web/api/services/`, `signals/`, `data/` | 已完成 |
| 旧 Web redirect 入口移除 | `web/frontend/src/router` | 已完成 |
| 旧手写回测 runner 入口移除 | `backtest/run_all_strategies.py` | 已完成 |

## 后续计划槽位

只有当工作流有清晰实现范围和验收标准时，才新建独立未来计划。候选方向：

- 关键 Web UI 流程的浏览器 smoke/e2e 覆盖。
- 行业和多资产维度的数据质量门禁。
- 策略研究生命周期：实验注册、OOS 窗口、模型晋级规则。
- 人工确认式半自动交易前的 Broker 执行准备。
