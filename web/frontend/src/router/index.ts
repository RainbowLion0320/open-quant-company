import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "ceo-office", component: () => import("../views/CEOOffice.vue") },
    { path: "/market", name: "market", component: () => import("../views/Market.vue") },
    { path: "/research", name: "research", component: () => import("../views/Research.vue") },
    { path: "/strategy-lab", name: "strategy-lab", component: () => import("../views/StrategyLab.vue") },
    { path: "/portfolio", name: "portfolio", component: () => import("../views/Portfolio.vue") },
    { path: "/pipeline", name: "pipeline", component: () => import("../views/Pipeline.vue") },
    { path: "/datahub", name: "datahub", component: () => import("../views/DataHub.vue") },
    { path: "/system", name: "system", component: () => import("../views/SystemHub.vue") },
    { path: "/stocks/:code", name: "stock-detail", component: () => import("../views/StockDetail.vue") },
  ],
});

export default router;
