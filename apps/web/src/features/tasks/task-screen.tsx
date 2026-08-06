"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IconBolt,
  IconCheck,
  IconChevronDown,
  IconClock,
  IconFilter,
  IconPlayerPlay,
  IconPlus,
  IconRefresh,
  IconSearch,
  IconStack2,
} from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import {
  api,
  CollectionTask,
  CollectionTaskWrite,
  TaskConfig,
} from "@/lib/api";

const defaultConfig: TaskConfig = {
  sources: {
    mode: "all_enabled",
    include_ids: [],
    exclude_ids: [],
    required_ids: [],
    fallback_ids: [],
    per_source_max_items: 20,
  },
  matching: {
    topics: ["AI"],
    include_any: [],
    include_all: [],
    exclude: [],
    search_scope: "title_and_content",
    languages: ["zh", "en"],
  },
  time_window: {
    mode: "rolling",
    lookback_hours: 24,
    overlap_hours: 2,
    timezone: "Asia/Shanghai",
  },
  quantity: {
    min_items: 5,
    target_items: 10,
    max_items: 30,
  },
  importance: {
    accepted_levels: ["important", "watch", "normal"],
  },
  quality_requirements: {
    require_source_link: true,
    prefer_primary_source: true,
    allow_unknown_publish_time: false,
    require_extractable_content: true,
  },
  deduplication: {
    mode: "balanced",
    window_days: 31,
    across_runs: true,
    preserve_related_sources: true,
  },
  schedule: {
    mode: "manual",
    time_of_day: "09:00",
    weekdays: [],
    interval_hours: null,
  },
  delivery: {
    destination: "task_view",
    notify_when: "important_or_problem",
    summary_max_chars: 400,
  },
};

function newDraft(): CollectionTaskWrite {
  return {
    name: "每日 AI 信息",
    goal: "持续收集值得阅读的 AI 产品、模型与 Agent 进展。",
    status: "draft",
    pinned: true,
    config: structuredClone(defaultConfig),
  };
}

function copyTask(task: CollectionTask): CollectionTaskWrite {
  return {
    name: task.name,
    goal: task.goal,
    status: task.status,
    pinned: task.pinned,
    config: structuredClone(task.config),
  };
}

function splitTerms(value: string) {
  return value
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function TaskStatus({ status }: { status: CollectionTask["status"] }) {
  const labels = {
    draft: "草稿",
    enabled: "运行中",
    paused: "已暂停",
    archived: "已归档",
  };
  return <span className={`task-status status-${status}`}>{labels[status]}</span>;
}

export function TaskScreen() {
  const queryClient = useQueryClient();
  const tasks = useQuery({
    queryKey: ["collection-tasks"],
    queryFn: api.collectionTasks,
  });
  const sources = useQuery({ queryKey: ["sources"], queryFn: api.sources });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<CollectionTaskWrite>(newDraft);
  const [sourceSearch, setSourceSearch] = useState("");
  const [notice, setNotice] = useState("");

  const selectedTask = tasks.data?.find((task) => task.id === selectedId);

  const save = useMutation({
    mutationFn: async (status?: CollectionTaskWrite["status"]) => {
      const payload = { ...draft, status: status ?? draft.status };
      return selectedId
        ? api.updateCollectionTask(selectedId, {
            ...payload,
            change_note: "在任务工作台更新",
          })
        : api.createCollectionTask(payload);
    },
    onSuccess: async (task) => {
      setSelectedId(task.id);
      setDraft(copyTask(task));
      setNotice("任务已保存");
      await queryClient.invalidateQueries({ queryKey: ["collection-tasks"] });
    },
  });

  const preview = useMutation({
    mutationFn: async () => {
      let taskId = selectedId;
      if (!taskId) {
        const created = await api.createCollectionTask(draft);
        taskId = created.id;
        setSelectedId(created.id);
        await queryClient.invalidateQueries({ queryKey: ["collection-tasks"] });
      }
      return api.previewCollectionTask(taskId, draft.config);
    },
    onSuccess: () => setNotice("试运行完成，没有写入信息库"),
  });

  const run = useMutation({
    mutationFn: async () => {
      const task = await save.mutateAsync("enabled");
      return api.runCollectionTask(task.id);
    },
    onSuccess: async (result) => {
      setNotice(
        result.coverage_status === "met"
          ? `运行完成，新增 ${result.items_added} 条`
          : `运行完成，新增 ${result.items_added} 条，覆盖未达目标`,
      );
      await queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  const visibleSources = useMemo(
    () =>
      (sources.data ?? []).filter((source) =>
        source.name.toLowerCase().includes(sourceSearch.toLowerCase()),
      ),
    [sourceSearch, sources.data],
  );

  function patchConfig<K extends keyof TaskConfig>(
    key: K,
    value: TaskConfig[K],
  ) {
    setDraft((current) => ({
      ...current,
      config: { ...current.config, [key]: value },
    }));
  }

  function selectTask(task: CollectionTask) {
    setSelectedId(task.id);
    setDraft(copyTask(task));
    setNotice("");
    preview.reset();
  }

  function toggleSource(sourceId: string) {
    const current = draft.config.sources.include_ids;
    const includeIds = current.includes(sourceId)
      ? current.filter((id) => id !== sourceId)
      : [...current, sourceId];
    patchConfig("sources", {
      ...draft.config.sources,
      mode: "selected",
      include_ids: includeIds,
    });
  }

  const funnel = preview.data?.funnel_counts;
  const sourceCount =
    draft.config.sources.mode === "all_enabled"
      ? sources.data?.filter((source) => source.enabled).length ?? 0
      : draft.config.sources.include_ids.length;

  return (
    <AppShell>
      <header className="topbar task-topbar">
        <div>
          <span className="eyebrow">自动信息流</span>
          <h1>任务</h1>
        </div>
        <div className="topbar-actions">
          {notice && <span className="inline-notice">{notice}</span>}
          <button
            className="secondary-button"
            onClick={() => preview.mutate()}
            disabled={preview.isPending}
          >
            <IconFilter size={17} />
            {preview.isPending ? "试运行中" : "试运行"}
          </button>
          <button
            className="primary-button"
            onClick={() => run.mutate()}
            disabled={run.isPending}
          >
            <IconPlayerPlay size={17} />
            {run.isPending ? "运行中" : "保存并运行"}
          </button>
          <button
            className="secondary-button"
            onClick={() => {
              setSelectedId(null);
              setDraft(newDraft());
              preview.reset();
            }}
          >
            <IconPlus size={17} />
            新建任务
          </button>
        </div>
      </header>

      <div className="task-workbench">
        <aside className="task-library" aria-label="任务列表">
          <div className="task-library-heading">
            <strong>我的任务</strong>
            <span>{tasks.data?.length ?? 0}</span>
          </div>
          {tasks.isLoading && <p className="muted-copy">正在读取任务…</p>}
          {tasks.data?.map((task) => (
            <button
              key={task.id}
              className={`task-list-item ${
                selectedId === task.id ? "active" : ""
              }`}
              onClick={() => selectTask(task)}
            >
              <span className="task-list-icon">
                <IconStack2 size={17} />
              </span>
              <span>
                <strong>{task.name}</strong>
                <small>
                  {task.next_run_at
                    ? `下次 ${new Date(task.next_run_at).toLocaleString("zh-CN", {
                        month: "numeric",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}`
                    : "仅手动运行"}
                </small>
              </span>
              <TaskStatus status={task.status} />
            </button>
          ))}
          {!tasks.isLoading && !tasks.data?.length && (
            <div className="task-library-empty">
              <IconBolt size={20} />
              <strong>从第一个任务开始</strong>
              <span>把来源、筛选和时间收进同一套配置。</span>
            </div>
          )}
          <button
            className="task-new-row"
            onClick={() => {
              setSelectedId(null);
              setDraft(newDraft());
            }}
          >
            <IconPlus size={16} />
            新建任务
          </button>
        </aside>

        <main className="task-editor">
          <div className="task-title-fields">
            <input
              className="task-name-input"
              value={draft.name}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  name: event.target.value,
                }))
              }
              aria-label="任务名称"
            />
            <textarea
              value={draft.goal}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  goal: event.target.value,
                }))
              }
              rows={2}
              maxLength={500}
              aria-label="任务目标"
            />
          </div>

          <section className="task-section">
            <div className="task-section-heading">
              <span>01</span>
              <div>
                <h2>信息来源</h2>
                <p>决定去哪里找，以及单个来源最多取多少条。</p>
              </div>
              <IconChevronDown size={18} />
            </div>
            <div className="task-section-body">
              <div className="segmented-control">
                <button
                  className={
                    draft.config.sources.mode === "all_enabled" ? "active" : ""
                  }
                  onClick={() =>
                    patchConfig("sources", {
                      ...draft.config.sources,
                      mode: "all_enabled",
                    })
                  }
                >
                  全部已启用
                </button>
                <button
                  className={
                    draft.config.sources.mode === "selected" ? "active" : ""
                  }
                  onClick={() =>
                    patchConfig("sources", {
                      ...draft.config.sources,
                      mode: "selected",
                    })
                  }
                >
                  指定来源
                </button>
              </div>
              {draft.config.sources.mode === "selected" && (
                <>
                  <label className="compact-search">
                    <IconSearch size={16} />
                    <input
                      value={sourceSearch}
                      onChange={(event) => setSourceSearch(event.target.value)}
                      placeholder="查找来源"
                    />
                  </label>
                  <div className="source-choice-list">
                    {visibleSources.map((source) => (
                      <label key={source.id}>
                        <input
                          type="checkbox"
                          checked={draft.config.sources.include_ids.includes(
                            source.id,
                          )}
                          onChange={() => toggleSource(source.id)}
                        />
                        <span className={`health-dot ${source.health_status}`} />
                        <span>{source.name}</span>
                        <small>{source.enabled ? "已启用" : "已停用"}</small>
                      </label>
                    ))}
                  </div>
                </>
              )}
              <label className="field-row">
                <span>单个来源上限</span>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={draft.config.sources.per_source_max_items}
                  onChange={(event) =>
                    patchConfig("sources", {
                      ...draft.config.sources,
                      per_source_max_items: Number(event.target.value),
                    })
                  }
                />
                <small>条</small>
              </label>
            </div>
          </section>

          <section className="task-section">
            <div className="task-section-heading">
              <span>02</span>
              <div>
                <h2>匹配规则</h2>
                <p>先用少量明确词语缩小范围，后续可逐步调整。</p>
              </div>
              <IconChevronDown size={18} />
            </div>
            <div className="task-section-body task-form-grid">
              <label className="field-stack">
                <span>主题</span>
                <input
                  value={draft.config.matching.topics.join("，")}
                  onChange={(event) =>
                    patchConfig("matching", {
                      ...draft.config.matching,
                      topics: splitTerms(event.target.value),
                    })
                  }
                  placeholder="Agent，模型，AI Coding"
                />
              </label>
              <label className="field-stack">
                <span>包含任一关键词</span>
                <input
                  value={draft.config.matching.include_any.join("，")}
                  onChange={(event) =>
                    patchConfig("matching", {
                      ...draft.config.matching,
                      include_any: splitTerms(event.target.value),
                    })
                  }
                  placeholder="release，发布，更新"
                />
              </label>
              <label className="field-stack">
                <span>排除词</span>
                <input
                  value={draft.config.matching.exclude.join("，")}
                  onChange={(event) =>
                    patchConfig("matching", {
                      ...draft.config.matching,
                      exclude: splitTerms(event.target.value),
                    })
                  }
                  placeholder="招聘，广告"
                />
              </label>
              <label className="field-stack">
                <span>搜索范围</span>
                <select
                  value={draft.config.matching.search_scope}
                  onChange={(event) =>
                    patchConfig("matching", {
                      ...draft.config.matching,
                      search_scope: event.target.value as
                        | "title"
                        | "title_and_content",
                    })
                  }
                >
                  <option value="title_and_content">标题和内容</option>
                  <option value="title">仅标题</option>
                </select>
              </label>
            </div>
          </section>

          <section className="task-section">
            <div className="task-section-heading">
              <span>03</span>
              <div>
                <h2>时间与数量</h2>
                <p>数量是结果覆盖目标，不是信息质量分数。</p>
              </div>
              <IconChevronDown size={18} />
            </div>
            <div className="task-section-body">
              <div className="task-form-grid">
                <label className="field-stack">
                  <span>回看范围</span>
                  <select
                    value={draft.config.time_window.lookback_hours}
                    onChange={(event) =>
                      patchConfig("time_window", {
                        ...draft.config.time_window,
                        lookback_hours: Number(event.target.value),
                      })
                    }
                  >
                    <option value={12}>过去 12 小时</option>
                    <option value={24}>过去 24 小时</option>
                    <option value={72}>过去 3 天</option>
                    <option value={168}>过去 7 天</option>
                  </select>
                </label>
                <label className="field-stack">
                  <span>时区</span>
                  <select
                    value={draft.config.time_window.timezone}
                    onChange={(event) =>
                      patchConfig("time_window", {
                        ...draft.config.time_window,
                        timezone: event.target.value,
                      })
                    }
                  >
                    <option value="Asia/Shanghai">Asia/Shanghai</option>
                    <option value="UTC">UTC</option>
                  </select>
                </label>
              </div>
              <div className="quantity-grid">
                {(
                  [
                    ["min_items", "最少"],
                    ["target_items", "目标"],
                    ["max_items", "最多"],
                  ] as const
                ).map(([key, label]) => (
                  <label key={key}>
                    <span>{label}</span>
                    <input
                      type="number"
                      min={key === "max_items" ? 1 : 0}
                      max={500}
                      value={draft.config.quantity[key]}
                      onChange={(event) =>
                        patchConfig("quantity", {
                          ...draft.config.quantity,
                          [key]: Number(event.target.value),
                        })
                      }
                    />
                    <small>条</small>
                  </label>
                ))}
              </div>
            </div>
          </section>

          <section className="task-section">
            <div className="task-section-heading">
              <span>04</span>
              <div>
                <h2>调度与交付</h2>
                <p>先决定何时运行，再决定信息进入哪个工作区。</p>
              </div>
              <IconChevronDown size={18} />
            </div>
            <div className="task-section-body task-form-grid">
              <label className="field-stack">
                <span>运行方式</span>
                <select
                  value={draft.config.schedule.mode}
                  onChange={(event) =>
                    patchConfig("schedule", {
                      ...draft.config.schedule,
                      mode: event.target.value as TaskConfig["schedule"]["mode"],
                    })
                  }
                >
                  <option value="manual">仅手动</option>
                  <option value="daily">每天</option>
                  <option value="weekdays">工作日</option>
                  <option value="weekly">每周</option>
                  <option value="interval">按间隔</option>
                </select>
              </label>
              <label className="field-stack">
                <span>运行时间</span>
                <input
                  type="time"
                  value={draft.config.schedule.time_of_day}
                  disabled={draft.config.schedule.mode === "manual"}
                  onChange={(event) =>
                    patchConfig("schedule", {
                      ...draft.config.schedule,
                      time_of_day: event.target.value,
                    })
                  }
                />
              </label>
              <label className="field-stack">
                <span>交付位置</span>
                <select
                  value={draft.config.delivery.destination}
                  onChange={(event) =>
                    patchConfig("delivery", {
                      ...draft.config.delivery,
                      destination: event.target.value as
                        | "task_view"
                        | "timeline"
                        | "review",
                    })
                  }
                >
                  <option value="task_view">任务结果</option>
                  <option value="timeline">AI 信息</option>
                  <option value="review">待处理</option>
                </select>
              </label>
              <label className="field-stack">
                <span>摘要最大字数</span>
                <input
                  type="number"
                  min={100}
                  max={1000}
                  value={draft.config.delivery.summary_max_chars}
                  onChange={(event) =>
                    patchConfig("delivery", {
                      ...draft.config.delivery,
                      summary_max_chars: Number(event.target.value),
                    })
                  }
                />
              </label>
            </div>
          </section>

          <div className="task-editor-actions">
            <span>
              {save.isError || preview.isError || run.isError
                ? (save.error ?? preview.error ?? run.error)?.message
                : selectedTask
                  ? `版本 ${selectedTask.version_number ?? "—"}`
                  : "尚未保存"}
            </span>
            <button
              className="secondary-button"
              onClick={() => save.mutate(undefined)}
              disabled={save.isPending}
            >
              <IconCheck size={17} />
              保存草稿
            </button>
            <button
              className="secondary-button"
              onClick={() => preview.mutate()}
              disabled={preview.isPending}
            >
              <IconFilter size={17} />
              {preview.isPending ? "试运行中" : "试运行"}
            </button>
            <button
              className="primary-button"
              onClick={() => run.mutate()}
              disabled={run.isPending}
            >
              <IconPlayerPlay size={17} />
              {run.isPending ? "运行中" : "保存并运行"}
            </button>
          </div>
        </main>

        <aside className="task-inspector" aria-label="任务摘要">
          <div className="task-inspector-heading">
            <span className="eyebrow">即时摘要</span>
            <h2>任务会怎样运行</h2>
          </div>
          <dl className="task-summary-list">
            <div>
              <dt>来源</dt>
              <dd>{sourceCount} 个</dd>
            </div>
            <div>
              <dt>时间范围</dt>
              <dd>{draft.config.time_window.lookback_hours} 小时</dd>
            </div>
            <div>
              <dt>目标结果</dt>
              <dd>
                {draft.config.quantity.min_items}–{draft.config.quantity.max_items} 条
              </dd>
            </div>
            <div>
              <dt>运行</dt>
              <dd>
                {draft.config.schedule.mode === "manual"
                  ? "手动"
                  : `${draft.config.schedule.time_of_day} · ${
                      draft.config.time_window.timezone
                    }`}
              </dd>
            </div>
          </dl>

          <div className="task-rule-summary">
            <h3>匹配摘要</h3>
            <p>
              {draft.config.matching.topics.length
                ? draft.config.matching.topics.join("、")
                : "未限定主题"}
            </p>
            <small>
              {draft.config.matching.exclude.length
                ? `排除：${draft.config.matching.exclude.join("、")}`
                : "未设置排除词"}
            </small>
          </div>

          <div className="preview-panel">
            <div>
              <IconRefresh size={17} />
              <h3>试运行结果</h3>
            </div>
            {!preview.data && (
              <p>试运行会执行真实读取与筛选，但不会写入信息库。</p>
            )}
            {funnel && (
              <ol className="funnel-list">
                {Object.entries(funnel).map(([key, value]) => (
                  <li key={key}>
                    <span>{key.replaceAll("_", " ")}</span>
                    <strong>{value}</strong>
                  </li>
                ))}
              </ol>
            )}
            {preview.data?.samples.slice(0, 3).map((sample) => (
              <article key={`${sample.source_name}-${sample.title}`}>
                <strong>{sample.title}</strong>
                <span>{sample.source_name}</span>
              </article>
            ))}
          </div>

          <div className="task-next-run">
            <IconClock size={17} />
            <div>
              <strong>下一步</strong>
              <span>先试运行检查覆盖，再启用自动调度。</span>
            </div>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}
