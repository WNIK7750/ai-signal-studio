import { expect, test } from "@playwright/test";
import path from "node:path";

test("filters capability calls with extensible top categories", async ({
  page,
}) => {
  const now = new Date().toISOString();
  await page.route("**/api/capability-invocations", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([
        invocation("inv_1", "intelligence.search", now),
        invocation("inv_2", "agent.conversation.list", now),
        invocation("inv_3", "artifact.search", now),
        invocation("inv_4", "future.unknown", now),
      ]),
    });
  });
  await page.route("**/api/collection-runs", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: "[]",
    });
  });

  await page.goto("/runs");

  await expect(page.getByRole("button", { name: "全部 4" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "信息处理 1" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "其他 1" })).toBeVisible();
  await page.getByRole("button", { name: "内容产物 1" }).click();
  await expect(page.getByText("artifact.search")).toBeVisible();
  await expect(page.getByText("intelligence.search")).toHaveCount(0);
  await page.getByRole("button", { name: "其他 1" }).click();
  await expect(page.getByText("future.unknown")).toBeVisible();
  await page.screenshot({
    path: path.join(
      process.env.TEMP ?? ".",
      "ai-signal-runs-categories-1440.png",
    ),
    fullPage: true,
  });
});

function invocation(id: string, capabilityId: string, startedAt: string) {
  return {
    id,
    capability_id: capabilityId,
    actor_type: "user",
    status: "completed",
    started_at: startedAt,
    error_code: null,
  };
}
