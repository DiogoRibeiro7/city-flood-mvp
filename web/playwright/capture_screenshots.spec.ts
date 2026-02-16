import { test } from "@playwright/test";

test.use({ viewport: { width: 1400, height: 900 } });

test("capture demo screenshots", async ({ page }) => {
  await page.goto("http://localhost:5173", { waitUntil: "networkidle" });
  await page.waitForSelector(".map-frame", { timeout: 60000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: "../docs/screenshots/01-map-layers.png", fullPage: true });

  const hotspotButton = page.locator(".hotspot-item button").first();
  if (await hotspotButton.count()) {
    await hotspotButton.click();
    await page.waitForTimeout(1500);
  }
  await page.screenshot({ path: "../docs/screenshots/02-hotspot-asset.png", fullPage: true });

  await page.screenshot({ path: "../docs/screenshots/03-events-card.png", fullPage: true });

  await page.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
  await page.fill('input[name="user"]', "admin");
  await page.fill('input[name="password"]', "admin");
  await page.click('button[type="submit"]');
  await page.waitForTimeout(2000);
  await page.goto("http://localhost:3000/d/floodmvp-api/floodmvp-api", { waitUntil: "networkidle" });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: "../docs/screenshots/04-grafana-dashboard.png", fullPage: true });
});
