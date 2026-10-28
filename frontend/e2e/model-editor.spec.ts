import { expect, test } from "@playwright/test";

// Phase 1 spec, section G: create a demo project with the mock provider, edit a station
// parameter in the model editor, see a new revision and the changed value after reload.
// The demo stations carry no parameters, so the test adds one first, then edits it.
test("a station parameter edited in the model editor is a new revision and survives a reload", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder(/We need to pack/).fill("Pack 300 tablets per minute into PVC/Alu blisters of 10.");
  await page.getByRole("button", { name: "Design the machine" }).click();
  await page.waitForURL(/\/projects\/[^/?]+/);
  await expect(page.getByRole("button", { name: "Revisions (1)" })).toBeVisible();

  await page.getByRole("button", { name: "Model", exact: true }).click();
  const station = page.getByTestId("station-st-forming");
  await station.getByRole("button", { name: /Film unwind and forming/ }).click();

  // Add the parameter: revision 2.
  await station.getByRole("button", { name: "Add parameter" }).click();
  const addForm = station.getByTestId("form-add-parameter");
  await addForm.getByLabel("Name").fill("film-width");
  await addForm.getByLabel("Value").fill("120");
  await addForm.getByLabel("Unit").fill("mm");
  await addForm.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "Revisions (2)" })).toBeVisible();
  const row = station.getByTestId("parameter-film-width");
  await expect(row).toContainText("120");
  await expect(row).toContainText("mm");

  // Edit its value: revision 3.
  await row.getByRole("button", { name: "Edit" }).click();
  const editForm = station.getByTestId("form-edit-parameter-film-width");
  await editForm.getByLabel("Value").fill("150");
  await editForm.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "Revisions (3)" })).toBeVisible();
  await expect(row).toContainText("150");
  await expect(page.getByText("from the model editor").first()).toBeVisible();

  // After a reload the value comes back from the server, on the Model tab (kept in the URL).
  await page.reload();
  await expect(page.getByRole("button", { name: "Revisions (3)" })).toBeVisible();
  const reloaded = page.getByTestId("station-st-forming");
  await reloaded.getByRole("button", { name: /Film unwind and forming/ }).click();
  const reloadedRow = reloaded.getByTestId("parameter-film-width");
  await expect(reloadedRow).toContainText("150");
  await expect(reloadedRow).toContainText("mm");
});
