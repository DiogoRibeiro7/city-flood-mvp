const { chromium } = require("playwright");

async function run() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const mode = process.env.SCREENSHOT_MODE || "full";

  async function gotoWithRetries(url, options = {}) {
    const attempts = 10;
    const delayMs = 1500;
    let lastErr;
    for (let i = 0; i < attempts; i++) {
      try {
        await page.goto(url, { waitUntil: "networkidle", ...options });
        return;
      } catch (err) {
        lastErr = err;
        await page.waitForTimeout(delayMs);
      }
    }
    throw lastErr;
  }
  await gotoWithRetries("http://localhost:5173");
  await page.waitForSelector(".map-frame", { timeout: 60000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "../docs/screenshots/01-map-layers.png", fullPage: true });

  const hotspotButton = page.locator(".hotspot-item button").first();
  if (await hotspotButton.count()) {
    await hotspotButton.click();
    await page.waitForTimeout(1500);
  }
  await page.screenshot({ path: "../docs/screenshots/02-hotspot-asset.png", fullPage: true });

  if (mode === "full") {
    await page.screenshot({ path: "../docs/screenshots/03-events-card.png", fullPage: true });

    await gotoWithRetries("http://localhost:3000/login");
    await page.fill('input[name="user"]', "admin");
    await page.fill('input[name="password"]', "admin");
    await page.click('button[type="submit"]');
    await page.waitForTimeout(2000);
    await gotoWithRetries("http://localhost:3000/d/floodmvp-api/floodmvp-api");
    await page.waitForTimeout(3000);
    await page.screenshot({ path: "../docs/screenshots/04-grafana-dashboard.png", fullPage: true });
  }

  await browser.close();
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
