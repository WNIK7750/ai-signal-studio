"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  IconAdjustments,
  IconCheck,
  IconChevronDown,
  IconChevronRight,
  IconArchive,
  IconEye,
  IconExternalLink,
  IconBookmarkPlus,
  IconRefresh,
  IconSearch,
  IconStar,
  IconX,
} from "@tabler/icons-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusMark } from "@/components/status-mark";
import { api, SourceKind, TimelineItem } from "@/lib/api";
import { Priority } from "@/lib/priority";
import {
  localDateKey,
  shouldCollapseTimelineDay,
  timelineDayLabel,
} from "./timeline-utils";

const priorityOptions: { value: Priority | ""; label: string }[] = [
  { value: "", label: "全部" },
  { value: "important", label: "重要" },
  { value: "watch", label: "关注" },
  { value: "normal", label: "普通" },
];

export function TimelineScreen() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState<Priority | "">("");
  const [sourceKind, setSourceKind] = useState<SourceKind | "">("");
  const [quickView, setQuickView] = useState<
    "all" | "today" | "unread" | "starred"
  >("all");
  const [asideOpen, setAsideOpen] = useState(true);
  const [collapsedDays, setCollapsedDays] = useState<Record<string, boolean>>(
    () => {
      if (typeof window === "undefined") return {};
      try {
        const stored = window.localStorage.getItem(
          "ai-signal-timeline:collapsed:v1",
        );
        return stored ? JSON.parse(stored) : {};
      } catch {
        return {};
      }
    },
  );
  const [selectedItem, setSelectedItem] = useState<TimelineItem | null>(null);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      if (window.matchMedia("(max-width: 820px)").matches) {
        setAsideOpen(false);
      }
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  const params = useMemo(() => {
    const value = new URLSearchParams();
    value.set("archived", "false");
    if (search.trim()) value.set("search", search.trim());
    if (priority) value.set("priority", priority);
    if (sourceKind) value.set("source_kind", sourceKind);
    if (quickView === "unread") value.set("seen", "false");
    if (quickView === "starred") value.set("starred", "true");
    if (quickView === "today") {
      const start = new Date();
      start.setHours(0, 0, 0, 0);
      value.set("published_from", start.toISOString());
    }
    return value;
  }, [priority, quickView, search, sourceKind]);
  const timeline = useInfiniteQuery({
    queryKey: ["timeline", params.toString()],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const pageParams = new URLSearchParams(params);
      pageParams.set("limit", "30");
      if (pageParam) pageParams.set("cursor", pageParam);
      return api.timeline(pageParams);
    },
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.next_cursor : undefined,
  });
  const {
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = timeline;
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const savedViews = useQuery({
    queryKey: ["saved-views"],
    queryFn: api.savedViews,
  });
  const collect = useMutation({
    mutationFn: api.collect,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["timeline"] }),
        queryClient.invalidateQueries({ queryKey: ["runs"] }),
      ]),
  });
  const updateState = useMutation({
    mutationFn: ({
      itemId,
      input,
    }: {
      itemId: string;
      input: { seen?: boolean; starred?: boolean; archived?: boolean };
    }) => api.updateInformationState(itemId, input),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["timeline"] }),
  });
  const saveView = useMutation({
    mutationFn: () =>
      api.createSavedView({
        name: `信息视图 ${new Date().toLocaleDateString("zh-CN")}`,
        query: Object.fromEntries(params.entries()),
        display: { mode: "timeline" },
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["saved-views"] }),
  });
  const timelineItems = useMemo(
    () => timeline.data?.pages.flatMap((page) => page.items) ?? [],
    [timeline.data?.pages],
  );
  const grouped = useMemo(() => {
    const groups = new Map<string, TimelineItem[]>();
    for (const item of timelineItems) {
      const key = localDateKey(item.published_at);
      groups.set(key, [...(groups.get(key) ?? []), item]);
    }
    return [...groups.entries()];
  }, [timelineItems]);
  const total = timeline.data?.pages[0]?.total ?? 0;

  useEffect(() => {
    const url = new URL(window.location.href);
    for (const key of [
      "archived",
      "search",
      "priority",
      "source_kind",
      "seen",
      "starred",
      "published_from",
    ]) {
      url.searchParams.delete(key);
    }
    params.forEach((value, key) => url.searchParams.set(key, value));
    window.history.replaceState(null, "", url);
  }, [params]);

  useEffect(() => {
    const node = loadMoreRef.current;
    if (!node || !hasNextPage) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !isFetchingNextPage) {
          void fetchNextPage();
        }
      },
      { rootMargin: "240px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  ]);

  useEffect(() => {
    const focusId = new URLSearchParams(window.location.search).get("focus");
    if (!focusId) return;
    const focused = timelineItems.find((item) => item.id === focusId);
    if (!focused) {
      if (hasNextPage && !isFetchingNextPage) {
        void fetchNextPage();
      }
      return;
    }
    const frame = requestAnimationFrame(() => {
      setSelectedItem(focused);
      const key = localDateKey(focused.published_at);
      setCollapsedDays((current) => ({ ...current, [key]: false }));
      document
        .querySelector(`[data-information-id="${CSS.escape(focusId)}"]`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    return () => cancelAnimationFrame(frame);
  }, [
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    timelineItems,
  ]);

  function toggleDay(key: string) {
    setCollapsedDays((current) => {
      const next = {
        ...current,
        [key]:
          current[key] === undefined
            ? !shouldCollapseTimelineDay(key)
            : !current[key],
      };
      window.localStorage.setItem(
        "ai-signal-timeline:collapsed:v1",
        JSON.stringify(next),
      );
      return next;
    });
  }
  const latestRun = runs.data?.[0];
  const activeFilterCount =
    Number(Boolean(priority)) +
    Number(Boolean(sourceKind)) +
    Number(quickView !== "all");

  const filterAside = (
    <>
      <div className="aside-title">
        <div>
          <span className="eyebrow">视图设置</span>
          <h2>筛选</h2>
        </div>
        <button className="icon-button" onClick={() => setAsideOpen(false)}>
          <IconX size={18} />
          <span className="sr-only">关闭筛选</span>
        </button>
      </div>
      <fieldset className="filter-group">
        <legend>信息标识</legend>
        {priorityOptions.map((option) => (
          <label key={option.label} className="radio-row">
            <input
              type="radio"
              name="priority"
              checked={priority === option.value}
              onChange={() => setPriority(option.value)}
            />
            {option.value ? <StatusMark priority={option.value} /> : "全部"}
          </label>
        ))}
      </fieldset>
      <fieldset className="filter-group">
        <legend>来源类型</legend>
        {[
          ["", "全部来源"],
          ["rss", "RSS"],
          ["github_releases", "GitHub Releases"],
          ["demo", "示例来源"],
        ].map(([value, label]) => (
          <label key={value} className="radio-row">
            <input
              type="radio"
              name="source"
              checked={sourceKind === value}
              onChange={() => setSourceKind(value as SourceKind | "")}
            />
            {label}
          </label>
        ))}
      </fieldset>
      <button
        className="text-button aside-reset"
        onClick={() => {
          setPriority("");
          setSourceKind("");
        }}
      >
        <IconRefresh size={17} />
        重置筛选
      </button>
    </>
  );

  return (
    <AppShell
      aside={filterAside}
      asideOpen={asideOpen}
      onAsideToggle={() => setAsideOpen((value) => !value)}
    >
      <header className="topbar">
        <div>
          <span className="eyebrow">工作台</span>
          <h1>AI 信息</h1>
        </div>
        <div className="topbar-actions">
          <div className="search-box">
            <IconSearch size={19} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索标题、摘要或来源"
              aria-label="搜索 AI 信息"
            />
          </div>
          <button
            className="secondary-button filter-button"
            onClick={() => setAsideOpen((value) => !value)}
          >
            <IconAdjustments size={18} />
            筛选
            {activeFilterCount > 0 && (
              <span className="count-badge">{activeFilterCount}</span>
            )}
          </button>
          <button
            className="primary-button"
            onClick={() => collect.mutate()}
            disabled={collect.isPending}
          >
            <IconRefresh
              size={18}
              className={collect.isPending ? "spinning" : ""}
            />
            {collect.isPending ? "采集中" : "立即采集"}
          </button>
        </div>
      </header>

      <section className="content-frame">
        <div className="information-viewbar">
          <div className="quick-views" aria-label="快捷视图">
            {(
              [
                ["all", "全部"],
                ["today", "今天"],
                ["unread", "未读"],
                ["starred", "已收藏"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                className={quickView === value ? "active" : ""}
                onClick={() => setQuickView(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="saved-view-strip">
            {savedViews.data?.slice(0, 3).map((view) => (
              <button
                key={view.id}
                onClick={() => {
                  const query = view.query;
                  setSearch(typeof query.search === "string" ? query.search : "");
                  setPriority(
                    typeof query.priority === "string"
                      ? (query.priority as Priority)
                      : "",
                  );
                  setSourceKind(
                    typeof query.source_kind === "string"
                      ? (query.source_kind as SourceKind)
                      : "",
                  );
                  setQuickView(
                    query.starred === "true"
                      ? "starred"
                      : query.seen === "false"
                        ? "unread"
                        : "all",
                  );
                }}
              >
                {view.name}
              </button>
            ))}
            <button
              className="save-view-button"
              onClick={() => saveView.mutate()}
              disabled={saveView.isPending}
            >
              <IconBookmarkPlus size={15} />
              保存当前视图
            </button>
          </div>
        </div>

        <div className="run-summary">
          <span className="success-icon">
            <IconCheck size={15} />
          </span>
          <strong>
            {latestRun
              ? latestRun.execution_status === "failed"
                ? "上次采集失败"
                : latestRun.coverage_status === "met"
                  ? "采集完成 · 覆盖达标"
                  : "采集完成 · 覆盖未达标"
              : "准备就绪"}
          </strong>
          <span>
            {latestRun
              ? `新增 ${latestRun.items_added} 条 · 共 ${total} 条`
              : "点击立即采集获取最新内容"}
          </span>
          <time>
            {latestRun?.completed_at
              ? new Date(latestRun.completed_at).toLocaleTimeString("zh-CN", {
                  hour: "2-digit",
                  minute: "2-digit",
                })
              : "本地工作区"}
          </time>
          <IconChevronDown size={17} />
        </div>

        {timeline.isLoading && <div className="empty-state">正在读取 AI 信息…</div>}
        {timeline.isError && (
          <div className="empty-state error-state">
            无法连接本地服务，请先启动 API。
          </div>
        )}
        {!timeline.isLoading && grouped.length === 0 && (
          <div className="empty-state">
            <span className="empty-glyph">◎</span>
            <strong>还没有匹配的信息</strong>
            <span>采集一次，或清空筛选后再看。</span>
          </div>
        )}

        <div className="timeline">
          {grouped.map(([dayKey, items]) => {
            const isCollapsed =
              collapsedDays[dayKey] ??
              shouldCollapseTimelineDay(dayKey);
            const unreadCount = items.filter((item) => !item.seen).length;
            const importantCount = items.filter(
              (item) => item.priority === "important",
            ).length;
            return (
            <section key={dayKey} className="timeline-day">
              <h2>
                <button
                  className="timeline-day-toggle"
                  onClick={() => toggleDay(dayKey)}
                  aria-expanded={!isCollapsed}
                >
                  {isCollapsed ? (
                    <IconChevronRight size={17} />
                  ) : (
                    <IconChevronDown size={17} />
                  )}
                  <span>{timelineDayLabel(dayKey)}</span>
                  <small>
                    {items.length} 条 · {unreadCount} 未读
                    {importantCount > 0 ? ` · ${importantCount} 重要` : ""}
                  </small>
                </button>
              </h2>
              {!isCollapsed && items.map((item) => (
                <article
                  key={item.id}
                  className={`timeline-item ${
                    selectedItem?.id === item.id ? "is-focused" : ""
                  }`}
                  data-information-id={item.id}
                >
                  <div className="timeline-rail">
                    <StatusMark priority={item.priority} compact />
                  </div>
                  <time className="item-time">
                    {new Date(item.published_at).toLocaleTimeString("zh-CN", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </time>
                  <div className="item-body">
                    <div className="item-meta">
                      <span>{item.source_name}</span>
                      <StatusMark priority={item.priority} />
                    </div>
                    <h3>
                      <button
                        className="timeline-title-button"
                        onClick={() => {
                          setSelectedItem(item);
                          if (!item.seen) {
                            updateState.mutate({
                              itemId: item.id,
                              input: { seen: true },
                            });
                          }
                        }}
                      >
                        {item.title}
                      </button>
                    </h3>
                    <p>{item.summary}</p>
                    <div className="tag-row">
                      {item.topics.slice(0, 3).map((topic) => (
                        <span key={topic}>{topic}</span>
                      ))}
                    </div>
                  </div>
                  <div className="item-actions">
                    <button
                      className={item.seen ? "active" : ""}
                      onClick={() =>
                        updateState.mutate({
                          itemId: item.id,
                          input: { seen: !item.seen },
                        })
                      }
                      aria-label={item.seen ? "标记为未读" : "标记为已读"}
                      title={item.seen ? "标记为未读" : "标记为已读"}
                    >
                      <IconEye size={17} />
                    </button>
                    <button
                      className={item.starred ? "active starred" : ""}
                      onClick={() =>
                        updateState.mutate({
                          itemId: item.id,
                          input: { starred: !item.starred },
                        })
                      }
                      aria-label={item.starred ? "取消收藏" : "收藏"}
                      title={item.starred ? "取消收藏" : "收藏"}
                    >
                      <IconStar size={17} />
                    </button>
                    <button
                      onClick={() =>
                        updateState.mutate({
                          itemId: item.id,
                          input: { archived: true },
                        })
                      }
                      aria-label="归档"
                      title="归档"
                    >
                      <IconArchive size={17} />
                    </button>
                    <a
                      href={item.canonical_url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={() =>
                        updateState.mutate({
                          itemId: item.id,
                          input: { seen: true },
                        })
                      }
                      aria-label={`打开 ${item.title}`}
                      title="打开原文"
                    >
                      <IconExternalLink size={17} />
                    </a>
                  </div>
                </article>
              ))}
            </section>
          )})}
          <div ref={loadMoreRef} className="timeline-load-more">
            {hasNextPage && (
              <button
                className="secondary-button"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
              >
                {isFetchingNextPage ? "正在加载…" : "加载更多"}
              </button>
            )}
          </div>
        </div>
        {selectedItem && (
          <aside className="information-detail-panel" aria-label="信息详情">
            <div className="information-detail-title">
              <div>
                <span className="eyebrow">{selectedItem.source_name}</span>
                <h2>{selectedItem.title}</h2>
              </div>
              <button
                className="icon-button"
                onClick={() => setSelectedItem(null)}
                aria-label="关闭信息详情"
              >
                <IconX size={18} />
              </button>
            </div>
            <p>{selectedItem.summary}</p>
            <div className="tag-row">
              {selectedItem.topics.map((topic) => (
                <span key={topic}>{topic}</span>
              ))}
            </div>
            <a
              className="primary-button"
              href={selectedItem.canonical_url}
              target="_blank"
              rel="noreferrer"
            >
              <IconExternalLink size={17} />
              打开原文
            </a>
          </aside>
        )}
      </section>
    </AppShell>
  );
}
