"""In-app уведомления. Здесь же — точки расширения на e-mail/Telegram/push."""
from __future__ import annotations

import uuid
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User

ORDER_PUBLISHED = "ORDER_PUBLISHED"
ORDER_ACK_DEADLINE = "ORDER_ACK_DEADLINE"
TASK_ASSIGNED = "TASK_ASSIGNED"
TASK_STATUS_CHANGED = "TASK_STATUS_CHANGED"
TASK_COMMENT = "TASK_COMMENT"
ORDER_UPDATED = "ORDER_UPDATED"
ORDER_RECIPIENTS = "ORDER_RECIPIENTS"
TASK_MARK = "TASK_MARK"
PLAN_PUBLISHED = "PLAN_PUBLISHED"
PLAN_UPDATED = "PLAN_UPDATED"


async def push(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    type_: str,
    title: str,
    body: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> Notification:
    n = Notification(
        user_id=user_id,
        type=type_,
        title=title[:300],
        body=(body[:1000] if body else None),
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )
    session.add(n)
    await session.flush()
    # TODO(prod): fan-out во внешние каналы (e-mail через брокер, Telegram-бот, WebPush).
    return n


async def push_many(
    session: AsyncSession,
    *,
    user_ids: Iterable[uuid.UUID],
    type_: str,
    title: str,
    body: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> int:
    count = 0
    for uid in user_ids:
        await push(
            session,
            user_id=uid,
            type_=type_,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
        count += 1
    return count


async def notify_order_published(session: AsyncSession, order, recipients: list[User]) -> int:
    return await push_many(
        session,
        user_ids=[u.id for u in recipients],
        type_=ORDER_PUBLISHED,
        title=f"Новый приказ №{order.number} — требуется ознакомление",
        body=order.title,
        entity_type="order",
        entity_id=order.id,
        payload={"ack_deadline": str(order.ack_deadline) if order.ack_deadline else None},
    )


async def notify_task_assigned(
    session: AsyncSession, task, actor: User, assignee_ids: list[uuid.UUID] | None = None
) -> int:
    """Уведомляет исполнителей о назначении (по умолчанию — всех исполнителей задачи)."""
    ids = assignee_ids if assignee_ids is not None else list(task.assignee_ids)
    ids = [uid for uid in ids if uid and uid != actor.id]
    if not ids:
        return 0
    total = len(task.assignees) if hasattr(task, "assignees") else len(ids)
    body = f"Постановщик: {actor.full_name}"
    if total > 1:
        body += f" · исполнителей: {total}"
    return await push_many(
        session,
        user_ids=ids,
        type_=TASK_ASSIGNED,
        title=f"Новая задача: {task.title}",
        body=body,
        entity_type="task",
        entity_id=task.id,
    )


async def notify_task_status(session: AsyncSession, task, actor: User, from_status: str | None) -> None:
    ids = set(task.assignee_ids) | ({task.creator_id} if task.creator_id else set())
    for uid in ids:
        if uid is None or uid == actor.id:
            continue
        await push(
            session,
            user_id=uid,
            type_=TASK_STATUS_CHANGED,
            title=f"Задача «{task.title}»: статус → {task.status}",
            body=f"Изменил(а): {actor.full_name}",
            entity_type="task",
            entity_id=task.id,
            payload={"from": from_status, "to": task.status},
        )


async def notify_task_mark(session: AsyncSession, task, actor: User, *, done: int, total: int, all_done: bool) -> None:
    """Постановщику — об отметке исполнителя (и о закрытии задачи, если отметки поставили все)."""
    if task.creator_id is None or task.creator_id == actor.id:
        return
    if all_done:
        title = f"Задача «{task.title}» выполнена — отметки поставили все исполнители"
        type_ = TASK_STATUS_CHANGED
    else:
        title = f"{actor.full_name} отметил(а) «выполнено» в задаче «{task.title}»"
        type_ = TASK_MARK
    await push(
        session,
        user_id=task.creator_id,
        type_=type_,
        title=title,
        body=f"Отметились {done} из {total}",
        entity_type="task",
        entity_id=task.id,
        payload={"done": done, "total": total, "all_done": all_done},
    )


async def notify_task_comment(session: AsyncSession, task, actor: User, body: str) -> None:
    ids = set(task.assignee_ids) | ({task.creator_id} if task.creator_id else set())
    for uid in ids:
        if uid is None or uid == actor.id:
            continue
        await push(
            session,
            user_id=uid,
            type_=TASK_COMMENT,
            title=f"Комментарий в задаче «{task.title}»",
            body=f"{actor.full_name}: {body[:200]}",
            entity_type="task",
            entity_id=task.id,
        )


async def notify_plan_published(session: AsyncSession, plan, responsible_ids: list[uuid.UUID], actor: User) -> int:
    """Публикация плана работы: уведомляем всех ответственных (кроме автора публикации)."""
    ids = [uid for uid in responsible_ids if uid and uid != actor.id]
    if not ids:
        return 0
    week = f"{plan.week_start:%d.%m.%Y}–{plan.week_end:%d.%m.%Y}"
    return await push_many(
        session,
        user_ids=ids,
        type_=PLAN_PUBLISHED,
        title=f"Опубликован план работы на неделю {week}",
        body="Вы отмечены ответственным — откройте план, чтобы увидеть свои мероприятия",
        entity_type="plan",
        entity_id=plan.id,
        payload={"week_start": str(plan.week_start), "week_end": str(plan.week_end)},
    )
