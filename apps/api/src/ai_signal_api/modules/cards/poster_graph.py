from __future__ import annotations

from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ai_signal_api.modules.cards.service import CardService
from ai_signal_api.schemas import CardGenerateInput


class PosterState(TypedDict, total=False):
    item_ids: list[str]
    max_chars: int
    approved_item_ids: list[str]
    draft_approved: bool
    render_approved: bool
    card_ids: list[str]
    rendered_artifact_ids: list[str]
    errors: list[dict[str, str]]
    status: str


class PosterGraphRunner:
    """LangGraph implementation of graph-specs Poster Graph v1.0.0."""

    def __init__(
        self,
        cards: CardService,
        *,
        artifact_root,
        artifact_max_bytes: int,
        checkpointer: MemorySaver,
    ) -> None:
        self.cards = cards
        self.artifact_root = artifact_root
        self.artifact_max_bytes = artifact_max_bytes
        graph = StateGraph(PosterState)
        graph.add_node("load_approved_items", self._load_approved_items)
        graph.add_node(
            "confirm_draft_generation",
            self._confirm_draft_generation,
        )
        graph.add_node("generate_drafts", self._generate_drafts)
        graph.add_node("save_drafts", self._save_drafts)
        graph.add_node("confirm_render", self._confirm_render)
        graph.add_node("render_cards", self._render_cards)
        graph.add_node("complete", self._complete)
        graph.add_edge(START, "load_approved_items")
        graph.add_edge(
            "load_approved_items",
            "confirm_draft_generation",
        )
        graph.add_edge("confirm_draft_generation", "generate_drafts")
        graph.add_edge("generate_drafts", "save_drafts")
        graph.add_edge("save_drafts", "confirm_render")
        graph.add_edge("confirm_render", "render_cards")
        graph.add_edge("render_cards", "complete")
        graph.add_edge("complete", END)
        self.graph = graph.compile(checkpointer=checkpointer)

    def advance(
        self,
        thread_id: str,
        *,
        input_state: PosterState | None = None,
        approval: bool | None = None,
    ) -> dict[str, Any]:
        config = {"configurable": {"thread_id": thread_id}}
        command: PosterState | Command
        if approval is None:
            command = input_state or {}
        else:
            command = Command(resume={"approved": approval})
        result = self.graph.invoke(command, config=config)
        interruptions = result.get("__interrupt__", ())
        if interruptions:
            return {
                "thread_id": thread_id,
                "status": "waiting_approval",
                "interrupt": interruptions[0].value,
                "card_ids": result.get("card_ids", []),
                "rendered_artifact_ids": result.get(
                    "rendered_artifact_ids", []
                ),
                "errors": result.get("errors", []),
            }
        return {
            "thread_id": thread_id,
            "status": result.get("status", "completed"),
            "interrupt": None,
            "card_ids": result.get("card_ids", []),
            "rendered_artifact_ids": result.get(
                "rendered_artifact_ids", []
            ),
            "errors": result.get("errors", []),
        }

    def _load_approved_items(self, state: PosterState) -> PosterState:
        return {"approved_item_ids": state.get("item_ids", [])}

    def _confirm_draft_generation(
        self,
        state: PosterState,
    ) -> PosterState:
        response = interrupt(
            {
                "phase": "confirm_draft_generation",
                "message": "确认根据审核保留项生成可编辑卡片草稿。",
                "item_ids": state.get("approved_item_ids", []),
            }
        )
        return {"draft_approved": bool(response.get("approved"))}

    def _generate_drafts(self, state: PosterState) -> PosterState:
        if not state.get("draft_approved"):
            return {"status": "cancelled"}
        return {"status": "draft_approved"}

    def _save_drafts(self, state: PosterState) -> PosterState:
        if not state.get("draft_approved"):
            return {"card_ids": []}
        result = self.cards.generate(
            CardGenerateInput(
                item_ids=state.get("approved_item_ids", []),
                max_chars=state.get("max_chars", 400),
            )
        )
        return {"card_ids": result.card_ids}

    def _confirm_render(self, state: PosterState) -> PosterState:
        if not state.get("card_ids"):
            return {"render_approved": False}
        response = interrupt(
            {
                "phase": "confirm_render",
                "message": "确认将卡片渲染为本地 PNG Artifact。",
                "card_ids": state["card_ids"],
            }
        )
        return {"render_approved": bool(response.get("approved"))}

    def _render_cards(self, state: PosterState) -> PosterState:
        if not state.get("render_approved"):
            return {"status": "drafts_saved"}
        artifacts: list[str] = []
        errors: list[dict[str, str]] = []
        for card_id in state.get("card_ids", []):
            try:
                result = self.cards.render(
                    card_id,
                    artifact_root=self.artifact_root,
                    artifact_max_bytes=self.artifact_max_bytes,
                )
                artifacts.append(result.artifact_id)
            except Exception as error:
                errors.append(
                    {
                        "card_id": card_id,
                        "error_code": "POSTER_RENDER_FAILED",
                        "message": str(error),
                    }
                )
        return {
            "rendered_artifact_ids": artifacts,
            "errors": errors,
            "status": "partial" if errors else "rendered",
        }

    @staticmethod
    def _complete(state: PosterState) -> PosterState:
        if state.get("status") in {"cancelled", "drafts_saved", "partial"}:
            return {}
        return {"status": "completed"}
