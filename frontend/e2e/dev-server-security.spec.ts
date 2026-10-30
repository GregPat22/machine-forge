import { test, expect } from "@playwright/test";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer, type ViteDevServer } from "vite";

// A disposable loopback server and a synthetic file only: no real .env or installation data.
let directory: string;
let server: ViteDevServer;
let origin: string;
const marker = "synthetic-file-content-for-deny-regression";

test.beforeAll(async () => {
  directory = await mkdtemp(join(tmpdir(), "machine-forge-vite-deny-"));
  await writeFile(join(directory, "index.html"), "<p>Synthetic fixture</p>");
  await writeFile(join(directory, "fixture.crt"), marker);
  server = await createServer({
    root: directory, configFile: false, envFile: false, logLevel: "silent",
    server: { host: "127.0.0.1", port: 0, fs: { allow: [directory] } },
  });
  await server.listen();
  const address = server.httpServer?.address();
  if (!address || typeof address === "string") throw new Error("The fixture server needs a TCP port");
  origin = `http://127.0.0.1:${address.port}`;
});

test.afterAll(async () => {
  await server?.close();
  if (directory) await rm(directory, { recursive: true, force: true });
});

test("the fixture server serves permitted files and denies the protected file", async ({ request }) => {
  expect((await request.get(`${origin}/index.html`)).status()).toBe(200);
  expect((await request.get(`${origin}/fixture.crt`)).status()).toBe(403);
});

for (const query of ["?raw", "?import&raw", "?import&url&inline"]) {
  test(`a query cannot bypass fs.deny: ${query}`, async ({ request }) => {
    const response = await request.get(`${origin}/fixture.crt${query}`);
    expect(response.status()).toBe(403);
    expect(await response.text()).not.toContain(marker);
  });
}
