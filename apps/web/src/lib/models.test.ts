import { describe, expect, it } from "vitest";
import {
  formatApiFailure,
  formatModelLabel,
  type ModelConfig,
} from "./api";

const model: ModelConfig = {
  id: "model_local",
  name: "本地规则模型",
  provider: "heuristic",
  model_id: "local-rules",
  base_url: "local://heuristic",
  supports_vision: false,
  enabled: true,
  is_default: true,
  updated_at: "2026-08-03T00:00:00Z",
};

describe("model presentation", () => {
  it("adds only the requested non-vision label", () => {
    expect(formatModelLabel(model)).toBe("本地规则模型（不支持识图）");
    expect(
      formatModelLabel({ ...model, supports_vision: true }),
    ).toBe("本地规则模型");
  });

  it("keeps numbered Chinese API errors readable", () => {
    expect(
      formatApiFailure(404, {
        detail: "MODEL-001（未找到指定模型）",
      }),
    ).toBe("MODEL-001（未找到指定模型）");
    expect(formatApiFailure(422, { detail: [] })).toBe(
      "API-001（请求参数不正确）",
    );
  });
});
