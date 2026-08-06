function pad(value: number) {
  return String(value).padStart(2, "0");
}

export function localDateKey(value: string | Date) {
  const date = value instanceof Date ? value : new Date(value);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate(),
  )}`;
}

export function timelineDayLabel(key: string, now = new Date()) {
  const todayKey = localDateKey(now);
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (key === todayKey) return "今天";
  if (key === localDateKey(yesterday)) return "昨天";
  const [, month, day] = key.split("-");
  return `${Number(month)} 月 ${Number(day)} 日`;
}

export function shouldCollapseTimelineDay(key: string, now = new Date()) {
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  return key !== localDateKey(now) && key !== localDateKey(yesterday);
}
