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
        },
      },
      system: {
        title: "System",
        eyebrow: "System",
        subtitle: "Runtime observation, config writes, and code intelligence tools in one system entry",
        tabs: {
          monitor: {
            label: "Monitor",
            meta: "Read-only ops",
            description: "Read-only view of resources, API health, schedules, and service status",
          },
          settings: {
            label: "Settings",
            meta: "Config writes",
            description: "Manage run mode, auth, notifications, data sources, strategy state, and risk parameters",
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
          codegraph: {
            label: "CodeGraph",
            meta: "Code graph",
            description: "Inspect modules, files, symbols, call flow, and structural impact across the project",
          },
        },
      },
    } as const;
