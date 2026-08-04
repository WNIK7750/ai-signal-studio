"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IconAdjustments,
  IconCheck,
  IconChevronDown,
  IconExternalLink,
  IconRefresh,
  IconSearch,
  IconX,
} from "@tabler/icons-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusMark } from "@/components/status-mark";
import { api, SourceKind, TimelineItem } from "@/lib/api";
import { Priority } from "@/lib/priority";

const priorityOptions: { value: Priority | ""; label: string }[] = [
  { value: "", label: "全部" },
  { value: "important", label: "重要" },
  { value: "watch", label: "关注" },
  { value: "normal", label: "普通" },
];

function dayLabel(value: string) {
  const date = new Date(value);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return "今天";
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return "昨天";
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
}

export function TimelineScreen() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState<Priority | "">("");
  const [sourceKind, setSourceKind] = useState<SourceKind | "">("");
  const [asideOpen, setAsideOpen] = useState(true);
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
    if (search.trim()) value.set("search", search.trim());
    if (priority) value.set("priority", priority);
    if (sourceKind) value.set("source_kind", sourceKind);
    return value;
  }, [priority, search, sourceKind]);
  const timeline = useQuery({
    queryKey: ["timeline", params.toString()],
    queryFn: () => api.timeline(params),
  });
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const collect = useMutation({
    mutationFn: api.collect,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["timeline"] }),
        queryClient.invalidateQueries({ queryKey: ["runs"] }),
      ]),
  });
  const timelineItems = timeline.data?.items;
  const grouped = useMemo(() => {
    const groups = new Map<string, TimelineItem[]>();
    for (const item of timelineItems ?? []) {
      const label = dayLabel(item.published_at);
      groups.set(label, [...(groups.get(label) ?? []), item]);
    }
    return [...groups.entries()];
  }, [timelineItems]);
  const latestRun = runs.data?.[0];
  const activeFilterCount = Number(Boolean(priority)) + Number(Boolean(sourceKind));

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
        <div className="run-summary">
          <span className="success-icon">
            <IconCheck size={15} />
          </span>
          <strong>{latestRun ? "采集已完成" : "准备就绪"}</strong>
          <span>
            {latestRun
              ? `新增 ${latestRun.items_added} 条 · 共 ${timeline.data?.total ?? 0} 条`
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
          {grouped.map(([label, items]) => (
            <section key={label} className="timeline-day">
              <h2>{label}</h2>
              {items.map((item) => (
                <article key={item.id} className="timeline-item">
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
                    <h3>{item.title}</h3>
                    <p>{item.summary}</p>
                    <div className="tag-row">
                      {item.topics.slice(0, 3).map((topic) => (
                        <span key={topic}>{topic}</span>
                      ))}
                    </div>
                  </div>
                  <a
                    className="item-open"
                    href={item.canonical_url}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={`打开 ${item.title}`}
                  >
                    <IconExternalLink size={18} />
                  </a>
                </article>
              ))}
            </section>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
