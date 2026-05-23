import { createRouter, createWebHistory } from "vue-router";

function redirectWithTab(path: string, tab: string) {
  return (to: any) => ({
    path,
    query: {
      ...to.query,
      tab,
    },
  });
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "market", component: () => import("../views/Market.vue") },
    { path: "/research", name: "research", component: () => import("../views/Research.vue") },
    { path: "/strategy-lab", name: "strategy-lab", component: () => import("../views/StrategyLab.vue") },
    { path: "/portfolio", name: "portfolio", component: () => import("../views/Portfolio.vue") },
    { path: "/datahub", name: "datahub", component: () => import("../views/DataHub.vue") },
    { path: "/system", name: "system", component: () => import("../views/SystemHub.vue") },
    { path: "/stocks/:code", name: "stock-detail", component: () => import("../views/StockDetail.vue") },
    { path: "/stocks", redirect: redirectWithTab("/research", "stocks") },
    { path: "/sectors", redirect: redirectWithTab("/research", "sectors") },
    { path: "/strategies", redirect: redirectWithTab("/strategy-lab", "strategies") },
    { path: "/signals", redirect: redirectWithTab("/strategy-lab", "signals") },
    { path: "/backtest", redirect: redirectWithTab("/strategy-lab", "backtest") },
    { path: "/db-health", redirect: redirectWithTab("/datahub", "health") },
    { path: "/monitor", redirect: redirectWithTab("/system", "monitor") },
    { path: "/settings", redirect: redirectWithTab("/system", "settings") },
    { path: "/hindsight", redirect: redirectWithTab("/system", "hindsight") },
  ],
});

export default router;
