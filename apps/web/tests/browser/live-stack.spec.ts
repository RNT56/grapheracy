import { expect, test, type Page } from "@playwright/test";

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

    const session = await browserGet(page, "/api/v1/auth/session");
    expect(session.ok).toBeTruthy();
    const csrfToken = String(session.json.csrf_token);
    expect(csrfToken).not.toBe("");

    const accepted = await page.evaluate(async ({ csrfToken, sourceTitle }) => {
      const form = new FormData();
      form.append("title", sourceTitle);
      form.append("graph_id", "project-default");
      form.append(
        "file",
        new File(
          [`# ${sourceTitle}\nGraphview persists provenance through a real browser, API, object store, queue, and worker.`],
          "live-stack.md",
          { type: "text/markdown" },
        ),
      );
      const response = await fetch("/api/v1/uploads", {
        method: "POST",
        headers: { "X-CSRF-Token": csrfToken },
        body: form,
      });
      return {
        status: response.status,
        traceId: response.headers.get("x-graphview-trace-id"),
        json: await response.json(),
      };
    }, { csrfToken, sourceTitle });
    expect(accepted.status).toBe(202);
    expect(accepted.traceId).toMatch(/^[0-9a-f]{32}$/);
    const jobId = String(accepted.json.job_id);

    await expect
      .poll(
        async () => {
          const response = await browserGet(page, `/api/v1/jobs/${encodeURIComponent(jobId)}`);
          expect(response.ok).toBeTruthy();
          return response.json;
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

    const review = await browserGet(page, "/api/v1/review-queue?graph_id=project-default&limit=100");
    expect(review.ok).toBeTruthy();
    const reviewQueue = review.json as {
      pending_count: number;
      items: Array<{ source?: { title?: string } }>;
    };
    expect(reviewQueue.pending_count).toBeGreaterThan(0);
    expect(reviewQueue.items.some((item: { source?: { title?: string } }) => item.source?.title === sourceTitle)).toBeTruthy();

    const jobStream = await browserGet(page, `/api/v1/jobs/${encodeURIComponent(jobId)}/stream`);
    expect(jobStream.ok).toBeTruthy();
    expect(jobStream.text).toContain("event: job.succeeded");
  });
});

async function browserGet(page: Page, path: string) {
  return page.evaluate(async (requestPath) => {
    const response = await fetch(requestPath);
    const text = await response.text();
    let json: Record<string, unknown> = {};
    try {
      json = JSON.parse(text) as Record<string, unknown>;
    } catch {
      // SSE and other non-JSON responses are asserted through text.
    }
    return { ok: response.ok, status: response.status, text, json };
  }, path);
}
