from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_signal_api.models import CapabilityInvocationModel
from ai_signal_api.schemas import ExecutionContext


CapabilityHandler = Callable[[BaseModel, ExecutionContext], BaseModel]


class CapabilityExecutionError(RuntimeError):
    def __init__(self, code: str, status_code: int = 400) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


def _digest(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class CapabilityRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, CapabilityHandler] = {}

    def register(
        self,
        capability_id: str,
        handler: CapabilityHandler,
    ) -> None:
        self._handlers[capability_id] = handler

    def resolve(self, capability_id: str) -> CapabilityHandler:
        try:
            return self._handlers[capability_id]
        except KeyError as error:
            raise LookupError("CAPABILITY_NOT_FOUND") from error

    def ids(self) -> list[str]:
        return sorted(self._handlers)


class CapabilityExecutor:
    def __init__(
        self,
        session: Session,
        registry: CapabilityRegistry,
        disabled_capabilities: set[str] | None = None,
    ) -> None:
        self.session = session
        self.registry = registry
        self.disabled_capabilities = disabled_capabilities or set()

    def execute(
        self,
        capability_id: str,
        input_data: BaseModel,
        context: ExecutionContext,
    ) -> BaseModel:
        invocation = CapabilityInvocationModel(
            capability_id=capability_id,
            request_id=context.request_id,
            actor_type=context.actor_type,
            actor_id=context.actor_id,
            input_digest=_digest(input_data),
        )
        self.session.add(invocation)
        self.session.commit()

        try:
            if capability_id in self.disabled_capabilities:
                raise CapabilityExecutionError(
                    "CAPABILITY_DISABLED",
                    status_code=403,
                )
            output = self.registry.resolve(capability_id)(input_data, context)
            output_status = getattr(output, "status", None)
            if output_status in {"partial", "failed"}:
                invocation.status = output_status
            else:
                invocation.status = "completed"
            if output_status == "failed":
                invocation.error_code = self._result_error_code(output)
            invocation.output_digest = _digest(output)
            return output
        except CapabilityExecutionError as error:
            invocation.status = "failed"
            invocation.error_code = error.code
            raise
        except Exception:
            invocation.status = "failed"
            invocation.error_code = "CAPABILITY_EXECUTION_FAILED"
            raise
        finally:
            invocation.completed_at = datetime.now(timezone.utc)
            self.session.commit()

    @staticmethod
    def _result_error_code(output: BaseModel) -> str:
        errors = getattr(output, "errors", None)
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            error_code = errors[0].get("error_code")
            if isinstance(error_code, str):
                return error_code
        return "CAPABILITY_RESULT_FAILED"
