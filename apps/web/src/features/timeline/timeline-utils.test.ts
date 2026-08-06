import { describe, expect, it } from "vitest";
import {
  localDateKey,
  shouldCollapseTimelineDay,
} from "./timeline-utils";

describe("timeline day grouping", () => {
  it("uses a stable local ISO date key instead of a display label", () => {
    expect(localDateKey("2026-08-06T10:30:00+08:00")).toBe("2026-08-06");
  });

  it("keeps today and yesterday open while older days start collapsed", () => {
    const now = new Date("2026-08-06T12:00:00+08:00");
    expect(shouldCollapseTimelineDay("2026-08-06", now)).toBe(false);
    expect(shouldCollapseTimelineDay("2026-08-05", now)).toBe(false);
    expect(shouldCollapseTimelineDay("2026-08-04", now)).toBe(true);
  });
});
