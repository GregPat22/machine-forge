import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

declare const process: { env: Record<string, string | undefined> };

// Backend URL for the dev proxy; override with MF_API_URL (e.g. a second backend on another port).
const API_URL = process.env.MF_API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // three.js (~550 kB) is in its own lazily loaded chunk, used only by the 3D tab.
  build: { chunkSizeWarningLimit: 700 },
  server: {
    proxy: {
      // The backend runs on :8000 (uvicorn); design generation can take a few minutes.
      "/api": { target: API_URL, changeOrigin: true, timeout: 600_000, proxyTimeout: 600_000 },
    },
  },
});
