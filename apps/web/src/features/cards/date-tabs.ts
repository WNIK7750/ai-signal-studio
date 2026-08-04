export interface DateTab {
  iso: string;
  day: number;
  weekday: string;
}

export function monthValue(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

export function buildMonthDays(value: string): DateTab[] {
  const [year, month] = value.split("-").map(Number);
  if (!year || !month || month < 1 || month > 12) return [];
  const count = new Date(year, month, 0).getDate();
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(year, month - 1, index + 1);
    return {
      iso: `${value}-${String(index + 1).padStart(2, "0")}`,
      day: index + 1,
      weekday: new Intl.DateTimeFormat("zh-CN", {
        weekday: "short",
      }).format(date),
    };
  });
}
