import { expect, test } from "@playwright/test";

const liveStackEnabled = process.env.GRAPHVIEW_LIVE_STACK === "1";
const username = process.env.GRAPHVIEW_LIVE_USERNAME ?? "";
const password = process.env.GRAPHVIEW_LIVE_PASSWORD ?? "";

test.describe("production reference stack", () => {
  test.skip(!liveStackEnabled, "requires the production reference stack");

  test("OIDC login, graph UI, upload, worker, and review proposals use live services", async ({ page }) => {
    test.setTimeout(90_000);
    expect(username).not.toBe("");
    expect(password).not.toBe("");
    const sourceTitle = `Playwright live-stack evidence ${Date.now()}`;

    await page.goto("/");
    await expect(page).toHaveURL(/\/identity\/realms\/graphview\//);
    await page.getByLabel(/username|email/i).fill(username);
    await page.getByRole("textbox", { name: "Password", exact: true }).fill(password);
    await page.getByRole("button", { name: /sign in/i }).click();

    await expect(page).toHaveURL(/\/graph$/);
    await expect(page.locator('[data-testid="graph-canvas-root"], .graph-canvas-wrap').first()).toBeVisible();
    await expect(page.getByRole("img", { name: /rendered graph nodes/i })).toBeVisible();

    const session = await page.request.get("/api/v1/auth/session");
    expect(session.ok()).toBeTruthy();
    const csrfToken = String((await session.json()).csrf_token);
    expect(csrfToken).not.toBe("");

    const accepted = await page.request.post("/api/v1/uploads", {
      headers: { "X-CSRF-Token": csrfToken },
      multipart: {
        title: sourceTitle,
        graph_id: "project-default",
        file: {
          name: "live-stack.md",
          mimeType: "text/markdown",
          buffer: Buffer.from(`# ${sourceTitle}\nGraphview persists provenance through a real browser, API, object store, queue, and worker.`),
        },
      },
    });
    expect(accepted.status()).toBe(202);
    const jobId = String((await accepted.json()).job_id);

    await expect
      .poll(
        async () => {
          const response = await page.request.get(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
          expect(response.ok()).toBeTruthy();
          return response.json();
        },
        { timeout: 60_000, intervals: [250, 500, 1_000] },
      )
      .toMatchObject({
        status: "succeeded",
        kind: "upload.ingest",
        attempt: 1,
        result: {
          source: { title: sourceTitle },
        },
      });

    const review = await page.request.get("/api/v1/review-queue?graph_id=project-default&limit=100");
    expect(review.ok()).toBeTruthy();
    const reviewQueue = await review.json();
    expect(reviewQueue.pending_count).toBeGreaterThan(0);
    expect(reviewQueue.items.some((item: { source?: { title?: string } }) => item.source?.title === sourceTitle)).toBeTruthy();
  });
});
