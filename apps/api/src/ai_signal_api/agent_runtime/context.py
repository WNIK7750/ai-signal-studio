from __future__ import annotations

import hashlib
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
        if step is not None and step.capability_id in available:
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
