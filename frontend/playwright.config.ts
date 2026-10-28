import { defineConfig, devices } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

// The end-to-end test starts its own scratch backend and Vite server (ADR 0025): a new SQLite
// file in the temp folder, the offline mock provider, ports 8010 and 5180. The user's database
// and a running dev server on :8000 / :5173 are never touched. A server already listening on
// either port is an error, not reused, so the test cannot run against someone's data.
const API_PORT = 8010;
const WEB_PORT = 5180;
const scratchDb = join(tmpdir(), `machine-forge-e2e-${Date.now()}.db`);
// Python with the backend installed: the backend virtualenv locally, `python` in CI.
const python =
  process.env.MF_E2E_PYTHON ?? (process.platform === "win32" ? ".venv/Scripts/python" : ".venv/bin/python");

export default defineConfig({
  testDir: "e2e",
  outputDir: join(tmpdir(), "machine-forge-e2e-results"),
  reporter: "list",
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  use: { baseURL: `http://localhost:${WEB_PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `${python} -m uvicorn app.main:create_app --factory --port ${API_PORT}`,
      cwd: "../backend",
      env: { MF_DB_PATH: scratchDb, MF_LLM_PROVIDER: "mock", MF_MOCK_SCENARIO: "blister" },
      url: `http://localhost:${API_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      env: { MF_API_URL: `http://localhost:${API_PORT}` },
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
