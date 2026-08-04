import type { Priority } from "@/lib/priority";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export type SourceKind = "demo" | "rss" | "github_releases";

export interface TimelineItem {
  id: string;
  title: string;
  summary: string;
  canonical_url: string;
  source_id: string;
  source_name: string;
  source_kind: SourceKind;
  published_at: string;
  topics: string[];
  priority: Priority;
}
export interface TimelinePage {
  total: number;
  items: TimelineItem[];
}
export interface Source {
  id: string;
  name: string;
  kind: SourceKind;
  config: Record<string, unknown>;
  enabled: boolean;
  updated_at: string;
}
export interface CollectionRun {
  id: string;
  status: string;
  items_collected: number;
  items_added: number;
  created_at: string;
  completed_at: string | null;
}
export interface CommonPlan {
  id: string;
  name: string;
  prompt: string;
  time_range_hours: number;
  topics: string[];
  source_ids: string[];
}
export interface ScheduledTask {
  id: string;
  name: string;
  plan_id: string;
  frequency: "daily";
  time_of_day: string;
  enabled: boolean;
  next_run_at: string | null;
}
export interface AgentResponse {
  message: string;
  capability_calls: { capability_id: string; status: string }[];
  result: Record<string, unknown>;
  schedule_draft?: {
    frequency: "daily";
    time_of_day: string;
    plan_name: string;
  } | null;
  requested_model_id: string | null;
  effective_model_id: string | null;
  model_switched: boolean;
  conversation_id: string | null;
  user_message_id: string | null;
  assistant_message_id: string | null;
}
export interface AgentMessage {
  id: string;
  conversation_id: string;
  role: "assistant" | "user";
  content: string;
  capability_calls: { capability_id: string; status: string }[];
  error_code: string | null;
  effective_model_id: string | null;
  image_count: number;
  created_at: string;
}
export interface AgentConversation {
  id: string;
  title: string;
  status: "active" | "archived";
  messages: AgentMessage[];
  created_at: string;
  updated_at: string;
}
export interface ModelConfig {
  id: string;
  name: string;
  provider: "heuristic" | "openai_compatible";
  provider_id: string;
  provider_name: string;
  model_id: string;
  base_url: string;
  has_api_key: boolean;
  supports_vision: boolean;
  output_token_limit: number | null;
  enabled: boolean;
  is_default: boolean;
  updated_at: string;
}
export interface ProviderConfig {
  id: string;
  name: string;
  base_url: string;
  protocol: "heuristic" | "openai_compatible";
  has_api_key: boolean;
}
export interface ModelWriteInput {
  name: string;
  model_id: string;
  provider_id?: string | null;
  provider_name?: string;
  base_url: string;
  api_key?: string;
  supports_vision: boolean;
  output_token_limit?: number | null;
  is_default: boolean;
}
export interface ModelConnectionResult {
  status: "ok";
  message: string;
}
export interface AgentInput {
  message: string;
  conversation_id?: string;
  client_message_id?: string;
  model_id?: string;
  image_urls?: string[];
}
export type ReviewDecision = "keep" | "reject" | "defer";
export interface ReviewItem extends TimelineItem {
  decision: ReviewDecision | null;
  edited_title: string | null;
  edited_summary: string | null;
  note: string;
}
export interface ReviewBatch {
  id: string;
  status: "pending" | "completed";
  items: ReviewItem[];
  created_at: string;
  completed_at: string | null;
}
export interface CardItem {
  id: string;
  title: string;
  summary: string;
  key_points: string[];
  cover_variant: number;
  cover_url: string | null;
  source_name: string;
  source_kind: SourceKind;
  canonical_url: string;
  published_at: string;
  priority: Priority;
  topics: string[];
}
export interface CardPage {
  total: number;
  items: CardItem[];
}
export interface CardGenerateResult {
  created: number;
  existing: number;
  card_ids: string[];
}
export interface CapabilityInvocation {
  id: string;
  capability_id: string;
  capability_version: string;
  request_id: string;
  actor_type: string;
  actor_id: string;
  status: string;
  error_code: string | null;
  started_at: string;
  completed_at: string | null;
}

export function formatModelLabel(model: ModelConfig): string {
  return model.supports_vision ? model.name : `${model.name}（不支持识图）`;
}

export function formatApiFailure(
  status: number,
  payload: unknown,
): string {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    Array.isArray(payload.detail)
  ) {
    return "API-001（请求参数不正确）";
  }
  return `SYS-001（请求失败，HTTP ${status}）`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(formatApiFailure(response.status, payload));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  timeline(params = new URLSearchParams()) {
    const suffix = params.size ? `?${params.toString()}` : "";
    return request<TimelinePage>(`/timeline${suffix}`);
  },
  collect() {
    return request<CollectionRun>("/collection-runs", {
      method: "POST",
      body: "{}",
    });
  },
  runs: () => request<CollectionRun[]>("/collection-runs"),
  invocations: () =>
    request<CapabilityInvocation[]>("/capability-invocations"),
  sources: () => request<Source[]>("/sources"),
  createSource(input: {
    name: string;
    kind: SourceKind;
    config: Record<string, string>;
  }) {
    return request<Source>("/sources", {
      method: "POST",
      body: JSON.stringify({ ...input, enabled: true }),
    });
  },
  toggleSource(source: Source) {
    return request<Source>(`/sources/${source.id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled: !source.enabled }),
    });
  },
  agent(input: AgentInput) {
    return request<AgentResponse>("/agent-runs", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  currentConversation: () =>
    request<AgentConversation>("/agent-conversations/current"),
  models: () => request<ModelConfig[]>("/models"),
  providers: () => request<ProviderConfig[]>("/providers"),
  createModel(input: ModelWriteInput) {
    return request<ModelConfig>("/models", {
      method: "POST",
      body: JSON.stringify({
        ...input,
        enabled: true,
      }),
    });
  },
  updateModel(modelId: string, input: ModelWriteInput) {
    return request<ModelConfig>(`/models/${modelId}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },
  deleteModel(modelId: string) {
    return request<void>(`/models/${modelId}`, {
      method: "DELETE",
    });
  },
  testModel(modelId: string) {
    return request<ModelConnectionResult>(`/models/${modelId}/test`, {
      method: "POST",
    });
  },
  activateModel(modelId: string) {
    return request<ModelConfig>(`/models/${modelId}/activate`, {
      method: "POST",
    });
  },
  plans: () => request<CommonPlan[]>("/plans"),
  updatePlan(planId: string, input: Partial<CommonPlan>) {
    return request<CommonPlan>(`/plans/${planId}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },
  tasks: () => request<ScheduledTask[]>("/scheduled-tasks"),
  createTask(input: {
    name: string;
    plan_id: string;
    time_of_day: string;
  }) {
    return request<ScheduledTask>("/scheduled-tasks", {
      method: "POST",
      body: JSON.stringify({ ...input, frequency: "daily", enabled: true }),
    });
  },
  updateTask(taskId: string, input: Partial<ScheduledTask>) {
    return request<ScheduledTask>(`/scheduled-tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },
  currentReview: () => request<ReviewBatch>("/review-batches/current"),
  submitReview(
    batchId: string,
    decisions: {
      item_id: string;
      decision: ReviewDecision;
      edited_title?: string | null;
      edited_summary?: string | null;
      note?: string;
    }[],
  ) {
    return request<ReviewBatch>(`/review-batches/${batchId}/decisions`, {
      method: "POST",
      body: JSON.stringify({ decisions, confirm: true }),
    });
  },
  cards(params = new URLSearchParams()) {
    const suffix = params.size ? `?${params.toString()}` : "";
    return request<CardPage>(`/cards${suffix}`);
  },
  card: (cardId: string) => request<CardItem>(`/cards/${cardId}`),
  generateCards(maxChars = 400) {
    return request<CardGenerateResult>("/cards/generate", {
      method: "POST",
      body: JSON.stringify({ max_chars: maxChars }),
    });
  },
};
