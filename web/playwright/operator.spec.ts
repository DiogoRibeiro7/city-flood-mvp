import { expect, Page, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const from = "2026-01-01T00:00:00.000Z",
  to = "2026-01-01T01:00:00.000Z";
const path = `/?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
const assets = ["synthetic", "noaa"].map((id, index) => ({
  asset_id: id,
  city_id: "city",
  asset_type: "rain_gauge",
  name: `${id} gauge`,
  props: {},
  geom_geojson: { type: "Point", coordinates: [-8.61 + index * 0.01, 41.15] },
}));
const event = {
  event_id: "rain-event",
  event_type: "rain",
  severity: 1,
  confidence: 0.8,
  start_ts: from,
  end_ts: to,
  asset_ids: ["synthetic"],
  summary: "Rain episode (peak=8.0 mm/h)",
};

async function fixture(page: Page) {
  const state = {
    evidenceFailure: false,
    comparisonFailure: false,
    reportFailure: false,
    calls: [] as URL[],
    notes: [] as any[],
  };
  await page.route("https://**", (route) => route.abort());
  await page.route("**/v1/**", async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      p = url.pathname;
    state.calls.push(url);
    const headers = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "*",
      "Access-Control-Allow-Methods": "GET, POST, DELETE",
    };
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers });
      return;
    }
    let body: any = [],
      status = 200;
    if (p === "/v1/cities")
      body = [{ city_id: "city", name: "Fixture City", country: "PT" }];
    else if (p.endsWith("/assets"))
      body = url.searchParams.get("type") === "rain_gauge" ? assets : [];
    else if (p.endsWith("/metrics")) body = ["rain_mmph"];
    else if (p.endsWith("/observations/evidence")) {
      const noaa = p.includes("/noaa/");
      status = state.evidenceFailure ? 503 : 200;
      body = {
        rows: [
          {
            ts: from,
            value: 8,
            quality_flag: noaa ? "unverified" : "ok",
            source: noaa ? "noaa_ghcnh" : "synthetic",
            source_type: "fixture",
            source_id: noaa ? "station-1" : "fixture-1",
            scenario_id: null,
            measurement_context: noaa
              ? {
                  interval_minutes: 360,
                  conversion: "six-hour mean, not instantaneous rainfall",
                }
              : {},
          },
        ],
        has_more: false,
        next_offset: null,
      };
    } else if (p.endsWith("/observations:compare")) {
      status = state.comparisonFailure ? 503 : 200;
      body = {
        series: [
          { ts: from, base: 8, compare: 12, delta: 4 },
          { ts: to, base: null, compare: 9, delta: null },
        ],
      };
    } else if (p.endsWith("/observations"))
      body = {
        series: [
          { ts: from, value: 8 },
          { ts: to, value: null },
        ],
      };
    else if (p.endsWith("/scenarios"))
      body = [
        { scenario_id: "base", name: "Synthetic base" },
        { scenario_id: "compare", name: "Synthetic comparison" },
      ];
    else if (p === "/v1/events") body = [event];
    else if (p === "/v1/events/rain-event/run")
      body = {
        run_id: "producing-run",
        version: "fixture-v1",
        start_ts: from,
        end_ts: to,
        params: { rain_threshold_mmph: 5, rain_min_duration_minutes: 15 },
      };
    else if (p.endsWith("/status"))
      body = { risk: "watch", active_events: 1, hotspots: 0 };
    else if (p.endsWith("/summary"))
      body = { rain_mmph: 0, river_level_m: 0, status_counts: {} };
    else if (p === "/v1/notes") {
      if (request.method() === "POST") {
        body = {
          ...request.postDataJSON(),
          note_id: "note-1",
          created_at: from,
          updated_at: from,
        };
        state.notes.push(body);
      } else body = state.notes;
    } else if (p === "/v1/analytics/jobs") {
      status = state.reportFailure ? 503 : 200;
      body = { job_id: "report-1" };
    } else if (p.endsWith("/report-1")) body = { status: "completed" };
    else if (p.endsWith("/download")) {
      await route.fulfill({
        headers,
        contentType: "text/csv",
        body: "event_id\nrain-event\n",
      });
      return;
    }
    await route.fulfill({
      status,
      headers,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await page.goto(path);
  await expect(
    page.getByLabel("Inspect asset (loaded map selection)").locator("option"),
  ).toHaveCount(3);
  return state;
}

test("keyboard review distinguishes recorded reports from synthetic evidence and explains the producing run", async ({
  page,
}) => {
  await fixture(page);
  const select = page.getByLabel("Inspect asset (loaded map selection)");
  await select.focus();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Synthetic data", { exact: true })).toBeVisible();
  await expect(page.locator(".leaflet-interactive")).toHaveCount(2);
  await page.locator(".timeline-item").click();
  await expect(
    page.getByText("Stored rule: rain_mmph ≥ 5 for at least 15 minutes."),
  ).toBeVisible();
  await expect(page.getByText(/Confidence is a heuristic score/)).toBeVisible();
  await select.selectOption("noaa");
  await expect(page.getByText("Recorded weather report (NOAA)")).toBeVisible();
  await expect(
    page.getByText("unverified", { exact: false }).first(),
  ).toBeVisible();
  await expect(
    page.getByText(/six-hour mean, not instantaneous rainfall/),
  ).toBeVisible();
  await expect(page.getByText("Synthetic data", { exact: true })).toHaveCount(
    0,
  );
  const audit = await new AxeBuilder({ page })
    .include(".review-card")
    .include(".timeline-detail")
    .include(".notes-card")
    .include(".compare-panel")
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(audit.violations).toEqual([]);
});

test("window validation, sparse comparisons, failure clearing and evidence retry", async ({
  page,
}) => {
  const state = await fixture(page);
  await page
    .getByLabel("Inspect asset (loaded map selection)")
    .selectOption("synthetic");
  await expect(page.getByText("Synthetic data", { exact: true })).toBeVisible();
  await page.getByLabel("Base", { exact: true }).selectOption("base");
  await page.getByLabel("Compare", { exact: true }).selectOption("compare");
  await page
    .getByText("Comparison measurements (UTC)", { exact: true })
    .click();
  await expect(
    page
      .getByRole("region", { name: "Scenario comparison table" })
      .getByText("No sample"),
  ).toHaveCount(2);
  await page.getByLabel("To (UTC)").fill("2025-12-31T23:00");
  await page.getByRole("button", { name: "Apply window" }).click();
  await expect(page.getByRole("alert")).toContainText("end after the start");
  state.evidenceFailure = true;
  state.comparisonFailure = true;
  await page.getByLabel("To (UTC)").fill("2026-01-01T02:00");
  await page.getByRole("button", { name: "Apply window" }).click();
  await expect(
    page.getByRole("button", { name: "Retry evidence" }),
  ).toBeVisible();
  await expect(page.getByText("Synthetic data", { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("region", { name: "Scenario comparison table" }),
  ).toHaveCount(0);
  expect(
    state.calls
      .filter((u) =>
        [
          "/v1/events",
          "/v1/assets/synthetic/observations",
          "/v1/assets/synthetic/observations:compare",
          "/v1/assets/synthetic/observations/evidence",
        ].includes(u.pathname),
      )
      .slice(-4)
      .every((u) => u.searchParams.get("to") === "2026-01-01T02:00:00.000Z"),
  ).toBe(true);
  state.evidenceFailure = false;
  await page.getByRole("button", { name: "Retry evidence" }).click();
  await expect(page.getByText("Synthetic data", { exact: true })).toBeVisible();
});

test("a late measurement response cannot replace a newly selected asset", async ({
  page,
}) => {
  await fixture(page);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let received!: () => void;
  const pending = new Promise<void>((resolve) => {
    received = resolve;
  });
  await page.route(
    "**/assets/synthetic/observations/evidence?**",
    async (route) => {
      received();
      await gate;
      await route.fulfill({
        headers: { "Access-Control-Allow-Origin": "*" },
        json: {
          rows: [
            {
              ts: from,
              value: 999,
              quality_flag: "ok",
              source: "synthetic",
              source_type: "fixture",
              source_id: "late",
              scenario_id: null,
              measurement_context: {},
            },
          ],
          has_more: false,
          next_offset: null,
        },
      });
    },
  );
  await page
    .getByLabel("Inspect asset (loaded map selection)")
    .selectOption("synthetic");
  await pending;
  await page
    .getByLabel("Inspect asset (loaded map selection)")
    .selectOption("noaa");
  await expect(page.getByText("Recorded weather report (NOAA)")).toBeVisible();
  const response = page.waitForResponse((r) =>
    r.url().includes("synthetic/observations/evidence"),
  );
  release();
  await response;
  await expect(page.getByText("Synthetic data", { exact: true })).toHaveCount(
    0,
  );
  await expect(page.getByText("Recorded weather report (NOAA)")).toBeVisible();
});

test("notes retain evidence links and failed reports remain recoverable", async ({
  page,
}) => {
  const state = await fixture(page);
  const errors: Error[] = [];
  page.on("pageerror", (error) => errors.push(error));
  await page.getByLabel("Role", { exact: true }).selectOption("analyst");
  await page
    .getByLabel("Inspect asset (loaded map selection)")
    .selectOption("synthetic");
  await page.locator(".timeline-item").click();
  await page.locator("#note-title").fill("Synthetic evidence review");
  await page
    .getByLabel("Note body", { exact: true })
    .fill(
      "Synthetic rain, quality ok; heuristic event, not a confirmed flood. UTC 00:00–01:00.",
    );
  await page.getByLabel("Attach to event").check();
  await page.getByRole("button", { name: "Add note", exact: true }).click();
  await expect.poll(() => state.notes.length).toBe(1);
  expect(state.notes[0]).toMatchObject({
    asset_id: "synthetic",
    event_id: "rain-event",
  });
  state.reportFailure = true;
  await page.getByRole("button", { name: "Download CSV", exact: true }).click();
  await expect(page.locator(".report-status")).toContainText("503");
  await expect(
    page.getByRole("button", { name: "Download CSV", exact: true }),
  ).toBeEnabled();
  state.reportFailure = false;
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.csv$/);
  await expect(page.locator(".report-status")).toHaveText("Report downloaded");
  expect(errors).toEqual([]);
});

test("saved reviews restore the historical window and selected event", async ({
  page,
}) => {
  await fixture(page);
  await page
    .getByLabel("Inspect asset (loaded map selection)")
    .selectOption("synthetic");
  await page.locator(".timeline-item").click();
  await page.getByLabel("Save view", { exact: true }).fill("Historical review");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await page.getByLabel("From (UTC)").fill("2026-01-02T00:00");
  await page.getByLabel("To (UTC)").fill("2026-01-02T01:00");
  await page.getByRole("button", { name: "Apply window", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Why this event fired" }),
  ).toHaveCount(0);
  await page
    .locator(".story-item")
    .filter({ hasText: "Historical review" })
    .getByRole("button", { name: "Apply", exact: true })
    .click();
  await expect(page.getByLabel("From (UTC)")).toHaveValue("2026-01-01T00:00");
  await expect(page.getByLabel("To (UTC)")).toHaveValue("2026-01-01T01:00");
  await expect(
    page.getByText("Stored rule: rain_mmph ≥ 5 for at least 15 minutes."),
  ).toBeVisible();
});
