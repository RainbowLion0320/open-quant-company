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
    // Heavy route-lazy visualization/runtime libraries are isolated so a page
    // only downloads the vendors it actually needs. ELK's bundled layout
    // engine is a known single-library payload, so the budget tracks that
    // explicit chunk instead of warning on an already-isolated dependency.
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("/echarts/")) return "vendor-echarts";
          if (id.includes("/vue-echarts/")) return "vendor-echarts-adapter";
          if (id.includes("/three/")) return "vendor-three";
          if (id.includes("/elkjs/")) return "vendor-elk";
          if (
            id.includes("/vue/") ||
            id.includes("/@vue/") ||
            id.includes("/pinia/") ||
            id.includes("/vue-router/")
          ) return "vendor-vue";
          return "vendor";
        },
      },
    },
  },
});
