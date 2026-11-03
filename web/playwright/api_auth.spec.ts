import { expect, test } from "@playwright/test";

test("all data reads use the runtime JWT and logout removes it", async ({ page }) => {
  // Load the actual Vite-transformed client without starting the map or a backend.
  await page.route("**/auth-test", route => route.fulfill({
    contentType: "text/html", body: "<!doctype html><title>API auth test</title>",
  }));
  await page.goto("/auth-test");
  const requests = await page.evaluate(async () => {
    const observed: { url: string; authorization: string | null }[] = [];
    window.fetch = async (input, init) => {
      observed.push({ url: String(input), authorization: new Headers(init?.headers).get("Authorization") });
      return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
    };
    // Variable import is resolved by Vite in the browser, not by Playwright's Node loader.
    const modulePath = "/src/api.ts";
    const api = await import(modulePath);
    api.setAuthToken("synthetic-browser-token");
    await api.fetchCities();
    await api.fetchAssets("city-a");
    await api.fetchMetrics("asset-a");
    await api.fetchObservations("asset-a", "rain_mmph", "2026-01-01", "2026-01-02");
    await api.fetchObservationEvidence("asset-a", "rain_mmph", "2026-01-01", "2026-01-02", "");
    await api.fetchEventRun("event-a");
    await api.fetchObservationsCompare("asset-a", "rain_mmph", "2026-01-01", "2026-01-02", "base", "compare");
    await api.fetchScenarios();
    await api.fetchCityStatus("city-a");
    await api.fetchHotspots("city-a");
    await api.fetchCitySummary("city-a");
    await api.fetchEvents("city-a", "2026-01-01", "2026-01-02");
    await api.fetchNotes("city-a");
    await api.fetchNote("note-a");
    await api.fetchJob("job-a");
    await api.downloadJob("job-a");
    api.setAuthToken("");
    await api.fetchCities();
    return observed;
  });
  expect(requests).toHaveLength(17);
  for (const request of requests.slice(0, -1)) {
    expect(request.authorization, request.url).toBe("Bearer synthetic-browser-token");
  }
  expect(requests.at(-1)?.authorization).toBeNull();
});

test("app applies a token by reloading data and clears it on logout", async ({ page }) => {
  const calls: (string | undefined)[] = [];
  await page.route("https://**", route => route.abort());
  await page.route("**/v1/**", async route => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: {
        "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET",
      } });
      return;
    }
    const authorization = route.request().headers()["authorization"];
    calls.push(authorization);
    await route.fulfill({
      status: authorization === "Bearer synthetic-ui-token" ? 200 : 401,
      contentType: "application/json",
      headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*" },
      body: authorization === "Bearer synthetic-ui-token" ? "[]" : '{"error":{"code":"UNAUTHORIZED"}}',
    });
  });
  await page.goto("/");
  const token = page.getByLabel("JWT token", { exact: true });
  await token.fill("synthetic-ui-token");
  expect(await page.evaluate(() => localStorage.getItem("floodmvp.jwt"))).toBeNull();
  await Promise.all([page.waitForEvent("load"), page.getByRole("button", { name: "Apply token", exact: true }).click()]);
  await expect.poll(() => calls.includes("Bearer synthetic-ui-token")).toBe(true);
  expect(await page.evaluate(() => localStorage.getItem("floodmvp.jwt"))).toBe("synthetic-ui-token");
  calls.length = 0;
  await token.fill("");
  await Promise.all([page.waitForEvent("load"), page.getByRole("button", { name: "Apply token", exact: true }).click()]);
  await expect.poll(() => calls.length).toBeGreaterThan(0);
  expect(calls.every(value => value === undefined)).toBe(true);
  expect(await page.evaluate(() => localStorage.getItem("floodmvp.jwt"))).toBeNull();
});
