from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from ai_signal_api.agent_runtime.contracts import (
    ContextSnapshot,
    ContextTraceLayer,
    PlanStep,
)
from ai_signal_api.capabilities.core import CapabilityExecutor


BASE_PROMPT_VERSION = "base-prompt@1.0.0"
RUNTIME_ROOT = Path(__file__).resolve().parent
MODULES_ROOT = RUNTIME_ROOT.parent / "modules"
CONTEXT_BUDGET_VERSION = "context-budget@1.0.0"


def serialize_bounded_json(
    value: Any,
    *,
    max_chars: int,
) -> tuple[str, bool]:
    """Serialize valid JSON within a budget without cutting it mid-token."""

    if max_chars < 256:
        raise ValueError("AGENT_CONTEXT_JSON_BUDGET_TOO_SMALL")
    serialized = _stable_json(value)
    if len(serialized) <= max_chars:
        return serialized, False

    profiles = (
        (1600, 12, 40),
        (800, 8, 32),
        (400, 5, 24),
        (200, 3, 16),
        (100, 2, 12),
        (64, 1, 8),
    )
    for string_limit, list_limit, dict_limit in profiles:
        compacted = _compact_context_value(
            value,
            string_limit=string_limit,
            list_limit=list_limit,
            dict_limit=dict_limit,
        )
        if isinstance(compacted, dict):
            compacted["_context_budget"] = {
                "applied": True,
                "strategy": "deterministic_bounded_json",
                "restorable_references_preserved": True,
            }
        candidate = _stable_json(compacted)
        if len(candidate) <= max_chars:
            return candidate, True

    fallback = {
        "_context_budget": {
            "applied": True,
            "strategy": "reference_only_fallback",
            "restorable_references_preserved": True,
        },
        "references": _reference_only(value),
    }
    candidate = _stable_json(fallback)
    if len(candidate) <= max_chars:
        return candidate, True
    fallback["references"] = str(fallback["references"])[: max_chars - 220]
    return _stable_json(fallback), True


def build_working_memory(
    *,
    plan: Any,
    step_statuses: dict[str, str],
    active_step_index: int,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive a restorable task notepad from persisted graph state."""

    steps = list(plan.steps)
    active_step_id = (
        steps[active_step_index].step_id
        if 0 <= active_step_index < len(steps)
        else None
    )
    notes = []
    for error in errors[-3:]:
        message = " ".join(
            str(error.get("message", "")).splitlines()[:1]
        ).strip()
        notes.append(
            {
                "kind": "error",
                "code": str(error.get("code", "UNKNOWN"))[:80],
                "summary": message[:280],
                "retryable": bool(error.get("retryable", False)),
            }
        )
    return {
        "version": CONTEXT_BUDGET_VERSION,
        "objective": str(plan.objective)[:600],
        "active_step_id": active_step_id,
        "todo": [
            {
                "step_id": step.step_id,
                "title": step.title[:180],
                "status": step_statuses.get(step.step_id, "pending"),
            }
            for step in steps[:12]
        ],
        "notes": notes,
    }


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    )


def _compact_context_value(
    value: Any,
    *,
    string_limit: int,
    list_limit: int,
    dict_limit: int,
    depth: int = 0,
) -> Any:
    if depth >= 7:
        return _reference_only(value)
    if isinstance(value, str):
        return value if len(value) <= string_limit else value[:string_limit]
    if isinstance(value, list):
        return [
            _compact_context_value(
                item,
                string_limit=string_limit,
                list_limit=list_limit,
                dict_limit=dict_limit,
                depth=depth + 1,
            )
            for item in value[:list_limit]
        ]
    if isinstance(value, tuple):
        return _compact_context_value(
            list(value),
            string_limit=string_limit,
            list_limit=list_limit,
            dict_limit=dict_limit,
            depth=depth,
        )
    if isinstance(value, dict):
        return {
            str(key): _compact_context_value(
                item,
                string_limit=string_limit,
                list_limit=list_limit,
                dict_limit=dict_limit,
                depth=depth + 1,
            )
            for key, item in list(value.items())[:dict_limit]
        }
    return value


def _reference_only(value: Any) -> Any:
    reference_keys = {
        "id",
        "turn_id",
        "step_id",
        "block_id",
        "information_id",
        "information_ids",
        "artifact_id",
        "run_id",
        "source_id",
        "source_url",
        "app_path",
        "objective",
        "status",
        "code",
        "title",
    }
    if isinstance(value, dict):
        references = {
            str(key): _reference_only(item)
            for key, item in value.items()
            if str(key) in reference_keys
            or str(key).endswith(("_id", "_ids", "_path", "_url"))
        }
        return references or {"omitted": True}
    if isinstance(value, (list, tuple)):
        return [_reference_only(item) for item in list(value)[:3]]
    if isinstance(value, str):
        return value[:160]
    return value


class ContextAssembler:
    """Builds a bounded Base + selected Domain + Step context snapshot."""

    def __init__(self, executor: CapabilityExecutor) -> None:
        self.executor = executor

    def assemble(
        self,
        *,
        selected_domain_ids: list[str],
        message: str,
        step: PlanStep | None,
        evidence: list[dict[str, Any]],
        working_memory: dict[str, Any] | None = None,
    ) -> ContextSnapshot:
        if len(selected_domain_ids) > 3:
            raise ValueError("AGENT_CONTEXT_DOMAIN_BUDGET_EXCEEDED")
        base = (RUNTIME_ROOT / "base-prompt.md").read_text(encoding="utf-8")
        prompt_parts = [base]
        domain_versions: dict[str, str] = {}
        declared_tools: list[str] = []
        for domain_id in selected_domain_ids:
            domain_root = MODULES_ROOT / domain_id / "agent"
            manifest = yaml.safe_load(
                (domain_root / "domain.yaml").read_text(encoding="utf-8")
            )
            domain_versions[domain_id] = str(manifest["version"])
            declared_tools.extend(manifest.get("capabilities", []))
            prompt_parts.append(
                (domain_root / "prompt.md").read_text(encoding="utf-8")
            )
        available = set(self.executor.registry.ids()).difference(
            self.executor.disabled_capabilities
        )
        declared_available = list(
            dict.fromkeys(
                tool_id
                for tool_id in declared_tools
                if tool_id in available
            )
        )
        if (
            step is not None
            and step.capability_id is not None
            and step.capability_id in available
        ):
            tool_ids = [step.capability_id]
        else:
            tool_ids = declared_available[:8]
        if step is not None:
            prompt_parts.append(
                "当前步骤："
                f"{step.title}\n目标：{step.goal}\n"
                f"验收：{step.success_criteria}"
            )
        if evidence:
            prompt_parts.append(
                "有界 Evidence："
                + "\n".join(
                    f"{item.get('business_object_id')}: "
                    f"{str(item.get('excerpt', ''))[:400]}"
                    for item in evidence[:8]
                )
            )
        working_memory_text = ""
        if working_memory:
            working_memory_text, _ = serialize_bounded_json(
                working_memory,
                max_chars=3600,
            )
            prompt_parts.append(
                "工作记事板（由持久 Plan、步骤状态和错误摘要派生，"
                "不是新的事实来源）："
                f"{working_memory_text}"
            )
        system_prompt = "\n\n".join(prompt_parts)
        layers = [
            self._trace("base", BASE_PROMPT_VERSION, base),
            self._trace(
                "conversation",
                "conversation-window@1",
                message[:4000],
            ),
        ]
        layers.extend(
            self._trace(
                f"domain:{domain_id}",
                domain_versions[domain_id],
                prompt_parts[index + 1],
            )
            for index, domain_id in enumerate(selected_domain_ids)
        )
        if working_memory_text:
            layers.append(
                self._trace(
                    "working-memory",
                    CONTEXT_BUDGET_VERSION,
                    working_memory_text,
                )
            )
        return ContextSnapshot(
            base_prompt_version=BASE_PROMPT_VERSION,
            domain_ids=selected_domain_ids,
            tool_ids=tool_ids,
            system_prompt=system_prompt,
            trace_layers=layers,
        )

    @staticmethod
    def _trace(name: str, version: str, content: str) -> ContextTraceLayer:
        return ContextTraceLayer(
            name=name,
            version=version,
            size_chars=len(content),
            summary_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )
