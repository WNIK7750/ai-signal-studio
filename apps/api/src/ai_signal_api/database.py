from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///"):
        sqlite_path = database_url.removeprefix("sqlite:///")
        if sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

    connect_args = (
        {"check_same_thread": False}
        if database_url.startswith("sqlite")
        else {}
    )
    return create_engine(database_url, connect_args=connect_args)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def ensure_runtime_schema(engine: Engine) -> None:
    """Apply small additive SQLite upgrades for local existing workspaces."""
    if engine.dialect.name != "sqlite":
        return
    additions = {
        "agent_conversations": {
            "title_source": "VARCHAR(24) NOT NULL DEFAULT 'auto'",
            "pinned_at": "DATETIME",
            "archived_at": "DATETIME",
            "deleted_at": "DATETIME",
            "active_turn_id": "VARCHAR(64)",
            "last_message_at": "DATETIME",
            "unread": "BOOLEAN NOT NULL DEFAULT 0",
        },
        "source_configs": {
            "health_status": "VARCHAR(24) NOT NULL DEFAULT 'unknown'",
            "last_success_at": "DATETIME",
            "last_error_at": "DATETIME",
            "last_error_code": "VARCHAR(80)",
            "last_items_count": "INTEGER NOT NULL DEFAULT 0",
        },
        "collection_runs": {
            "coverage_status": "VARCHAR(24) NOT NULL DEFAULT 'unknown'",
            "task_id": "VARCHAR(64)",
            "task_version_id": "VARCHAR(64)",
            "trigger_type": "VARCHAR(24) NOT NULL DEFAULT 'manual'",
            "parent_run_id": "VARCHAR(64)",
            "idempotency_key": "VARCHAR(160)",
            "source_version_ids": "JSON NOT NULL DEFAULT '[]'",
            "funnel_counts": "JSON NOT NULL DEFAULT '{}'",
            "warning_codes": "JSON NOT NULL DEFAULT '[]'",
        },
        "agent_messages": {
            "task_draft": "JSON",
            "turn_id": "VARCHAR(64)",
        },
        "agent_turns": {
            "lease_owner": "VARCHAR(120)",
            "lease_expires_at": "DATETIME",
            "deadline_at": "DATETIME",
        },
        "cards": {
            "revision": "INTEGER NOT NULL DEFAULT 1",
            "template_id": "VARCHAR(40) NOT NULL DEFAULT 'offline-quote'",
            "cover_source": "VARCHAR(24) NOT NULL DEFAULT 'offline'",
            "render_status": (
                "VARCHAR(24) NOT NULL DEFAULT 'not_rendered'"
            ),
            "rendered_artifact_id": "VARCHAR(64)",
            "rendered_revision": "INTEGER",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, columns in additions.items():
            if not inspector.has_table(table_name):
                continue
            existing = {
                column["name"]
                for column in inspector.get_columns(table_name)
            }
            for column_name, definition in columns.items():
                if column_name in existing:
                    continue
                connection.exec_driver_sql(
                    f'ALTER TABLE "{table_name}" '
                    f'ADD COLUMN "{column_name}" {definition}'
                )
        if inspector.has_table("agent_conversations"):
            connection.exec_driver_sql(
                """
                UPDATE agent_conversations
                SET last_message_at = COALESCE(
                    (
                        SELECT MAX(agent_messages.created_at)
                        FROM agent_messages
                        WHERE agent_messages.conversation_id =
                            agent_conversations.id
                    ),
                    updated_at
                )
                WHERE last_message_at IS NULL
                """
            )
            connection.exec_driver_sql(
                """
                UPDATE agent_conversations
                SET archived_at = COALESCE(archived_at, updated_at)
                WHERE status = 'archived' AND archived_at IS NULL
                """
            )


def session_scope(
    session_factory: sessionmaker[Session],
) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
