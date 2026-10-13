"""Лёгкий миграционный раннер (идемпотентный, без внешних зависимостей).

Зачем: на Synology NAS развёртывание должно быть «скопировал папку → поднял контейнер»,
без обязательного прогона Alembic. Поэтому при старте приложения схема приводится
к актуальному состоянию набором версионированных шагов: каждый шаг проверяет
текущее состояние БД и применяет только отсутствующие изменения.

Для больших инсталляций рекомендуется Alembic (см. docs/DEPLOY-NAS.md → «Миграции»).
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger("schoolhub.migrations")


async def _has_column(conn: AsyncConnection, table: str, column: str) -> bool:
    dialect = conn.engine.dialect.name
    if dialect == "postgresql":
        row = await conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c LIMIT 1"
            ),
            {"t": table, "c": column},
        )
    else:  # sqlite
        rows = await conn.execute(text(f'PRAGMA table_info("{table}")'))
        return any(r[1] == column for r in rows.fetchall())
    return row.first() is not None


async def _has_index(conn: AsyncConnection, index: str) -> bool:
    dialect = conn.engine.dialect.name
    if dialect == "postgresql":
        row = await conn.execute(text("SELECT 1 FROM pg_indexes WHERE indexname = :i LIMIT 1"), {"i": index})
        return row.first() is not None
    rows = await conn.execute(text("SELECT 1 FROM sqlite_master WHERE type='index' AND name = :i"), {"i": index})
    return rows.first() is not None


Step = Callable[[AsyncConnection], Awaitable[bool]]


async def _m001_ad_columns(conn: AsyncConnection) -> bool:
    """Колонки интеграции с Active Directory в таблице users. Возвращает True, если были изменения."""
    changed = False
    columns = {
        "auth_source": "VARCHAR(16) NOT NULL DEFAULT 'local'",
        "domain_account": "VARCHAR(120)",
        "dn": "VARCHAR(512)",
        "ad_groups": "JSON" if conn.engine.dialect.name != "postgresql" else "JSONB",
        "last_ad_sync_at": "TIMESTAMP",
    }
    for column, ddl in columns.items():
        if not await _has_column(conn, "users", column):
            await conn.execute(text(f"ALTER TABLE users ADD COLUMN {column} {ddl}"))
            logger.info("migrations: users.%s добавлена", column)
            changed = True

    if not await _has_index(conn, "ix_users_domain_account"):
        await conn.execute(text("CREATE UNIQUE INDEX ix_users_domain_account ON users (domain_account)"))
        logger.info("migrations: индекс ix_users_domain_account создан")
        changed = True
    if not await _has_index(conn, "ix_users_auth_source"):
        await conn.execute(text("CREATE INDEX ix_users_auth_source ON users (auth_source)"))
        changed = True
    return changed


async def _m002_setup_state(conn: AsyncConnection) -> bool:
    """Таблица состояния первоначальной настройки (для уже работающих инсталляций)."""
    from app.database import Base
    from app.models.setup import SetupState  # noqa: F401 — регистрация таблицы в metadata

    table = SetupState.__table__
    if conn.engine.dialect.name == "sqlite":
        exists = (
            await conn.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='setup_state'"))
        ).first() is not None
    else:
        exists = (
            await conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name='setup_state' LIMIT 1")
            )
        ).first() is not None
    if exists:
        return False

    await conn.run_sync(lambda sync_conn: table.create(sync_conn, checkfirst=True))
    logger.info("migrations: создана таблица setup_state")
    return True


async def _m003_task_multiassignee(conn: AsyncConnection) -> bool:
    """v1.2: несколько исполнителей у задачи.

    1) переносим tasks.assignee_id -> task_assignees (таблицу создаёт create_all);
    2) добавляем orders.recipient_ids (выбранный круг ознакомления);
    3) убираем устаревшую колонку tasks.assignee_id.
    """
    import uuid as _uuid

    changed = False
    dialect = conn.engine.dialect.name

    if await _has_column(conn, "tasks", "assignee_id"):
        # копируем старые назначения (идемпотентно: только отсутствующие строки)
        rows = (
            await conn.execute(
                text("SELECT id, assignee_id FROM tasks WHERE assignee_id IS NOT NULL")
            )
        ).fetchall()
        for task_id, assignee_id in rows:
            exists_row = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM task_assignees WHERE task_id = :t AND user_id = :u LIMIT 1"
                    ),
                    {"t": str(task_id), "u": str(assignee_id)},
                )
            ).first()
            if exists_row:
                continue
            await conn.execute(
                text(
                    "INSERT INTO task_assignees (id, task_id, user_id, done_at, created_at) "
                    "VALUES (:id, :t, :u, NULL, CURRENT_TIMESTAMP)"
                ),
                {"id": str(_uuid.uuid4()), "t": str(task_id), "u": str(assignee_id)},
            )
            changed = True
        if rows:
            logger.info("migrations: перенесено назначений tasks.assignee_id -> task_assignees: %d", len(rows))

        # отметки «выполнено» для старых завершённых задач — чтобы история выглядела целостно
        await conn.execute(
            text(
                "UPDATE task_assignees SET done_at = CURRENT_TIMESTAMP "
                "WHERE done_at IS NULL AND task_id IN (SELECT id FROM tasks WHERE status = 'DONE')"
            )
        )
        # задачи «в работе» с единственным исполнителем считаем начатыми им
        try:
            await conn.execute(text("ALTER TABLE tasks DROP COLUMN assignee_id"))
            logger.info("migrations: колонка tasks.assignee_id удалена")
            changed = True
        except Exception:  # pragma: no cover — старый SQLite без DROP COLUMN: колонка останется, но не используется
            logger.warning("migrations: не удалось удалить tasks.assignee_id — колонка оставлена (не используется)")

    if not await _has_column(conn, "orders", "recipient_ids"):
        ddl = "JSONB" if dialect == "postgresql" else "JSON"
        await conn.execute(text(f"ALTER TABLE orders ADD COLUMN recipient_ids {ddl}"))
        logger.info("migrations: orders.recipient_ids добавлена")
        changed = True

    return changed


MIGRATIONS: dict[str, Step] = {
    "m001_ad_columns": _m001_ad_columns,
    "m002_setup_state": _m002_setup_state,
    "m003_task_multiassignee": _m003_task_multiassignee,
}


async def run_migrations(conn: AsyncConnection) -> list[str]:
    """Применяет все шаги. Возвращает список шагов, которые ФАКТИЧЕСКИ что-то изменили.

    Каждый шаг идемпотентен: сам проверяет текущее состояние схемы, поэтому
    повторный запуск (каждый старт контейнера) безопасен и ничего не ломает.
    """
    applied: list[str] = []
    for name, step in MIGRATIONS.items():
        if await step(conn):
            applied.append(name)
    return applied
