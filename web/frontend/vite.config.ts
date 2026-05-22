import { defineConfig, splitVendorChunkPlugin } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [vue(), tailwindcss(), splitVendorChunkPlugin()],
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
    // ECharts (~350KB) + Vue (~130KB) + shared deps → ~1MB vendor chunk.
    // This is expected for an SPA with charting; routes are already lazy-loaded.
    chunkSizeWarningLimit: 2000,
  },
});
