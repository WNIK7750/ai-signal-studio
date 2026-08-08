"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IconArchive,
  IconCheck,
  IconFile,
  IconExternalLink,
  IconPackage,
  IconPlus,
  IconTrash,
  IconUpload,
} from "@tabler/icons-react";
import { ChangeEvent, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { AgentSkill, api } from "@/lib/api";

export function AssetsScreen() {
  const queryClient = useQueryClient();
  const [packArchive, setPackArchive] = useState("");
  const [packName, setPackName] = useState("");
  const [activePackId, setActivePackId] = useState("");
  const [preferenceText, setPreferenceText] = useState("");
  const [nextVersion, setNextVersion] = useState("1.1.0");
  const [packView, setPackView] = useState("rules");
  const [rules, setRules] = useState("");
  const [skills, setSkills] = useState<AgentSkill[]>([]);
  const [loadedCustomizationVersion, setLoadedCustomizationVersion] =
    useState("");
  const [artifactView, setArtifactView] = useState("all");
  const artifacts = useQuery({
    queryKey: ["artifacts"],
    queryFn: api.artifacts,
  });
  const customization = useQuery({
    queryKey: ["agent-pack-customization", "ai-editor"],
    queryFn: () => api.agentPackCustomization("ai-editor"),
  });
  if (
    customization.data
    && customization.data.version !== loadedCustomizationVersion
  ) {
    setRules(customization.data.rules);
    setSkills(customization.data.skills);
    setNextVersion(nextPatchVersion(customization.data.version));
    setActivePackId(customization.data.pack_id);
    setLoadedCustomizationVersion(customization.data.version);
  }
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
  const saveCustomization = useMutation({
    mutationFn: () =>
      api.saveAgentPackCustomization("ai-editor", {
        version: nextVersion,
        rules,
        skills,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["agent-pack-customization", "ai-editor"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["agent-pack-versions", "ai-editor"],
      });
    },
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
  const artifactViews = useMemo(() => {
    const items = artifacts.data ?? [];
    const definitions = [
      ["all", "全部", () => true],
      ["generated", "生成内容", (item: (typeof items)[number]) =>
        item.metadata.artifact_kind === "rendered_card"],
      ["image", "图片", (item: (typeof items)[number]) =>
        item.media_type.startsWith("image/")
        && item.metadata.artifact_kind !== "rendered_card"],
      ["document", "文档", (item: (typeof items)[number]) =>
        !item.media_type.startsWith("image/")],
    ] as const;
    return definitions
      .map(([id, label, match]) => ({
        id,
        label,
        match,
        count: items.filter(match).length,
      }))
      .filter((view) => view.id === "all" || view.count > 0);
  }, [artifacts.data]);
  const visibleArtifacts = useMemo(() => {
    const selected = artifactViews.find((view) => view.id === artifactView);
    return (artifacts.data ?? []).filter(
      (item) => !selected || selected.match(item),
    );
  }, [artifactView, artifactViews, artifacts.data]);

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
          <div className="view-switcher asset-editor-switcher" aria-label="Agent Pack 编辑区">
            {[
              ["rules", "Rules"],
              ["skills", "Skills"],
              ["versions", "版本"],
            ].map(([id, label]) => (
              <button
                key={id}
                className={packView === id ? "selected" : ""}
                aria-pressed={packView === id}
                onClick={() => setPackView(id)}
              >
                {label}
                {id === "skills" && <span>{skills.length}</span>}
              </button>
            ))}
          </div>
          {packView === "rules" && (
            <div className="rules-editor">
              <label>
                工作区规则
                <textarea
                  value={rules}
                  onChange={(event) => setRules(event.target.value)}
                  placeholder="定义语言、证据、安全与输出习惯。"
                />
              </label>
            </div>
          )}
          {packView === "skills" && (
            <div className="skills-editor">
              {skills.map((skill, index) => (
                <article key={skill.id}>
                  <div className="skill-editor-heading">
                    <label className="check-control">
                      <input
                        type="checkbox"
                        checked={skill.enabled}
                        onChange={(event) =>
                          updateSkill(setSkills, index, {
                            enabled: event.target.checked,
                          })
                        }
                      />
                      启用
                    </label>
                    <button
                      className="icon-button"
                      aria-label={`删除 Skill ${skill.name}`}
                      onClick={() =>
                        setSkills((items) =>
                          items.filter((_, itemIndex) => itemIndex !== index)
                        )
                      }
                    >
                      <IconTrash size={16} />
                    </button>
                  </div>
                  <input
                    value={skill.name}
                    aria-label="Skill 名称"
                    onChange={(event) =>
                      updateSkill(setSkills, index, { name: event.target.value })
                    }
                  />
                  <input
                    value={skill.description}
                    aria-label="Skill 说明"
                    placeholder="说明这个 Skill 解决什么问题"
                    onChange={(event) =>
                      updateSkill(setSkills, index, {
                        description: event.target.value,
                      })
                    }
                  />
                  <input
                    value={skill.domains.join(", ")}
                    aria-label="适用 Domain"
                    onChange={(event) =>
                      updateSkill(setSkills, index, {
                        domains: event.target.value
                          .split(",")
                          .map((value) => value.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                  <textarea
                    value={skill.instructions}
                    aria-label="Skill 指令"
                    onChange={(event) =>
                      updateSkill(setSkills, index, {
                        instructions: event.target.value,
                      })
                    }
                  />
                </article>
              ))}
              <button
                className="secondary-button"
                onClick={() =>
                  setSkills((items) => [
                    ...items,
                    {
                      id: `custom-skill-${Date.now()}`,
                      name: "自定义 Skill",
                      description: "用户自定义工作方式",
                      enabled: true,
                      domains: ["*"],
                      instructions: "请填写可执行、可验证的工作指令。",
                    },
                  ])
                }
              >
                <IconPlus size={16} /> 添加 Skill
              </button>
            </div>
          )}
          {(packView === "rules" || packView === "skills") && (
            <div className="customization-save">
              <label>
                新版本
                <input
                  value={nextVersion}
                  onChange={(event) => setNextVersion(event.target.value)}
                  pattern="[0-9]+\.[0-9]+\.[0-9]+"
                />
              </label>
              <button
                className="primary-button"
                onClick={() => saveCustomization.mutate()}
                disabled={
                  !rules.trim()
                  || skills.length === 0
                  || saveCustomization.isPending
                }
              >
                {saveCustomization.isPending ? "正在保存" : "保存 Rules / Skills"}
              </button>
            </div>
          )}
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
          {packView === "versions" && <div className="pack-versions">
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
          </div>}
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
          <div className="view-switcher artifact-switcher" aria-label="Artifact 分类">
            {artifactViews.map((view) => (
              <button
                key={view.id}
                className={artifactView === view.id ? "selected" : ""}
                aria-pressed={artifactView === view.id}
                onClick={() => setArtifactView(view.id)}
              >
                {view.label}<span>{view.count}</span>
              </button>
            ))}
          </div>
          <div className="artifact-list">
            {visibleArtifacts.map((artifact) => (
              <article key={artifact.artifact_id}>
                <IconFile size={18} />
                <div>
                  <strong>{artifact.filename}</strong>
                  <small>
                    {artifact.media_type} ·{" "}
                    {Math.ceil(artifact.size_bytes / 1024)} KB
                  </small>
                  <span className="artifact-source">
                    <b>{artifact.source_title}</b>
                    <time dateTime={artifact.source_time}>
                      {new Date(artifact.source_time).toLocaleString("zh-CN")}
                    </time>
                    {artifact.source_url && (
                      <a
                        href={artifact.source_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <IconExternalLink size={13} /> 查看来源
                      </a>
                    )}
                  </span>
                </div>
                <code title={artifact.artifact_id}>
                  {artifact.artifact_id.slice(0, 18)}…
                </code>
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

function nextPatchVersion(version: string) {
  const [major = 1, minor = 0, patch = 0] = version
    .split(".")
    .map(Number);
  return `${major}.${minor}.${patch + 1}`;
}

function updateSkill(
  setSkills: React.Dispatch<React.SetStateAction<AgentSkill[]>>,
  index: number,
  patch: Partial<AgentSkill>,
) {
  setSkills((items) =>
    items.map((item, itemIndex) =>
      itemIndex === index ? { ...item, ...patch } : item
    )
  );
}
