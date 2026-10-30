import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

async function projectWithThreeRevisions(request: APIRequestContext): Promise<string> {
  const created = await request.post("/api/projects", { data: { problem: "Synthetic revision comparison test" } });
  expect(created.status()).toBe(201);
  const { id } = await created.json();
  for (const [revision, name] of [[1, "Synthetic B"], [2, "Synthetic C"]] as const) {
    const response = await request.post(`/api/projects/${id}/patches`, {
      data: { expected_revision: revision, patches: [{ op: "set_param", name: "name", text: name }] },
    });
    expect(response.status()).toBe(200);
  }
  return id;
}

async function paint(page: Page) {
  // Wait for response callbacks and React's next paint; no arbitrary network timing assumption.
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
}

for (const lateError of [false, true]) {
  test(`a late ${lateError ? "error" : "result"} cannot replace the selected revision pair`, async ({ page, request }) => {
    const id = await projectWithThreeRevisions(request);
    await page.goto(`/projects/${id}?tab=revisions`);
    await expect(page.getByText("r2 → r3", { exact: true })).toBeVisible();
    let release!: () => void;
    let arrived!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const pending = new Promise<void>((resolve) => { arrived = resolve; });
    const delayed = `**/api/projects/${id}/diff?from=1&to=3`;
    await page.route(delayed, async (route) => {
      const response = await route.fetch();
      arrived();
      await gate;
      if (lateError) await route.fulfill({ status: 500, json: { detail: "Synthetic obsolete error" } });
      else await route.fulfill({ response });
    });
    await page.getByRole("combobox").nth(0).selectOption("1");
    await pending;
    await page.getByRole("combobox").nth(1).selectOption("2");
    await expect(page.getByText("r1 → r2", { exact: true })).toBeVisible();
    const completed = page.waitForResponse((r) => r.url().endsWith("/diff?from=1&to=3"));
    release();
    await (await completed).finished();
    await paint(page);
    await expect(page.getByText("r1 → r2", { exact: true })).toBeVisible();
    await expect(page.getByText("Synthetic obsolete error")).toHaveCount(0);
  });
}

test("a failed comparison can recover when a different revision pair is selected", async ({ page, request }) => {
  const id = await projectWithThreeRevisions(request);
  await page.route(`**/api/projects/${id}/diff?from=2&to=3`, route =>
    route.fulfill({ status: 500, json: { detail: "Synthetic temporary error" } }));
  await page.goto(`/projects/${id}?tab=revisions`);
  await expect(page.getByText("Synthetic temporary error")).toBeVisible();
  await page.getByRole("combobox").nth(0).selectOption("1");
  await expect(page.getByText("r1 → r3", { exact: true })).toBeVisible();
  await expect(page.getByText("Synthetic temporary error")).toHaveCount(0);
});
