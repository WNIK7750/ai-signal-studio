export type Priority = "important" | "watch" | "normal";

export const priorityMeta: Record<
  Priority,
  { label: string; shape: "circle" | "diamond" }
> = {
  important: { label: "重要", shape: "circle" },
  watch: { label: "关注", shape: "diamond" },
  normal: { label: "普通", shape: "circle" },
};
