import { Priority, priorityMeta } from "@/lib/priority";

export function StatusMark({
  priority,
  compact = false,
}: {
  priority: Priority;
  compact?: boolean;
}) {
  const meta = priorityMeta[priority];
  return (
    <span
      className={`status-mark status-${priority} ${
        compact ? "status-compact" : ""
      }`}
      aria-label={`优先级：${meta.label}`}
      title={meta.label}
    >
      <span
        className={`status-shape status-shape-${meta.shape}`}
        aria-hidden="true"
      />
      {!compact && <span>{meta.label}</span>}
    </span>
  );
}
