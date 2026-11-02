import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "api_auth.spec.ts",
  outputDir: "../../test-results/web/security",
  reporter: [["list"], ["junit", { outputFile: "../test-results/web/security.xml" }]],
  workers: 1,
  timeout: 60000,
  use: { baseURL: "http://127.0.0.1:5177", headless: true },
  webServer: {
    command: "yarn dev --host 127.0.0.1 --port 5177 --strictPort",
    url: "http://127.0.0.1:5177",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
