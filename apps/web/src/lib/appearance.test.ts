import { describe, expect, it } from "vitest";
import {
  applyAppearance,
  DEFAULT_APPEARANCE,
  readAppearance,
  writeAppearancePatch,
} from "./appearance";

function createStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  const writes: Array<[string, string]> = [];

  return {
    storage: {
      getItem(key: string) {
        return values.get(key) ?? null;
      },
      setItem(key: string, value: string) {
        values.set(key, value);
        writes.push([key, value]);
      },
    },
    writes,
  };
}

describe("appearance persistence", () => {
  it("restores valid non-default settings without writing during initialization", () => {
    const { storage, writes } = createStorage({
      "ai-signal-theme": "paper",
      "ai-signal-radius": "18",
      "ai-signal-density": "16",
      "ai-signal-font-size": "17",
    });

    const result = readAppearance(storage);

    expect(result.value).toEqual({
      theme: "paper",
      radius: 18,
      density: 16,
      fontSize: 17,
    });
    expect(result.correctedKeys).toEqual([]);
    expect(writes).toEqual([]);
  });

  it("normalizes malformed or out-of-range stored values once", () => {
    const { storage } = createStorage({
      "ai-signal-theme": "unknown",
      "ai-signal-radius": "",
      "ai-signal-density": "99",
      "ai-signal-font-size": "not-a-number",
    });

    const result = readAppearance(storage);

    expect(result.value).toEqual({
      ...DEFAULT_APPEARANCE,
      density: 20,
    });
    expect(result.correctedKeys).toEqual([
      "theme",
      "radius",
      "density",
      "fontSize",
    ]);
  });

  it("persists only fields changed by a user action", () => {
    const { storage, writes } = createStorage();

    writeAppearancePatch(storage, { theme: "forest" });

    expect(writes).toEqual([["ai-signal-theme", "forest"]]);
  });

  it("applies the complete setting set to the root target", () => {
    const properties = new Map<string, string>();
    const target = {
      dataset: {} as { theme?: string },
      style: {
        setProperty(name: string, value: string) {
          properties.set(name, value);
        },
      },
    };

    applyAppearance(target, {
      theme: "midnight",
      radius: 14,
      density: 11,
      fontSize: 16,
    });

    expect(target.dataset.theme).toBe("midnight");
    expect(Object.fromEntries(properties)).toEqual({
      "--radius": "14px",
      "--density": "11px",
      "--base-font-size": "16px",
    });
  });
});
