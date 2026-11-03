import { expect, test, type APIRequestContext } from "@playwright/test";

async function project(request: APIRequestContext) {
  const response = await request.post("/api/projects", { data: { problem: "Synthetic frontend renewal fixture" } });
  expect(response.status()).toBe(201);
  return response.json();
}

test("Overview uses live model counts and requirements for different designs", async ({ page, request }) => {
  for (const changed of [false, true]) {
    let current = await project(request);
    if (changed) {
      const response = await request.post(`/api/projects/${current.id}/patches`, {
        data: {
          expected_revision: 1,
          patches: [
            { op: "remove_station", station_id: "st-control" },
            { op: "set_param", name: "target_rate_text", text: "450 packs/min" },
            { op: "add_open_question", text: "Synthetic additional engineering question?" },
          ],
        },
      });
      expect(response.status()).toBe(200);
      current = await response.json();
    }
    await page.goto(`/projects/${current.id}`);
    await expect(page.getByTestId("overview-requested-rate")).toHaveText(current.design.target_rate_text);
    await expect(page.getByTestId("overview-station-count")).toHaveText(String(current.design.stations.length));
    const count = current.design.stations.reduce(
      (total: number, station: { components: unknown[] }) => total + station.components.length,
      0,
    );
    await expect(page.getByTestId("overview-component-count")).toHaveText(String(count));
    await expect(page.getByTestId("overview-question-count")).toHaveText(String(current.design.open_questions.length));
  }
});

test("station inspection reaches the selected station's actual editor", async ({ page, request }) => {
  const current = await project(request);
  await page.goto(`/projects/${current.id}`);
  await page.getByTestId("inspect-st-sealing").click();
  const inspector = page.getByRole("dialog", { name: "Lidding and sealing" });
  await expect(inspector).toContainText("1,000 mm");
  await expect(inspector).toContainText("m-sealing-lift");
  await inspector.getByRole("button", { name: "Open in model editor" }).click();
  await expect(page).toHaveURL(/tab=model.*station=st-sealing/);
  const station = page.getByTestId("station-st-sealing");
  await expect(station.getByRole("button", { name: /Lidding and sealing/ }).first()).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  await expect(station.getByTestId("mechanism-m-sealing-lift")).toBeVisible();
});

test("assistant draft survives closing and navigation; question prefill does not send", async ({ page, request }) => {
  const current = await project(request);
  const prompts: string[] = [];
  page.on("request", (req) => {
    if (/\/prompt(\/stream)?$/.test(new URL(req.url()).pathname)) prompts.push(req.url());
  });
  await page.goto(`/projects/${current.id}`);
  await page.getByRole("button", { name: "Review open question" }).click();
  const assistant = page.getByRole("dialog", { name: "Engineering assistant", exact: true });
  const draft = assistant.getByRole("textbox", { name: "Message" });
  await expect(draft).toHaveValue(new RegExp(current.design.open_questions[0].replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  await draft.fill("Synthetic draft kept across views");
  await assistant.getByRole("button", { name: "Close assistant" }).click();
  await page.getByRole("navigation", { name: "Project" }).getByRole("button", { name: "Model", exact: true }).click();
  await page.getByRole("button", { name: "Engineering assistant", exact: true }).click();
  await expect(draft).toHaveValue("Synthetic draft kept across views");
  expect(prompts).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Engineering assistant", exact: true })).toBeFocused();
});

test("history remains read-only and downloads follow the viewed revision", async ({ page, request }) => {
  const current = await project(request);
  const updated = await request.post(`/api/projects/${current.id}/patches`, {
    data: {
      expected_revision: 1,
      patches: [{ op: "set_param", name: "name", text: "Synthetic newer design" }],
    },
  });
  expect(updated.status()).toBe(200);
  await page.goto(`/projects/${current.id}?tab=revisions`);
  await page.getByTestId("revision-1").getByRole("button", { name: "View", exact: true }).click();
  await expect(page.getByTestId("historical-revision")).toContainText("Viewing revision 1");
  const nav = page.getByRole("navigation", { name: "Project" });
  await nav.getByRole("button", { name: "Model", exact: true }).click();
  await expect(page.getByText("This is an older revision:", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add station", exact: true })).toHaveCount(0);
  await nav.getByRole("button", { name: "Layout", exact: true }).click();
  await expect(page.getByRole("link", { name: "DXF for CAD" })).toHaveAttribute("href", /revision=1/);
  await page.getByRole("button", { name: "Back to latest" }).click();
  await expect(page.getByTestId("historical-revision")).toHaveCount(0);
  await nav.getByRole("button", { name: "Model", exact: true }).click();
  await expect(page.getByRole("button", { name: "Add station", exact: true })).toBeVisible();
});

test("all project outputs remain reachable and tab URLs survive reload", async ({ page, request }) => {
  const current = await project(request);
  await page.goto(`/projects/${current.id}`);
  const nav = page.getByRole("navigation", { name: "Project" });
  for (const [name, tab] of [
    ["Model", "model"],
    ["Timing", "timing"],
    ["Layout", "layout"],
    ["Parts", "parts"],
    ["Documents", "docs"],
    ["PLC", "plc"],
    ["Revisions (1)", "revisions"],
  ]) {
    await nav.getByRole("button", { name, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`tab=${tab}`));
    await page.reload();
    await expect(nav.getByRole("button", { name, exact: true })).toHaveAttribute("aria-current", "page");
  }
  await nav.getByRole("button", { name: "Documents", exact: true }).click();
  await expect(page.getByRole("link", { name: /Word/ })).toHaveAttribute("href", /documents\.docx\?revision=1/);
  await nav.getByRole("button", { name: "Parts", exact: true }).click();
  await expect(page.getByRole("link", { name: "Download CSV" })).toHaveAttribute(
    "href",
    /spare-parts\.csv\?revision=1/,
  );
  await nav.getByRole("button", { name: "PLC", exact: true }).click();
  await expect(page.getByRole("link", { name: "PLCopen XML" })).toHaveAttribute("href", /plc\.xml\?revision=1/);
  await page.getByRole("link", { name: "Suppliers", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Supplier ratings", exact: true })).toBeVisible();
});

test("mobile project navigation and station dialog support keyboard dismissal", async ({ page, request }) => {
  const current = await project(request);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/projects/${current.id}`);
  const menu = page.getByRole("button", { name: "Open navigation", exact: true });
  await menu.click();
  await expect(page.getByRole("dialog", { name: "Navigation" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeFocused();
  await page.getByTestId("inspect-st-sealing").click();
  await expect(page.getByRole("dialog", { name: "Lidding and sealing" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("inspect-st-sealing")).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("empty model and missing requirement have readable Overview states", async ({ page, request }) => {
  const current = await project(request);
  await page.route(`**/api/projects/${current.id}`, (route) =>
    route.fulfill({
      json: {
        ...current,
        design: { ...current.design, stations: [], transports: [], target_rate_text: null, open_questions: [] },
      },
    }),
  );
  await page.goto(`/projects/${current.id}`);
  await expect(page.getByTestId("overview-station-count")).toHaveText("0");
  await expect(page.getByTestId("overview-requested-rate")).toHaveText("Not specified");
  await expect(page.getByText("No stations in this concept yet.", { exact: true })).toBeVisible();
  await expect(page.getByText("No open questions recorded.", { exact: true })).toBeVisible();
});

test("a layout failure can be retried without hiding the project model", async ({ page, request }) => {
  const current = await project(request);
  let failed = true;
  await page.route(`**/api/projects/${current.id}/layout?*`, (route) =>
    failed ? route.fulfill({ status: 500, json: { detail: "Synthetic layout failure" } }) : route.continue(),
  );
  await page.goto(`/projects/${current.id}`);
  await expect(page.getByText("Synthetic layout failure", { exact: true })).toBeVisible();
  await expect(page.getByTestId("overview-station-count")).toHaveText(String(current.design.stations.length));
  failed = false;
  await page.getByRole("button", { name: "Retry layout", exact: true }).click();
  await expect(page.getByTestId("concept-preview")).toBeVisible();
  await expect(page.getByText("Synthetic layout failure", { exact: true })).toHaveCount(0);
});

test("closing the assistant and changing views preserves one active request", async ({ page, request }) => {
  const current = await project(request);
  let finish!: () => void;
  const held = new Promise<void>((resolve) => {
    finish = resolve;
  });
  let calls = 0;
  await page.route(`**/api/projects/${current.id}/prompt/stream`, async (route) => {
    calls += 1;
    await held;
    const saved = await request.post(`/api/projects/${current.id}/patches`, {
      data: {
        expected_revision: 1,
        patches: [{ op: "set_param", name: "name", text: "Synthetic completed change" }],
      },
    });
    expect(saved.status()).toBe(200);
    const updated = await saved.json();
    await route.fulfill({
      contentType: "text/event-stream",
      body: `event: done\ndata: ${JSON.stringify({ ...updated, messages: [...updated.messages, { role: "assistant", content: "Synthetic completed response", revision: 2 }] })}\n\n`,
    });
  });
  await page.goto(`/projects/${current.id}`);
  await page.getByRole("button", { name: "Engineering assistant", exact: true }).click();
  const assistant = page.getByRole("dialog", { name: "Engineering assistant", exact: true });
  await assistant.getByRole("textbox", { name: "Message" }).fill("Synthetic pending request");
  await assistant.getByRole("button", { name: "Send", exact: true }).click();
  await expect(assistant.getByRole("button", { name: "Working…", exact: true })).toBeDisabled();
  await assistant.getByRole("button", { name: "Close assistant" }).click();
  await page.getByRole("navigation", { name: "Project" }).getByRole("button", { name: "Timing", exact: true }).click();
  await page.getByRole("button", { name: "Engineering assistant", exact: true }).click();
  await expect(assistant.getByRole("textbox", { name: "Message" })).toHaveValue("Synthetic pending request");
  await expect(assistant.getByRole("button", { name: "Working…", exact: true })).toBeDisabled();
  finish();
  await expect(assistant.getByText("Synthetic completed response", { exact: false })).toBeVisible();
  await expect(assistant.getByRole("textbox", { name: "Message" })).toHaveValue("");
  expect(calls).toBe(1);
});

test("dense model, timing and revision views fit a mobile viewport", async ({ page, request }) => {
  const current = await project(request);
  const patched = await request.post(`/api/projects/${current.id}/patches`, {
    data: {
      expected_revision: 1,
      patches: [{ op: "set_param", name: "name", text: "Synthetic longer project name for mobile revision controls" }],
    },
  });
  expect(patched.status()).toBe(200);
  await page.setViewportSize({ width: 390, height: 844 });
  for (const tab of ["model", "timing", "revisions"]) {
    await page.goto(`/projects/${current.id}?tab=${tab}`);
    if (tab === "model") {
      await page
        .getByTestId("station-st-sealing")
        .getByRole("button", { name: /Lidding and sealing/ })
        .first()
        .click();
      await expect(page.getByTestId("mechanism-m-sealing-lift")).toBeVisible();
      const mechanismTable = page.locator("table").filter({ has: page.getByTestId("mechanism-m-sealing-lift") });
      expect(await mechanismTable.evaluate((table) => table.scrollWidth > table.parentElement!.clientWidth)).toBe(true);
      expect(await mechanismTable.evaluate((table) => getComputedStyle(table.parentElement!).overflowX)).toBe("auto");
      const idCell = page.getByTestId("mechanism-m-sealing-lift").locator("td").first();
      const idLines = await idCell.evaluate((cell) => {
        const text = document.createRange();
        text.selectNodeContents(cell);
        return text.getBoundingClientRect().height / parseFloat(getComputedStyle(cell).lineHeight);
      });
      // This three-part ID may wrap at hyphens; it must not collapse into individual characters.
      expect(idLines).toBeLessThanOrEqual(3);
    } else if (tab === "timing") {
      await expect(page.getByTestId("timing-check")).toBeVisible();
    } else {
      await expect(page.getByTestId("revision-1")).toBeVisible();
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});
