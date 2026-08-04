import { describe, expect, it } from "vitest";
import {
  findProviderPreset,
  PROVIDER_PRESETS,
} from "./provider-presets";

describe("provider presets", () => {
  it("fills official OpenAI-compatible base URLs", () => {
    expect(findProviderPreset("preset:openai")?.baseUrl).toBe(
      "https://api.openai.com/v1",
    );
    expect(findProviderPreset("preset:deepseek")?.baseUrl).toBe(
      "https://api.deepseek.com",
    );
    expect(findProviderPreset("preset:qwen")?.baseUrl).toBe(
      "https://dashscope.aliyuncs.com/compatible-mode/v1",
    );
    expect(PROVIDER_PRESETS).toHaveLength(3);
  });
});
