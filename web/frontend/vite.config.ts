import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8501",
        ws: true,
      },
      "/ws": {
        target: "ws://localhost:8501",
        ws: true,
      },
    },
  },
  build: {
    // ECharts and Three are large, route-lazy visualization libraries. Keep
    // them isolated in vendor chunks and raise the warning threshold to match
    // the expected library payload instead of hiding all size signals.
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("/echarts/")) return "vendor-echarts";
          if (id.includes("/three/")) return "vendor-three";
          if (id.includes("/vue") || id.includes("/pinia/") || id.includes("/vue-router/")) return "vendor-vue";
          return "vendor";
        },
      },
    },
  },
});
