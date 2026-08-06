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
import {
  api,
  CapabilityInvocation,
  CollectionRun,
} from "@/lib/api";

export default function RunsPage() {
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const invocations = useQuery({
    queryKey: ["capability-invocations"],
    queryFn: api.invocations,
  });
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
        <div className="source-list">
          {invocations.data?.map((invocation: CapabilityInvocation) => (
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
