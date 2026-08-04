"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IconArrowRight,
  IconCheck,
  IconClockPause,
  IconExternalLink,
  IconSparkles,
  IconTrash,
} from "@tabler/icons-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { StatusMark } from "@/components/status-mark";
import {
  api,
  ReviewDecision,
  ReviewItem,
} from "@/lib/api";

type Draft = {
  decision: ReviewDecision | null;
  editedTitle: string;
  editedSummary: string;
  note: string;
};

function initialDraft(item: ReviewItem): Draft {
  return {
    decision: item.decision,
    editedTitle: item.edited_title ?? item.title,
    editedSummary: item.edited_summary ?? item.summary,
    note: item.note,
  };
}

const decisions: {
  value: ReviewDecision;
  label: string;
  icon: typeof IconCheck;
}[] = [
  { value: "keep", label: "保留", icon: IconCheck },
  { value: "reject", label: "排除", icon: IconTrash },
  { value: "defer", label: "稍后", icon: IconClockPause },
];

export function ReviewScreen() {
  const queryClient = useQueryClient();
  const review = useQuery({
    queryKey: ["review", "current"],
    queryFn: api.currentReview,
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const items = useMemo(() => review.data?.items ?? [], [review.data?.items]);
  const effectiveDrafts = useMemo(
    () =>
      Object.fromEntries(
        items.map((item) => [
          item.id,
          drafts[item.id] ?? initialDraft(item),
        ]),
      ),
    [drafts, items],
  );
  const effectiveSelectedId = selectedId ?? items[0]?.id ?? null;
  const selected =
    items.find((item) => item.id === effectiveSelectedId) ?? null;
  const selectedDraft = selected ? effectiveDrafts[selected.id] : null;
  const decidedCount = useMemo(
    () => items.filter((item) => effectiveDrafts[item.id]?.decision).length,
    [effectiveDrafts, items],
  );
  const submit = useMutation({
    mutationFn: () =>
      api.submitReview(
        review.data!.id,
        items.map((item) => ({
          item_id: item.id,
          decision: effectiveDrafts[item.id].decision!,
          edited_title:
            effectiveDrafts[item.id].editedTitle === item.title
              ? null
              : effectiveDrafts[item.id].editedTitle,
          edited_summary:
            effectiveDrafts[item.id].editedSummary === item.summary
              ? null
              : effectiveDrafts[item.id].editedSummary,
          note: effectiveDrafts[item.id].note,
        })),
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["review"] }),
  });

  function updateDraft(itemId: string, patch: Partial<Draft>) {
    const item = items.find((candidate) => candidate.id === itemId);
    if (!item) return;
    setDrafts((current) => ({
      ...current,
      [itemId]: {
        ...(current[itemId] ?? initialDraft(item)),
        ...patch,
      },
    }));
  }

  function applySuggestion() {
    setDrafts((current) =>
      Object.fromEntries(
        items.map((item) => [
          item.id,
          {
            ...(current[item.id] ?? initialDraft(item)),
            decision: item.priority === "normal" ? "defer" : "keep",
          },
        ]),
      ),
    );
  }

  return (
    <AppShell>
      <header className="topbar">
        <div>
          <span className="eyebrow">编辑工作台</span>
          <h1>审核</h1>
        </div>
        <div className="topbar-actions">
          <span className="review-progress">
            {decidedCount}/{items.length} 已决定
          </span>
          <button className="secondary-button" onClick={applySuggestion}>
            <IconSparkles size={17} />
            应用 Agent 建议
          </button>
          {review.data?.status === "completed" ? (
            <Link className="primary-button" href="/cards">
              前往卡片
              <IconArrowRight size={17} />
            </Link>
          ) : (
            <button
              className="primary-button"
              disabled={
                !items.length ||
                decidedCount !== items.length ||
                submit.isPending
              }
              onClick={() => submit.mutate()}
            >
              <IconCheck size={17} />
              {submit.isPending ? "确认中" : "确认决定"}
            </button>
          )}
        </div>
      </header>

      {review.isLoading && (
        <div className="empty-state">正在准备审核批次…</div>
      )}
      {review.isError && (
        <div className="empty-state error-state">无法读取审核批次。</div>
      )}
      {!review.isLoading && items.length === 0 && (
        <div className="empty-state">
          <strong>没有待审核信息</strong>
          <span>先在 AI 信息页完成一次采集。</span>
          <Link className="secondary-button" href="/timeline">
            返回 AI 信息
          </Link>
        </div>
      )}

      {items.length > 0 && (
        <div className="review-layout">
          <section className="review-queue" aria-label="待审核信息">
            <div className="review-queue-heading">
              <strong>本批信息</strong>
              <span>{items.length} 条</span>
            </div>
            {items.map((item) => {
              const draft = effectiveDrafts[item.id];
              return (
                <button
                  key={item.id}
                  className={`review-row ${
                    effectiveSelectedId === item.id ? "selected" : ""
                  }`}
                  onClick={() => setSelectedId(item.id)}
                >
                  <span className="review-row-meta">
                    <StatusMark priority={item.priority} />
                    <time>
                      {new Date(item.published_at).toLocaleTimeString("zh-CN", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </time>
                  </span>
                  <strong>{draft?.editedTitle ?? item.title}</strong>
                  <small>{item.source_name}</small>
                  <span className="review-actions">
                    {decisions.map(({ value, label, icon: Icon }) => (
                      <span
                        key={value}
                        role="button"
                        tabIndex={0}
                        className={draft?.decision === value ? "active" : ""}
                        onClick={(event) => {
                          event.stopPropagation();
                          updateDraft(item.id, { decision: value });
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            updateDraft(item.id, { decision: value });
                          }
                        }}
                        aria-label={`${label}：${item.title}`}
                      >
                        <Icon size={14} />
                        {label}
                      </span>
                    ))}
                  </span>
                </button>
              );
            })}
          </section>

          {selected && selectedDraft && (
            <aside className="review-inspector" aria-label="审核详情">
              <div className="review-inspector-heading">
                <div>
                  <span className="eyebrow">{selected.source_name}</span>
                  <h2>校对信息</h2>
                </div>
                <a
                  className="icon-button"
                  href={selected.canonical_url}
                  target="_blank"
                  rel="noreferrer"
                  aria-label="打开原文"
                >
                  <IconExternalLink size={18} />
                </a>
              </div>
              <label>
                标题
                <textarea
                  rows={3}
                  value={selectedDraft.editedTitle}
                  onChange={(event) =>
                    updateDraft(selected.id, {
                      editedTitle: event.target.value,
                    })
                  }
                />
              </label>
              <label>
                摘要
                <textarea
                  rows={7}
                  value={selectedDraft.editedSummary}
                  onChange={(event) =>
                    updateDraft(selected.id, {
                      editedSummary: event.target.value,
                    })
                  }
                />
              </label>
              <label>
                备注
                <textarea
                  rows={3}
                  value={selectedDraft.note}
                  placeholder="可选，仅保存在审核记录中"
                  onChange={(event) =>
                    updateDraft(selected.id, { note: event.target.value })
                  }
                />
              </label>
              <div className="review-decision-bar">
                {decisions.map(({ value, label, icon: Icon }) => (
                  <button
                    key={value}
                    className={
                      selectedDraft.decision === value ? "selected" : ""
                    }
                    onClick={() =>
                      updateDraft(selected.id, { decision: value })
                    }
                  >
                    <Icon size={16} />
                    {label}
                  </button>
                ))}
              </div>
            </aside>
          )}
        </div>
      )}
    </AppShell>
  );
}
