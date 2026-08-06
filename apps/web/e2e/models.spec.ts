import { expect, test } from "@playwright/test";
import path from "node:path";

test("create, manually switch, and track connection state for an image model", async ({
  page,
}) => {
  const browserMessages: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      browserMessages.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => browserMessages.push(error.message));

  await page.goto("/settings/models");
  await expect(page).toHaveTitle(/AI Signal Studio/);
  await expect(
    page.getByRole("heading", { name: "模型", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("不支持识图", { exact: true })).toBeVisible();

  const modelName = `视觉模型 ${Date.now()}`;
  await page.getByRole("button", { name: "添加模型" }).click();
  await page
    .getByLabel("提供商", { exact: true })
    .selectOption("preset:deepseek");
  await expect(page.getByLabel("接口地址")).toHaveValue(
    "https://api.deepseek.com",
  );
  await expect(page.getByRole("textbox", { name: "API Key" })).toHaveAttribute(
    "required",
    "",
  );
  await page
    .getByRole("textbox", { name: "API Key" })
    .fill("sk-e2e-not-real");
  await page.getByLabel("显示名称").fill(modelName);
  await page.getByLabel("模型 ID").fill("vision-model-e2e");
  await page.getByLabel("图片输入").check();
  await page
    .getByLabel("最大输出额度快捷选择")
    .getByRole("button", { name: "16K" })
    .click();
  await page.getByLabel("设为默认模型").check();
  await page.screenshot({
    path: path.join(
      process.env.TEMP ?? ".",
      "ai-signal-model-dialog-1440.png",
    ),
  });
  await page.getByRole("button", { name: "保存", exact: true }).click();

  const modelRow = page.locator(".model-row").filter({ hasText: modelName });
  await expect(modelRow).toContainText("当前默认");
  await expect(modelRow).toContainText("密钥已配置");
  await expect(modelRow).toContainText("待检测");
  await expect(
    page.getByRole("button", { name: `测试模型 ${modelName}` }),
  ).toBeVisible();

  const editedModelName = `${modelName} Pro`;
  await page.getByRole("button", { name: `编辑模型 ${modelName}` }).click();
  await expect(
    page.getByRole("heading", { name: "编辑模型" }),
  ).toBeVisible();
  await page.getByLabel("显示名称").fill(editedModelName);
  await page
    .getByLabel("最大输出额度快捷选择")
    .getByRole("button", { name: "32K" })
    .click();
  await page.screenshot({
    path: path.join(
      process.env.TEMP ?? ".",
      "ai-signal-model-edit-1440.png",
    ),
  });
  await page.getByRole("button", { name: "保存", exact: true }).click();
  const editedModelRow = page
    .locator(".model-row")
    .filter({ hasText: editedModelName });
  await expect(editedModelRow).toContainText("最大输出 32K");
  await expect(editedModelRow).toContainText("待检测");
  await page.screenshot({
    path: path.join(
      process.env.TEMP ?? ".",
      "ai-signal-model-settings-1440.png",
    ),
  });

  await page.getByRole("link", { name: "Agent", exact: true }).click();
  const modelSelect = page.getByLabel("选择对话模型");
  await expect(page.getByRole("link", { name: "设定模型" })).toBeVisible();
  await expect(page.getByRole("button", { name: "语音转文字" })).toBeVisible();
  await expect(modelSelect.locator("option:checked")).toContainText(
    editedModelName,
  );
  await modelSelect.selectOption({
    label: "本地规则模型（不支持识图）",
  });

  const upload = page.getByLabel("上传图片");
  await upload.setInputFiles({
    name: "chart.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAA" +
        "C0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
      "base64",
    ),
  });
  await expect(page.getByText("chart.png")).toBeVisible();
  await page
    .getByPlaceholder("向 Workspace Agent 发送消息…")
    .fill("请分析这张图");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(
    page.getByText("MODEL-002（当前模型不支持图片）"),
  ).toBeVisible();
  await expect(modelSelect.locator("option:checked")).toContainText(
    "本地规则模型（不支持识图）",
  );
  await page.screenshot({
    path: path.join(
      process.env.TEMP ?? ".",
      "ai-signal-agent-image-upload-1440.png",
    ),
  });

  await page.setViewportSize({ width: 1024, height: 768 });
  await expect(page.locator(".conversation")).toBeVisible();
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll");
  await page.screenshot({
    path: path.join(
      process.env.TEMP ?? ".",
      "ai-signal-agent-image-upload-1024.png",
    ),
  });

  await page.evaluate(() => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(window, "MediaRecorder", {
      configurable: true,
      value: undefined,
    });
  });
  await page.getByRole("button", { name: "语音转文字" }).click();
  await expect(
    page.getByText("VOICE-001（当前浏览器不支持实时语音转文字）"),
  ).toBeVisible();

  await modelSelect.selectOption({ label: editedModelName });
  await expect(modelSelect.locator("option:checked")).toContainText(
    editedModelName,
  );

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("link", { name: "设定模型" }).click();
  await page
    .getByRole("button", { name: `删除模型 ${editedModelName}` })
    .click();
  await expect(
    page.getByRole("heading", { name: `删除“${editedModelName}”？` }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(
      process.env.TEMP ?? ".",
      "ai-signal-model-delete-confirm-1440.png",
    ),
  });
  await page.getByRole("button", { name: "确认删除" }).click();
  await expect(
    page.locator(".model-row").filter({ hasText: editedModelName }),
  ).toHaveCount(0);
  const localModelRow = page
    .locator(".model-row")
    .filter({ hasText: "本地规则模型" });
  await expect(localModelRow).toContainText("当前默认");
  await expect(
    page.getByRole("button", { name: "编辑模型 本地规则模型" }),
  ).toHaveCount(0);
  await page.screenshot({
    path: path.join(
      process.env.TEMP ?? ".",
      "ai-signal-models-local-only-1440.png",
    ),
  });

  expect(browserMessages).toEqual([]);
});
