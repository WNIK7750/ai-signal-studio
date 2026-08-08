"use client";

import { useQuery } from "@tanstack/react-query";
import {
  IconBolt,
  IconAlertTriangle,
  IconCheck,
  IconHistory,
  IconX,
} from "@tabler/icons-react";
import { AppShell } from "@/components/app-shell";
import { useMemo, useState } from "react";
import {
  api,
  CapabilityInvocation,
  CollectionRun,
} from "@/lib/api";

export default function RunsPage() {
  const [invocationView, setInvocationView] = useState("all");
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const invocations = useQuery({
    queryKey: ["capability-invocations"],
    queryFn: api.invocations,
  });
  const invocationViews = useMemo(() => {
    const items = invocations.data ?? [];
    const definitions = [
      ["all", "全部", () => true],
      ["information", "信息处理", (id: string) =>
        /^(collection|intelligence|research|review)\./.test(id)],
      ["agent", "Agent", (id: string) =>
        /^(agent|conversation|model|task)\./.test(id)],
      ["content", "内容产物", (id: string) =>
        /^(card|artifact|poster)\./.test(id)],
      ["other", "其他", (id: string) =>
        !/^(collection|intelligence|research|review|agent|conversation|model|task|card|artifact|poster)\./.test(id)],
    ] as const;
    return definitions
      .map(([id, label, match]) => ({
        id,
        label,
        match,
        count: items.filter((item) => match(item.capability_id)).length,
      }))
      .filter((view) => view.id === "all" || view.count > 0);
  }, [invocations.data]);
  const visibleInvocations = useMemo(() => {
    const selected = invocationViews.find((view) => view.id === invocationView);
    return (invocations.data ?? []).filter(
      (item) => !selected || selected.match(item.capability_id),
    );
  }, [invocationView, invocationViews, invocations.data]);
  return (
    <AppShell>
      <header className="topbar">
        <div><span className="eyebrow">可追溯记录</span><h1>运行记录</h1></div>
      </header>
      <section className="settings-page">
        <div className="run-section-heading">
          <div>
            <span className="eyebrow">统一能力入口</span>
            <h2>能力调用</h2>
          </div>
          <span>{invocations.data?.length ?? 0} 次</span>
        </div>
        <div className="view-switcher" aria-label="能力调用分类">
          {invocationViews.map((view) => (
            <button
              key={view.id}
              className={invocationView === view.id ? "selected" : ""}
              aria-pressed={invocationView === view.id}
              onClick={() => setInvocationView(view.id)}
            >
              {view.label}<span>{view.count}</span>
            </button>
          ))}
        </div>
        <div className="source-list">
          {visibleInvocations.map((invocation: CapabilityInvocation) => (
            <article className="source-card" key={invocation.id}>
              <span className="source-icon"><IconBolt size={20} /></span>
              <div>
                <strong>{invocation.capability_id}</strong>
                <small>
                  {invocation.actor_type} ·{" "}
                  {new Date(invocation.started_at).toLocaleString("zh-CN")}
                </small>
              </div>
              <span className={invocation.status === "completed" ? "run-ok" : "run-error"}>
                {invocation.status === "completed" ? (
                  <><IconCheck size={16} /> 已完成</>
                ) : (
                  <><IconX size={16} /> {invocation.error_code ?? "失败"}</>
                )}
              </span>
            </article>
          ))}
        </div>
        <div className="run-section-heading run-section-spaced">
          <div>
            <span className="eyebrow">数据采集</span>
            <h2>采集运行</h2>
          </div>
          <span>{runs.data?.length ?? 0} 次</span>
        </div>
        <div className="source-list">
          {runs.data?.map((run: CollectionRun) => (
            <article className="source-card" key={run.id}>
              <span className="source-icon"><IconHistory size={20} /></span>
              <div>
                <strong>
                  {run.task_id ? "任务运行" : "快速采集"} · {run.items_added} 条新增
                </strong>
                <small>
                  {new Date(run.created_at).toLocaleString("zh-CN")} ·{" "}
                  {run.trigger_type}
                </small>
              </div>
              <span
                className={
                  run.execution_status === "completed" ? "run-ok" : "run-error"
                }
              >
                {run.execution_status === "completed" ? (
                  <><IconCheck size={16} /> 执行完成</>
                ) : (
                  <><IconX size={16} /> {run.execution_status}</>
                )}
              </span>
              <span
                className={
                  run.coverage_status === "met" ? "run-ok" : "run-warning"
                }
              >
                {run.coverage_status === "met" ? (
                  <><IconCheck size={16} /> 覆盖达标</>
                ) : (
                  <><IconAlertTriangle size={16} /> 覆盖未达标</>
                )}
              </span>
            </article>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
