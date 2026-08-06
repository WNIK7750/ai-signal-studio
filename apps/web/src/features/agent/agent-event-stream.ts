import { AgentTurnEvent, api } from "@/lib/api";

const EVENT_TYPES = [
  "turn.created",
  "plan.ready",
  "step.started",
  "tool.started",
  "tool.completed",
  "result.block",
  "turn.completed",
  "turn.partial",
  "turn.failed",
  "turn.cancelled",
] as const;

const TERMINAL_EVENTS = new Set([
  "turn.completed",
  "turn.partial",
  "turn.failed",
  "turn.cancelled",
]);

export function subscribeToAgentTurn(
  turnId: string,
  callbacks: {
    onEvent(event: AgentTurnEvent): void;
    onTerminal(): void;
    onError(): void;
  },
): () => void {
  const stream = new EventSource(api.agentTurnEventsUrl(turnId));
  for (const type of EVENT_TYPES) {
    stream.addEventListener(type, (rawEvent) => {
      const message = rawEvent as MessageEvent<string>;
      const payload = JSON.parse(message.data) as Record<string, unknown>;
      callbacks.onEvent({
        id: Number(message.lastEventId),
        type,
        elapsed_ms: Number(payload.elapsed_ms ?? 0),
        step_id:
          typeof payload.step_id === "string" ? payload.step_id : null,
        data: payload,
      });
      if (TERMINAL_EVENTS.has(type)) {
        stream.close();
        callbacks.onTerminal();
      }
    });
  }
  stream.onerror = () => callbacks.onError();
  return () => stream.close();
}
