export const modules = {
      research: {
        title: "市场研究",
        eyebrow: "Research",
        subtitle: "行业轮动、个股搜索和标的深挖集中在一个研究入口",
        tabs: {
          sectors: { label: "行业雷达", meta: "Sector rotation" },
          stocks: { label: "个股搜索", meta: "Stock research" },
        },
      },
      datahub: {
        title: "数据中台",
        eyebrow: "DataHub",
        subtitle: "数据注册表、健康扫描和修复动作收敛到统一入口",
        tabs: {
          health: {
            label: "健康扫描",
            meta: "Registry health",
            description: "按表检查新鲜度、缺失、异常和可修复数据维度",
          },
          assets: {
            label: "资产覆盖",
            meta: "Asset coverage",
            description: "查看多资产数据来源、研究就绪度和交易能力",
          },
          sources: {
            label: "数据源能力",
            meta: "Capability registry",
            description: "对比外部数据源能力、项目数据维度和本地来源缺口",
          },
        },
      },
      strategyLab: {
        title: "策略实验室",
        eyebrow: "Strategy Lab",
        subtitle: "策略目录、信号变化和回测证据合并为完整研究闭环",
        tabs: {
          strategies: {
            label: "策略目录",
            meta: "Catalog & gates",
            description: "查看生产策略和候选策略目录、生命周期、研究扫描与生产隔离状态",
          },
          signals: {
            label: "信号历史",
            meta: "Signal changes",
            description: "追踪最近信号迁移，识别新增买入、降级和策略一致性变化",
          },
          backtest: {
            label: "回测证据",
            meta: "Evidence",
            description: "对比策略收益、风险、回撤、强基准和晋级证据",
          },
          evidence: {
            label: "证据面板",
            meta: "Evidence panel",
            description: "查看策略证据制品、OOS状态、成本模型和晋级决策",
          },
        },
      },
      system: {
        title: "系统控制",
        eyebrow: "System",
        subtitle: "运行观测、配置写入和 AI 记忆工具收敛为系统入口",
        tabs: {
          monitor: {
            label: "系统信息",
            meta: "Read-only ops",
            description: "只读观测系统资源、API 健康、任务计划和服务状态",
          },
          settings: {
            label: "系统设置",
            meta: "Config writes",
            description: "集中管理认证、通知、数据源、策略状态和风控参数",
          },
          config: {
            label: "配置中心",
            meta: "Config center",
            description: "查看和编辑所有系统参数：数据获取、信号、Regime、风控、回测、费率",
          },
          tests: {
            label: "测试设计",
            meta: "Design intelligence",
            description: "审查测试用例、风险、代码目标、规格文档和设计风险",
          },
          ast: {
            label: "AST 检测",
            meta: "AST Intelligence",
            description: "检查全项目重复实现、近似 clone、重复 helper 和 canonical helper 绕行风险",
          },
          lifecycle: {
            label: "生命周期",
            meta: "Evidence chain",
            description: "查看数据源、数据健康、策略证据和执行链路是否满足正式运行门禁",
          },
          codegraph: {
            label: "代码图谱",
            meta: "CodeGraph",
            description: "浏览项目模块、文件、符号和调用关系，检查代码结构与影响面",
          },
        },
      },
    } as const;
