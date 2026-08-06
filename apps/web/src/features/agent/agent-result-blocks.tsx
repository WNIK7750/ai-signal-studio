import {
  IconActivity,
  IconArrowRight,
  IconRefresh,
  IconTimeline,
} from "@tabler/icons-react";
import Link from "next/link";
import { AgentResultBlock } from "@/lib/api";

type Props = {
  blocks: AgentResultBlock[];
  onRetry?: () => void;
};

export function AgentResultBlocks({ blocks, onRetry }: Props) {
  const summary = blocks.find((block) => block.type === "result_summary");
  const plan = blocks.find((block) => block.type === "plan_summary");
  const collections = blocks.filter(
    (block) => block.type === "collection_summary",
  );
  const evidence = blocks.find(
    (block) => block.type === "evidence_sources",
  );
  const signals = blocks.filter((block) => block.type === "signal_preview");
  const partial = blocks.find((block) => block.type === "partial_failure");
  const navigation = blocks.find(
    (block) => block.type === "navigation_action",
  );
  const researchLists = blocks.filter(
    (block) =>
      block.type === "information_list" ||
      block.type === "recommendation_list",
  );
  const comparison = blocks.find(
    (block) => block.type === "comparison_table",
  );
  const trend = blocks.find((block) => block.type === "trend_summary");
  const modelResponses = blocks.filter(
    (block) => block.type === "model_response",
  );
  const assetLists = blocks.filter(
    (block) => block.type === "artifact_list",
  );
  const recognized = new Set([
    "result_summary",
    "plan_summary",
    "signal_preview",
    "collection_summary",
    "information_list",
    "recommendation_list",
    "comparison_table",
    "trend_summary",
    "evidence_sources",
    "artifact_list",
    "partial_failure",
    "navigation_action",
    "model_response",
  ]);
  const unknown = blocks.filter((block) => !recognized.has(block.type));
  return (
    <div className="agent-result-blocks">
      {summary && (
        <section
          className={`agent-turn-summary is-${String(summary.data.status ?? "complete")}`}
          role="status"
        >
          <div className="agent-turn-summary-heading">
            <strong>{summary.title}</strong>
            <span>{statusLabel(summary.data.status)}</span>
          </div>
          <div className="agent-turn-summary-metrics">
            <span>
              推荐 {String(summary.data.recommendation_count ?? 0)} 条
            </span>
            <span>引用 {String(summary.data.evidence_count ?? 0)} 条</span>
            {Number(summary.data.backfilled_count ?? 0) > 0 && (
              <span>
                背景补充 {String(summary.data.backfilled_count)} 条
              </span>
            )}
            {Number(summary.data.web_searched_count ?? 0) > 0 && (
              <span>
                联网检索 {String(summary.data.web_searched_count)} 条
              </span>
            )}
            {Number(summary.data.web_added_count ?? 0) > 0 && (
              <span>联网新增 {String(summary.data.web_added_count)} 条</span>
            )}
            {Boolean(summary.data.web_cache_hit) && (
              <span>已复用搜索缓存</span>
            )}
          </div>
          {asRecords(summary.data.errors).length > 0 && (
            <div className="agent-error-explanation">
              <strong>需要注意</strong>
              <ol>
                {asRecords(summary.data.errors).map((error, index) => (
                  <li key={`${String(error.code ?? "error")}:${index}`}>
                    {String(error.message ?? "任务执行出现异常。")}
                    {Boolean(error.retryable) && "（可重试）"}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </section>
      )}
      {plan && (
        <section className="agent-result-summary">
          <strong>{plan.title}</strong>
          <p>{String(asRecord(plan.data.goal).topic ?? "当前任务")}</p>
          <small>
            {asRecords(plan.data.steps)
              .map((step) => String(step.title ?? step.capability_id ?? "步骤"))
              .join(" → ")}
          </small>
        </section>
      )}
      {collections.map((collection) => (
        <section className="agent-result-summary" key={collection.block_id}>
          <strong>{collection.title}</strong>
          <p>
            {Boolean(collection.data.summary)
              ? String(collection.data.summary)
              : `采集 ${String(collection.data.items_collected ?? 0)} 条，新增 ${String(collection.data.items_added ?? 0)} 条`}
          </p>
        </section>
      ))}
      {signals.map((block) => {
        const data = block.data;
        return (
          <article
            className={`agent-signal-preview is-${String(data.color ?? "normal")}`}
            key={block.block_id}
          >
            <span className="signal-rail" aria-hidden="true" />
            <div>
              <small>
                {String(data.source_name ?? "未知来源")} ·{" "}
                {formatPublishedAt(data.published_at)}
              </small>
              <h4>{String(data.title ?? block.title)}</h4>
              <p>{String(data.quick_summary ?? "")}</p>
              <span className="agent-signal-reason">
                {String(data.reason ?? "")}
              </span>
              {uniqueStrings(data.tags).length > 0 && (
                <ul className="agent-signal-tags" aria-label="模型标签">
                  {uniqueStrings(data.tags).map((tag) => (
                    <li key={tag}>{tag}</li>
                  ))}
                </ul>
              )}
              <Link href={String(data.app_path ?? "/timeline")}>
                查看这条信息
                <IconArrowRight size={14} aria-hidden="true" />
              </Link>
            </div>
          </article>
        );
      })}
      {signals.length === 0 && researchLists.flatMap((block) =>
        asRecords(block.data.items).map((item, index) => (
          <article
            className="agent-signal-preview is-watch"
            key={`${block.block_id}:${index}`}
          >
            <span className="signal-rail" aria-hidden="true" />
            <div>
              <small>{String(item.source_name ?? "已保存信息")}</small>
              <h4>{String(item.title ?? block.title)}</h4>
              <p>{String(item.summary ?? "")}</p>
              <span className="agent-signal-reason">
                {String(item.reason ?? "")}
              </span>
              {uniqueStrings(item.tags).length > 0 && (
                <ul className="agent-signal-tags" aria-label="模型标签">
                  {uniqueStrings(item.tags).map((tag) => (
                    <li key={tag}>{tag}</li>
                  ))}
                </ul>
              )}
              <Link href={safeAppPath(item.app_path)}>
                查看 AI 信息
                <IconArrowRight size={14} aria-hidden="true" />
              </Link>
            </div>
          </article>
        )),
      )}
      {researchLists.map((block) =>
        Boolean(block.data.overview) ? (
          <section className="agent-result-summary" key={`${block.block_id}:overview`}>
            <strong>{block.title}</strong>
            <p>{String(block.data.overview)}</p>
            {Array.isArray(block.data.backfilled_information_ids) &&
              block.data.backfilled_information_ids.length > 0 && (
                <p className="agent-window-note">
                  精确时间窗内找到{" "}
                  {String(block.data.requested_item_count ?? 0)} 条；为避免遗漏，
                  已明确补充最近{" "}
                  {String(block.data.effective_lookback_hours ?? "")} 小时内的
                  已保存背景信息。
                </p>
              )}
            {uniqueStrings(
              block.data.uncertainties ?? block.data.coverage_gaps,
            ).length > 0 && (
              <div className="agent-evidence-boundaries">
                <strong>证据边界</strong>
                <ol>
                  {uniqueStrings(
                    block.data.uncertainties ?? block.data.coverage_gaps,
                  ).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ol>
              </div>
            )}
          </section>
        ) : null,
      )}
      {assetLists.flatMap((block) =>
        asRecords(block.data.items).map((item, index) => (
          <article
            className="agent-asset-reference"
            key={`${block.block_id}:${index}`}
          >
            <div>
              <small>
                {String(item.media_type ?? block.data.source_type ?? "Evidence")}
              </small>
              <h4>{String(item.filename ?? item.path ?? block.title)}</h4>
              <p>{String(item.excerpt ?? "")}</p>
            </div>
            {Boolean(item.artifact_id) && (
              <code>{String(item.artifact_id)}</code>
            )}
          </article>
        )),
      )}
      {comparison && (
        <div className="agent-research-table">
          <strong>{comparison.title}</strong>
          <table>
            <thead>
              <tr>
                <th>对象</th>
                <th>带引用事实</th>
              </tr>
            </thead>
            <tbody>
              {asRecords(comparison.data.rows).map((row, index) => (
                <tr key={`${comparison.block_id}:${index}`}>
                  <th>{String(row.object_name ?? "")}</th>
                  <td>
                    {asRecords(row.facts)
                      .map((fact) => String(fact.value ?? ""))
                      .join("；")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {trend && (
        <div className="agent-trend-summary">
          <strong>{trend.title}</strong>
          {Boolean(trend.data.overview) && (
            <p>{String(trend.data.overview)}</p>
          )}
          {asRecords(
            trend.data.key_findings ?? trend.data.trends,
          ).map((item, index) => (
            <p key={`${trend.block_id}:${index}`}>
              <b>{String(item.title ?? "")}</b>：{String(item.summary ?? "")}
            </p>
          ))}
          {asRecords(trend.data.why_it_matters).map((item, index) => (
            <p key={`${trend.block_id}:why:${index}`}>
              <b>为什么重要</b>：{String(item.summary ?? "")}
            </p>
          ))}
          {asRecords(trend.data.differences).map((item, index) => (
            <p key={`${trend.block_id}:difference:${index}`}>
              <b>差异</b>：{String(item.summary ?? "")}
            </p>
          ))}
          {uniqueStrings(
            trend.data.uncertainties ?? trend.data.coverage_gaps,
          ).length > 0 && (
            <div className="agent-evidence-boundaries">
              <strong>不确定性</strong>
              <ol>
                {uniqueStrings(
                  trend.data.uncertainties ?? trend.data.coverage_gaps,
                ).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}
      {modelResponses.map((block) => (
        <section className="agent-trend-summary" key={block.block_id}>
          <strong>{block.title}</strong>
          <p>{String(block.data.content ?? "")}</p>
          <small>
            {String(
              block.data.evidence_boundary
                ?? "回答基于当前会话的有界上下文。",
            )}
          </small>
        </section>
      ))}
      {evidence && (
        <section className="agent-result-summary">
          <strong>{evidence.title}</strong>
          <p>
            已引用 {asStrings(evidence.data.information_ids).length} 条工作区信息
          </p>
        </section>
      )}
      {partial && (
        <div className="agent-partial-failure" role="status">
          <div>
            <strong>
              {Array.isArray(partial.data.errors)
                ? "部分来源失败，已保留可用结果"
                : "证据覆盖不足，已完成可执行分析"}
            </strong>
            <p>
              {Array.isArray(partial.data.errors)
                ? "可以只重试失败来源，不会重复已完成的采集。"
                : `请求 ${String(partial.data.requested ?? "指定数量")} 条，当前返回 ${String(partial.data.returned ?? 0)} 条；系统没有补造信息。`}
            </p>
          </div>
          {onRetry && Array.isArray(partial.data.errors) && (
            <button className="secondary-button" type="button" onClick={onRetry}>
              <IconRefresh size={14} aria-hidden="true" />
              重试失败来源
            </button>
          )}
        </div>
      )}
      {navigation && (
        <div className="agent-result-actions">
          <Link
            className="secondary-button"
            href={String(navigation.data.view_all_path ?? "/timeline")}
          >
            <IconTimeline size={15} aria-hidden="true" />
            查看全部
          </Link>
          <Link
            className="secondary-button"
            href={String(navigation.data.run_path ?? "/runs")}
          >
            <IconActivity size={15} aria-hidden="true" />
            查看运行详情
          </Link>
        </div>
      )}
      {unknown.map((block) => (
        <details className="agent-result-summary" key={block.block_id}>
          <summary>{block.title || "后续结果"}</summary>
          <p>该结果类型将在后续版本中提供专用视图，数据已安全保留。</p>
        </details>
      ))}
    </div>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function asRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is Record<string, unknown> =>
          typeof item === "object" && item !== null,
      )
    : [];
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

export function uniqueStrings(value: unknown): string[] {
  return [...new Set(asStrings(value).map((item) => item.trim()).filter(Boolean))];
}

function statusLabel(value: unknown): string {
  if (value === "complete") return "已完成";
  if (value === "partial") return "部分完成";
  if (value === "cancelled") return "已取消";
  return "未完成";
}

function safeAppPath(value: unknown): string {
  return typeof value === "string" && value.startsWith("/")
    ? value
    : "/timeline";
}

function formatPublishedAt(value: unknown): string {
  if (typeof value !== "string") return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
