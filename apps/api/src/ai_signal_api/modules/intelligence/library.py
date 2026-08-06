from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_signal_api.models import (
    IntelligenceItemModel,
    SavedViewModel,
    WorkspaceItemStateModel,
)
from ai_signal_api.schemas import (
    SavedViewCreate,
    SavedViewPatch,
    WorkspaceItemStatePatch,
    WorkspaceItemStateRead,
)


class InformationLibraryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def update_state(
        self,
        item_id: str,
        payload: WorkspaceItemStatePatch,
    ) -> WorkspaceItemStateRead:
        if self.session.get(IntelligenceItemModel, item_id) is None:
            raise LookupError("INFORMATION_NOT_FOUND")
        state = self.session.scalar(
            select(WorkspaceItemStateModel).where(
                WorkspaceItemStateModel.intelligence_item_id == item_id
            )
        )
        if state is None:
            state = WorkspaceItemStateModel(
                intelligence_item_id=item_id
            )
            self.session.add(state)
        now = datetime.now(timezone.utc)
        if payload.seen is not None:
            state.seen_at = now if payload.seen else None
        if payload.starred is not None:
            state.starred = payload.starred
        if payload.archived is not None:
            state.archived_at = now if payload.archived else None
        if "snoozed_until" in payload.model_fields_set:
            state.snoozed_until = payload.snoozed_until
        if payload.note is not None:
            state.note = payload.note
        self.session.commit()
        return self._state_read(state)

    def list_views(self) -> list[SavedViewModel]:
        return list(
            self.session.scalars(
                select(SavedViewModel).order_by(
                    SavedViewModel.pinned.desc(),
                    SavedViewModel.created_at,
                )
            )
        )

    def create_view(self, payload: SavedViewCreate) -> SavedViewModel:
        if payload.is_default:
            self._clear_default()
        view = SavedViewModel(**payload.model_dump())
        self.session.add(view)
        self.session.commit()
        return view

    def patch_view(
        self,
        view_id: str,
        payload: SavedViewPatch,
    ) -> SavedViewModel:
        view = self.session.get(SavedViewModel, view_id)
        if view is None:
            raise LookupError("SAVED_VIEW_NOT_FOUND")
        values = payload.model_dump(exclude_unset=True)
        if values.get("is_default") is True:
            self._clear_default()
        for key, value in values.items():
            setattr(view, key, value)
        self.session.commit()
        return view

    def delete_view(self, view_id: str) -> None:
        view = self.session.get(SavedViewModel, view_id)
        if view is None:
            raise LookupError("SAVED_VIEW_NOT_FOUND")
        self.session.delete(view)
        self.session.commit()

    def _clear_default(self) -> None:
        for view in self.session.scalars(
            select(SavedViewModel).where(
                SavedViewModel.is_default.is_(True)
            )
        ):
            view.is_default = False

    @staticmethod
    def _state_read(
        state: WorkspaceItemStateModel,
    ) -> WorkspaceItemStateRead:
        return WorkspaceItemStateRead(
            intelligence_item_id=state.intelligence_item_id,
            seen=state.seen_at is not None,
            starred=state.starred,
            archived=state.archived_at is not None,
            snoozed_until=state.snoozed_until,
            note=state.note,
        )
