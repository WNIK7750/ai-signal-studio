import { expect, test } from "@playwright/test";

test("agent collection completes and the conversation survives reload", async ({
  page,
}) => {
  const browserMessages: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      browserMessages.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => browserMessages.push(error.message));

  await page.goto("/agent");
  await expect(page.getByRole("heading", { name: "对话" })).toBeVisible();

  const prompt = "请立即采集最新 AI 信息";
  await page.getByPlaceholder("向 Workspace Agent 发送消息…").fill(prompt);
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByText(prompt, { exact: true })).toBeVisible();
  await expect(page.getByText(/采集完成/)).toBeVisible();
  await expect(page.getByText("采集 AI 信息", { exact: true })).toBeVisible();
  await expect(page.getByText("已完成", { exact: true })).toBeVisible();
  const messageCount = await page.locator(".message").count();
  expect(messageCount).toBeGreaterThanOrEqual(2);

  await page.reload();

  await expect(page.getByText(prompt, { exact: true })).toHaveCount(1);
  await expect(page.getByText(/采集完成/)).toBeVisible();
  await expect(page.getByText("采集 AI 信息", { exact: true })).toBeVisible();
  await expect(page.locator(".message")).toHaveCount(messageCount);

  await page.setViewportSize({ width: 1024, height: 768 });
  await expect(page.locator(".side-nav")).toHaveCSS("width", "68px");
  await expect(page.locator(".conversation")).toBeVisible();
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll");

  expect(browserMessages).toEqual([]);
});
