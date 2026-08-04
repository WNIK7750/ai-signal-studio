import { describe, expect, it } from "vitest";
import { buildMonthDays } from "./date-tabs";

describe("card date tabs", () => {
  it("builds every day for the selected month", () => {
    expect(buildMonthDays("2026-08")).toHaveLength(31);
    expect(buildMonthDays("2026-02")).toHaveLength(28);
  });
});
