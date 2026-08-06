import type { Priority } from "@/lib/priority";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export function transcriptionWebSocketUrl(
  sessionId: string,
  token: string,
) {
  const origin = API_BASE.replace(/\/api\/?$/, "").replace(/^http/, "ws");
  return `${origin}/ws/transcription/${encodeURIComponent(
    sessionId,
  )}?token=${encodeURIComponent(token)}`;
}

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
  task_ids: string[];
  seen: boolean;
  starred: boolean;
  archived: boolean;
  note: string;
}
export interface TimelinePage {
  total: number;
  items: TimelineItem[];
  next_cursor: string | null;
  has_more: boolean;
}
export interface Source {
  id: string;
  name: string;
  kind: SourceKind;
  config: Record<string, unknown>;
  enabled: boolean;
  health_status: "unknown" | "healthy" | "warning" | "error";
  last_success_at: string | null;
  last_error_at: string | null;
  last_error_code: string | null;
  last_items_count: number;
  updated_at: string;
}
export interface SourceUpdateInput {
  name?: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
}
export interface SourceTestResult {
  source_id: string | null;
  status: "healthy" | "error";
  items_count: number;
  sample_titles: string[];
  error_code: string | null;
}
export interface TranscriptionSession {
  session_id: string;
  status: string;
  provider: string;
  language: string;
  format: "webm_opus" | "pcm_s16le";
  sample_rate: number;
  final_text: string;
  error_code: string | null;
  websocket_url: string | null;
  token: string | null;
}
export interface AgentPackVersion {
  id: string;
  pack_id: string;
  version: string;
  content_digest: string;
  status: string;
  previous_version_id: string | null;
  validation_result: Record<string, unknown>;
  created_at: string;
  activated_at: string | null;
}
export interface AgentPackPreview {
  pack_id: string;
  version: string;
  content_digest: string;
  added: string[];
  removed: string[];
  changed: string[];
}
export interface Artifact {
  artifact_id: string;
  media_type: string;
  filename: string;
  storage_uri: string;
  sha256: string;
  size_bytes: number;
  status: string;
  extracted_text: string;
  metadata: Record<string, unknown>;
  created_at: string;
}
export interface CollectionRun {
  id: string;
  status: string;
  execution_status: string;
  coverage_status: string;
  task_id: string | null;
  task_version_id: string | null;
  trigger_type: string;
  parent_run_id: string | null;
  funnel_counts: Record<string, number>;
  warning_codes: string[];
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
  task_draft?: CollectionTaskWrite | null;
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
  turn_id: string | null;
  role: "assistant" | "user";
  content: string;
  result: AgentTurnResult | Record<string, unknown>;
  capability_calls: { capability_id: string; status: string }[];
  schedule_draft: AgentResponse["schedule_draft"];
  task_draft: CollectionTaskWrite | null;
  error_code: string | null;
  effective_model_id: string | null;
  image_count: number;
  created_at: string;
}
export type AgentTurnStatus =
  | "queued"
  | "running"
  | "waiting_input"
  | "waiting_approval"
  | "complete"
  | "partial"
  | "failed"
  | "cancelled";
export interface AgentPlanStep {
  step_id: string;
  title: string;
  goal: string;
  capability_id: string;
  dependencies: string[];
}
export interface AgentPlan {
  objective: string;
  planning_mode: "direct" | "fast" | "dynamic";
  selected_domains: string[];
  steps: AgentPlanStep[];
}
export interface AgentResultBlock {
  block_id: string;
  type:
    | "plan_summary"
    | "signal_preview"
    | "collection_summary"
    | "information_list"
    | "recommendation_list"
    | "comparison_table"
    | "trend_summary"
    | "evidence_sources"
    | "artifact_list"
    | "partial_failure"
    | "navigation_action";
  title: string;
  data: Record<string, unknown>;
}
export interface AgentTurnResult {
  status: "complete" | "partial" | "failed" | "cancelled";
  message: string;
  plan: AgentPlan;
  result_blocks: AgentResultBlock[];
  business_run_ids: string[];
  errors: {
    code: string;
    message: string;
    source: string;
    retryable: boolean;
    partial: boolean;
  }[];
  retryable_errors: {
    code: string;
    message: string;
    source: string;
    retryable: boolean;
    partial: boolean;
  }[];
  total_duration_ms: number;
}
export interface AgentTurn {
  id: string;
  conversation_id: string;
  request_id: string;
  client_message_id: string;
  status: AgentTurnStatus;
  message: string;
  workflow_version: string;
  plan: AgentPlan | Record<string, never>;
  result: AgentTurnResult | Record<string, never>;
  error: Record<string, unknown> | null;
  total_duration_ms: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}
export interface AgentTurnEvent {
  id: number;
  type: string;
  elapsed_ms: number;
  step_id: string | null;
  data: Record<string, unknown>;
}
export type AgentConversationScope = "active" | "archived" | "deleted";

export interface AgentConversationSummary {
  id: string;
  title: string;
  title_source: "auto" | "manual";
  status: "active" | "archived";
  pinned_at: string | null;
  archived_at: string | null;
  deleted_at: string | null;
  active_turn_id: string | null;
  last_message_at: string | null;
  unread: boolean;
  created_at: string;
  updated_at: string;
}
export interface AgentConversation extends AgentConversationSummary {
  messages: AgentMessage[];
}
export interface AgentConversationUpdate {
  title?: string;
  pinned?: boolean;
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
  artifact_ids?: string[];
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
  revision: number;
  template_id: "offline-quote" | "offline-grid" | "source-cover";
  cover_source: "original" | "offline";
  render_status: "not_rendered" | "rendering" | "rendered" | "failed";
  rendered_artifact_id: string | null;
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
export interface PosterWorkflow {
  thread_id: string;
  status: "waiting_approval" | "completed" | "partial" | "drafts_saved";
  interrupt: {
    phase: "confirm_draft_generation" | "confirm_render";
    message: string;
    item_ids?: string[];
    card_ids?: string[];
  } | null;
  card_ids: string[];
  rendered_artifact_ids: string[];
  errors: { card_id: string; error_code: string; message: string }[];
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

export interface TaskConfig {
  sources: {
    mode: "selected" | "all_enabled";
    include_ids: string[];
    exclude_ids: string[];
    required_ids: string[];
    fallback_ids: string[];
    per_source_max_items: number;
  };
  matching: {
    topics: string[];
    include_any: string[];
    include_all: string[];
    exclude: string[];
    search_scope: "title" | "title_and_content";
    languages: string[];
  };
  time_window: {
    mode: "rolling" | "since_last_success";
    lookback_hours: number;
    overlap_hours: number;
    timezone: string;
  };
  quantity: {
    min_items: number;
    target_items: number;
    max_items: number;
  };
  importance: {
    accepted_levels: Priority[];
  };
  quality_requirements: {
    require_source_link: boolean;
    prefer_primary_source: boolean;
    allow_unknown_publish_time: boolean;
    require_extractable_content: boolean;
  };
  deduplication: {
    mode: "conservative" | "balanced" | "event";
    window_days: number;
    across_runs: boolean;
    preserve_related_sources: boolean;
  };
  schedule: {
    mode: "manual" | "interval" | "daily" | "weekdays" | "weekly";
    time_of_day: string;
    weekdays: number[];
    interval_hours: number | null;
  };
  delivery: {
    destination: "task_view" | "timeline" | "review";
    notify_when: "always" | "important_or_problem" | "problem_only" | "never";
    summary_max_chars: number;
  };
}

export interface CollectionTaskWrite {
  name: string;
  goal: string;
  status: "draft" | "enabled" | "paused" | "archived";
  pinned: boolean;
  config: TaskConfig;
}

export interface CollectionTask extends CollectionTaskWrite {
  id: string;
  latest_version_id: string | null;
  active_version_id: string | null;
  version_number: number | null;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskPreview {
  funnel_counts: Record<string, number>;
  samples: {
    title: string;
    source_name: string;
    published_at: string;
    priority: Priority;
    reason: string;
  }[];
  warning_codes: string[];
}

export interface SavedView {
  id: string;
  name: string;
  query: Record<string, unknown>;
  display: Record<string, unknown>;
  pinned: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
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
  updateSource(sourceId: string, input: SourceUpdateInput) {
    return request<Source>(`/sources/${sourceId}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },
  testSource(sourceId: string) {
    return request<SourceTestResult>(`/sources/${sourceId}/test`, {
      method: "POST",
    });
  },
  testSourceDefinition(input: {
    name: string;
    kind: SourceKind;
    config: Record<string, string>;
  }) {
    return request<SourceTestResult>("/sources/test-definition", {
      method: "POST",
      body: JSON.stringify({ ...input, enabled: true }),
    });
  },
  startTranscription() {
    return request<TranscriptionSession>("/transcription/sessions", {
      method: "POST",
      body: JSON.stringify({
        language: "zh",
        format: "webm_opus",
        sample_rate: 48000,
      }),
    });
  },
  previewAgentPack(zipBase64: string) {
    return request<AgentPackPreview>("/agent-packs/import-preview", {
      method: "POST",
      body: JSON.stringify({ zip_base64: zipBase64, activate: false }),
    });
  },
  importAgentPack(zipBase64: string) {
    return request<AgentPackVersion>("/agent-packs/import", {
      method: "POST",
      body: JSON.stringify({ zip_base64: zipBase64, activate: true }),
    });
  },
  editAgentPack(
    packId: string,
    input: { path: string; content: string; version: string },
  ) {
    return request<AgentPackVersion>(`/agent-packs/${packId}/edit`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  agentPackVersions(packId: string) {
    return request<AgentPackVersion[]>(
      `/agent-packs/${packId}/versions`,
    );
  },
  activateAgentPackVersion(versionId: string) {
    return request<AgentPackVersion>(
      `/agent-packs/versions/${versionId}/activate`,
      { method: "POST" },
    );
  },
  artifacts: () => request<Artifact[]>("/artifacts"),
  createArtifact(input: {
    filename: string;
    media_type: string;
    content_base64: string;
  }) {
    return request<Artifact>("/artifacts", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  agent(input: AgentInput) {
    return request<AgentResponse>("/agent-runs", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  createAgentTurn(
    conversationId: string,
    input: {
      message: string;
      client_message_id: string;
      model_id?: string;
    },
  ) {
    return request<AgentTurn>(
      `/agent-conversations/${conversationId}/turns`,
      {
        method: "POST",
        body: JSON.stringify(input),
      },
    );
  },
  agentTurn: (turnId: string) =>
    request<AgentTurn>(`/agent-turns/${turnId}`),
  agentTurnEventsUrl: (turnId: string) =>
    `${API_BASE}/agent-turns/${turnId}/events`,
  cancelAgentTurn(turnId: string) {
    return request<AgentTurn>(`/agent-turns/${turnId}/cancel`, {
      method: "POST",
    });
  },
  resumeAgentTurn(turnId: string) {
    return request<AgentTurn>(`/agent-turns/${turnId}/resume`, {
      method: "POST",
    });
  },
  currentConversation: () =>
    request<AgentConversation>("/agent-conversations/current"),
  conversations(scope: AgentConversationScope = "active") {
    return request<AgentConversationSummary[]>(
      `/agent-conversations?scope=${scope}`,
    );
  },
  conversation(conversationId: string) {
    return request<AgentConversation>(
      `/agent-conversations/${conversationId}`,
    );
  },
  createConversation(input: { title?: string } = {}) {
    return request<AgentConversation>("/agent-conversations", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  updateConversation(
    conversationId: string,
    input: AgentConversationUpdate,
  ) {
    return request<AgentConversation>(
      `/agent-conversations/${conversationId}`,
      {
        method: "PATCH",
        body: JSON.stringify(input),
      },
    );
  },
  archiveConversation(conversationId: string) {
    return request<AgentConversation>(
      `/agent-conversations/${conversationId}/archive`,
      { method: "POST" },
    );
  },
  restoreConversation(conversationId: string) {
    return request<AgentConversation>(
      `/agent-conversations/${conversationId}/restore`,
      { method: "POST" },
    );
  },
  deleteConversation(conversationId: string) {
    return request<AgentConversation>(
      `/agent-conversations/${conversationId}`,
      { method: "DELETE" },
    );
  },
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
  collectionTasks: () => request<CollectionTask[]>("/tasks"),
  collectionTask: (taskId: string) =>
    request<CollectionTask>(`/tasks/${taskId}`),
  createCollectionTask(input: CollectionTaskWrite) {
    return request<CollectionTask>("/tasks", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  updateCollectionTask(
    taskId: string,
    input: Partial<CollectionTaskWrite> & { change_note?: string },
  ) {
    return request<CollectionTask>(`/tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },
  previewCollectionTask(taskId: string, config?: TaskConfig) {
    return request<TaskPreview>(`/tasks/${taskId}/preview`, {
      method: "POST",
      body: JSON.stringify({ config }),
    });
  },
  runCollectionTask(taskId: string) {
    return request<CollectionRun>(`/tasks/${taskId}/runs`, {
      method: "POST",
      body: JSON.stringify({ trigger_type: "manual" }),
    });
  },
  updateInformationState(
    itemId: string,
    input: Partial<Pick<TimelineItem, "seen" | "starred" | "archived" | "note">>,
  ) {
    return request(`/information/${itemId}/state`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },
  savedViews: () => request<SavedView[]>("/saved-views"),
  createSavedView(input: {
    name: string;
    query: Record<string, unknown>;
    display?: Record<string, unknown>;
    pinned?: boolean;
    is_default?: boolean;
  }) {
    return request<SavedView>("/saved-views", {
      method: "POST",
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
  startPosterWorkflow(maxChars = 400) {
    return request<PosterWorkflow>("/cards/workflows", {
      method: "POST",
      body: JSON.stringify({ max_chars: maxChars, item_ids: [] }),
    });
  },
  resumePosterWorkflow(threadId: string, approved: boolean) {
    return request<PosterWorkflow>(`/cards/workflows/${threadId}/resume`, {
      method: "POST",
      body: JSON.stringify({ approved }),
    });
  },
  updateCard(
    cardId: string,
    input: {
      expected_revision: number;
      title: string;
      summary: string;
      key_points: string[];
      template_id: CardItem["template_id"];
      cover_source: CardItem["cover_source"];
    },
  ) {
    return request<CardItem>(`/cards/${cardId}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },
  renderCard(cardId: string) {
    return request<{
      card_id: string;
      artifact_id: string;
      status: string;
      width: number;
      height: number;
    }>(`/cards/${cardId}/render`, { method: "POST" });
  },
};

export function artifactContentUrl(artifactId: string) {
  return `${API_BASE}/artifacts/${encodeURIComponent(artifactId)}/content`;
}
