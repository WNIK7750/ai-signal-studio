"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  IconArrowLeft,
  IconBrain,
  IconCheck,
  IconEye,
  IconEyeOff,
  IconKey,
  IconPencil,
  IconPlugConnected,
  IconPlus,
  IconServer,
  IconTrash,
  IconX,
} from "@tabler/icons-react";
import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { api, ModelConfig, ModelWriteInput } from "@/lib/api";
import {
  findProviderPreset,
  PROVIDER_PRESETS,
} from "@/lib/provider-presets";

const OUTPUT_LIMITS = [8000, 16000, 32000, 64000];

function compactTokens(value: number | null) {
  if (!value) return "默认额度";
  return `${Math.round(value / 1000)}K`;
}

export function ModelsScreen() {
  const queryClient = useQueryClient();
  const [formMode, setFormMode] = useState<"create" | "edit" | null>(null);
  const [editingModel, setEditingModel] = useState<ModelConfig | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ModelConfig | null>(null);
  const [error, setError] = useState("");
  const [providerId, setProviderId] = useState("custom");
  const [customBaseUrl, setCustomBaseUrl] = useState(
    "https://api.openai.com/v1",
  );
  const [showKey, setShowKey] = useState(false);
  const [outputLimit, setOutputLimit] = useState<number | "">("");
  const [connectionNotice, setConnectionNotice] = useState<{
    modelId: string;
    message: string;
    ok: boolean;
  } | null>(null);
  const models = useQuery({ queryKey: ["models"], queryFn: api.models });
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: api.providers,
  });
  const selectedProvider = useMemo(
    () => providers.data?.find((provider) => provider.id === providerId),
    [providerId, providers.data],
  );
  const selectedPreset = findProviderPreset(providerId);
  const editingCurrentProvider = Boolean(
    formMode === "edit"
    && editingModel
    && editingModel.provider_id === providerId,
  );

  function resetFormState() {
    setFormMode(null);
    setEditingModel(null);
    setProviderId("custom");
    setCustomBaseUrl("https://api.openai.com/v1");
    setShowKey(false);
    setOutputLimit("");
    setError("");
  }

  function openCreate() {
    resetFormState();
    setFormMode("create");
  }

  function openEdit(model: ModelConfig) {
    setError("");
    setEditingModel(model);
    setProviderId(model.provider_id);
    setCustomBaseUrl(model.base_url);
    setShowKey(false);
    setOutputLimit(model.output_token_limit ?? "");
    setFormMode("edit");
  }

  function refreshModels() {
    void queryClient.invalidateQueries({ queryKey: ["models"] });
    void queryClient.invalidateQueries({ queryKey: ["providers"] });
  }

  const createModel = useMutation({
    mutationFn: api.createModel,
    onSuccess: () => {
      resetFormState();
      refreshModels();
    },
    onError: (reason) =>
      setError(
        reason instanceof Error
          ? reason.message
          : "SYS-001（创建模型失败）",
      ),
  });
  const updateModel = useMutation({
    mutationFn: ({
      modelId,
      input,
    }: {
      modelId: string;
      input: ModelWriteInput;
    }) => api.updateModel(modelId, input),
    onSuccess: () => {
      resetFormState();
      refreshModels();
    },
    onError: (reason) =>
      setError(
        reason instanceof Error
          ? reason.message
          : "SYS-001（编辑模型失败）",
      ),
  });
  const deleteModel = useMutation({
    mutationFn: api.deleteModel,
    onSuccess: () => {
      setDeleteTarget(null);
      setError("");
      refreshModels();
    },
    onError: (reason) =>
      setError(
        reason instanceof Error
          ? reason.message
          : "SYS-001（删除模型失败）",
      ),
  });
  const activateModel = useMutation({
    mutationFn: api.activateModel,
    onSuccess: () => {
      setError("");
      void queryClient.invalidateQueries({ queryKey: ["models"] });
    },
    onError: (reason) =>
      setError(
        reason instanceof Error
          ? reason.message
          : "SYS-001（切换模型失败）",
      ),
  });
  const testModel = useMutation({
    mutationFn: api.testModel,
    onMutate: (modelId) => {
      setError("");
      setConnectionNotice({
        modelId,
        message: "正在测试连接…",
        ok: true,
      });
    },
    onSuccess: (result, modelId) => {
      setConnectionNotice({
        modelId,
        message: result.message,
        ok: true,
      });
    },
    onError: (reason, modelId) => {
      setConnectionNotice({
        modelId,
        message: reason instanceof Error
          ? reason.message
          : "MODEL-005（模型服务调用失败）",
        ok: false,
      });
    },
  });

  function changeProvider(nextId: string) {
    const preset = findProviderPreset(nextId);
    const provider = providers.data?.find((item) => item.id === nextId);
    setProviderId(nextId);
    if (preset) setCustomBaseUrl(preset.baseUrl);
    if (provider) setCustomBaseUrl(provider.base_url);
  }

  function submitModel(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const providerName = String(form.get("provider_name") ?? "").trim();
    const input: ModelWriteInput = {
      name: String(form.get("name")),
      model_id: String(form.get("model_id")),
      provider_id:
        formMode === "edit"
          ? selectedProvider
            ? providerId
            : null
          : selectedProvider
            ? providerId
            : undefined,
      provider_name:
        selectedProvider
          ? editingCurrentProvider
            ? providerName || selectedProvider.name
            : undefined
          : selectedPreset?.name ?? providerName,
      base_url: customBaseUrl,
      api_key: String(form.get("api_key") ?? "") || undefined,
      supports_vision: form.get("supports_vision") === "on",
      output_token_limit:
        outputLimit || (formMode === "edit" ? null : undefined),
      is_default: form.get("is_default") === "on",
    };
    if (formMode === "edit" && editingModel) {
      updateModel.mutate({ modelId: editingModel.id, input });
    } else {
      createModel.mutate(input);
    }
  }

  const formBusy = createModel.isPending || updateModel.isPending;

  return (
    <AppShell>
      <header className="topbar">
        <div>
          <span className="eyebrow">设置</span>
          <h1>模型</h1>
        </div>
        <div className="topbar-actions">
          <Link className="secondary-button" href="/agent">
            <IconArrowLeft size={18} />
            返回对话
          </Link>
          <button className="primary-button" onClick={openCreate}>
            <IconPlus size={18} />
            添加模型
          </button>
        </div>
      </header>
      <section className="settings-page model-settings-page">
        <div className="settings-heading">
          <span className="settings-icon">
            <IconBrain size={23} />
          </span>
          <div>
            <h2>工作区模型</h2>
            <p>在对话页直接切换；这里管理提供商、能力与默认模型。</p>
          </div>
        </div>

        <div className="credential-note">
          <IconKey size={18} />
          <span>
            密钥保存在本地独立文件中，保存后不再回显；同一提供商可供多个模型复用。
          </span>
        </div>
        {error && !formMode && !deleteTarget && (
          <p className="inline-error" role="alert">{error}</p>
        )}
        {models.isLoading && <p className="muted-copy">正在读取模型…</p>}
        {models.isError && (
          <p className="inline-error" role="alert">
            {models.error instanceof Error
              ? models.error.message
              : "SYS-001（读取模型失败）"}
          </p>
        )}
        <div className="model-list">
          {models.data?.map((model: ModelConfig) => (
            <article
              className={`model-row ${model.is_default ? "selected" : ""}`}
              key={model.id}
            >
              <span className="model-row-icon" aria-hidden="true">
                <IconBrain size={20} />
              </span>
              <div className="model-row-main">
                <div className="model-title-line">
                  <strong>{model.name}</strong>
                  {!model.supports_vision && (
                    <span className="model-capability-tag">不支持识图</span>
                  )}
                  {model.has_api_key && (
                    <span className="model-capability-tag">密钥已配置</span>
                  )}
                  {model.provider !== "heuristic" && !model.has_api_key && (
                    <span className="model-capability-tag warning">
                      缺少 API Key
                    </span>
                  )}
                  {connectionNotice?.modelId === model.id && (
                    <span
                      className={`model-capability-tag ${
                        connectionNotice.ok ? "success" : "error"
                      }`}
                      role="status"
                    >
                      {connectionNotice.message}
                    </span>
                  )}
                </div>
                <span>{model.model_id}</span>
                <small>
                  {model.provider_name} · {model.base_url}
                  {" · "}
                  最大输出 {compactTokens(model.output_token_limit)}
                </small>
              </div>
              <div className="model-row-actions">
                {model.is_default ? (
                  <span className="model-default">
                    <IconCheck size={15} /> 当前默认
                  </span>
                ) : (
                  <button
                    className="secondary-button"
                    onClick={() => activateModel.mutate(model.id)}
                    disabled={activateModel.isPending}
                  >
                    设为默认
                  </button>
                )}
                {model.provider !== "heuristic" && (
                  <>
                    <button
                      className="icon-button"
                      onClick={() => testModel.mutate(model.id)}
                      aria-label={`测试模型 ${model.name}`}
                      title="测试连接"
                      disabled={
                        testModel.isPending
                        && testModel.variables === model.id
                      }
                    >
                      <IconPlugConnected size={18} />
                    </button>
                    <button
                      className="icon-button"
                      onClick={() => openEdit(model)}
                      aria-label={`编辑模型 ${model.name}`}
                      title="编辑"
                    >
                      <IconPencil size={18} />
                    </button>
                    <button
                      className="icon-button delete-icon-button"
                      onClick={() => {
                        setError("");
                        setDeleteTarget(model);
                      }}
                      aria-label={`删除模型 ${model.name}`}
                      title="删除"
                    >
                      <IconTrash size={18} />
                    </button>
                  </>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>

      {formMode && (
        <div className="modal-backdrop">
          <form
            key={editingModel?.id ?? "new-model"}
            className="modal model-form"
            onSubmit={submitModel}
          >
            <div className="model-form-header">
              <div className="model-form-title">
                <h2>{formMode === "edit" ? "编辑模型" : "添加模型"}</h2>
                <span>OpenAI 兼容 API</span>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={resetFormState}
                aria-label={formMode === "edit" ? "关闭编辑模型" : "关闭添加模型"}
              >
                <IconX size={20} />
              </button>
            </div>

            <div className="model-form-body">
              <div className="model-form-field">
                <label htmlFor="model-provider">提供商</label>
                <select
                  id="model-provider"
                  name="provider_id"
                  value={providerId}
                  onChange={(event) => changeProvider(event.target.value)}
                >
                  <option value="custom">＋ 自定义 / Custom</option>
                  <optgroup label="快捷预设">
                    {PROVIDER_PRESETS.map((preset) => (
                      <option key={preset.id} value={preset.id}>
                        {preset.name}
                      </option>
                    ))}
                  </optgroup>
                  {Boolean(providers.data?.length) && (
                    <optgroup label="已保存">
                      {providers.data?.map((provider) => (
                        <option key={provider.id} value={provider.id}>
                          {provider.name}
                          {provider.has_api_key ? "（密钥已配置）" : ""}
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
              </div>

              {(providerId === "custom" || editingCurrentProvider) && (
                <label>
                  提供商名称
                  <input
                    name="provider_name"
                    defaultValue={
                      editingCurrentProvider
                        ? editingModel?.provider_name
                        : ""
                    }
                    placeholder="例如：OpenAI、OpenRouter"
                    required
                  />
                </label>
              )}

              <label>
                接口地址
                <span className="input-with-icon">
                  <IconServer size={18} aria-hidden="true" />
                  <input
                    name="base_url"
                    type="url"
                    value={customBaseUrl}
                    onChange={(event) => setCustomBaseUrl(event.target.value)}
                    readOnly={Boolean(selectedProvider) && formMode === "create"}
                    required
                  />
                </span>
                {selectedPreset && <small>{selectedPreset.note}</small>}
                {editingCurrentProvider && (
                  <small>修改地址或 Key 会影响复用此提供商的其他模型。</small>
                )}
              </label>

              <div className="model-form-field">
                <label htmlFor="model-api-key">API Key</label>
                <span className="input-with-action">
                  <input
                    id="model-api-key"
                    name="api_key"
                    type={showKey ? "text" : "password"}
                    placeholder={
                      selectedProvider?.has_api_key
                        ? "留空则继续使用已保存密钥"
                        : "输入 API Key"
                    }
                    autoComplete="off"
                    required={!selectedProvider?.has_api_key}
                  />
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => setShowKey((value) => !value)}
                    aria-label={showKey ? "隐藏 API Key" : "显示 API Key"}
                  >
                    {showKey ? <IconEyeOff size={18} /> : <IconEye size={18} />}
                  </button>
                </span>
                <small>保存后只显示是否已配置，不会从接口取回明文。</small>
              </div>

              <div className="model-form-grid">
                <label>
                  显示名称
                  <input
                    name="name"
                    defaultValue={editingModel?.name}
                    placeholder="例如：视觉分析"
                    required
                  />
                </label>
                <label>
                  模型 ID
                  <input
                    name="model_id"
                    defaultValue={editingModel?.model_id}
                    placeholder="例如：gpt-4o"
                    required
                  />
                </label>
              </div>

              <div className="model-runtime-grid">
                <fieldset className="capability-fieldset">
                  <legend>模型能力</legend>
                  <label className="check-control">
                    <input
                      name="supports_vision"
                      type="checkbox"
                      defaultChecked={editingModel?.supports_vision}
                    />
                    图片输入
                  </label>
                </fieldset>
                <TokenLimit
                  label="最大输出"
                  name="output_token_limit"
                  options={OUTPUT_LIMITS}
                  value={outputLimit}
                  onChange={setOutputLimit}
                />
              </div>

              <label className="check-control default-model-control">
                <input
                  name="is_default"
                  type="checkbox"
                  defaultChecked={editingModel?.is_default}
                />
                设为默认模型
              </label>
              {error && <p className="inline-error" role="alert">{error}</p>}
            </div>

            <div className="model-form-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={resetFormState}
              >
                取消
              </button>
              <button
                className="primary-button"
                type="submit"
                disabled={formBusy}
              >
                {formBusy ? "正在保存…" : "保存"}
              </button>
            </div>
          </form>
        </div>
      )}

      {deleteTarget && (
        <div className="modal-backdrop">
          <section
            className="modal delete-model-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-model-title"
          >
            <div className="delete-dialog-icon" aria-hidden="true">
              <IconTrash size={22} />
            </div>
            <div>
              <h2 id="delete-model-title">删除“{deleteTarget.name}”？</h2>
              <p>
                模型会从设置和对话选择中移除。提供商与密钥仍会保留，供其他模型继续复用。
              </p>
            </div>
            {error && <p className="inline-error" role="alert">{error}</p>}
            <div className="delete-dialog-actions">
              <button
                className="secondary-button"
                onClick={() => {
                  setDeleteTarget(null);
                  setError("");
                }}
              >
                取消
              </button>
              <button
                className="danger-button"
                onClick={() => deleteModel.mutate(deleteTarget.id)}
                disabled={deleteModel.isPending}
              >
                {deleteModel.isPending ? "正在删除…" : "确认删除"}
              </button>
            </div>
          </section>
        </div>
      )}
    </AppShell>
  );
}

function TokenLimit({
  label,
  name,
  options,
  value,
  onChange,
}: {
  label: string;
  name: string;
  options: number[];
  value: number | "";
  onChange: (value: number | "") => void;
}) {
  return (
    <div className="token-limit">
      <label>
        {label}
        <input
          name={name}
          type="number"
          min={256}
          value={value}
          onChange={(event) =>
            onChange(event.target.value ? Number(event.target.value) : "")
          }
          placeholder="使用提供商默认值"
        />
      </label>
      <div className="token-presets" aria-label={`${label}额度快捷选择`}>
        {options.map((option) => (
          <button
            type="button"
            key={option}
            className={value === option ? "selected" : ""}
            onClick={() => onChange(option)}
          >
            {compactTokens(option)}
          </button>
        ))}
      </div>
    </div>
  );
}
