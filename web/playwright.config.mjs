import { defineConfig } from "@playwright/test";

const backendPort = process.env.PDA_E2E_BACKEND_PORT || "8010";
const frontendPort = process.env.PDA_E2E_FRONTEND_PORT || "3001";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `python3 -m server.app.api --host 127.0.0.1 --port ${backendPort} --root-dir web/.playwright-runtime`,
      url: `http://127.0.0.1:${backendPort}/api/health`,
      cwd: "..",
      reuseExistingServer: !process.env.CI,
      stdout: "pipe",
      stderr: "pipe",
      timeout: 120_000,
    },
    {
      command: `npm run dev -- --hostname 127.0.0.1 --port ${frontendPort}`,
      url: `http://127.0.0.1:${frontendPort}`,
      cwd: ".",
      env: {
        ...process.env,
        PDA_BACKEND_URL: `http://127.0.0.1:${backendPort}`,
      },
      reuseExistingServer: !process.env.CI,
      stdout: "pipe",
      stderr: "pipe",
      timeout: 120_000,
    },
  ],
});
