import { expect, test } from "@playwright/test";
import path from "node:path";

test("create, preview, run, and resize a collection task", async ({ page }) => {
  const browserMessages: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      browserMessages.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => browserMessages.push(error.message));

  await page.goto("/tasks");
  await expect(
    page.getByRole("heading", { name: "任务", exact: true }),
  ).toBeVisible();
  await page.getByLabel("任务名称").fill("每日 Agent 追踪");
  await page.getByLabel("任务目标").fill("收集最近一天的 Agent 产品更新");

  await page.getByRole("button", { name: "试运行" }).first().click();
  await expect(page.getByText(/试运行完成/)).toBeVisible();
  await expect(page.getByText("试运行结果")).toBeVisible();

  await page.getByRole("button", { name: "保存并运行" }).first().click();
  await expect(page.getByText(/运行完成/)).toBeVisible();
  await expect(page.getByText("每日 Agent 追踪", { exact: true }).first()).toBeVisible();

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.join(process.env.TEMP ?? ".", "ai-signal-tasks-1536.png"),
  });

  await page.setViewportSize({ width: 1024, height: 768 });
  await expect(page.locator(".side-nav")).toHaveCSS("width", "68px");
  await expect(page.locator(".task-editor")).toBeVisible();
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll");

  expect(browserMessages).toEqual([]);
});
