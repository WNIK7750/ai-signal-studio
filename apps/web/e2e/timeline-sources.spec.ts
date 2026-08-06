import { expect, test } from "@playwright/test";

test("timeline groups by stable day, opens detail, and restores collapse state", async ({
  page,
}) => {
  await page.goto("/timeline");
  const collectionResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/collection-runs") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "立即采集" }).click();
  await collectionResponse;

  const recentDay = page.locator(".timeline-day").first();
  const toggle = recentDay.locator(".timeline-day-toggle");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await recentDay.locator(".timeline-title-button").first().click();
  await expect(
    page.getByRole("complementary", { name: "信息详情" }),
  ).toBeVisible();

  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await page.reload();
  await expect(
    page.locator(".timeline-day").first().locator(".timeline-day-toggle"),
  ).toHaveAttribute("aria-expanded", "false");
});

test("source draft can be tested in a dialog before it is saved", async ({
  page,
}) => {
  await page.route("**/api/sources/test-definition", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        source_id: null,
        status: "healthy",
        items_count: 2,
        sample_titles: ["示例标题一", "示例标题二"],
        error_code: null,
      }),
    });
  });

  await page.goto("/settings/sources");
  await page.getByRole("button", { name: "添加来源" }).click();
  const dialog = page.getByRole("dialog", { name: "添加来源" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("来源名称").fill("测试草稿来源");
  await dialog
    .getByLabel("地址或仓库")
    .fill("https://example.com/feed.xml");
  await dialog.getByRole("button", { name: "保存前测试" }).click();

  await expect(dialog.getByRole("status")).toContainText(
    "连接正常 · 读取到 2 条",
  );
  await expect(dialog.getByText("示例标题一")).toBeVisible();
  await dialog.getByRole("button", { name: "关闭来源表单" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("测试草稿来源")).toHaveCount(0);
});
