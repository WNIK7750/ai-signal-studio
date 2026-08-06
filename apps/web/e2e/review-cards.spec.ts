import { expect, test } from "@playwright/test";
import path from "node:path";

test("collect, review, edit, render, and download cards", async ({ page }) => {
  const browserMessages: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      browserMessages.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => browserMessages.push(error.message));

  await page.goto("/timeline");
  await page.getByRole("button", { name: "立即采集" }).click();
  await expect(page.getByText(/新增 3 条/)).toBeVisible();

  await page.getByRole("link", { name: "待处理", exact: true }).click();
  await expect(page.getByRole("heading", { name: "审核" })).toBeVisible();
  await expect(page.locator(".review-row")).toHaveCount(3);
  await page.getByRole("button", { name: "应用 Agent 建议" }).click();
  await page.getByRole("button", { name: "确认决定" }).click();
  await expect(page.getByRole("link", { name: "前往卡片" })).toBeVisible();

  await page.getByRole("link", { name: "前往卡片" }).click();
  await expect(page.getByRole("heading", { name: "卡片" })).toBeVisible();
  await page.getByRole("button", { name: "生成卡片" }).click();
  await expect(
    page.getByRole("heading", { name: "确认生成卡片草稿？" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "生成草稿" }).click();
  await expect(page.locator(".browse-card").first()).toBeVisible();
  expect(await page.locator(".browse-card").count()).toBeGreaterThan(0);
  await expect(page.locator(".cover-template").first()).toBeVisible();
  await page.locator(".browse-card").first().click();
  await expect(page.getByRole("complementary", { name: "卡片详情" })).toBeVisible();
  await page
    .getByRole("button", { name: /^编辑 / })
    .click();
  const editedTitle = `已编辑：${await page.getByLabel("标题").inputValue()}`;
  await page.getByLabel("标题").fill(editedTitle);
  const summary = await page.getByLabel("摘要（100～1000 字）").inputValue();
  await page
    .getByLabel("摘要（100～1000 字）")
    .fill(`${summary} 这是在渲染前完成的人工校订，用于验证修订版本、幂等渲染和下载闭环。`.padEnd(120, "。"));
  await page.getByRole("button", { name: "保存编辑" }).click();
  await expect(page.getByRole("heading", { name: editedTitle })).toBeVisible();
  await page.getByRole("button", { name: "确认渲染" }).click();
  await expect(page.getByRole("link", { name: "下载 PNG" })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载 PNG" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.png$/);
  await expect(page.getByRole("link", { name: "查看原始信息" })).toBeVisible();

  await page.screenshot({
    path: path.join(
      process.env.TEMP ?? ".",
      "ai-signal-cards-1440.png",
    ),
    fullPage: true,
  });

  await page.setViewportSize({ width: 1024, height: 768 });
  await expect(page.locator(".cards-main")).toBeVisible();
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll");
  await page.screenshot({
    path: path.join(
      process.env.TEMP ?? ".",
      "ai-signal-cards-1024.png",
    ),
  });

  await page.setViewportSize({ width: 1200, height: 1000 });
  await expect(page.locator(".side-nav")).toHaveCSS("width", "68px");
  await expect(page.locator(".card-detail")).toBeVisible();
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll");

  expect(browserMessages).toEqual([]);
});
