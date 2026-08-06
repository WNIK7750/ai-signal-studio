import { expect, test } from "@playwright/test";

test("previews an Agent Pack and uploads a local Artifact", async ({ page }) => {
  await page.route("**/api/agent-packs/import-preview", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        pack_id: "ai-editor",
        version: "1.0.0",
        content_digest: "a".repeat(64),
        added: ["agent.yaml", "memory/preferences.md"],
        removed: [],
        changed: [],
      }),
    });
  });
  await page.route("**/api/agent-packs/import", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        id: "packversion_e2e",
        pack_id: "ai-editor",
        version: "1.0.0",
        content_digest: "a".repeat(64),
        status: "active",
        previous_version_id: null,
        validation_result: { status: "valid" },
        created_at: new Date().toISOString(),
        activated_at: new Date().toISOString(),
      }),
    });
  });

  await page.goto("/settings/assets");
  await expect(
    page.getByRole("heading", { name: "Agent 资产" }),
  ).toBeVisible();
  await page.locator('input[accept*=".zip"]').setInputFiles({
    name: "ai-editor.zip",
    mimeType: "application/zip",
    buffer: Buffer.from("fake archive handled by route"),
  });
  await expect(page.getByText("新增 2 · 修改 0 · 删除 0")).toBeVisible();
  await page.getByRole("button", { name: "确认激活" }).click();

  await page
    .locator('input[accept*=".md"]')
    .setInputFiles({
      name: "evidence.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Evidence\nOfficial source only."),
    });
  await expect(page.getByText("evidence.md")).toBeVisible();
  await expect(page.locator(".artifact-list code").first()).toContainText(
    "artifact_",
  );
});
