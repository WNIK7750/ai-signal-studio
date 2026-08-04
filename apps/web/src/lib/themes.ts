export type ThemeId = "signal-light" | "paper" | "midnight" | "forest";

export const themePresets: {
  id: ThemeId;
  name: string;
  colors: [string, string, string];
}[] = [
  { id: "signal-light", name: "Signal Light", colors: ["#1769e0", "#ffffff", "#172033"] },
  { id: "paper", name: "Paper", colors: ["#8b5d2e", "#fbf8f2", "#29241e"] },
  { id: "midnight", name: "Midnight", colors: ["#7da7ff", "#111722", "#eef4ff"] },
  { id: "forest", name: "Forest", colors: ["#20705a", "#f4f8f4", "#17332a"] },
];

export function clampToken(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}
