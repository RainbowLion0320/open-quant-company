import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "market", component: () => import("../views/Market.vue") },
    { path: "/strategies", name: "strategies", component: () => import("../views/Strategies.vue") },
    { path: "/portfolio", name: "portfolio", component: () => import("../views/Portfolio.vue") },
    { path: "/stocks", name: "stocks", component: () => import("../views/Stocks.vue") },
    { path: "/stocks/:code", name: "stock-detail", component: () => import("../views/StockDetail.vue") },
    { path: "/backtest", name: "backtest", component: () => import("../views/Backtest.vue") },
    { path: "/signals", name: "signals", component: () => import("../views/Signals.vue") },
    { path: "/monitor", name: "monitor", component: () => import("../views/ActivityMonitor.vue") },
    { path: "/db-health", name: "db-health", component: () => import("../views/DatabaseHealth.vue") },
    { path: "/hindsight", name: "hindsight", component: () => import("../views/HindsightGraph.vue") },
    { path: "/settings", name: "settings", component: () => import("../views/Settings.vue") },
  ],
});

export default router;
