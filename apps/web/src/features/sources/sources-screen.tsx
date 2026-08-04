"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { IconDatabase, IconPlus, IconRss } from "@tabler/icons-react";
import { FormEvent, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { api, Source, SourceKind } from "@/lib/api";

export function SourcesScreen() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const sources = useQuery({ queryKey: ["sources"], queryFn: api.sources });
  const create = useMutation({
    mutationFn: api.createSource,
    onSuccess: () => {
      setShowForm(false);
      void queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const kind = String(form.get("kind")) as SourceKind;
    const endpoint = String(form.get("endpoint"));
    create.mutate({
      name: String(form.get("name")),
      kind,
      config: kind === "github_releases" ? { repository: endpoint } : { url: endpoint },
    });
  }
  return (
    <AppShell>
      <header className="topbar">
        <div><span className="eyebrow">设置</span><h1>来源</h1></div>
        <button className="primary-button" onClick={() => setShowForm((value) => !value)}>
          <IconPlus size={18} />添加来源
        </button>
      </header>
      <section className="settings-page">
        {showForm && (
          <form className="inline-form" onSubmit={submit}>
            <input name="name" placeholder="来源名称" required />
            <select name="kind">
              <option value="rss">RSS</option>
              <option value="github_releases">GitHub Releases</option>
            </select>
            <input name="endpoint" placeholder="订阅地址或 owner/repo" required />
            <button className="primary-button">保存</button>
          </form>
        )}
        <div className="source-list">
          {sources.data?.map((source: Source) => (
            <article className="source-card" key={source.id}>
              <span className="source-icon">
                {source.kind === "rss" ? <IconRss size={20} /> : <IconDatabase size={20} />}
              </span>
              <div><strong>{source.name}</strong><small>{source.kind}</small></div>
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
