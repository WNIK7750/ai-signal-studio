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
  const assetLists = blocks.filter(
    (block) => block.type === "artifact_list",
  );
  return (
    <div className="agent-result-blocks">
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
              <Link href={String(data.app_path ?? "/timeline")}>
                查看这条信息
                <IconArrowRight size={14} aria-hidden="true" />
              </Link>
            </div>
          </article>
        );
      })}
      {researchLists.flatMap((block) =>
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
              <Link href={safeAppPath(item.app_path)}>
                查看 AI 信息
                <IconArrowRight size={14} aria-hidden="true" />
              </Link>
            </div>
          </article>
        )),
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
          {asRecords(trend.data.trends).map((item, index) => (
            <p key={`${trend.block_id}:${index}`}>
              <b>{String(item.title ?? "")}</b>：{String(item.summary ?? "")}
            </p>
          ))}
          {asStrings(trend.data.counterexamples).map((item) => (
            <p key={item}>反例：{item}</p>
          ))}
          {asStrings(trend.data.coverage_gaps).map((item) => (
            <p key={item}>资料缺口：{item}</p>
          ))}
        </div>
      )}
      {partial && (
        <div className="agent-partial-failure" role="status">
          <div>
            <strong>部分来源失败，已保留可用结果</strong>
            <p>可以只重试失败来源，不会重复已完成的采集。</p>
          </div>
          {onRetry && (
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
    </div>
  );
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
