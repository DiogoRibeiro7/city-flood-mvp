import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

const api = process.env.OPERATOR_API_BASE!;
if (!api || new URL(api).hostname !== "127.0.0.1")
  throw new Error("Disposable loopback API required");

test("real observation → producing event → persisted note → worker CSV → synthetic comparison", async ({
  page,
  request,
}, info) => {
  const errors: Error[] = [];
  page.on("pageerror", (error) => errors.push(error));
  await page.goto("/?from=2026-01-01T00:00:00Z&to=2026-01-01T01:00:00Z");
  const asset = page.getByLabel("Inspect asset (loaded map selection)");
  await expect(asset.locator("option")).toHaveCount(4); // Placeholder plus the three smoke assets.
  await asset.selectOption("smoke_rain");
  await expect(page.getByText("12 records on this page.")).toBeVisible();
  await expect(
    page
      .getByRole("table", { name: "Raw measurements" })
      .getByText("Synthetic data", { exact: true }),
  ).toHaveCount(12);
  await page
    .locator(".timeline-item")
    .filter({ has: page.locator(".timeline-title", { hasText: /^rain$/ }) })
    .click();
  await expect(
    page.getByText("Stored rule: rain_mmph ≥ 5 for at least 15 minutes."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Focus asset", exact: true }).click();
  await expect(asset).toHaveValue("smoke_rain");
  await page
    .locator(".review-card")
    .screenshot({ path: info.outputPath("synthetic-observation-review.png") });
  await page
    .locator(".timeline-detail")
    .screenshot({ path: info.outputPath("synthetic-event-explanation.png") });
  await page.getByLabel("Role", { exact: true }).selectOption("analyst");
  await page.locator("#note-title").fill("Operator smoke evidence review");
  await page
    .getByLabel("Note body", { exact: true })
    .fill(
      "Synthetic smoke-v1 rain. 8 mm/h, stored quality ok. Producing rule 5 mm/h for 15 minutes. Heuristic event, not a confirmed flood; 2026-01-01 00:00–01:00 UTC.",
    );
  await page.getByLabel("Attach to event").check();
  await page.getByRole("button", { name: "Add note", exact: true }).click();
  await expect(page.locator(".note-list")).toContainText(
    "Operator smoke evidence review",
  );
  const notesResponse = await request.get(
    `${api}/v1/notes?city_id=city_porto_mvp`,
  );
  expect(notesResponse.ok()).toBe(true);
  const note = (await notesResponse.json()).find(
    (n: any) => n.title === "Operator smoke evidence review",
  );
  expect(note.asset_id).toBe("smoke_rain");
  expect(note.event_id).toBeTruthy();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV", exact: true }).click();
  const csv = await download;
  await csv.saveAs(info.outputPath("operator-report.csv"));
  const content = await readFile(
    info.outputPath("operator-report.csv"),
    "utf8",
  );
  expect(content).toContain(note.event_id);
  expect(content).toContain("rain");
  await expect(page.locator(".report-status")).toHaveText("Report downloaded");

  // The comparison is explicitly a separate synthetic what-if window, not evidence for the Jan 1 event.
  await page.getByLabel("From (UTC)").fill("2026-01-02T00:00");
  await page.getByLabel("To (UTC)").fill("2026-01-02T01:00");
  await page.getByRole("button", { name: "Apply window" }).click();
  await asset.selectOption("smoke_pipe");
  await page
    .getByLabel("Scenario", { exact: true })
    .selectOption("operator-base");
  await expect(
    page.getByText("suspect", { exact: false }).first(),
  ).toBeVisible();
  await page.getByLabel("Base", { exact: true }).selectOption("operator-base");
  await page
    .getByLabel("Compare", { exact: true })
    .selectOption("operator-test");
  await page
    .getByText("Comparison measurements (UTC)", { exact: true })
    .click();
  const table = page.getByRole("region", { name: "Scenario comparison table" });
  await expect(table.getByRole("row")).toHaveCount(13);
  await expect(table.getByText("No sample", { exact: true })).toHaveCount(2);
  await expect(table.getByRole("cell", { name: "1", exact: true })).toHaveCount(
    11,
  );
  await page
    .locator(".compare-panel")
    .screenshot({ path: info.outputPath("synthetic-scenario-comparison.png") });
  expect(errors).toEqual([]);
});
