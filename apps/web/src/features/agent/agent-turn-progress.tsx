import {
  IconCheck,
  IconClock,
  IconLoader2,
  IconPlayerStop,
} from "@tabler/icons-react";
import {
  AgentPlan,
  AgentTurnEvent,
  AgentTurnStatus,
} from "@/lib/api";

type Props = {
  status: AgentTurnStatus;
  plan?: AgentPlan;
  events?: AgentTurnEvent[];
  elapsedMs: number;
  onStop?: () => void;
};

const TERMINAL = new Set(["complete", "partial", "failed", "cancelled"]);

export function AgentTurnProgress({
  status,
  plan,
  events = [],
  elapsedMs,
  onStop,
}: Props) {
  const completed = new Set(
    events
      .filter((event) => event.type === "tool.completed")
      .map((event) => event.step_id),
  );
  const activeStep = [...events]
    .reverse()
    .find((event) => event.type === "step.started")?.step_id;
  const label = turnStatusLabel(status);

  return (
    <section className={`agent-turn-progress is-${status}`} aria-label="Agent 运行进度">
      <header>
        {TERMINAL.has(status) ? (
          <IconCheck size={16} aria-hidden="true" />
        ) : (
          <IconLoader2 className="is-spinning" size={16} aria-hidden="true" />
        )}
        <strong>{label}</strong>
        <span>
          <IconClock size={14} aria-hidden="true" />
          {TERMINAL.has(status) ? "总耗时" : "服务端耗时"}{" "}
          {(elapsedMs / 1000).toFixed(1)} 秒
        </span>
        {onStop && !TERMINAL.has(status) && (
          <button className="secondary-button" type="button" onClick={onStop}>
            <IconPlayerStop size={14} aria-hidden="true" />
            停止
          </button>
        )}
      </header>
      {plan?.steps?.length ? (
        <details open={!TERMINAL.has(status)}>
          <summary>执行计划 · {plan.steps.length} 步</summary>
          <ol>
            {plan.steps.map((step) => {
              const stepStatus = completed.has(step.step_id)
                ? "已完成"
                : activeStep === step.step_id
                  ? "进行中"
                  : "等待";
              return (
                <li key={step.step_id}>
                  <span>{step.title}</span>
                  <small>{stepStatus}</small>
                </li>
              );
            })}
          </ol>
        </details>
      ) : (
        <p>已接收，正在规划…</p>
      )}
    </section>
  );
}

function turnStatusLabel(status: AgentTurnStatus): string {
  const labels: Record<AgentTurnStatus, string> = {
    queued: "已接收",
    running: "正在执行",
    waiting_input: "等待补充",
    waiting_approval: "等待确认",
    complete: "已完成",
    partial: "部分完成",
    failed: "未完成",
    cancelled: "已停止",
  };
  return labels[status];
}
