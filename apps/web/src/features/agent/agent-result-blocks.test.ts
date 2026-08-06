import { describe, expect, it } from "vitest";
import { uniqueStrings } from "./agent-result-blocks";

describe("agent result presentation", () => {
  it("groups repeated uncertainty messages into one ordered list", () => {
    expect(
      uniqueStrings([
        "证据时间窗不足。",
        "证据时间窗不足。",
        "缺少统一统计口径。",
      ]),
    ).toEqual(["证据时间窗不足。", "缺少统一统计口径。"]);
  });
});
