import { describe, expect, it } from "vitest";
import { clampToken, themePresets } from "./themes";

describe("appearance tokens", () => {
  it("keeps slider values inside their supported range", () => {
    expect(clampToken(2, 4, 20)).toBe(4);
    expect(clampToken(12, 4, 20)).toBe(12);
    expect(clampToken(24, 4, 20)).toBe(20);
  });

  it("ships four one-click theme presets", () => {
    expect(themePresets.map((theme) => theme.id)).toEqual([
      "signal-light",
      "paper",
      "midnight",
      "forest",
    ]);
  });
});
