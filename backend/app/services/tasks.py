"""Сервис Task Manager (v1.2 — несколько исполнителей, личные отметки, вложения).

Ключевые проектные решения:
  * «Просрочена» (OVERDUE) — ВЫЧИСЛЯЕМОЕ состояние: (status != DONE) AND (deadline < now).
    Хранить его нельзя (устаревает само), поэтому оно считается в SQL-предикатах
    и отдаётся полями effective_status / is_overdue / days_left.
  * Исполнителей НЕСКОЛЬКО (task_assignees). У каждого — своя отметка «выполнено»
    (done_at). Отметились все → задача автоматически закрывается (DONE);
    снятие отметки возвращает задачу в IN_PROGRESS. Ручные переходы статуса
    администрацией работают как раньше (state machine).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from fastapi import UploadFile
from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.enums import OVERDUE, TASK_TRANSITIONS, Role, TaskStatus
from app.errors import bad_request, conflict, forbidden, not_found
from app.models.task import Task, TaskAssignee, TaskComment, TaskFile, TaskPriority, TaskStatusHistory
from app.models.user import User
from app.schemas.task import TaskCreateIn, TaskUpdateIn
from app.dbutils import ilike
from app.services import audit, notifications
from app.services.storage import storage
from app.types import enum_value

# ----------------------------------------------------------------- вычисления
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_overdue(task: Task, now: datetime | None = None) -> bool:
    now = _aware(now) or utcnow()
    deadline = _aware(task.deadline)
    return bool(deadline and enum_value(task.status) != TaskStatus.DONE.value and deadline < now)


def effective_status(task: Task, now: datetime | None = None) -> str:
    if is_overdue(task, now):
        return OVERDUE
    return enum_value(task.status)


def days_left(task: Task, now: datetime | None = None) -> int | None:
    """Сколько полных суток осталось до дедлайна (отрицательное = просрочено)."""
    deadline = _aware(task.deadline)
    if deadline is None:
        return None
    now = _aware(now) or utcnow()
    return (deadline - now).days


def _status_value(task: Task) -> str:
    return enum_value(task.status)


# ------------------------------------------------------------------- доступы
def is_assignee(actor: User, task: Task) -> bool:
    return any(a.user_id == actor.id for a in task.assignees)


def can_edit(actor: User, task: Task) -> bool:
    """Кто может менять задачу.

    OWNER/ADMIN  — любую (постановщики);
    TEACHER      — только где он исполнитель, и только рабочие поля
                    (статус/описание/комментарии/отметка/вложения),
                    без переназначения, дедлайна и приоритета.
    """
    if actor.role in (Role.OWNER, Role.ADMIN):
        return True
    return is_assignee(actor, task)


def can_see(actor: User, task: Task) -> bool:
    if actor.role in (Role.OWNER, Role.ADMIN):
        return True                       # админ видит ВСЕ задачи
    return is_assignee(actor, task) or task.creator_id == actor.id


def ensure_can_edit(actor: User, task: Task) -> None:
    if not can_edit(actor, task):
        raise forbidden("Вы не можете редактировать эту задачу")


# ------------------------------------------------------------------- запросы
def _base_select() -> Select:
    return select(Task).options(
        selectinload(Task.creator),
        selectinload(Task.assignees).selectinload(TaskAssignee.user),
        selectinload(Task.files).selectinload(TaskFile.uploaded_by),
    )


def scope_filter(actor: User):
    """Row-level scoping: учитель — только свои задачи (исполнитель или постановщик)."""
    if actor.role in (Role.OWNER, Role.ADMIN):
        return None
    assigned = exists().where(and_(TaskAssignee.task_id == Task.id, TaskAssignee.user_id == actor.id))
    return or_(assigned, Task.creator_id == actor.id)


async def _resolve_assignees(session: AsyncSession, ids: Sequence[uuid.UUID]) -> list[User]:
    """Валидация списка исполнителей: существуют, активны, без дублей."""
    unique = list(dict.fromkeys(ids))
    if not unique:
        return []
    rows = await session.execute(select(User).where(User.id.in_(unique)))
    found = {u.id: u for u in rows.scalars().all()}
    users: list[User] = []
    for uid in unique:
        user = found.get(uid)
        if user is None or not user.is_active:
            raise bad_request("Исполнитель не найден или заблокирован")
        users.append(user)
    return users


async def list_tasks(
    session: AsyncSession,
    actor: User,
    *,
    status: str | None = None,          # NEW | IN_PROGRESS | DONE | OVERDUE
    assignee_id: uuid.UUID | None = None,
    creator_id: uuid.UUID | None = None,
    priority: str | None = None,
    search: str | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    sort: str = "deadline",             # deadline | created | priority | title
    order: str = "asc",
    page: int = 1,
    per_page: int = 20,
) -> tuple[Sequence[Task], int, dict[str, int]]:
    now = utcnow()
    conds = []

    scoped = scope_filter(actor)
    if scoped is not None:
        conds.append(scoped)

    if assignee_id:
        if actor.role == Role.TEACHER and assignee_id != actor.id:
            raise forbidden("Учитель может фильтровать только по себе")
        conds.append(exists().where(and_(TaskAssignee.task_id == Task.id, TaskAssignee.user_id == assignee_id)))
    if creator_id:
        conds.append(Task.creator_id == creator_id)
    if priority:
        conds.append(Task.priority == priority)
    if search:
        conds.append(or_(ilike(Task.title, search), ilike(Task.description, search)))
    if due_after:
        conds.append(Task.deadline >= due_after)
    if due_before:
        conds.append(Task.deadline <= due_before)

    # статус-фильтр (OVERDUE — составной предикат)
    if status:
        status = status.upper()
        if status == OVERDUE:
            conds.append(and_(Task.deadline.is_not(None), Task.deadline < now, Task.status != TaskStatus.DONE))
        elif status in {s.value for s in TaskStatus}:
            if status == TaskStatus.DONE.value:
                conds.append(Task.status == TaskStatus.DONE.value)
            else:
                conds.append(and_(Task.status == TaskStatus(status), or_(Task.deadline.is_(None), Task.deadline >= now)))
        else:
            raise bad_request(f"Неизвестный статус: {status}")

    stmt = _base_select()
    count_stmt = select(func.count()).select_from(Task)
    if conds:
        stmt = stmt.where(and_(*conds))
        count_stmt = count_stmt.where(and_(*conds))

    total = int((await session.execute(count_stmt)).scalar_one())

    sort_map = {
        "deadline": (Task.deadline.is_(None), Task.deadline),
        "created": (Task.created_at,),
        "priority": (Task.priority,),
        "title": (Task.title,),
        "updated": (Task.updated_at,),
    }
    cols = sort_map.get(sort, sort_map["deadline"])
    stmt = stmt.order_by(*[c.desc() if order == "desc" else c.asc() for c in cols])
    stmt = stmt.limit(per_page).offset((page - 1) * per_page)

    tasks = (await session.execute(stmt)).scalars().all()
    counts = await status_counts(session, actor)
    return tasks, total, counts


async def status_counts(session: AsyncSession, actor: User) -> dict[str, int]:
    """Счётчики по статусам (включая вычисляемый OVERDUE) в пределах видимости пользователя."""
    now = utcnow()
    base = select(func.count()).select_from(Task)
    scoped = scope_filter(actor)
    if scoped is not None:
        base = base.where(scoped)

    async def count(*extra) -> int:
        stmt = base.where(and_(*extra)) if extra else base
        return int((await session.execute(stmt)).scalar_one())

    done = await count(Task.status == TaskStatus.DONE)
    overdue = await count(
        Task.deadline.is_not(None), Task.deadline < now, Task.status != TaskStatus.DONE
    )
    new = await count(Task.status == TaskStatus.NEW, or_(Task.deadline.is_(None), Task.deadline >= now))
    in_progress = await count(
        Task.status == TaskStatus.IN_PROGRESS, or_(Task.deadline.is_(None), Task.deadline >= now)
    )
    return {
        "all": done + overdue + new + in_progress,
        TaskStatus.NEW.value: new,
        TaskStatus.IN_PROGRESS.value: in_progress,
        TaskStatus.DONE.value: done,
        OVERDUE: overdue,
    }


async def get_task(session: AsyncSession, task_id: uuid.UUID, actor: User, *, with_details: bool = True) -> Task:
    stmt = _base_select()
    if with_details:
        stmt = stmt.options(
            selectinload(Task.comments).selectinload(TaskComment.author),
            selectinload(Task.history).selectinload(TaskStatusHistory.actor),
        )
    task = (await session.execute(stmt.where(Task.id == task_id))).scalar_one_or_none()
    if task is None:
        raise not_found("Задача")
    if not can_see(actor, task):
        # 403, а не 404: факт существования задачи не скрываем от сотрудника школы
        raise forbidden("Нет доступа к этой задаче")
    return task


# --------------------------------------------------------------------- CRUD
async def create_task(session: AsyncSession, actor: User, data: TaskCreateIn) -> Task:
    if actor.role == Role.TEACHER:
        raise forbidden("Создавать задачи могут Владелец и Администрация")

    if data.priority not in TaskPriority.ALL:
        raise bad_request("Некорректный приоритет")

    assignees = await _resolve_assignees(session, data.assignee_ids)

    deadline = _aware(data.deadline)
    if deadline and deadline < utcnow():
        raise bad_request("Дедлайн не может быть в прошлом")

    task = Task(
        title=data.title.strip(),
        description=data.description,
        status=TaskStatus.NEW,
        priority=data.priority,
        creator_id=actor.id,
        deadline=deadline,
    )
    for user in assignees:
        task.assignees.append(TaskAssignee(user_id=user.id))
    session.add(task)
    await session.flush()

    session.add(
        TaskStatusHistory(task_id=task.id, from_status=None, to_status=TaskStatus.NEW.value, actor_id=actor.id,
                          note="Задача создана")
    )
    await notifications.notify_task_assigned(session, task, actor, [u.id for u in assignees])
    await audit.write_audit(
        session, actor=actor, action="TASK_CREATE", entity_type="task", entity_id=task.id,
        changes={"title": task.title, "assignees": [u.full_name for u in assignees], "deadline": str(task.deadline)},
    )
    await session.flush()
    return task


async def update_task(session: AsyncSession, actor: User, task: Task, data: TaskUpdateIn) -> Task:
    ensure_can_edit(actor, task)
    patch: dict[str, Any] = data.model_dump(exclude_unset=True)
    if not patch:
        return task

    is_teacher = actor.role == Role.TEACHER
    if is_teacher and set(patch) - {"description", "status"}:
        raise forbidden("Учитель может менять только описание и статус своей задачи")

    before = {
        "title": task.title, "description": task.description, "priority": task.priority,
        "assignees": sorted(str(x) for x in task.assignee_ids),
        "deadline": str(task.deadline), "status": _status_value(task),
    }

    if "status" in patch and patch["status"] is not None:
        await change_status(
            session, actor, task,
            patch["status"] if isinstance(patch["status"], TaskStatus) else TaskStatus(patch["status"]),
        )
    patch.pop("status", None)

    if "assignee_ids" in patch:
        new_ids = [uuid.UUID(str(x)) for x in (patch.pop("assignee_ids") or [])]
        users = await _resolve_assignees(session, new_ids)
        current = {a.user_id: a for a in task.assignees}
        target = {u.id for u in users}
        # убрать отсутствующих (вместе с их отметками), добавить новых
        for uid, row in list(current.items()):
            if uid not in target:
                await session.delete(row)
                task.assignees.remove(row)
        added = [u for u in users if u.id not in current]
        for user in added:
            task.assignees.append(TaskAssignee(task_id=task.id, user_id=user.id))
        await session.flush()
        if added:
            await notifications.notify_task_assigned(session, task, actor, [u.id for u in added])

    if "deadline" in patch:
        dl = _aware(patch.pop("deadline"))
        if dl and dl < utcnow() and _status_value(task) != TaskStatus.DONE.value:
            raise bad_request("Дедлайн не может быть в прошлом")
        task.deadline = dl

    if "priority" in patch:
        pr = patch.pop("priority")
        if pr not in TaskPriority.ALL:
            raise bad_request("Некорректный приоритет")
        task.priority = pr

    for field in ("title", "description"):
        if field in patch and patch[field] is not None:
            setattr(task, field, str(patch[field]).strip() if field == "title" else patch[field])

    await session.flush()

    after = {
        "title": task.title, "description": task.description, "priority": task.priority,
        "assignees": sorted(str(x) for x in task.assignee_ids),
        "deadline": str(task.deadline), "status": _status_value(task),
    }
    changes = audit.diff(before, after)
    if changes:
        await audit.write_audit(
            session, actor=actor, action="TASK_UPDATE", entity_type="task", entity_id=task.id, changes=changes
        )
        notify_ids = {a.user_id for a in task.assignees} | ({task.creator_id} if task.creator_id else set())
        if changes.keys() & {"deadline", "title", "description", "priority"}:
            await notifications.push_many(
                session,
                user_ids=[uid for uid in notify_ids if uid and uid != actor.id],
                type_=notifications.TASK_STATUS_CHANGED,
                title=f"Задача «{task.title}» обновлена",
                body=", ".join(changes.keys()),
                entity_type="task",
                entity_id=task.id,
                payload=changes,
            )
    return task


async def change_status(session: AsyncSession, actor: User, task: Task, new_status: TaskStatus) -> Task:
    ensure_can_edit(actor, task)
    current = _status_value(task)
    if current == new_status.value:
        return task
    if new_status.value not in TASK_TRANSITIONS.get(current, set()):
        raise conflict(f"Недопустимый переход статуса: {current} → {new_status.value}")

    task.status = new_status
    task.completed_at = utcnow() if new_status == TaskStatus.DONE else None

    session.add(
        TaskStatusHistory(
            task_id=task.id, from_status=current, to_status=new_status.value, actor_id=actor.id
        )
    )
    await session.flush()
    await notifications.notify_task_status(session, task, actor, current)
    await audit.write_audit(
        session, actor=actor, action="TASK_STATUS", entity_type="task", entity_id=task.id,
        changes={"from": current, "to": new_status.value},
    )
    return task


# ------------------------------------------------- отметки «выполнено» (v1.2)
async def set_my_mark(session: AsyncSession, actor: User, task: Task) -> Task:
    """Исполнитель отмечает СВОЮ часть выполненной.

    Автоматика статусов:
      * первая отметка (задача NEW)            → IN_PROGRESS;
      * отметились ВСЕ исполнители             → DONE (completed_at = сейчас);
    """
    row = task.mark_of(actor.id)
    if row is None:
        raise forbidden("Отмечаться могут только исполнители задачи")
    if row.done_at is not None:
        raise conflict("Отметка «выполнено» уже поставлена")

    now = utcnow()
    row.done_at = now
    current = _status_value(task)

    all_done = bool(task.assignees) and all(a.done_at is not None for a in task.assignees)
    if all_done and current != TaskStatus.DONE.value:
        task.status = TaskStatus.DONE
        task.completed_at = now
        session.add(TaskStatusHistory(
            task_id=task.id, from_status=current, to_status=TaskStatus.DONE.value, actor_id=actor.id,
            note="Все исполнители отметили «выполнено»",
        ))
    elif current == TaskStatus.NEW.value:
        task.status = TaskStatus.IN_PROGRESS
        session.add(TaskStatusHistory(
            task_id=task.id, from_status=current, to_status=TaskStatus.IN_PROGRESS.value, actor_id=actor.id,
            note="Исполнитель отметил «выполнено»",
        ))
    await session.flush()

    done = sum(1 for a in task.assignees if a.done_at is not None)
    await notifications.notify_task_mark(session, task, actor, done=done, total=len(task.assignees), all_done=all_done)
    await audit.write_audit(
        session, actor=actor, action="TASK_MARK", entity_type="task", entity_id=task.id,
        changes={"user": actor.full_name, "mark": "done", "progress": f"{done}/{len(task.assignees)}"},
    )
    return task


async def clear_my_mark(session: AsyncSession, actor: User, task: Task) -> Task:
    """Снять свою отметку. Если задача была закрыта по отметкам — вернуть в IN_PROGRESS."""
    row = task.mark_of(actor.id)
    if row is None:
        raise forbidden("Отмечаться могут только исполнители задачи")
    if row.done_at is None:
        raise conflict("Отметки нет — снимать нечего")

    row.done_at = None
    current = _status_value(task)
    if current == TaskStatus.DONE.value:
        task.status = TaskStatus.IN_PROGRESS
        task.completed_at = None
        session.add(TaskStatusHistory(
            task_id=task.id, from_status=current, to_status=TaskStatus.IN_PROGRESS.value, actor_id=actor.id,
            note="Снята отметка «выполнено»",
        ))
    await session.flush()

    done = sum(1 for a in task.assignees if a.done_at is not None)
    await notifications.notify_task_mark(session, task, actor, done=done, total=len(task.assignees), all_done=False)
    await audit.write_audit(
        session, actor=actor, action="TASK_MARK", entity_type="task", entity_id=task.id,
        changes={"user": actor.full_name, "mark": "cleared", "progress": f"{done}/{len(task.assignees)}"},
    )
    return task


# ---------------------------------------------------------------- комментарии
async def add_comment(session: AsyncSession, actor: User, task: Task, body: str) -> TaskComment:
    if not (can_see(actor, task)):
        raise forbidden("Нет доступа к этой задаче")
    comment = TaskComment(task_id=task.id, author_id=actor.id, body=body.strip())
    session.add(comment)
    await session.flush()
    await notifications.notify_task_comment(session, task, actor, body)
    return comment


async def delete_task(session: AsyncSession, actor: User, task: Task) -> None:
    if actor.role not in (Role.OWNER, Role.ADMIN):
        raise forbidden("Удалять задачи могут Владелец и Администрация")
    title = task.title
    for f in list(task.files):
        storage.delete(f.storage_path)
    await session.delete(task)
    await session.flush()
    await audit.write_audit(
        session, actor=actor, action="TASK_DELETE", entity_type="task", entity_id=task.id, changes={"title": title}
    )


# ------------------------------------------------------------------ вложения
async def add_file(session: AsyncSession, actor: User, task: Task, file: UploadFile) -> TaskFile:
    """Прикрепить файл к задаче. Может любой участник (исполнитель/постановщик/админ)."""
    if not can_see(actor, task):
        raise forbidden("Нет доступа к этой задаче")
    if not (is_assignee(actor, task) or task.creator_id == actor.id or actor.role in (Role.OWNER, Role.ADMIN)):
        raise forbidden("Прикреплять файлы могут участники задачи")

    mime = (file.content_type or "").lower()
    if mime not in settings.allowed_task_file_mimes:
        raise bad_request("Недопустимый тип файла: " + (mime or "не определён"))

    stored = await storage.save(file.file, file.filename or "file.bin", mime, allowed_mimes=settings.allowed_task_file_mimes)
    row = TaskFile(
        task_id=task.id,
        storage_path=stored.storage_path,
        original_name=stored.original_name,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        checksum=stored.checksum,
        uploaded_by_id=actor.id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(task, attribute_names=["files"])
    await audit.write_audit(
        session, actor=actor, action="TASK_FILE", entity_type="task", entity_id=task.id,
        changes={"file": row.original_name, "size": row.size_bytes},
    )
    return row


async def delete_file(session: AsyncSession, actor: User, task: Task, file_id: uuid.UUID) -> None:
    row = next((f for f in task.files if f.id == file_id), None)
    if row is None:
        raise not_found("Файл")
    is_manager = actor.role in (Role.OWNER, Role.ADMIN)
    if not (is_manager or row.uploaded_by_id == actor.id or task.creator_id == actor.id):
        raise forbidden("Удалить файл может загрузивший, постановщик или администрация")
    storage.delete(row.storage_path)
    await session.delete(row)
    await session.flush()
    await session.refresh(task, attribute_names=["files"])
    await audit.write_audit(
        session, actor=actor, action="TASK_FILE_DELETE", entity_type="task", entity_id=task.id,
        changes={"file": row.original_name},
    )


# -------------------------------------------------------------------- отчёты
async def overdue_report(session: AsyncSession, actor: User) -> list[dict[str, Any]]:
    """Список просроченных задач в разрезе исполнителей (для планёрки/отчёта)."""
    now = utcnow()
    stmt = (
        _base_select()
        .where(and_(Task.deadline.is_not(None), Task.deadline < now, Task.status != TaskStatus.DONE))
        .order_by(Task.deadline.asc())
    )
    scoped = scope_filter(actor)
    if scoped is not None:
        stmt = stmt.where(scoped)
    tasks = (await session.execute(stmt)).scalars().all()
    result: list[dict[str, Any]] = []
    for t in tasks:
        deadline = _aware(t.deadline)
        result.append(
            {
                "id": str(t.id),
                "title": t.title,
                "assignees": [u.full_name for u in t.assignee_users] or ["Не назначен"],
                "assignee_ids": [str(x) for x in t.assignee_ids],
                "deadline": deadline.isoformat() if deadline else None,
                "overdue_by_days": int((now - deadline).total_seconds() // 86400) if deadline else None,
                "status": _status_value(t),
                "priority": t.priority,
            }
        )
    return result
