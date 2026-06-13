export const lifecycle = {
  eyebrow: "Lifecycle Readiness",
  title: "全生命周期证据链",
  status: "状态",
  blockers: "阻断项",
  warnings: "提醒",
  updated: "更新时间",
  noArtifact: "还没有生命周期检查产物，请在 CLI 运行：",
  blockerList: "阻断明细",
  warningList: "提醒明细",
  none: "无",
  checks: {
    source_capabilities: "数据源能力",
    data_freshness: "本地数据新鲜度",
    strategy_evidence: "策略证据",
    execution: "执行链路",
  },
} as const;
