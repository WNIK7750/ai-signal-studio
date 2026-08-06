import { defineConfig } from "@playwright/test";

const useExternalServers =
  process.env.PLAYWRIGHT_EXTERNAL_SERVERS === "1";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  use: {
    baseURL: "http://127.0.0.1:3010",
    channel: "chrome",
    viewport: { width: 1536, height: 1024 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: useExternalServers
    ? undefined
    : [
        {
          command:
            "..\\..\\.venv\\Scripts\\python.exe -m uvicorn " +
            "ai_signal_api.main:app --app-dir ..\\..\\apps\\api\\src " +
            "--host 127.0.0.1 --port 8010",
          url: "http://127.0.0.1:8010/api/health",
          timeout: 30_000,
          reuseExistingServer: false,
          env: {
            AI_SIGNAL_DATABASE_URL:
              "sqlite:///../../data/playwright-models.db",
            AI_SIGNAL_LLM_PROVIDER: "heuristic",
            AI_SIGNAL_SOURCE_SEED_MODE: "demo",
            AI_SIGNAL_CORS_ORIGINS:
              '["http://127.0.0.1:3010"]',
          },
        },
        {
          command:
            "node node_modules/next/dist/bin/next dev " +
            "--hostname 127.0.0.1 --port 3010",
          url: "http://127.0.0.1:3010/settings/models",
          timeout: 30_000,
          reuseExistingServer: false,
          env: {
            NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8010/api",
          },
        },
      ],
});
