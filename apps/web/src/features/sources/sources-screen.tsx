"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IconActivityHeartbeat,
  IconDatabase,
  IconEdit,
  IconPlus,
  IconRss,
  IconX,
} from "@tabler/icons-react";
import { FormEvent, useRef, useState } from "react";
import { AppShell } from "@/components/app-shell";
import {
  api,
  Source,
  SourceKind,
  SourceTestResult,
  SourceUpdateInput,
} from "@/lib/api";

export function SourcesScreen() {
  const queryClient = useQueryClient();
  const formRef = useRef<HTMLFormElement | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingSource, setEditingSource] = useState<Source | null>(null);
  const [testingSourceId, setTestingSourceId] = useState<string | null>(null);
  const [draftResult, setDraftResult] = useState<SourceTestResult | null>(null);
  const sources = useQuery({ queryKey: ["sources"], queryFn: api.sources });
  const create = useMutation({
    mutationFn: api.createSource,
    onSuccess: () => {
      setShowForm(false);
      void queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });
  const update = useMutation({
    mutationFn: ({
      sourceId,
      input,
    }: {
      sourceId: string;
      input: SourceUpdateInput;
    }) => api.updateSource(sourceId, input),
    onSuccess: () => {
      setEditingSource(null);
      void queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });
  const test = useMutation({
    mutationFn: api.testSource,
    onMutate: (sourceId) => setTestingSourceId(sourceId),
    onSettled: () => {
      setTestingSourceId(null);
      return queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });
  const testDraft = useMutation({
    mutationFn: api.testSourceDefinition,
    onSuccess: setDraftResult,
  });
  function definitionFromForm(form: HTMLFormElement): {
    name: string;
    kind: SourceKind;
    config: Record<string, string>;
  } {
    const data = new FormData(form);
    const kind =
      editingSource?.kind ?? (String(data.get("kind")) as SourceKind);
    const endpoint = String(data.get("endpoint"));
    const config: Record<string, string> =
      kind === "github_releases"
        ? { repository: endpoint }
        : kind === "rss"
          ? { url: endpoint }
          : {};
    return {
      name: String(data.get("name")),
      kind,
      config,
    };
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const definition = definitionFromForm(event.currentTarget);
    if (editingSource) {
      update.mutate({
        sourceId: editingSource.id,
        input: {
          name: definition.name,
          config: definition.config,
        },
      });
      return;
    }
    create.mutate(definition);
  }
  return (
    <AppShell>
      <header className="topbar">
        <div><span className="eyebrow">设置</span><h1>来源</h1></div>
        <button className="primary-button" onClick={() => {
          setEditingSource(null);
          setDraftResult(null);
          setShowForm(true);
        }}>
          <IconPlus size={18} />添加来源
        </button>
      </header>
      <section className="settings-page">
        {(showForm || editingSource) && (
          <div className="modal-backdrop">
            <form
              ref={formRef}
              className="modal source-form-modal"
              onSubmit={submit}
              role="dialog"
              aria-modal="true"
              aria-labelledby="source-form-title"
            >
              <div className="modal-title">
                <div>
                  <span className="eyebrow">来源定义</span>
                  <h2 id="source-form-title">
                    {editingSource ? "编辑来源" : "添加来源"}
                  </h2>
                </div>
                <button
                  className="icon-button"
                  type="button"
                  onClick={() => {
                    setShowForm(false);
                    setEditingSource(null);
                    setDraftResult(null);
                  }}
                  aria-label="关闭来源表单"
                >
                  <IconX size={18} />
                </button>
              </div>
              <label>
                来源名称
                <input
                  name="name"
                  placeholder="例如：OpenAI Blog"
                  defaultValue={editingSource?.name}
                  required
                />
              </label>
              <label>
                来源类型
                {editingSource ? (
                  <input
                    aria-label="来源类型"
                    value={editingSource.kind}
                    readOnly
                  />
                ) : (
                  <select name="kind" defaultValue="rss">
                    <option value="rss">RSS</option>
                    <option value="github_releases">GitHub Releases</option>
                  </select>
                )}
              </label>
              <label>
                地址或仓库
                <input
                  name="endpoint"
                  placeholder="https://example.com/feed.xml 或 owner/repo"
                  defaultValue={String(
                    editingSource?.config.url ??
                      editingSource?.config.repository ??
                      "",
                  )}
                  required
                />
              </label>
              {draftResult && (
                <div
                  className={`source-draft-result ${
                    draftResult.status === "healthy" ? "is-ok" : "is-error"
                  }`}
                  role="status"
                >
                  {draftResult.status === "healthy"
                    ? `连接正常 · 读取到 ${draftResult.items_count} 条`
                    : `测试失败 · ${draftResult.error_code ?? "SOURCE_TEST_FAILED"}`}
                  {draftResult.sample_titles.map((title) => (
                    <small key={title}>{title}</small>
                  ))}
                </div>
              )}
              <div className="source-form-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => {
                    if (formRef.current?.reportValidity()) {
                      setDraftResult(null);
                      testDraft.mutate(
                        definitionFromForm(formRef.current),
                      );
                    }
                  }}
                  disabled={testDraft.isPending}
                >
                  <IconActivityHeartbeat size={16} />
                  {testDraft.isPending ? "正在测试" : "保存前测试"}
                </button>
                <button
                  className="primary-button"
                  type="submit"
                  disabled={create.isPending || update.isPending}
                >
                  {create.isPending || update.isPending ? "正在保存" : "保存"}
                </button>
              </div>
            </form>
          </div>
        )}
        <div className="source-list">
          {sources.data?.map((source: Source) => (
            <article className="source-card" key={source.id}>
              <span className="source-icon">
                {source.kind === "rss" ? <IconRss size={20} /> : <IconDatabase size={20} />}
              </span>
              <div className="source-main">
                <strong>{source.name}</strong>
                <small>
                  {source.kind} ·{" "}
                  {source.last_success_at
                    ? `最近成功 ${new Date(source.last_success_at).toLocaleString(
                        "zh-CN",
                        { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" },
                      )}`
                    : "尚未验证"}
                </small>
              </div>
              <span className={`source-health health-${source.health_status}`}>
                <i />
                {source.health_status === "healthy"
                  ? `正常 · ${source.last_items_count} 条`
                  : source.health_status === "error"
                    ? source.last_error_code ?? "连接失败"
                    : "待检测"}
              </span>
              <div className="source-row-actions">
                <button
                  className="secondary-button compact-button"
                  onClick={() => test.mutate(source.id)}
                  disabled={testingSourceId === source.id}
                >
                  <IconActivityHeartbeat size={15} />
                  {testingSourceId === source.id ? "测试中" : "测试"}
                </button>
                <button
                  className="icon-button"
                  onClick={() => {
                    setEditingSource(source);
                    setShowForm(false);
                    setDraftResult(null);
                  }}
                  aria-label={`编辑 ${source.name}`}
                >
                  <IconEdit size={16} />
                </button>
              </div>
              <button
                className={`toggle ${source.enabled ? "is-on" : ""}`}
                onClick={() => api.toggleSource(source).then(() => queryClient.invalidateQueries({ queryKey: ["sources"] }))}
                aria-label={`${source.enabled ? "停用" : "启用"} ${source.name}`}
              />
            </article>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
