import { expect, test } from "@playwright/test";

declare global {
  interface Window {
    __appearanceWrites: Array<[string, string]>;
  }
}

test("restores appearance without overwriting it and saves user changes", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem("ai-signal-theme", "paper");
    localStorage.setItem("ai-signal-radius", "18");
    localStorage.setItem("ai-signal-density", "16");
    localStorage.setItem("ai-signal-font-size", "17");

    window.__appearanceWrites = [];
    const originalSetItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function setItem(key, value) {
      if (key.startsWith("ai-signal-")) {
        window.__appearanceWrites.push([key, String(value)]);
      }
      return originalSetItem.call(this, key, value);
    };
  });

  await page.goto("/settings/appearance");

  await expect(page.locator(".theme-card.selected")).toContainText("Paper");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "paper");
  await expect
    .poll(() =>
      page.evaluate(
        () => window.__appearanceWrites,
      ),
    )
    .toEqual([]);

  await page.getByRole("button", { name: /Forest/ }).click();

  await expect(page.locator("html")).toHaveAttribute("data-theme", "forest");
  await expect
    .poll(() =>
      page.evaluate(() => ({
        theme: localStorage.getItem("ai-signal-theme"),
        radius: localStorage.getItem("ai-signal-radius"),
        writes: window.__appearanceWrites,
      })),
    )
    .toEqual({
      theme: "forest",
      radius: "18",
      writes: [["ai-signal-theme", "forest"]],
    });

  await page.getByRole("link", { name: "AI 信息", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "forest");
});

test("normalizes invalid stored appearance values once", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("ai-signal-theme", "unknown");
    localStorage.setItem("ai-signal-radius", "");
    localStorage.setItem("ai-signal-density", "99");
    localStorage.setItem("ai-signal-font-size", "bad");

    window.__appearanceWrites = [];
    const originalSetItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function setItem(key, value) {
      if (key.startsWith("ai-signal-")) {
        window.__appearanceWrites.push([key, String(value)]);
      }
      return originalSetItem.call(this, key, value);
    };
  });

  await page.goto("/timeline");

  await expect(page.locator("html")).toHaveAttribute(
    "data-theme",
    "signal-light",
  );
  await expect
    .poll(() =>
      page.evaluate(() => ({
        radius: document.documentElement.style.getPropertyValue("--radius"),
        density: document.documentElement.style.getPropertyValue("--density"),
        fontSize:
          document.documentElement.style.getPropertyValue("--base-font-size"),
        writes: window.__appearanceWrites,
      })),
    )
    .toEqual({
      radius: "10px",
      density: "20px",
      fontSize: "15px",
      writes: [
        ["ai-signal-theme", "signal-light"],
        ["ai-signal-radius", "10"],
        ["ai-signal-density", "20"],
        ["ai-signal-font-size", "15"],
      ],
    });
});
