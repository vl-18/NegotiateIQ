import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist/buyer",
    emptyOutDir: true,
  },
  // Proxy /api → FastAPI backend in dev (avoids CORS issues locally)
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8001",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
