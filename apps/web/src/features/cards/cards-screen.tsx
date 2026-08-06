"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IconAdjustments,
  IconCalendarMonth,
  IconChevronLeft,
  IconChevronRight,
  IconCheck,
  IconDownload,
  IconEdit,
  IconExternalLink,
  IconLayoutSidebarLeftCollapse,
  IconRefresh,
  IconX,
} from "@tabler/icons-react";
import { useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusMark } from "@/components/status-mark";
import {
  api,
  artifactContentUrl,
  CardItem,
  PosterWorkflow,
  SourceKind,
} from "@/lib/api";
import { Priority } from "@/lib/priority";
import { buildMonthDays, monthValue } from "./date-tabs";

const priorities: { value: Priority | ""; label: string }[] = [
  { value: "", label: "全部标识" },
  { value: "important", label: "重要" },
  { value: "watch", label: "关注" },
  { value: "normal", label: "普通" },
];

function CoverSurface({
  card,
  detail = false,
}: {
  card: CardItem;
  detail?: boolean;
}) {
  const className = `${detail ? "card-detail-cover" : "browse-card-cover"} ${
    card.cover_url
      ? "cover-original"
      : `cover-template cover-color-${card.cover_variant} ${
          card.cover_variant % 2 === 0 ? "cover-quote" : "cover-note"
        }`
  }`;
  if (card.cover_url) {
    return (
      <span
        className={className}
        role="img"
        aria-label={`${card.title}封面`}
        style={{ backgroundImage: `url("${card.cover_url}")` }}
      />
    );
  }
  return (
    <span className={className} role="img" aria-label={`${card.title}文字封面`}>
      {card.cover_variant % 2 === 0 && (
        <span className="cover-quote-mark" aria-hidden="true">
          “
        </span>
      )}
      <span className="cover-title">{card.title}</span>
      {card.cover_variant % 2 === 1 && (
        <span className="cover-marker" aria-hidden="true" />
      )}
      <span className="cover-signature" aria-hidden="true">
        AI SIGNAL
      </span>
    </span>
  );
}

export function CardsScreen() {
  const queryClient = useQueryClient();
  const today = useMemo(() => new Date(), []);
  const [month, setMonth] = useState(monthValue(today));
  const [day, setDay] = useState("");
  const [priority, setPriority] = useState<Priority | "">("");
  const [sourceKind, setSourceKind] = useState<SourceKind | "">("");
  const [topic, setTopic] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [maxChars, setMaxChars] = useState(400);
  const [posterWorkflow, setPosterWorkflow] =
    useState<PosterWorkflow | null>(null);
  const [editing, setEditing] = useState(false);
  const [editDraft, setEditDraft] = useState<{
    title: string;
    summary: string;
    keyPoints: string;
    templateId: CardItem["template_id"];
    coverSource: CardItem["cover_source"];
  } | null>(null);
  const tabsRef = useRef<HTMLDivElement>(null);
  const days = useMemo(() => buildMonthDays(month), [month]);
  const params = useMemo(() => {
    const value = new URLSearchParams();
    if (day) value.set("day", day);
    else value.set("month", month);
    if (priority) value.set("priority", priority);
    if (sourceKind) value.set("source_kind", sourceKind);
    if (topic) value.set("topic", topic);
    return value;
  }, [day, month, priority, sourceKind, topic]);
  const cards = useQuery({
    queryKey: ["cards", params.toString()],
    queryFn: () => api.cards(params),
  });
  const allCards = useQuery({
    queryKey: ["cards", "all"],
    queryFn: () => api.cards(),
  });
  const generate = useMutation({
    mutationFn: () => api.startPosterWorkflow(maxChars),
    onSuccess: setPosterWorkflow,
  });
  const resumePoster = useMutation({
    mutationFn: (approved: boolean) =>
      api.resumePosterWorkflow(posterWorkflow!.thread_id, approved),
    onSuccess: async (result) => {
      setPosterWorkflow(result);
      setDay("");
      await queryClient.invalidateQueries({ queryKey: ["cards"] });
      setSelectedId((current) => current ?? result.card_ids[0] ?? null);
      if (result.status !== "waiting_approval") {
        setPosterWorkflow(null);
      }
    },
  });
  const updateCard = useMutation({
    mutationFn: () =>
      api.updateCard(selected!.id, {
        expected_revision: selected!.revision,
        title: editDraft!.title,
        summary: editDraft!.summary,
        key_points: editDraft!.keyPoints
          .split("\n")
          .map((value) => value.trim())
          .filter(Boolean),
        template_id: editDraft!.templateId,
        cover_source: editDraft!.coverSource,
      }),
    onSuccess: async () => {
      setEditing(false);
      setEditDraft(null);
      await queryClient.invalidateQueries({ queryKey: ["cards"] });
    },
  });
  const renderOne = useMutation({
    mutationFn: (cardId: string) => api.renderCard(cardId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["cards"] }),
  });
  const items = cards.data?.items ?? [];
  const selected =
    items.find((item) => item.id === selectedId) ??
    allCards.data?.items.find((item) => item.id === selectedId) ??
    null;
  const topics = useMemo(
    () => [
      ...new Set((allCards.data?.items ?? []).flatMap((card) => card.topics)),
    ],
    [allCards.data?.items],
  );

  function changeMonth(value: string) {
    setMonth(value);
    const currentMonth = monthValue(today);
    setDay(
      value === currentMonth
        ? `${value}-${String(today.getDate()).padStart(2, "0")}`
        : `${value}-01`,
    );
  }

  function scrollDates(direction: number) {
    tabsRef.current?.scrollBy({ left: direction * 320, behavior: "smooth" });
  }

  return (
    <AppShell>
      <header className="cards-topbar">
        <div className="cards-title">
          <span className="eyebrow">编辑精选</span>
          <h1>卡片</h1>
        </div>
        <button
          className="icon-button"
          onClick={() => scrollDates(-1)}
          aria-label="向前滚动日期"
        >
          <IconChevronLeft size={18} />
        </button>
        <div className="date-tabs" ref={tabsRef} aria-label="按日期浏览">
          {days.map((tab) => (
            <button
              key={tab.iso}
              className={day === tab.iso ? "selected" : ""}
              onClick={() => setDay(tab.iso)}
            >
              <span>{tab.weekday}</span>
              <strong>{tab.day}</strong>
            </button>
          ))}
        </div>
        <button
          className="icon-button"
          onClick={() => scrollDates(1)}
          aria-label="向后滚动日期"
        >
          <IconChevronRight size={18} />
        </button>
        <label className="month-picker">
          <IconCalendarMonth size={18} />
          <span className="sr-only">选择月份</span>
          <input
            type="month"
            value={month}
            onChange={(event) => changeMonth(event.target.value)}
          />
        </label>
      </header>

      <div
        className={`cards-layout ${filtersOpen ? "" : "filters-collapsed"} ${
          selected ? "detail-open" : ""
        }`}
      >
        {posterWorkflow?.interrupt?.phase ===
          "confirm_draft_generation" && (
          <div className="modal-backdrop">
            <div
              className="modal poster-confirm-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="poster-confirm-title"
            >
              <span className="eyebrow">Poster Graph</span>
              <h2 id="poster-confirm-title">确认生成卡片草稿？</h2>
              <p>{posterWorkflow.interrupt.message}</p>
              <div>
                <button
                  className="secondary-button"
                  onClick={() => {
                    resumePoster.mutate(false);
                    setPosterWorkflow(null);
                  }}
                >
                  取消
                </button>
                <button
                  className="primary-button"
                  onClick={() => resumePoster.mutate(true)}
                  disabled={resumePoster.isPending}
                >
                  <IconCheck size={16} />
                  生成草稿
                </button>
              </div>
            </div>
          </div>
        )}
        <aside className="cards-filters" aria-label="卡片筛选">
          <div className="cards-filter-heading">
            <strong>筛选</strong>
            <button
              className="icon-button"
              onClick={() => setFiltersOpen(false)}
              aria-label="收起卡片筛选"
            >
              <IconLayoutSidebarLeftCollapse size={18} />
            </button>
          </div>
          <fieldset>
            <legend>信息标识</legend>
            {priorities.map((option) => (
              <label key={option.label}>
                <input
                  type="radio"
                  name="card-priority"
                  checked={priority === option.value}
                  onChange={() => setPriority(option.value)}
                />
                {option.value ? (
                  <StatusMark priority={option.value} />
                ) : (
                  option.label
                )}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>来源</legend>
            {[
              ["", "全部来源"],
              ["demo", "示例来源"],
              ["rss", "RSS"],
              ["github_releases", "GitHub Releases"],
            ].map(([value, label]) => (
              <label key={value}>
                <input
                  type="radio"
                  name="card-source"
                  checked={sourceKind === value}
                  onChange={() => setSourceKind(value as SourceKind | "")}
                />
                {label}
              </label>
            ))}
          </fieldset>
          {topics.length > 0 && (
            <fieldset>
              <legend>主题</legend>
              <label>
                <input
                  type="radio"
                  name="card-topic"
                  checked={!topic}
                  onChange={() => setTopic("")}
                />
                全部主题
              </label>
              {topics.map((value) => (
                <label key={value}>
                  <input
                    type="radio"
                    name="card-topic"
                    checked={topic === value}
                    onChange={() => setTopic(value)}
                  />
                  {value}
                </label>
              ))}
            </fieldset>
          )}
          <button
            className="text-button"
            onClick={() => {
              setPriority("");
              setSourceKind("");
              setTopic("");
            }}
          >
            <IconRefresh size={16} />
            重置
          </button>
        </aside>

        <main className="cards-main">
          <div className="cards-toolbar">
            {!filtersOpen && (
              <button
                className="secondary-button"
                onClick={() => setFiltersOpen(true)}
              >
                <IconAdjustments size={17} />
                筛选
              </button>
            )}
            <button className="date-all" onClick={() => setDay("")}>
              {day ? "查看整月" : "正在查看整月"}
            </button>
            <label className="summary-length">
              详情上限
              <input
                type="range"
                min={100}
                max={1000}
                step={50}
                value={maxChars}
                onChange={(event) => setMaxChars(Number(event.target.value))}
              />
              <output>{maxChars} 字</output>
            </label>
            <button
              className="primary-button"
              onClick={() => generate.mutate()}
              disabled={generate.isPending}
            >
              <IconRefresh
                size={17}
                className={generate.isPending ? "spinning" : ""}
              />
              {generate.isPending ? "生成中" : "生成卡片"}
            </button>
          </div>
          {posterWorkflow?.interrupt?.phase === "confirm_render" && (
            <div className="poster-render-banner" role="status">
              <div>
                <strong>草稿已保存</strong>
                <span>可先编辑卡片，再确认批量渲染 PNG。</span>
              </div>
              <button
                className="primary-button"
                onClick={() => resumePoster.mutate(true)}
                disabled={resumePoster.isPending}
              >
                <IconDownload size={16} />
                确认渲染
              </button>
            </div>
          )}

          {cards.isLoading && (
            <div className="empty-state">正在读取卡片…</div>
          )}
          {cards.isError && (
            <div className="empty-state error-state">无法读取卡片。</div>
          )}
          {!cards.isLoading && !items.length && (
            <div className="empty-state cards-empty">
              <strong>这一天还没有卡片</strong>
              <span>选择其他日期，或将审核通过的信息整理为卡片。</span>
            </div>
          )}
          <section className="card-masonry" aria-label="卡片浏览">
            {items.map((card) => (
              <button
                key={card.id}
                className={`browse-card ${
                  selectedId === card.id ? "selected" : ""
                }`}
                onClick={() => setSelectedId(card.id)}
              >
                <CoverSurface card={card} />
                <strong>{card.title}</strong>
                <span className="browse-card-footer">
                  <span>{card.source_name}</span>
                  <StatusMark priority={card.priority} />
                </span>
              </button>
            ))}
          </section>
        </main>

        {selected && (
          <aside className="card-detail" aria-label="卡片详情">
            <div className="card-detail-heading">
              <span className="eyebrow">信息详情</span>
              <button
                className="icon-button"
                onClick={() => setSelectedId(null)}
                aria-label="关闭卡片详情"
              >
                <IconX size={18} />
              </button>
            </div>
            <CoverSurface card={selected} detail />
            {editing && editDraft ? (
              <form
                className="card-edit-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  updateCard.mutate();
                }}
              >
                <label>
                  标题
                  <input
                    value={editDraft.title}
                    onChange={(event) =>
                      setEditDraft({
                        ...editDraft,
                        title: event.target.value,
                      })
                    }
                    maxLength={500}
                    required
                  />
                </label>
                <label>
                  摘要（100～1000 字）
                  <textarea
                    value={editDraft.summary}
                    onChange={(event) =>
                      setEditDraft({
                        ...editDraft,
                        summary: event.target.value,
                      })
                    }
                    minLength={100}
                    maxLength={1000}
                    required
                  />
                </label>
                <label>
                  要点（每行一条）
                  <textarea
                    value={editDraft.keyPoints}
                    onChange={(event) =>
                      setEditDraft({
                        ...editDraft,
                        keyPoints: event.target.value,
                      })
                    }
                    required
                  />
                </label>
                <label>
                  模板
                  <select
                    value={editDraft.templateId}
                    onChange={(event) =>
                      setEditDraft({
                        ...editDraft,
                        templateId: event.target
                          .value as CardItem["template_id"],
                      })
                    }
                  >
                    <option value="offline-quote">引语底板</option>
                    <option value="offline-grid">网格底板</option>
                    {selected.cover_url && (
                      <option value="source-cover">来源封面</option>
                    )}
                  </select>
                </label>
                <div>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => setEditing(false)}
                  >
                    取消
                  </button>
                  <button
                    className="primary-button"
                    type="submit"
                    disabled={updateCard.isPending}
                  >
                    保存编辑
                  </button>
                </div>
              </form>
            ) : (
              <>
                <div className="card-detail-title-row">
                  <h2>{selected.title}</h2>
                  <button
                    className="icon-button"
                    onClick={() => {
                      setEditDraft({
                        title: selected.title,
                        summary: selected.summary,
                        keyPoints: selected.key_points.join("\n"),
                        templateId: selected.template_id,
                        coverSource: selected.cover_source,
                      });
                      setEditing(true);
                    }}
                    aria-label={`编辑 ${selected.title}`}
                  >
                    <IconEdit size={17} />
                  </button>
                </div>
            <div className="card-detail-meta">
              <span>{selected.source_name}</span>
              <time>
                {new Date(selected.published_at).toLocaleString("zh-CN", {
                  month: "long",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </time>
              <StatusMark priority={selected.priority} />
            </div>
            <p className="card-detail-summary">{selected.summary}</p>
            <section className="card-key-points">
              <h3>快速了解</h3>
              <ul>
                {selected.key_points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </section>
            <div className="tag-row">
              {selected.topics.map((value) => (
                <span key={value}>{value}</span>
              ))}
            </div>
            {selected.rendered_artifact_id ? (
              <a
                className="secondary-button"
                href={artifactContentUrl(selected.rendered_artifact_id)}
                download
              >
                <IconDownload size={16} />
                下载 PNG
              </a>
            ) : (
              <button
                className="secondary-button"
                onClick={() => renderOne.mutate(selected.id)}
                disabled={renderOne.isPending}
              >
                <IconDownload size={16} />
                渲染当前卡片
              </button>
            )}
            <a
              className="primary-button card-source-link"
              href={selected.canonical_url}
              target="_blank"
              rel="noreferrer"
            >
              查看原始信息
              <IconExternalLink size={17} />
            </a>
              </>
            )}
          </aside>
        )}
      </div>
    </AppShell>
  );
}
