"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IconBolt,
  IconBrain,
  IconRobot,
  IconCheck,
  IconClock,
  IconEdit,
  IconMicrophone,
  IconPhotoPlus,
  IconPlayerPlay,
  IconSend2,
  IconSettingsAutomation,
  IconX,
} from "@tabler/icons-react";
import Image from "next/image";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/app-shell";
import {
  AgentMessage,
  api,
  CommonPlan,
  formatModelLabel,
  ModelConfig,
  ScheduledTask,
} from "@/lib/api";

type PendingMessage = {
  id: string;
  content: string;
  images?: ImageAttachment[];
};

type ImageAttachment = {
  name: string;
  dataUrl: string;
};

type SpeechRecognitionResultLike = {
  0: { transcript: string };
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: SpeechRecognitionResultLike;
  };
};

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

const ACCEPTED_IMAGE_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/webp",
]);
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_IMAGES = 4;

export function AgentScreen() {
  const queryClient = useQueryClient();
  const [asideOpen, setAsideOpen] = useState(true);
  const [pendingMessage, setPendingMessage] =
    useState<PendingMessage | null>(null);
  const [sendError, setSendError] = useState("");
  const [draft, setDraft] = useState("");
  const [selectedModelId, setSelectedModelId] = useState("");
  const [images, setImages] = useState<ImageAttachment[]>([]);
  const [imageError, setImageError] = useState("");
  const [voiceError, setVoiceError] = useState("");
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const [editingPlan, setEditingPlan] = useState<CommonPlan | null>(null);
  const [schedulePlanId, setSchedulePlanId] = useState("");
  const [scheduleTime, setScheduleTime] = useState("09:00");
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      if (window.matchMedia("(max-width: 820px)").matches) {
        setAsideOpen(false);
      }
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  useEffect(
    () => () => {
      recognitionRef.current?.abort();
    },
    [],
  );
  const conversation = useQuery({
    queryKey: ["agent-conversation"],
    queryFn: api.currentConversation,
  });
  const plans = useQuery({ queryKey: ["plans"], queryFn: api.plans });
  const tasks = useQuery({ queryKey: ["tasks"], queryFn: api.tasks });
  const models = useQuery({ queryKey: ["models"], queryFn: api.models });
  const activeModelId =
    selectedModelId ||
    models.data?.find((model: ModelConfig) => model.is_default)?.id ||
    models.data?.[0]?.id ||
    "";

  const agent = useMutation({
    mutationFn: api.agent,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["agent-conversation"],
      });
      setPendingMessage(null);
      void queryClient.invalidateQueries({ queryKey: ["timeline"] });
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: async (reason) => {
      setSendError(
        reason instanceof Error
          ? reason.message
          : "SYS-001（本地服务暂时不可用）",
      );
      await queryClient.invalidateQueries({
        queryKey: ["agent-conversation"],
      });
      setPendingMessage(null);
    },
  });
  const updatePlan = useMutation({
    mutationFn: ({
      id,
      input,
    }: {
      id: string;
      input: Partial<CommonPlan>;
    }) => api.updatePlan(id, input),
    onSuccess: () => {
      setEditingPlan(null);
      void queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
  const saveTask = useMutation({
    mutationFn: ({
      plan,
      time,
    }: {
      plan: CommonPlan;
      time: string;
    }) => {
      const existing = tasks.data?.find(
        (task: ScheduledTask) => task.plan_id === plan.id,
      );
      return existing
        ? api.updateTask(existing.id, {
            time_of_day: time,
            enabled: true,
          })
        : api.createTask({
            name: plan.name,
            plan_id: plan.id,
            time_of_day: time,
          });
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["tasks"] }),
  });
  const activeTasks = useMemo(
    () => tasks.data?.filter((task: ScheduledTask) => task.enabled) ?? [],
    [tasks.data],
  );
  const selectedPlan =
    plans.data?.find((plan: CommonPlan) => plan.id === schedulePlanId) ??
    plans.data?.[0];

  function send(message: string) {
    const value = message.trim();
    if (!value || agent.isPending) return;
    recognitionRef.current?.abort();
    recognitionRef.current = null;
    setIsListening(false);
    const attachedImages = images;
    const clientMessageId = globalThis.crypto.randomUUID();
    setPendingMessage({
      id: clientMessageId,
      content: value,
      images: attachedImages.length ? attachedImages : undefined,
    });
    setSendError("");
    setDraft("");
    setImages([]);
    setImageError("");
    agent.mutate({
      message: value,
      conversation_id: conversation.data?.id,
      client_message_id: clientMessageId,
      model_id: activeModelId || undefined,
      image_urls: attachedImages.map((image) => image.dataUrl),
    });
  }

  async function addImages(fileList: FileList | null) {
    const files = Array.from(fileList ?? []);
    if (!files.length) return;
    if (images.length + files.length > MAX_IMAGES) {
      setImageError("IMAGE-003（一次最多上传 4 张图片）");
      return;
    }
    const unsupported = files.find(
      (file) => !ACCEPTED_IMAGE_TYPES.has(file.type),
    );
    if (unsupported) {
      setImageError("IMAGE-001（仅支持 PNG、JPEG 和 WebP 图片）");
      return;
    }
    const oversized = files.find((file) => file.size > MAX_IMAGE_BYTES);
    if (oversized) {
      setImageError("IMAGE-002（单张图片不能超过 5 MB）");
      return;
    }
    let additions: ImageAttachment[];
    try {
      additions = await Promise.all(
        files.map(async (file) => ({
          name: file.name,
          dataUrl: await readFileAsDataUrl(file),
        })),
      );
    } catch {
      setImageError("IMAGE-004（读取图片失败）");
      return;
    }
    setImages((current) => [...current, ...additions]);
    setImageError("");
  }

  function toggleVoiceInput() {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      return;
    }

    const speechWindow = window as typeof window & {
      SpeechRecognition?: SpeechRecognitionConstructor;
      webkitSpeechRecognition?: SpeechRecognitionConstructor;
    };
    const Recognition =
      speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
    if (!Recognition) {
      setVoiceError("VOICE-001（当前浏览器不支持语音转文字）");
      return;
    }

    const recognition = new Recognition();
    const baseDraft = draft.trimEnd();
    recognition.lang = "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      let transcript = "";
      for (let index = 0; index < event.results.length; index += 1) {
        transcript += event.results[index][0].transcript;
      }
      const separator = baseDraft && transcript ? " " : "";
      setDraft(`${baseDraft}${separator}${transcript}`);
    };
    recognition.onerror = (event) => {
      setVoiceError(
        event.error === "not-allowed" || event.error === "security"
          ? "VOICE-002（无法访问麦克风）"
          : "VOICE-003（语音转文字失败）",
      );
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      setIsListening(false);
    };
    try {
      recognition.start();
      recognitionRef.current = recognition;
      setIsListening(true);
      setVoiceError("");
    } catch {
      setVoiceError("VOICE-003（语音转文字失败）");
    }
  }

  function submitMessage(event: FormEvent) {
    event.preventDefault();
    send(draft);
  }

  const automationAside = (
    <>
      <div className="aside-title">
        <div>
          <span className="eyebrow">快捷控制</span>
          <h2>方案与定时</h2>
        </div>
        <button className="icon-button" onClick={() => setAsideOpen(false)}>
          <IconX size={18} />
          <span className="sr-only">关闭</span>
        </button>
      </div>
      <section className="aside-section">
        <div className="section-heading">
          <h3>常用方案</h3>
          <span>{plans.data?.length ?? 0}</span>
        </div>
        <div className="plan-list">
          {plans.data?.map((plan: CommonPlan) => (
            <div className="plan-card" key={plan.id}>
              <button className="plan-run" onClick={() => send(plan.prompt)}>
                <IconPlayerPlay size={16} />
                <span>
                  <strong>{plan.name}</strong>
                  <small>
                    {plan.time_range_hours} 小时 · {plan.topics.join("、")}
                  </small>
                </span>
              </button>
              <button
                className="icon-button"
                onClick={() => setEditingPlan(plan)}
                aria-label={`编辑 ${plan.name}`}
              >
                <IconEdit size={16} />
              </button>
            </div>
          ))}
        </div>
      </section>
      <section className="aside-section">
        <div className="section-heading">
          <h3>每日定时</h3>
          <span>{activeTasks.length}</span>
        </div>
        {tasks.data?.map((task: ScheduledTask) => (
          <div className="task-row" key={task.id}>
            <IconClock size={17} />
            <span>
              <strong>{task.name}</strong>
              <small>每天 {task.time_of_day}</small>
            </span>
            <button
              className={`toggle ${task.enabled ? "is-on" : ""}`}
              onClick={() =>
                api
                  .updateTask(task.id, { enabled: !task.enabled })
                  .then(() =>
                    queryClient.invalidateQueries({ queryKey: ["tasks"] }),
                  )
              }
              aria-label={`${task.enabled ? "停用" : "启用"} ${task.name}`}
            />
          </div>
        ))}
        <div className="schedule-create">
          <select
            value={selectedPlan?.id ?? ""}
            onChange={(event) => setSchedulePlanId(event.target.value)}
            aria-label="选择常用方案"
          >
            {plans.data?.map((plan: CommonPlan) => (
              <option key={plan.id} value={plan.id}>
                {plan.name}
              </option>
            ))}
          </select>
          <input
            type="time"
            value={scheduleTime}
            onChange={(event) => setScheduleTime(event.target.value)}
            aria-label="定时时间"
          />
          <button
            className="secondary-button"
            disabled={!selectedPlan || saveTask.isPending}
            onClick={() =>
              selectedPlan &&
              saveTask.mutate({ plan: selectedPlan, time: scheduleTime })
            }
          >
            <IconSettingsAutomation size={17} />
            {tasks.data?.some(
              (task: ScheduledTask) => task.plan_id === selectedPlan?.id,
            )
              ? "更新"
              : "设定"}
          </button>
        </div>
      </section>
    </>
  );

  return (
    <AppShell
      aside={automationAside}
      asideOpen={asideOpen}
      onAsideToggle={() => setAsideOpen((value) => !value)}
    >
      <header className="topbar">
        <div>
          <span className="eyebrow">Workspace Agent</span>
          <h1>对话</h1>
        </div>
        <div className="topbar-actions">
          <button
            className="secondary-button"
            onClick={() => setAsideOpen((value) => !value)}
          >
            <IconSettingsAutomation size={18} />
            方案与定时
          </button>
        </div>
      </header>
      <section className="conversation">
        <div className="conversation-thread" aria-live="polite">
          <div className="conversation-intro">
            <span className="agent-orb">
              <IconRobot size={25} />
            </span>
            <h2>今天想了解什么？</h2>
            <p>直接说“采集最新信息”或“查询 LangGraph”。</p>
          </div>
          {conversation.isLoading && (
            <div className="conversation-loading">正在恢复对话…</div>
          )}
          {conversation.isError && (
            <div className="conversation-error" role="alert">
              无法读取已保存的对话，请确认本地服务已启动。
            </div>
          )}
          {conversation.data?.messages.map((message: AgentMessage) => (
            <div
              className={`message message-${message.role}`}
              key={message.id}
            >
              {message.role === "assistant" && (
                <span className="message-avatar">
                  <IconRobot size={17} />
                </span>
              )}
              <div className="message-content">
                {message.image_count > 0 && (
                  <small>已附 {message.image_count} 张图片</small>
                )}
                <p>{message.content}</p>
                {message.capability_calls.map((call) => (
                  <div
                    className={`message-capability is-${call.status}`}
                    key={`${message.id}-${call.capability_id}`}
                  >
                    <IconBolt size={14} aria-hidden="true" />
                    <span>{capabilityLabel(call.capability_id)}</span>
                    <small>{capabilityStatusLabel(call.status)}</small>
                  </div>
                ))}
                {message.error_code &&
                  message.capability_calls.length === 0 && (
                    <small className="message-error-code">
                      {message.error_code}
                    </small>
                  )}
              </div>
            </div>
          ))}
          {pendingMessage && (
            <div className="message message-user" key={pendingMessage.id}>
              <div className="message-content">
                {pendingMessage.images && (
                  <div className="message-images">
                    {pendingMessage.images.map((image) => (
                      <Image
                        key={image.name}
                        src={image.dataUrl}
                        alt={image.name}
                        width={72}
                        height={54}
                        unoptimized
                      />
                    ))}
                  </div>
                )}
                <p>{pendingMessage.content}</p>
              </div>
            </div>
          )}
          {sendError && !agent.isPending && (
            <div className="message message-assistant">
              <span className="message-avatar">
                <IconRobot size={17} />
              </span>
              <div className="message-content">
                <p>{sendError}</p>
              </div>
            </div>
          )}
          {agent.isPending && (
            <div className="message message-assistant">
              <span className="message-avatar">
                <IconRobot size={17} />
              </span>
              <div className="message-content">
                <p className="typing">正在执行</p>
              </div>
            </div>
          )}
        </div>
        <form className="composer" onSubmit={submitMessage}>
          {images.length > 0 && (
            <div className="composer-images" aria-label="待发送图片">
              {images.map((image, index) => (
                <div className="composer-image" key={`${image.name}-${index}`}>
                  <Image
                    src={image.dataUrl}
                    alt=""
                    width={48}
                    height={48}
                    unoptimized
                  />
                  <span title={image.name}>{image.name}</span>
                  <button
                    className="icon-button"
                    type="button"
                    onClick={() =>
                      setImages((current) =>
                        current.filter((_, itemIndex) => itemIndex !== index),
                      )
                    }
                    aria-label={`移除图片 ${image.name}`}
                  >
                    <IconX size={15} />
                  </button>
                </div>
              ))}
            </div>
          )}
          {(imageError || voiceError) && (
            <span className="composer-error" role="alert">
              {imageError || voiceError}
            </span>
          )}
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="向 Workspace Agent 发送消息…"
            rows={2}
          />
          <div className="composer-footer">
            <div className="composer-tools">
              <label
                className="icon-button file-button"
                title="上传图片"
              >
                <IconPhotoPlus size={18} />
                <span className="sr-only">上传图片</span>
                <input
                  className="sr-only"
                  type="file"
                  aria-label="上传图片"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  onChange={(event) => {
                    void addImages(event.target.files);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
              <button
                className={`icon-button voice-button ${isListening ? "is-active" : ""}`}
                type="button"
                onClick={toggleVoiceInput}
                aria-label={isListening ? "停止语音转文字" : "语音转文字"}
                aria-pressed={isListening}
                title={isListening ? "停止语音转文字" : "语音转文字"}
              >
                <IconMicrophone size={18} />
              </button>
              <span>Enter 发送 · Shift + Enter 换行</span>
            </div>
            <div className="composer-actions">
              <label className="model-switcher composer-model-switcher">
                <IconBrain size={16} aria-hidden="true" />
                <span className="sr-only">选择对话模型</span>
                <select
                  value={activeModelId}
                  onChange={(event) => setSelectedModelId(event.target.value)}
                  disabled={models.isLoading || !models.data?.length}
                  aria-label="选择对话模型"
                >
                  {!models.data?.length && (
                    <option value="">
                      {models.isError
                        ? "SYS-001（读取模型失败）"
                        : "正在读取模型…"}
                    </option>
                  )}
                  {models.data?.map((model: ModelConfig) => (
                    <option key={model.id} value={model.id}>
                      {formatModelLabel(model)}
                    </option>
                  ))}
                </select>
              </label>
              <Link
                className="composer-settings-link"
                href="/settings/models"
                title="设定模型"
              >
                设定模型
              </Link>
              <button
                className="send-button"
                type="submit"
                disabled={
                  !draft.trim() ||
                  agent.isPending ||
                  conversation.isLoading
                }
                aria-label="发送"
              >
                <IconSend2 size={19} />
              </button>
            </div>
          </div>
        </form>
      </section>
      {editingPlan && (
        <div className="modal-backdrop">
          <form
            className="modal"
            onSubmit={(event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              updatePlan.mutate({
                id: editingPlan.id,
                input: {
                  name: String(form.get("name")),
                  prompt: String(form.get("prompt")),
                  time_range_hours: Number(form.get("hours")),
                },
              });
            }}
          >
            <div className="modal-title">
              <h2>编辑常用方案</h2>
              <button
                type="button"
                className="icon-button"
                onClick={() => setEditingPlan(null)}
              >
                <IconX size={18} />
              </button>
            </div>
            <label>
              名称
              <input name="name" defaultValue={editingPlan.name} required />
            </label>
            <label>
              指令
              <textarea
                name="prompt"
                defaultValue={editingPlan.prompt}
                rows={4}
                required
              />
            </label>
            <label>
              时间范围（小时）
              <input
                name="hours"
                type="number"
                min={1}
                max={720}
                defaultValue={editingPlan.time_range_hours}
                required
              />
            </label>
            <button className="primary-button" type="submit">
              <IconCheck size={18} />
              保存方案
            </button>
          </form>
        </div>
      )}
    </AppShell>
  );
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result)));
    reader.addEventListener("error", () => reject(reader.error));
    reader.readAsDataURL(file);
  });
}

function capabilityLabel(capabilityId: string): string {
  const labels: Record<string, string> = {
    "collection.run.start": "采集 AI 信息",
    "intelligence.timeline.query": "查询 AI 信息",
    "review.batch.submit": "提交审核",
    "poster.draft.generate": "生成卡片",
  };
  return labels[capabilityId] ?? capabilityId;
}

function capabilityStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    completed: "已完成",
    partial: "部分完成",
    failed: "失败",
    running: "执行中",
  };
  return labels[status] ?? status;
}
