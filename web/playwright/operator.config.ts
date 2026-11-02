import { defineConfig } from "@playwright/test";

// A live run is supplied only by the disposable smoke runner. Default tests mock the API.
const live = process.env.OPERATOR_WEB_BASE;
if (live && new URL(live).hostname !== "127.0.0.1")
  throw new Error("Live operator tests require loopback");
export default defineConfig({
  testDir: ".",
  testMatch: live ? "operator_live.spec.ts" : "operator.spec.ts",
  outputDir: `../../test-results/web/${live ? "operator-live" : "operator"}`,
  reporter: [
    ["list"],
    [
      "junit",
      {
        outputFile: `../test-results/web/${live ? "operator-live" : "operator"}.xml`,
      },
    ],
  ],
  workers: 1,
  timeout: 60000,
  use: {
    baseURL: live || "http://127.0.0.1:5178",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: live
    ? undefined
    : {
        command: "yarn dev --host 127.0.0.1 --port 5178 --strictPort",
        url: "http://127.0.0.1:5178",
        reuseExistingServer: false,
        timeout: 30000,
      },
});
