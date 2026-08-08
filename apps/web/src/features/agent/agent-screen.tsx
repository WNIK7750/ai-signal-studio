"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IconArchive,
  IconArrowBackUp,
  IconBolt,
  IconBrain,
  IconCheck,
  IconClock,
  IconEdit,
  IconHistory,
  IconMessage,
  IconMicrophone,
  IconPin,
  IconPinnedOff,
  IconPhotoPlus,
  IconPlayerPlay,
  IconPlus,
  IconRobot,
  IconSearch,
  IconSend2,
  IconSettingsAutomation,
  IconTrash,
  IconX,
} from "@tabler/icons-react";
import Image from "next/image";
import Link from "next/link";
import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AppShell } from "@/components/app-shell";
import { subscribeToAgentTurn } from "@/features/agent/agent-event-stream";
import { AgentResultBlocks } from "@/features/agent/agent-result-blocks";
import { AgentTurnProgress } from "@/features/agent/agent-turn-progress";
import {
  AgentConversationScope,
  AgentConversationSummary,
  AgentMessage,
  AgentPlan,
  AgentResultBlock,
  AgentTurn,
  AgentTurnEvent,
  AgentTurnResult,
  api,
  CollectionTask,
  CollectionTaskWrite,
  formatModelLabel,
  ModelConfig,
  transcriptionWebSocketUrl,
} from "@/lib/api";

type PendingMessage = {
  id: string;
  content: string;
  images?: ImageAttachment[];
};

type ImageAttachment = {
  name: string;
  dataUrl: string;
  artifactId: string;
};

const ACCEPTED_IMAGE_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/webp",
]);
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_IMAGES = 4;
const DRAFT_STORAGE_PREFIX = "ai-signal-agent:draft:v1:";
const SCROLL_STORAGE_PREFIX = "ai-signal-agent:scroll:v1:";
const ACTIVE_CONVERSATION_KEY = "ai-signal-agent:active-conversation:v1";
const MODEL_STORAGE_PREFIX = "ai-signal-agent:model:v1:";

type ConversationAction = {
  kind: "rename" | "pin" | "archive" | "restore" | "delete";
  conversation: AgentConversationSummary;
  title?: string;
};

type ConversationGroup = {
  label: string;
  conversations: AgentConversationSummary[];
};

export function AgentScreen() {
  const queryClient = useQueryClient();
  const [asideOpen, setAsideOpen] = useState(true);
  const [conversationPanelOpen, setConversationPanelOpen] = useState(false);
  const [conversationScope, setConversationScope] =
    useState<AgentConversationScope>("active");
  const [activeConversationId, setActiveConversationId] = useState("");
  const [conversationSearch, setConversationSearch] = useState("");
  const [conversationActionError, setConversationActionError] = useState("");
  const [renamingConversationId, setRenamingConversationId] = useState("");
  const [renameDraft, setRenameDraft] = useState("");
  const [deletedConversation, setDeletedConversation] = useState<{
    id: string;
    title: string;
  } | null>(null);
  const [pendingMessage, setPendingMessage] =
    useState<PendingMessage | null>(null);
  const [sendError, setSendError] = useState("");
  const [draft, setDraft] = useState("");
  const [selectedModelIds, setSelectedModelIds] = useState<
    Record<string, string>
  >({});
  const [images, setImages] = useState<ImageAttachment[]>([]);
  const [imageError, setImageError] = useState("");
  const [voiceError, setVoiceError] = useState("");
  const [voicePartial, setVoicePartial] = useState("");
  const [createdDraftMessages, setCreatedDraftMessages] = useState<Set<string>>(
    () => new Set(),
  );
  const [isListening, setIsListening] = useState(false);
  const [activeTurn, setActiveTurn] = useState<AgentTurn | null>(null);
  const [turnEvents, setTurnEvents] = useState<AgentTurnEvent[]>([]);
  const [turnElapsedMs, setTurnElapsedMs] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const transcriptionSocketRef = useRef<WebSocket | null>(null);
  const finalTranscriptSegmentsRef = useRef<Set<string>>(new Set());
  const closeTurnStreamRef = useRef<(() => void) | null>(null);
  const conversationThreadRef = useRef<HTMLDivElement | null>(null);
  const activeConversationIdRef = useRef("");
  const scrollRestoreConversationRef = useRef("");
  const requestedInitialConversationRef = useRef(false);
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
      if (mediaRecorderRef.current?.state !== "inactive") {
        mediaRecorderRef.current?.stop();
      }
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      transcriptionSocketRef.current?.close();
      closeTurnStreamRef.current?.();
    },
    [],
  );
  const conversationList = useQuery({
    queryKey: ["agent-conversations", conversationScope],
    queryFn: () => api.conversations(conversationScope),
  });
  const conversation = useQuery({
    queryKey: ["agent-conversation", activeConversationId],
    queryFn: () => api.conversation(activeConversationId),
    enabled: Boolean(activeConversationId),
  });
  const tasks = useQuery({
    queryKey: ["collection-tasks"],
    queryFn: api.collectionTasks,
  });
  const models = useQuery({ queryKey: ["models"], queryFn: api.models });
  const activeModelId =
    selectedModelIds[activeConversationId] ||
    readLocalValue(`${MODEL_STORAGE_PREFIX}${activeConversationId}`) ||
    models.data?.find((model: ModelConfig) => model.is_default)?.id ||
    models.data?.[0]?.id ||
    "";

  const openTurnStream = useCallback(
    (turnId: string) => {
      closeTurnStreamRef.current?.();
      closeTurnStreamRef.current = subscribeToAgentTurn(turnId, {
        onEvent: (event) => {
          setTurnElapsedMs((current) => Math.max(current, event.elapsed_ms));
          setTurnEvents((current) =>
            current.some((item) => item.id === event.id)
              ? current
              : [...current, event],
          );
          if (event.type === "plan.ready" && event.data.plan) {
            setActiveTurn((current) =>
              current
                ? {
                    ...current,
                    status: "running",
                    plan: event.data.plan as AgentPlan,
                    effective_model_id:
                      typeof event.data.effective_model_id === "string"
                        ? event.data.effective_model_id
                        : current.effective_model_id,
                  }
                : current,
            );
          } else if (event.type === "turn.partial") {
            setActiveTurn((current) =>
              current ? { ...current, status: "partial" } : current,
            );
          } else if (event.type === "turn.completed") {
            setActiveTurn((current) =>
              current ? { ...current, status: "complete" } : current,
            );
          }
        },
        onTerminal: () => {
          void (async () => {
            const completed = await api.agentTurn(turnId);
            setActiveTurn(completed);
            setTurnElapsedMs(completed.total_duration_ms);
            await queryClient.invalidateQueries({
              queryKey: ["agent-conversation", completed.conversation_id],
            });
            setPendingMessage(null);
            void queryClient.invalidateQueries({
              queryKey: ["agent-conversations"],
            });
            void queryClient.invalidateQueries({ queryKey: ["timeline"] });
            void queryClient.invalidateQueries({ queryKey: ["runs"] });
            setActiveTurn(null);
            setTurnEvents([]);
          })().catch((reason) => setSendError(errorMessage(reason)));
        },
        onError: () => {
          // Native EventSource reconnects with Last-Event-ID.
        },
      });
    },
    [queryClient],
  );

  const researchTurn = useMutation({
    mutationFn: ({
      conversationId,
      message,
      clientMessageId,
      modelId,
      artifactIds,
    }: {
      conversationId: string;
      message: string;
      clientMessageId: string;
      modelId?: string;
      artifactIds: string[];
    }) =>
      api.createAgentTurn(conversationId, {
        message,
        client_message_id: clientMessageId,
        model_id: modelId,
        artifact_ids: artifactIds,
      }),
    onSuccess: (turn) => {
      setActiveTurn(turn);
      setTurnEvents([]);
      setTurnElapsedMs(0);
      openTurnStream(turn.id);
      void queryClient.invalidateQueries({
        queryKey: ["agent-conversations"],
      });
    },
    onError: async (reason) => {
      setSendError(errorMessage(reason));
      setPendingMessage(null);
      await queryClient.invalidateQueries({
        queryKey: ["agent-conversation", activeConversationId],
      });
    },
  });
  const cancelTurn = useMutation({
    mutationFn: (turnId: string) => api.cancelAgentTurn(turnId),
    onSuccess: setActiveTurn,
  });
  const resumeTurn = useMutation({
    mutationFn: (turnId: string) => api.resumeAgentTurn(turnId),
    onSuccess: (turn) => {
      setActiveTurn(turn);
      setTurnEvents([]);
      openTurnStream(turn.id);
    },
  });
  const isAgentBusy =
    researchTurn.isPending ||
    (activeTurn !== null &&
      !["complete", "partial", "failed", "cancelled"].includes(
        activeTurn.status,
      ));
  const streamedResultBlocks = useMemo<AgentResultBlock[]>(
    () =>
      turnEvents.reduce<AgentResultBlock[]>((blocks, event) => {
        if (
          event.type === "result.block" &&
          isAgentResultBlock(event.data) &&
          !blocks.some(
            (candidate) => candidate.block_id === event.data.block_id,
          )
        ) {
          blocks.push(event.data);
        }
        return blocks;
      }, []),
    [turnEvents],
  );
  const createConversation = useMutation({
    mutationFn: () => api.createConversation(),
    onSuccess: (created) => {
      queryClient.setQueryData<AgentConversationSummary[]>(
        ["agent-conversations", "active"],
        (current = []) => [
          created,
          ...current.filter((item) => item.id !== created.id),
        ],
      );
      setConversationScope("active");
      activateConversation(created.id);
      queryClient.setQueryData(
        ["agent-conversation", created.id],
        created,
      );
      void queryClient.invalidateQueries({
        queryKey: ["agent-conversations"],
      });
    },
    onError: (reason) => {
      requestedInitialConversationRef.current = false;
      setConversationActionError(errorMessage(reason));
    },
  });
  const conversationAction = useMutation({
    mutationFn: (action: ConversationAction) => {
      switch (action.kind) {
        case "rename":
          return api.updateConversation(action.conversation.id, {
            title: action.title?.trim() || action.conversation.title,
          });
        case "pin":
          return api.updateConversation(action.conversation.id, {
            pinned: !action.conversation.pinned_at,
          });
        case "archive":
          return api.archiveConversation(action.conversation.id);
        case "restore":
          return api.restoreConversation(action.conversation.id);
        case "delete":
          return api.deleteConversation(action.conversation.id);
      }
    },
    onSuccess: (updated, action) => {
      setConversationActionError("");
      setRenamingConversationId("");
      queryClient.setQueryData(
        ["agent-conversation", updated.id],
        updated,
      );
      void queryClient.invalidateQueries({
        queryKey: ["agent-conversations"],
      });

      if (action.kind === "delete") {
        setDeletedConversation({
          id: action.conversation.id,
          title: action.conversation.title,
        });
      }
      if (
        (action.kind === "archive" || action.kind === "delete") &&
        action.conversation.id === activeConversationId
      ) {
        saveCurrentConversationScroll();
        activeConversationIdRef.current = "";
        setActiveConversationId("");
      }
      if (action.kind === "restore") {
        queryClient.setQueryData<AgentConversationSummary[]>(
          ["agent-conversations", "active"],
          (current = []) => [
            updated,
            ...current.filter((item) => item.id !== updated.id),
          ],
        );
        setConversationScope("active");
        activateConversation(updated.id);
      }
    },
    onError: (reason) => {
      setConversationActionError(errorMessage(reason));
    },
  });
  const createTask = useMutation({
    mutationFn: ({
      input,
    }: {
      messageId: string;
      input: CollectionTaskWrite;
    }) =>
      api.createCollectionTask({ ...input, status: "enabled" }),
    onSuccess: (_task, variables) => {
      setCreatedDraftMessages((current) => {
        const next = new Set(current);
        next.add(variables.messageId);
        return next;
      });
      return queryClient.invalidateQueries({ queryKey: ["collection-tasks"] });
    },
  });
  const runTask = useMutation({
    mutationFn: (taskId: string) => api.runCollectionTask(taskId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void queryClient.invalidateQueries({ queryKey: ["timeline"] });
      void queryClient.invalidateQueries({ queryKey: ["collection-tasks"] });
    },
  });
  const activeTasks = useMemo(
    () =>
      tasks.data?.filter((task: CollectionTask) => task.status === "enabled") ??
      [],
    [tasks.data],
  );
  const visibleConversationGroups = useMemo(
    () =>
      groupConversations(
        conversationList.data ?? [],
        conversationSearch,
        conversationScope,
      ),
    [conversationList.data, conversationScope, conversationSearch],
  );
  const conversationWritable =
    conversation.data?.status === "active" &&
    !conversation.data.deleted_at &&
    !conversation.data.archived_at;

  useEffect(() => {
    if (
      conversationScope !== "active" ||
      !conversationList.isSuccess
    ) {
      return;
    }
    if (conversationList.data.length > 0) {
      requestedInitialConversationRef.current = false;
      return;
    }
    if (
      requestedInitialConversationRef.current ||
      createConversation.isPending
    ) {
      return;
    }
    requestedInitialConversationRef.current = true;
    createConversation.mutate();
  }, [
    conversationList.data,
    conversationList.isSuccess,
    conversationScope,
    createConversation,
  ]);

  useEffect(() => {
    const turnId = conversation.data?.active_turn_id;
    if (!turnId || activeTurn?.id === turnId) return;
    let cancelled = false;
    void api
      .agentTurn(turnId)
      .then((turn) => {
        if (cancelled) return;
        setActiveTurn(turn);
        setTurnElapsedMs(turn.total_duration_ms);
        openTurnStream(turn.id);
      })
      .catch((reason) => {
        if (!cancelled) setSendError(errorMessage(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [activeTurn?.id, conversation.data?.active_turn_id, openTurnStream]);

  useEffect(() => {
    const listedConversations = conversationList.data;
    if (!listedConversations?.length) return;
    if (
      activeConversationId &&
      listedConversations.some(
        (item) => item.id === activeConversationId,
      )
    ) {
      return;
    }
    const savedConversationId = readSessionValue(ACTIVE_CONVERSATION_KEY);
    const nextConversation =
      listedConversations.find(
        (item) => item.id === savedConversationId,
      ) ?? listedConversations[0];
    const frame = requestAnimationFrame(() => {
      scrollRestoreConversationRef.current = nextConversation.id;
      activeConversationIdRef.current = nextConversation.id;
      setActiveConversationId(nextConversation.id);
      setDraft(readDraft(nextConversation.id));
      writeSessionValue(ACTIVE_CONVERSATION_KEY, nextConversation.id);
    });
    return () => cancelAnimationFrame(frame);
  }, [activeConversationId, conversationList.data]);

  useEffect(() => {
    if (
      !conversation.data ||
      conversation.data.id !== activeConversationId
    ) {
      return;
    }
    const frame = requestAnimationFrame(() => {
      const thread = conversationThreadRef.current;
      if (!thread) return;
      if (
        scrollRestoreConversationRef.current === activeConversationId
      ) {
        thread.scrollTop =
          readScrollPosition(activeConversationId) ?? thread.scrollHeight;
        scrollRestoreConversationRef.current = "";
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [
    activeConversationId,
    conversation.data,
    conversation.data?.messages.length,
  ]);

  function saveCurrentConversationScroll() {
    if (!activeConversationId || !conversationThreadRef.current) return;
    writeSessionValue(
      `${SCROLL_STORAGE_PREFIX}${activeConversationId}`,
      String(conversationThreadRef.current.scrollTop),
    );
  }

  function activateConversation(conversationId: string) {
    if (!conversationId || isAgentBusy) return;
    saveCurrentConversationScroll();
    releaseVoiceResources();
    transcriptionSocketRef.current?.close();
    transcriptionSocketRef.current = null;
    setImages([]);
    setImageError("");
    setVoiceError("");
    setSendError("");
    setPendingMessage(null);
    closeTurnStreamRef.current?.();
    setActiveTurn(null);
    setTurnEvents([]);
    setTurnElapsedMs(0);
    scrollRestoreConversationRef.current = conversationId;
    activeConversationIdRef.current = conversationId;
    setActiveConversationId(conversationId);
    setDraft(readDraft(conversationId));
    writeSessionValue(ACTIVE_CONVERSATION_KEY, conversationId);
    if (window.matchMedia("(max-width: 1359px)").matches) {
      setConversationPanelOpen(false);
    }
  }

  function scrollConversationToEnd() {
    requestAnimationFrame(() => {
      const thread = conversationThreadRef.current;
      if (!thread) return;
      thread.scrollTop = thread.scrollHeight;
      if (activeConversationId) {
        writeSessionValue(
          `${SCROLL_STORAGE_PREFIX}${activeConversationId}`,
          String(thread.scrollTop),
        );
      }
    });
  }

  function beginRename(item: AgentConversationSummary) {
    setRenamingConversationId(item.id);
    setRenameDraft(item.title);
    setConversationActionError("");
  }

  function submitRename(
    event: FormEvent<HTMLFormElement>,
    item: AgentConversationSummary,
  ) {
    event.preventDefault();
    const title = renameDraft.trim();
    if (!title || title === item.title) {
      setRenamingConversationId("");
      return;
    }
    conversationAction.mutate({
      kind: "rename",
      conversation: item,
      title,
    });
  }

  function undoDelete() {
    if (!deletedConversation || conversationAction.isPending) return;
    const summary =
      conversationList.data?.find(
        (item) => item.id === deletedConversation.id,
      ) ??
      ({
        id: deletedConversation.id,
        title: deletedConversation.title,
      } as AgentConversationSummary);
    conversationAction.mutate(
      { kind: "restore", conversation: summary },
      { onSuccess: () => setDeletedConversation(null) },
    );
  }

  function send(message: string) {
    const value = message.trim();
    if (!value || isAgentBusy || !conversationWritable) return;
    releaseVoiceResources();
    transcriptionSocketRef.current?.close();
    transcriptionSocketRef.current = null;
    const attachedImages = images;
    const clientMessageId = globalThis.crypto.randomUUID();
    setPendingMessage({
      id: clientMessageId,
      content: value,
      images: attachedImages.length ? attachedImages : undefined,
    });
    setSendError("");
    setDraft("");
    removeDraft(activeConversationId);
    setImages([]);
    setImageError("");
    scrollConversationToEnd();
    setActiveTurn({
      id: "",
      conversation_id: activeConversationId,
      request_id: "",
      client_message_id: clientMessageId,
      status: "queued",
      message: value,
      workflow_version: "0.8.0",
      requested_model_id: activeModelId || null,
      effective_model_id: null,
      manifest: {},
      plan: {},
      result: {},
      error: null,
      total_duration_ms: 0,
      created_at: new Date().toISOString(),
      started_at: null,
      completed_at: null,
    });
    researchTurn.mutate({
      conversationId: activeConversationId,
      message: value,
      clientMessageId,
      modelId: activeModelId || undefined,
      artifactIds: attachedImages.map((image) => image.artifactId),
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
        files.map(async (file) => {
          const dataUrl = await readFileAsDataUrl(file);
          const artifact = await api.createArtifact({
            filename: file.name,
            media_type: file.type,
            content_base64: dataUrl.slice(dataUrl.indexOf(",") + 1),
          });
          return {
            name: file.name,
            dataUrl,
            artifactId: artifact.artifact_id,
          };
        }),
      );
    } catch {
      setImageError("IMAGE-004（读取图片失败）");
      return;
    }
    setImages((current) => [...current, ...additions]);
    setImageError("");
  }

  function releaseVoiceResources() {
    if (mediaRecorderRef.current?.state !== "inactive") {
      mediaRecorderRef.current?.stop();
    }
    mediaRecorderRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    setIsListening(false);
  }

  async function toggleVoiceInput() {
    if (isListening) {
      releaseVoiceResources();
      const socket = transcriptionSocketRef.current;
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "stop" }));
      } else {
        socket?.close();
        transcriptionSocketRef.current = null;
      }
      return;
    }
    if (
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined" ||
      typeof WebSocket === "undefined"
    ) {
      setVoiceError("VOICE-001（当前浏览器不支持实时语音转文字）");
      return;
    }
    try {
      setVoiceError("");
      setVoicePartial("");
      finalTranscriptSegmentsRef.current.clear();
      const transcription = await api.startTranscription();
      if (!transcription.token) {
        throw new Error("STT_TOKEN_MISSING");
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });
      mediaStreamRef.current = stream;
      const recorder = new MediaRecorder(stream, {
        mimeType: "audio/webm;codecs=opus",
      });
      mediaRecorderRef.current = recorder;
      const socket = new WebSocket(
        transcriptionWebSocketUrl(
          transcription.session_id,
          transcription.token,
        ),
      );
      transcriptionSocketRef.current = socket;
      recorder.ondataavailable = async (event) => {
        if (event.data.size && socket.readyState === WebSocket.OPEN) {
          socket.send(await event.data.arrayBuffer());
        }
      };
      socket.onopen = () => {
        socket.send(
          JSON.stringify({
            type: "start",
            language: "zh",
            format: "webm_opus",
            sample_rate: 48000,
          }),
        );
        recorder.start(300);
        setIsListening(true);
      };
      socket.onmessage = (event) => {
        const message = JSON.parse(String(event.data)) as {
          type: string;
          segment_id?: string;
          revision?: number;
          text?: string;
          code?: string;
        };
        if (message.type === "transcript.partial") {
          setVoicePartial(message.text ?? "");
        } else if (message.type === "transcript.final") {
          const key = `${message.segment_id}:${message.revision}`;
          if (finalTranscriptSegmentsRef.current.has(key)) return;
          finalTranscriptSegmentsRef.current.add(key);
          setVoicePartial("");
          setDraft((current) => {
            const text = message.text?.trim() ?? "";
            const next = `${current.trimEnd()}${
              current.trimEnd() && text ? " " : ""
            }${text}`;
            if (activeConversationId) {
              writeDraft(activeConversationId, next);
            }
            return next;
          });
        } else if (message.type === "session.error") {
          setVoiceError(
            `VOICE-003（实时语音转文字失败：${
              message.code ?? "STT_PROVIDER_ERROR"
            }）`,
          );
          releaseVoiceResources();
        } else if (message.type === "session.closed") {
          releaseVoiceResources();
          setVoicePartial("");
          socket.close();
        }
      };
      socket.onerror = () => {
        setVoiceError("VOICE-003（实时语音连接失败）");
        releaseVoiceResources();
      };
      socket.onclose = () => {
        transcriptionSocketRef.current = null;
        releaseVoiceResources();
      };
    } catch (error) {
      releaseVoiceResources();
      transcriptionSocketRef.current?.close();
      transcriptionSocketRef.current = null;
      setVoiceError(
        error instanceof DOMException &&
          (error.name === "NotAllowedError" ||
            error.name === "SecurityError")
          ? "VOICE-002（无法访问麦克风）"
          : "VOICE-003（实时语音转文字启动失败）",
      );
    }
  }

  function submitMessage(event: FormEvent) {
    event.preventDefault();
    send(draft);
  }

  const conversationWorkbar = (
    <aside
      className={`agent-conversation-workbar ${
        conversationPanelOpen ? "is-open" : ""
      }`}
      aria-label="对话列表"
    >
      <div className="agent-workbar-heading">
        <div>
          <span className="eyebrow">Agent</span>
          <strong>会话</strong>
        </div>
        <div>
          <button
            className="icon-button agent-workbar-close"
            type="button"
            onClick={() => setConversationPanelOpen(false)}
            aria-label="关闭会话列表"
          >
            <IconX size={17} />
          </button>
          <button
            className="icon-button"
            type="button"
            onClick={() => createConversation.mutate()}
            disabled={createConversation.isPending || isAgentBusy}
            aria-label="新建对话"
            title="新建对话"
          >
            <IconPlus size={18} />
          </button>
        </div>
      </div>

      <label className="agent-conversation-search">
        <IconSearch size={16} aria-hidden="true" />
        <span className="sr-only">搜索对话</span>
        <input
          type="search"
          value={conversationSearch}
          onChange={(event) => setConversationSearch(event.target.value)}
          placeholder="搜索对话"
        />
      </label>

      <div className="agent-conversation-scopes" aria-label="会话范围">
        <button
          className={conversationScope === "active" ? "active" : ""}
          type="button"
          onClick={() => setConversationScope("active")}
        >
          <IconMessage size={15} />
          最近
        </button>
        <button
          className={conversationScope === "archived" ? "active" : ""}
          type="button"
          onClick={() => setConversationScope("archived")}
        >
          <IconHistory size={15} />
          已归档
        </button>
      </div>

      {conversationActionError && (
        <p className="agent-workbar-error" role="alert">
          {conversationActionError}
        </p>
      )}

      <div className="agent-conversation-list">
        {conversationList.isLoading && (
          <p className="agent-conversation-empty">正在读取会话…</p>
        )}
        {conversationList.isError && (
          <p className="agent-workbar-error" role="alert">
            无法读取会话列表。
          </p>
        )}
        {!conversationList.isLoading &&
          !conversationList.isError &&
          visibleConversationGroups.length === 0 && (
            <div className="agent-conversation-empty">
              <IconMessage size={20} />
              <strong>
                {conversationSearch
                  ? "没有匹配的会话"
                  : conversationScope === "archived"
                    ? "暂无归档会话"
                    : "暂无会话"}
              </strong>
              {!conversationSearch && conversationScope === "active" && (
                <button
                  className="text-button"
                  type="button"
                  onClick={() => createConversation.mutate()}
                  disabled={createConversation.isPending}
                >
                  <IconPlus size={15} />
                  新建对话
                </button>
              )}
            </div>
          )}
        {visibleConversationGroups.map((group) => (
          <section className="agent-conversation-group" key={group.label}>
            <h2>{group.label}</h2>
            {group.conversations.map((item) => {
              const isActive = item.id === activeConversationId;
              const isRenaming = item.id === renamingConversationId;
              const actionDisabled =
                isAgentBusy ||
                createConversation.isPending ||
                conversationAction.isPending;
              return (
                <article
                  className={`agent-conversation-item ${
                    isActive ? "is-active" : ""
                  }`}
                  key={item.id}
                >
                  {isRenaming ? (
                    <form
                      className="agent-conversation-rename"
                      onSubmit={(event) => submitRename(event, item)}
                    >
                      <input
                        autoFocus
                        aria-label="会话名称"
                        value={renameDraft}
                        onChange={(event) => setRenameDraft(event.target.value)}
                        maxLength={160}
                      />
                      <button
                        className="icon-button"
                        type="submit"
                        aria-label="保存名称"
                        disabled={!renameDraft.trim() || actionDisabled}
                      >
                        <IconCheck size={15} />
                      </button>
                      <button
                        className="icon-button"
                        type="button"
                        onClick={() => setRenamingConversationId("")}
                        aria-label="取消重命名"
                      >
                        <IconX size={15} />
                      </button>
                    </form>
                  ) : (
                    <>
                      <button
                        className="agent-conversation-select"
                        type="button"
                        onClick={() => activateConversation(item.id)}
                        disabled={isAgentBusy}
                        aria-current={isActive ? "true" : undefined}
                      >
                        <IconMessage size={16} aria-hidden="true" />
                        <span>
                          <strong title={item.title}>{item.title}</strong>
                          <small>{conversationTimeLabel(item)}</small>
                        </span>
                        {item.unread && (
                          <i aria-label="有未读消息" title="有未读消息" />
                        )}
                      </button>
                      <div className="agent-conversation-actions">
                        {conversationScope === "active" && (
                          <>
                            <button
                              className="icon-button"
                              type="button"
                              onClick={() =>
                                conversationAction.mutate({
                                  kind: "pin",
                                  conversation: item,
                                })
                              }
                              aria-label={`${item.pinned_at ? "取消置顶" : "置顶"} ${item.title}`}
                              title={item.pinned_at ? "取消置顶" : "置顶"}
                              disabled={actionDisabled}
                            >
                              {item.pinned_at ? (
                                <IconPinnedOff size={15} />
                              ) : (
                                <IconPin size={15} />
                              )}
                            </button>
                            <button
                              className="icon-button"
                              type="button"
                              onClick={() => beginRename(item)}
                              aria-label={`重命名 ${item.title}`}
                              title="重命名"
                              disabled={actionDisabled}
                            >
                              <IconEdit size={15} />
                            </button>
                            <button
                              className="icon-button"
                              type="button"
                              onClick={() =>
                                conversationAction.mutate({
                                  kind: "archive",
                                  conversation: item,
                                })
                              }
                              aria-label={`归档 ${item.title}`}
                              title="归档"
                              disabled={actionDisabled}
                            >
                              <IconArchive size={15} />
                            </button>
                          </>
                        )}
                        {conversationScope === "archived" && (
                          <button
                            className="icon-button"
                            type="button"
                            onClick={() =>
                              conversationAction.mutate({
                                kind: "restore",
                                conversation: item,
                              })
                            }
                            aria-label={`恢复 ${item.title}`}
                            title="恢复"
                            disabled={actionDisabled}
                          >
                            <IconArrowBackUp size={15} />
                          </button>
                        )}
                        <button
                          className="icon-button is-danger"
                          type="button"
                          onClick={() =>
                            conversationAction.mutate({
                              kind: "delete",
                              conversation: item,
                            })
                          }
                          aria-label={`删除 ${item.title}`}
                          title="删除"
                          disabled={actionDisabled}
                        >
                          <IconTrash size={15} />
                        </button>
                      </div>
                    </>
                  )}
                </article>
              );
            })}
          </section>
        ))}
      </div>
    </aside>
  );

  const automationAside = (
    <>
      <div className="aside-title">
        <div>
          <span className="eyebrow">快捷控制</span>
          <h2>任务控制</h2>
        </div>
        <button className="icon-button" onClick={() => setAsideOpen(false)}>
          <IconX size={18} />
          <span className="sr-only">关闭</span>
        </button>
      </div>
      <section className="aside-section">
        <div className="section-heading">
          <h3>可运行任务</h3>
          <span>{tasks.data?.length ?? 0}</span>
        </div>
        <div className="plan-list">
          {tasks.data?.map((task: CollectionTask) => (
            <div className="plan-card" key={task.id}>
              <button
                className="plan-run"
                onClick={() => runTask.mutate(task.id)}
                disabled={runTask.isPending}
              >
                <IconPlayerPlay size={16} />
                <span>
                  <strong>{task.name}</strong>
                  <small>
                    {task.config.time_window.lookback_hours} 小时 ·{" "}
                    {task.config.quantity.min_items}–
                    {task.config.quantity.max_items} 条
                  </small>
                </span>
              </button>
              <Link
                className="icon-button"
                href="/tasks"
                aria-label={`编辑 ${task.name}`}
              >
                <IconSettingsAutomation size={16} />
              </Link>
            </div>
          ))}
        </div>
      </section>
      <section className="aside-section">
        <div className="section-heading">
          <h3>已启用调度</h3>
          <span>{activeTasks.length}</span>
        </div>
        {activeTasks.map((task: CollectionTask) => (
          <div className="task-row" key={task.id}>
            <IconClock size={17} />
            <span>
              <strong>{task.name}</strong>
              <small>
                {task.config.schedule.mode === "manual"
                  ? "仅手动"
                  : `${task.config.schedule.mode} ${task.config.schedule.time_of_day}`}
              </small>
            </span>
          </div>
        ))}
        <Link className="secondary-button aside-task-link" href="/tasks">
          <IconSettingsAutomation size={17} />
          管理任务配置
        </Link>
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
            className="secondary-button agent-conversation-toggle"
            type="button"
            onClick={() => setConversationPanelOpen(true)}
            aria-label="打开会话列表"
            aria-expanded={conversationPanelOpen}
          >
            <IconMessage size={18} />
            会话
          </button>
          <button
            className="secondary-button"
            type="button"
            onClick={() => setAsideOpen((value) => !value)}
          >
            <IconSettingsAutomation size={18} />
            任务控制
          </button>
        </div>
      </header>
      <div className="agent-conversation-layout">
        {conversationWorkbar}
        {conversationPanelOpen && (
          <button
            className="agent-conversation-scrim"
            type="button"
            onClick={() => setConversationPanelOpen(false)}
            aria-label="关闭会话列表"
          />
        )}
        <section className="conversation">
          <div
            className="conversation-thread"
            ref={conversationThreadRef}
            onScroll={(event) => {
              if (!activeConversationId) return;
              writeSessionValue(
                `${SCROLL_STORAGE_PREFIX}${activeConversationId}`,
                String(event.currentTarget.scrollTop),
              );
            }}
            aria-live="polite"
          >
            {!conversation.isLoading &&
              (conversation.data?.messages.length ?? 0) === 0 && (
                <div className="conversation-intro">
                  <span className="agent-orb">
                    <IconRobot size={25} />
                  </span>
                  <h2>今天想了解什么？</h2>
                  <p>直接说“采集最新信息”或“查询 LangGraph”。</p>
                </div>
              )}
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
                {message.task_draft && (
                  <div className="agent-task-draft">
                    <div>
                      <IconSettingsAutomation size={17} />
                      <strong>{message.task_draft.name}</strong>
                    </div>
                    <p>{message.task_draft.goal}</p>
                    <dl>
                      <div>
                        <dt>数量</dt>
                        <dd>
                          {message.task_draft.config.quantity.min_items}–
                          {message.task_draft.config.quantity.max_items} 条
                        </dd>
                      </div>
                      <div>
                        <dt>调度</dt>
                        <dd>
                          {message.task_draft.config.schedule.time_of_day}
                        </dd>
                      </div>
                      <div>
                        <dt>摘要</dt>
                        <dd>
                          {message.task_draft.config.delivery.summary_max_chars} 字
                        </dd>
                      </div>
                    </dl>
                    <div className="agent-task-actions">
                      <Link className="secondary-button" href="/tasks">
                        打开任务工作台
                      </Link>
                      <button
                        className="primary-button"
                        onClick={() =>
                          createTask.mutate({
                            messageId: message.id,
                            input: message.task_draft!,
                          })
                        }
                        disabled={
                          createTask.isPending ||
                          createdDraftMessages.has(message.id)
                        }
                      >
                        {createdDraftMessages.has(message.id)
                          ? "已创建"
                          : createTask.isPending
                            ? "创建中"
                            : "确认并启用"}
                      </button>
                    </div>
                  </div>
                )}
                {isAgentTurnResult(message.result) && (
                  <>
                    <AgentTurnProgress
                      status={message.result.status}
                      plan={message.result.plan}
                      elapsedMs={message.result.total_duration_ms}
                    />
                    <AgentResultBlocks
                      blocks={message.result.result_blocks}
                      onRetry={
                        message.turn_id &&
                        message.result.retryable_errors.length > 0
                          ? () => resumeTurn.mutate(message.turn_id!)
                          : undefined
                      }
                    />
                  </>
                )}
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
          {activeTurn && (
            <div className="message message-assistant">
              <span className="message-avatar">
                <IconRobot size={17} />
              </span>
              <div className="message-content">
                <AgentTurnProgress
                  status={activeTurn.status}
                  plan={
                    "steps" in activeTurn.plan
                      ? (activeTurn.plan as AgentPlan)
                      : undefined
                  }
                  events={turnEvents}
                  elapsedMs={turnElapsedMs}
                  onStop={
                    activeTurn.id &&
                    !["complete", "partial", "failed", "cancelled"].includes(
                      activeTurn.status,
                    )
                      ? () => cancelTurn.mutate(activeTurn.id)
                      : undefined
                  }
                />
                {activeTurn.requested_model_id && (
                  <small className="agent-model-runtime">
                    请求模型：{activeTurn.requested_model_id}
                    {activeTurn.effective_model_id
                      ? ` · 实际模型：${activeTurn.effective_model_id}`
                      : " · 正在确认实际模型"}
                  </small>
                )}
                {streamedResultBlocks.length > 0 && (
                  <AgentResultBlocks blocks={streamedResultBlocks} />
                )}
              </div>
            </div>
          )}
          {sendError && !isAgentBusy && (
            <div className="message message-assistant">
              <span className="message-avatar">
                <IconRobot size={17} />
              </span>
              <div className="message-content">
                <p>{sendError}</p>
              </div>
            </div>
          )}
          {researchTurn.isPending && !activeTurn && (
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
          {(isListening || voicePartial) && (
            <div className="voice-transcript-status" role="status">
              <span>{isListening ? "正在聆听" : "正在整理"}</span>
              {voicePartial && <em>{voicePartial}</em>}
            </div>
          )}
          <textarea
            value={draft}
            onChange={(event) => {
              const value = event.target.value;
              setDraft(value);
              const conversationId =
                activeConversationIdRef.current || activeConversationId;
              if (conversationId) {
                writeDraft(conversationId, value);
              }
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder={
              conversationWritable
                ? "向 Workspace Agent 发送消息…"
                : conversationScope === "archived"
                  ? "恢复会话后可继续发送"
                  : "正在准备新会话…"
            }
            disabled={!conversationWritable}
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
                onClick={() => void toggleVoiceInput()}
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
                  onChange={(event) => {
                    const modelId = event.target.value;
                    setSelectedModelIds((current) => ({
                      ...current,
                      [activeConversationId]: modelId,
                    }));
                    if (activeConversationId) {
                      writeLocalValue(
                        `${MODEL_STORAGE_PREFIX}${activeConversationId}`,
                        modelId,
                      );
                    }
                  }}
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
                  isAgentBusy ||
                  conversation.isLoading ||
                  !conversationWritable
                }
                aria-label="发送"
              >
                <IconSend2 size={19} />
              </button>
            </div>
          </div>
        </form>
        </section>
      </div>
      {deletedConversation && (
        <div className="agent-undo-toast" role="status">
          <span>已删除“{deletedConversation.title}”</span>
          <button
            className="text-button"
            type="button"
            onClick={undoDelete}
            disabled={conversationAction.isPending}
            aria-label="撤销删除"
          >
            <IconArrowBackUp size={15} />
            撤销
          </button>
          <button
            className="icon-button"
            type="button"
            onClick={() => setDeletedConversation(null)}
            aria-label="关闭撤销提示"
          >
            <IconX size={15} />
          </button>
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

function groupConversations(
  conversations: AgentConversationSummary[],
  search: string,
  scope: AgentConversationScope,
): ConversationGroup[] {
  const normalizedSearch = search.trim().toLocaleLowerCase("zh-CN");
  const filtered = normalizedSearch
    ? conversations.filter((conversation) =>
        conversation.title
          .toLocaleLowerCase("zh-CN")
          .includes(normalizedSearch),
      )
    : conversations;
  if (scope === "archived") {
    return filtered.length
      ? [{ label: "已归档", conversations: filtered }]
      : [];
  }

  const groups: ConversationGroup[] = [];
  const pinned: AgentConversationSummary[] = [];
  const today: AgentConversationSummary[] = [];
  const recent: AgentConversationSummary[] = [];
  const earlier: AgentConversationSummary[] = [];
  const now = new Date();
  const todayKey = localDateKey(now);
  const recentBoundary = now.getTime() - 7 * 24 * 60 * 60 * 1000;

  for (const conversation of filtered) {
    if (conversation.pinned_at) {
      pinned.push(conversation);
      continue;
    }
    const timestamp = new Date(
      conversation.last_message_at ?? conversation.updated_at,
    );
    if (localDateKey(timestamp) === todayKey) {
      today.push(conversation);
    } else if (timestamp.getTime() >= recentBoundary) {
      recent.push(conversation);
    } else {
      earlier.push(conversation);
    }
  }

  if (pinned.length) groups.push({ label: "置顶", conversations: pinned });
  if (today.length) groups.push({ label: "今天", conversations: today });
  if (recent.length) groups.push({ label: "最近 7 天", conversations: recent });
  if (earlier.length) groups.push({ label: "更早", conversations: earlier });
  return groups;
}

function conversationTimeLabel(
  conversation: AgentConversationSummary,
): string {
  const timestamp = new Date(
    conversation.last_message_at ?? conversation.updated_at,
  );
  if (Number.isNaN(timestamp.getTime())) return "暂无消息";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(timestamp);
}

function localDateKey(value: Date): string {
  if (Number.isNaN(value.getTime())) return "";
  return `${value.getFullYear()}-${value.getMonth()}-${value.getDate()}`;
}

function readDraft(conversationId: string): string {
  if (!conversationId || typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(
      `${DRAFT_STORAGE_PREFIX}${conversationId}`,
    ) ?? "";
  } catch {
    return "";
  }
}

function writeDraft(conversationId: string, value: string) {
  if (!conversationId || typeof window === "undefined") return;
  try {
    if (value) {
      window.localStorage.setItem(
        `${DRAFT_STORAGE_PREFIX}${conversationId}`,
        value,
      );
    } else {
      window.localStorage.removeItem(
        `${DRAFT_STORAGE_PREFIX}${conversationId}`,
      );
    }
  } catch {
    // The composer remains usable when browser storage is unavailable.
  }
}

function removeDraft(conversationId: string) {
  writeDraft(conversationId, "");
}

function readScrollPosition(conversationId: string): number | null {
  const value = readSessionValue(
    `${SCROLL_STORAGE_PREFIX}${conversationId}`,
  );
  if (value === null) return null;
  const position = Number(value);
  return Number.isFinite(position) ? position : null;
}

function readSessionValue(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeSessionValue(key: string, value: string) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    // Scroll restoration is a progressive enhancement.
  }
}

function readLocalValue(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeLocalValue(key: string, value: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Model selection remains usable for the current render.
  }
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error
    ? reason.message
    : "SYS-001（会话操作失败）";
}

function isAgentTurnResult(
  value: AgentMessage["result"],
): value is AgentTurnResult {
  return (
    typeof value === "object" &&
    value !== null &&
    "result_blocks" in value &&
    Array.isArray(value.result_blocks) &&
    "plan" in value
  );
}

function isAgentResultBlock(
  value: unknown,
): value is AgentResultBlock {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.block_id === "string" &&
    typeof record.type === "string" &&
    typeof record.title === "string" &&
    typeof record.data === "object" &&
    record.data !== null
  );
}

function capabilityLabel(capabilityId: string): string {
  const labels: Record<string, string> = {
    "collection.run.start": "采集 AI 信息",
    "web.search.collect": "按需联网补证",
    "intelligence.timeline.query": "查询 AI 信息",
    "intelligence.search": "统一检索 AI 信息",
    "intelligence.recommend": "推荐 AI 信息",
    "research.filter": "筛选 AI 信息",
    "research.recommend": "推荐 AI 信息",
    "research.match_requirements": "匹配研究要求",
    "research.compare": "比较 Agent 框架",
    "research.trend_brief": "整理趋势",
    "research.coverage_gap": "分析覆盖缺口",
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
    skipped: "未执行",
  };
  return labels[status] ?? status;
}
