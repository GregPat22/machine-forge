import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Phase 2 spec, "Tests to add / Frontend (step 7b)": the Timing tab draws the engine's result on a
// scale the test can measure, and a stroke edited in the model editor changes the cycle time with no
// AI call. The scratch backend runs the mock blister scenario (playwright.config.ts, ADR 0025).

interface StationTiming {
  station_id: string;
  cycle_time_s: number | null;
}

async function blisterProject(request: APIRequestContext): Promise<string> {
  const created = await request.post("/api/projects", { data: { problem: "Pack tablets into blisters." } });
  expect(created.status()).toBe(201);
  return (await created.json()).id;
}

async function timing(request: APIRequestContext, id: string): Promise<StationTiming[]> {
  const response = await request.get(`/api/projects/${id}/timing`);
  expect(response.status()).toBe(200);
  return (await response.json()).stations;
}

/** The x of a vertical tick mark, in page pixels. */
async function tickX(page: Page, testId: string): Promise<number> {
  const box = await page.getByTestId(testId).boundingBox();
  expect(box, testId).not.toBeNull();
  return box!.x + box!.width / 2;
}

test("the cycle bar of each blister station spans the computed cycle time", async ({ page, request }) => {
  const id = await blisterProject(request);
  const stations = (await timing(request, id)).filter((s) => s.cycle_time_s !== null);
  // Section H: every blister process station is computable.
  expect(stations.map((s) => s.station_id)).toEqual(["st-forming", "st-feeding", "st-sealing", "st-cutting"]);

  await page.goto(`/projects/${id}?tab=timing`);
  for (const station of stations) {
    const sid = station.station_id;
    const cycle = station.cycle_time_s!;
    await expect(page.getByTestId(`timing-diagram-${sid}`)).toBeVisible();

    // The drawn scale: pixels per second between the 0 tick and the axis end tick.
    const x0 = await tickX(page, `timing-axis-zero-${sid}`);
    const xEnd = await tickX(page, `timing-axis-end-${sid}`);
    const endTime = Number(await page.getByTestId(`timing-axis-end-${sid}`).getAttribute("data-time-s"));
    expect(endTime).toBeGreaterThanOrEqual(cycle);
    const scale = (xEnd - x0) / endTime;

    // The critical-path bar that ends last.
    const bars = page.locator(`[data-testid^="timing-bar-${sid}-"][data-critical="true"]`);
    let last = { end: -1, right: 0 };
    for (const bar of await bars.all()) {
      const end = Number(await bar.getAttribute("data-end-s"));
      const box = (await bar.boundingBox())!;
      if (end > last.end) last = { end, right: box.x + box.width };
    }
    expect(last.end).toBe(cycle);
    expect(Math.abs(last.right - (x0 + cycle * scale)), sid).toBeLessThanOrEqual(1);

    const readout = page.getByTestId(`timing-cycle-readout-${sid}`);
    expect(Number(await readout.getAttribute("data-value-s"))).toBe(cycle);
    await expect(readout).toContainText(`${cycle.toFixed(3)} s`);
  }
});

test("changing a stroke in the model editor changes the cycle time with no AI call", async ({ page, request }) => {
  const id = await blisterProject(request);
  const before = (await timing(request, id)).find((s) => s.station_id === "st-forming")!.cycle_time_s!;

  await page.goto(`/projects/${id}?tab=model`);
  await expect(page.getByRole("button", { name: "Revisions (1)" })).toBeVisible();
  // Every request from here on: none may reach an endpoint that calls the AI.
  const urls: string[] = [];
  page.on("request", (r) => urls.push(new URL(r.url()).pathname));

  // Section H: the film index of st-forming is on the critical path.
  const station = page.getByTestId("station-st-forming");
  await station.getByRole("button", { name: /Film unwind and forming/ }).click();
  await station.getByTestId("mechanism-m-film-index").getByRole("button", { name: "Edit" }).click();
  const form = station.getByTestId("form-edit-mechanism-m-film-index");
  await form.getByLabel("Stroke").fill("200");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "Revisions (2)" })).toBeVisible();

  await page.getByRole("button", { name: "Timing", exact: true }).click();
  const after = (await timing(request, id)).find((s) => s.station_id === "st-forming")!.cycle_time_s!;
  expect(after).not.toBe(before);
  const readout = page.getByTestId("timing-cycle-readout-st-forming");
  await expect(readout).toHaveAttribute("data-value-s", String(after));
  await expect(readout).toContainText(`${after.toFixed(3)} s`);
  // 200 mm takes the forming station past its 1.2 s target: the engine's warning reaches the panel.
  await expect(page.getByTestId("timing-check-st-forming")).toHaveAttribute("data-status", "misses");
  await expect(page.getByTestId("timing-warning-st-forming-target_not_met")).toBeVisible();

  expect(urls.some((u) => u.includes("/api/"))).toBe(true);
  expect(urls.filter((u) => /\/prompt(\/stream)?$|^\/api\/projects\/stream$/.test(u))).toEqual([]);
});
