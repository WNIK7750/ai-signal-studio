import { expect, test } from "@playwright/test";

test("agent conversations can be renamed, pinned, archived, deleted, and restored", async ({
  page,
}) => {
  const suffix = Date.now();
  const conversationA = `E2E 会话 A ${suffix}`;
  const conversationB = `E2E 会话 B ${suffix}`;
  const draftA = `仅保存在 ${conversationA} 的草稿`;
  const draftB = `仅保存在 ${conversationB} 的草稿`;

  await page.goto("/agent");
  const workbar = page.getByRole("complementary", { name: "对话列表" });
  await expect(workbar).toBeVisible();

  await workbar.getByRole("button", { name: "新建对话" }).click();
  let activeRow = workbar.locator(".agent-conversation-item.is-active");
  await activeRow.getByRole("button", { name: /^重命名/ }).click();
  await activeRow.getByRole("textbox", { name: "会话名称" }).fill(conversationA);
  await activeRow.getByRole("button", { name: "保存名称" }).click();
  await expect(workbar.getByText(conversationA, { exact: true })).toBeVisible();

  const composer = page.getByPlaceholder("向 Workspace Agent 发送消息…");
  await composer.fill(draftA);
  await workbar.getByRole("button", { name: "新建对话" }).click();
  activeRow = workbar.locator(".agent-conversation-item.is-active");
  await activeRow.getByRole("button", { name: /^重命名/ }).click();
  await activeRow.getByRole("textbox", { name: "会话名称" }).fill(conversationB);
  await activeRow.getByRole("button", { name: "保存名称" }).click();
  await composer.fill(draftB);

  await workbar.getByText(conversationA, { exact: true }).click();
  await expect(composer).toHaveValue(draftA);
  activeRow = workbar.locator(".agent-conversation-item.is-active");
  await activeRow.getByRole("button", { name: /^置顶/ }).click();
  await expect(activeRow.getByRole("button", { name: /^取消置顶/ })).toBeVisible();

  await workbar.getByText(conversationB, { exact: true }).click();
  await expect(composer).toHaveValue(draftB);
  activeRow = workbar.locator(".agent-conversation-item.is-active");
  await activeRow.getByRole("button", { name: /^归档/ }).click();
  await workbar.getByRole("button", { name: "已归档" }).click();
  await expect(workbar.getByText(conversationB, { exact: true })).toBeVisible();
  await workbar
    .getByRole("button", { name: `恢复 ${conversationB}` })
    .click();

  await workbar.getByRole("button", { name: "最近" }).click();
  await workbar.getByText(conversationA, { exact: true }).click();
  activeRow = workbar.locator(".agent-conversation-item.is-active");
  await activeRow.getByRole("button", { name: /^删除/ }).click();
  await expect(page.getByText(`已删除“${conversationA}”`)).toBeVisible();
  await page.getByRole("button", { name: "撤销删除" }).click();
  await expect(workbar.getByText(conversationA, { exact: true })).toBeVisible();

  await page.reload();
  await expect(workbar.getByText(conversationA, { exact: true })).toBeVisible();
  await workbar.getByText(conversationA, { exact: true }).click();
  await expect(composer).toHaveValue(draftA);
});

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
  await page.getByRole("button", { name: "打开会话列表" }).click();
  await expect(
    page.getByRole("complementary", { name: "对话列表" }),
  ).toHaveClass(/is-open/);
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll");

  expect(browserMessages).toEqual([]);
});

test("agent turn streams progress, recommendations, partial state, and deep links", async ({
  page,
}) => {
  await page.goto("/agent");
  const prompt =
    "收集最近 24 小时的 AI 信息，并从中推荐 5 条最值得看的 Agent 相关内容。";

  await page.getByPlaceholder("向 Workspace Agent 发送消息…").fill(prompt);
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByText(prompt, { exact: true })).toBeVisible();
  await expect(
    page.getByText("已接收，正在规划…", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/总耗时 \d/)).toBeVisible();
  await expect(
    page.getByLabel("Agent 运行进度").locator("header strong"),
  ).toHaveText(/已完成|部分完成/);
  await expect(page.locator(".agent-signal-preview")).toHaveCount(3);

  const firstSignal = page.locator(".agent-signal-preview").first();
  const href = await firstSignal.getByRole("link").getAttribute("href");
  expect(href).toContain("/timeline?focus=info_");
  await firstSignal.getByRole("link").click();
  await expect(page).toHaveURL(/\/timeline\?focus=info_/);
});
