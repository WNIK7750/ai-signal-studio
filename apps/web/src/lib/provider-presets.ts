export interface ProviderPreset {
  id: string;
  name: string;
  baseUrl: string;
  note: string;
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: "preset:openai",
    name: "OpenAI / GPT",
    baseUrl: "https://api.openai.com/v1",
    note: "OpenAI 官方 v1 地址",
  },
  {
    id: "preset:deepseek",
    name: "DeepSeek",
    baseUrl: "https://api.deepseek.com",
    note: "DeepSeek 官方 OpenAI 兼容地址",
  },
  {
    id: "preset:qwen",
    name: "阿里云百炼 / 千问",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    note: "默认华北公共地址；其他地域可直接修改",
  },
];

export function findProviderPreset(
  id: string,
): ProviderPreset | undefined {
  return PROVIDER_PRESETS.find((preset) => preset.id === id);
}
