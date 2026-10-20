import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // three.js (~550 kB) is in its own lazily loaded chunk, used only by the 3D tab.
  build: { chunkSizeWarningLimit: 700 },
  server: {
    proxy: {
      // The backend runs on :8000 (uvicorn); design generation can take a few minutes.
      "/api": { target: "http://localhost:8000", changeOrigin: true, timeout: 600_000, proxyTimeout: 600_000 },
    },
  },
});
