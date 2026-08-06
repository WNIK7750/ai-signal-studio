"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IconArchive,
  IconCheck,
  IconFile,
  IconPackage,
  IconUpload,
} from "@tabler/icons-react";
import { ChangeEvent, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { api } from "@/lib/api";

export function AssetsScreen() {
  const queryClient = useQueryClient();
  const [packArchive, setPackArchive] = useState("");
  const [packName, setPackName] = useState("");
  const [activePackId, setActivePackId] = useState("");
  const [preferenceText, setPreferenceText] = useState("");
  const [nextVersion, setNextVersion] = useState("1.1.0");
  const artifacts = useQuery({
    queryKey: ["artifacts"],
    queryFn: api.artifacts,
  });
  const versions = useQuery({
    queryKey: ["agent-pack-versions", activePackId],
    queryFn: () => api.agentPackVersions(activePackId),
    enabled: Boolean(activePackId),
  });
  const preview = useMutation({
    mutationFn: api.previewAgentPack,
  });
  const importPack = useMutation({
    mutationFn: api.importAgentPack,
    onSuccess: (pack) => {
      setActivePackId(pack.pack_id);
      void queryClient.invalidateQueries({
        queryKey: ["agent-pack-versions", pack.pack_id],
      });
    },
  });
  const editPack = useMutation({
    mutationFn: () =>
      api.editAgentPack(activePackId, {
        path: "memory/preferences.md",
        content: preferenceText,
        version: nextVersion,
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["agent-pack-versions", activePackId],
      }),
  });
  const activateVersion = useMutation({
    mutationFn: api.activateAgentPackVersion,
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["agent-pack-versions", activePackId],
      }),
  });
  const uploadArtifact = useMutation({
    mutationFn: async (file: File) =>
      api.createArtifact({
        filename: file.name,
        media_type: file.type || mediaTypeFromName(file.name),
        content_base64: await fileBase64(file),
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["artifacts"] }),
  });

  async function choosePack(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const encoded = await fileBase64(file);
    setPackArchive(encoded);
    setPackName(file.name);
    preview.mutate(encoded);
    event.target.value = "";
  }

  return (
    <AppShell>
      <header className="topbar">
        <div>
          <span className="eyebrow">设置</span>
          <h1>Agent 资产</h1>
        </div>
      </header>
      <section className="settings-page asset-settings">
        <section className="asset-section">
          <div className="settings-heading">
            <span className="settings-icon">
              <IconPackage size={20} />
            </span>
            <div>
              <h2>Agent Pack</h2>
              <p>先预览差异，再原子激活；失败不会替换当前版本。</p>
            </div>
          </div>
          <label className="secondary-button asset-upload-button">
            <IconUpload size={16} />
            选择 ZIP
            <input
              className="sr-only"
              type="file"
              accept=".zip,application/zip"
              onChange={(event) => void choosePack(event)}
            />
          </label>
          {preview.data && (
            <div className="pack-preview" role="status">
              <strong>
                {preview.data.pack_id} · {preview.data.version}
              </strong>
              <span>
                新增 {preview.data.added.length} · 修改{" "}
                {preview.data.changed.length} · 删除{" "}
                {preview.data.removed.length}
              </span>
              <code>{packName}</code>
              <button
                className="primary-button"
                onClick={() => importPack.mutate(packArchive)}
                disabled={importPack.isPending}
              >
                <IconCheck size={16} />
                {importPack.isPending ? "正在激活" : "确认激活"}
              </button>
            </div>
          )}
          {activePackId && (
            <div className="pack-editor">
              <label>
                已确认偏好
                <textarea
                  value={preferenceText}
                  onChange={(event) => setPreferenceText(event.target.value)}
                  placeholder="只写入用户明确确认的偏好。"
                />
              </label>
              <label>
                新版本
                <input
                  value={nextVersion}
                  onChange={(event) => setNextVersion(event.target.value)}
                  pattern="[0-9]+\.[0-9]+\.[0-9]+"
                />
              </label>
              <button
                className="secondary-button"
                onClick={() => editPack.mutate()}
                disabled={!preferenceText.trim() || editPack.isPending}
              >
                保存为新版本
              </button>
            </div>
          )}
          <div className="pack-versions">
            {versions.data?.map((version) => (
              <article key={version.id}>
                <div>
                  <strong>{version.version}</strong>
                  <small>{version.content_digest.slice(0, 12)}</small>
                </div>
                {version.status === "active" ? (
                  <span>当前版本</span>
                ) : (
                  <button
                    className="text-button"
                    onClick={() => activateVersion.mutate(version.id)}
                  >
                    回退到此版本
                  </button>
                )}
              </article>
            ))}
          </div>
        </section>

        <section className="asset-section">
          <div className="settings-heading">
            <span className="settings-icon">
              <IconArchive size={20} />
            </span>
            <div>
              <h2>Artifact</h2>
              <p>文件保存在本地；数据库只记录摘要、Digest 与引用。</p>
            </div>
          </div>
          <label className="secondary-button asset-upload-button">
            <IconUpload size={16} />
            上传文档或图片
            <input
              className="sr-only"
              type="file"
              accept=".md,.txt,.json,.yaml,.yml,image/png,image/jpeg,image/webp"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) uploadArtifact.mutate(file);
                event.target.value = "";
              }}
            />
          </label>
          <div className="artifact-list">
            {artifacts.data?.map((artifact) => (
              <article key={artifact.artifact_id}>
                <IconFile size={18} />
                <div>
                  <strong>{artifact.filename}</strong>
                  <small>
                    {artifact.media_type} ·{" "}
                    {Math.ceil(artifact.size_bytes / 1024)} KB
                  </small>
                </div>
                <code>{artifact.artifact_id}</code>
              </article>
            ))}
          </div>
        </section>
      </section>
    </AppShell>
  );
}

function fileBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () =>
      resolve(String(reader.result ?? "").split(",", 2)[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function mediaTypeFromName(filename: string) {
  if (filename.endsWith(".md")) return "text/markdown";
  if (filename.endsWith(".json")) return "application/json";
  if (filename.endsWith(".yaml") || filename.endsWith(".yml")) {
    return "application/yaml";
  }
  return "text/plain";
}
