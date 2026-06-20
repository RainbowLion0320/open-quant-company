export const modules = {
      research: {
        title: "Research",
        eyebrow: "Research",
        subtitle: "Sector rotation, stock search, and deep-dive research in one workspace",
        tabs: {
          sectors: { label: "Sector Radar", meta: "Sector rotation" },
          stocks: { label: "Stock Search", meta: "Stock research" },
        },
      },
      datahub: {
        title: "Data Hub",
        eyebrow: "DataHub",
        subtitle: "Registry health, freshness scans, and repair actions in one entry point",
        tabs: {
          health: {
            label: "Health Scan",
            meta: "Registry health",
            description: "Check freshness, missing values, anomalies, and repairable dimensions by table",
          },
          assets: {
            label: "Asset Coverage",
            meta: "Asset coverage",
            description: "Inspect multi-asset data sources, research readiness, and trading capability",
          },
          sources: {
            label: "Source Capabilities",
            meta: "Capability registry",
            description: "Compare external provider capabilities with project data dimensions and local source gaps",
          },
        },
      },
      strategyLab: {
        title: "Strategy Lab",
        eyebrow: "Strategy Lab",
        subtitle: "Strategy catalog, signal changes, and backtest evidence in a full research loop",
        tabs: {
          strategies: {
            label: "Catalog",
            meta: "Catalog & gates",
            description: "Review production and candidate strategies, lifecycle, scans, and production isolation",
          },
          signals: {
            label: "Signal History",
            meta: "Signal changes",
            description: "Track recent signal migrations, new buys, downgrades, and strategy agreement changes",
          },
          backtest: {
            label: "Backtest",
            meta: "Evidence",
            description: "Compare returns, risk, drawdowns, strong baselines, and promotion evidence",
          },
          evidence: {
            label: "Evidence Panel",
            meta: "Evidence panel",
            description: "Inspect evidence artifacts, OOS status, cost models, and promotion decisions",
          },
          dataCoverage: {
            label: "Data Coverage",
            meta: "Data matrix",
            description: "Inspect each strategy's declared data families, required gaps, and optional expansion areas",
          },
        },
      },
      system: {
        title: "System",
        eyebrow: "System",
        subtitle: "Base settings, runtime status, and system diagnostics in one system entry",
        tabs: {
          settings: {
            label: "Settings",
            meta: "Status & config",
            description: "View API health and schedules, and manage auth, notifications, data sources, strategy state, and risk parameters",
          },
          config: {
            label: "Config Center",
            meta: "Config center",
            description: "View and edit system parameters for data fetch, signals, regime, risk, backtest, and fees",
          },
          tests: {
            label: "Test Design",
            meta: "Design intelligence",
            description: "Inspect test cases, risks, code targets, specs, and design risks",
          },
          ast: {
            label: "AST Intelligence",
            meta: "AST analysis",
            description: "Inspect duplicate implementations, near clones, repeated helpers, and canonical helper bypass risks",
          },
          lifecycle: {
            label: "Lifecycle",
            meta: "Evidence chain",
            description: "Inspect whether source, data health, strategy evidence, and execution gates are ready for formal runs",
          },
          codegraph: {
            label: "CodeGraph",
            meta: "Code graph",
            description: "Inspect modules, files, symbols, call flow, and structural impact across the project",
          },
        },
      },
    } as const;
