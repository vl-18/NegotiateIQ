import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev mode, Vite always serves index.html for "/".
// This plugin rewrites the root request to the merchant entry so
// navigating to http://localhost:5174/ opens the merchant portal.
function merchantEntryPlugin() {
  return {
    name: "merchant-entry",
    // No return here — middleware added BEFORE Vite's internal HTML serving.
    // With "return () => {}", it runs after and the rewrite is too late.
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.url === "/" || req.url === "") {
          req.url = "/index.merchant.html";
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), merchantEntryPlugin()],
  build: {
    outDir: "dist/merchant",
    emptyOutDir: true,
    rollupOptions: {
      input: "index.merchant.html",
    },
  },
  server: {
    port: 5174,
    proxy: {
      "/api": {
        target: "http://localhost:8001",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
