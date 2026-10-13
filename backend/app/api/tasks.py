"""API Task Manager (v1.2).

Видимость:
  OWNER/ADMIN — все задачи школы, любые назначения;
  TEACHER     — только свои (где он исполнитель или постановщик), статус/описание/
                комментарии/отметка «выполнено»/вложения.

Исполнителей у задачи может быть НЕСКОЛЬКО; у каждого — своя отметка «выполнено»
(POST/DELETE /tasks/{id}/my-mark). Когда отметки поставили все — задача закрывается.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.enums import Role, TaskStatus
from app.errors import forbidden, not_found
from app.models.task import Task, TaskFile
from app.models.user import User
from app.schemas.common import Page
from app.schemas.task import (
    CommentIn,
    CommentOut,
    StatusChangeIn,
    TaskCreateIn,
    TaskDetailOut,
    TaskOut,
    TaskUpdateIn,
)
from app.security import CurrentUser, SessionDep, require_role
from app.services import tasks as service
from app.services.storage import storage

router = APIRouter(prefix="/tasks", tags=["tasks"])

ManagerDep = Annotated[User, Depends(require_role(Role.ADMIN))]


# ---------------------------------------------------------------- serializers
def _task_out(task: Task, actor: User) -> TaskOut:
    my = task.mark_of(actor.id)
    return TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        effective_status=service.effective_status(task),
        priority=task.priority,
        deadline=task.deadline,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
        creator=task.creator,
        assignees=list(task.assignees),
        is_overdue=service.is_overdue(task),
        days_left=service.days_left(task),
        can_edit=service.can_edit(actor, task),
        can_mark=my is not None,
        my_done=bool(my and my.done_at),
        marks_done=task.marks_done,
        files_count=len(task.files),
    )


def _task_detail(task: Task, actor: User) -> TaskDetailOut:
    base = _task_out(task, actor).model_dump()
    return TaskDetailOut(**base, comments=task.comments, history=task.history, files=task.files)


# --------------------------------------------------------------------- list
@router.get("", summary="Список задач (учитель — только свои)")
async def list_tasks(
    session: SessionDep,
    actor: CurrentUser,
    status: Annotated[str | None, Query(pattern="^(NEW|IN_PROGRESS|DONE|OVERDUE)$")] = None,
    assignee_id: uuid.UUID | None = None,
    creator_id: uuid.UUID | None = None,
    priority: Annotated[str | None, Query(pattern="^(LOW|NORMAL|HIGH|URGENT)$")] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    sort: Annotated[str, Query(pattern="^(deadline|created|priority|title|updated)$")] = "deadline",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> dict:
    rows, total, counts = await service.list_tasks(
        session,
        actor,
        status=status,
        assignee_id=assignee_id,
        creator_id=creator_id,
        priority=priority,
        search=search,
        due_before=due_before,
        due_after=due_after,
        sort=sort,
        order=order,
        page=page,
        per_page=per_page,
    )
    payload = Page[TaskOut](
        items=[_task_out(t, actor) for t in rows],
        total=total,
        page=page,
        per_page=per_page,
        pages=max(1, (total + per_page - 1) // per_page),
    )
    return {**payload.model_dump(), "status_counts": counts}


@router.get("/status-counts", summary="Счётчики по статусам (для табов/канбана)")
async def status_counts(session: SessionDep, actor: CurrentUser) -> dict:
    return await service.status_counts(session, actor)


@router.get("/overdue-report", summary="Отчёт по просроченным задачам (в разрезе исполнителей)")
async def overdue_report(session: SessionDep, actor: CurrentUser) -> dict:
    if actor.role == Role.TEACHER:
        raise forbidden("Отчёт доступен Администрации и Владельцу")
    return {"items": await service.overdue_report(session, actor)}


@router.post("", response_model=TaskOut, status_code=201, summary="Создать задачу (несколько исполнителей)")
async def create_task(payload: TaskCreateIn, session: SessionDep, actor: CurrentUser) -> TaskOut:
    task = await service.create_task(session, actor, payload)
    await session.refresh(task)          # подтянуть eager-связи до сериализации
    return _task_out(task, actor)


@router.get("/{task_id}", response_model=TaskDetailOut, summary="Карточка задачи (исполнители, отметки, файлы, история)")
async def get_task(task_id: uuid.UUID, session: SessionDep, actor: CurrentUser) -> TaskDetailOut:
    task = await service.get_task(session, task_id, actor)
    return _task_detail(task, actor)


@router.patch("/{task_id}", response_model=TaskOut, summary="Обновить задачу")
async def update_task(
    task_id: uuid.UUID, payload: TaskUpdateIn, session: SessionDep, actor: CurrentUser
) -> TaskOut:
    task = await service.get_task(session, task_id, actor, with_details=False)
    task = await service.update_task(session, actor, task, payload)
    await session.refresh(task)
    return _task_out(task, actor)


@router.post("/{task_id}/status", response_model=TaskOut, summary="Сменить статус (state machine)")
async def change_status(
    task_id: uuid.UUID, payload: StatusChangeIn, session: SessionDep, actor: CurrentUser
) -> TaskOut:
    task = await service.get_task(session, task_id, actor, with_details=False)
    task = await service.change_status(session, actor, task, payload.status)
    await session.refresh(task)
    return _task_out(task, actor)


# ------------------------------------------------------- отметки «выполнено»
@router.post("/{task_id}/my-mark", response_model=TaskOut, summary="Отметить «выполнено» (исполнитель)")
async def set_my_mark(task_id: uuid.UUID, session: SessionDep, actor: CurrentUser) -> TaskOut:
    task = await service.get_task(session, task_id, actor, with_details=False)
    task = await service.set_my_mark(session, actor, task)
    await session.refresh(task)
    return _task_out(task, actor)


@router.delete("/{task_id}/my-mark", response_model=TaskOut, summary="Снять отметку «выполнено»")
async def clear_my_mark(task_id: uuid.UUID, session: SessionDep, actor: CurrentUser) -> TaskOut:
    task = await service.get_task(session, task_id, actor, with_details=False)
    task = await service.clear_my_mark(session, actor, task)
    await session.refresh(task)
    return _task_out(task, actor)


# ------------------------------------------------------------------ вложения
@router.post("/{task_id}/files", status_code=201, summary="Прикрепить файл к задаче")
async def upload_task_file(
    task_id: uuid.UUID,
    session: SessionDep,
    actor: CurrentUser,
    file: Annotated[UploadFile, File(description="Офисные файлы, изображения, архивы — до 25 МБ")],
) -> TaskDetailOut:
    task = await service.get_task(session, task_id, actor, with_details=False)
    await service.add_file(session, actor, task, file)
    task = await service.get_task(session, task_id, actor)
    return _task_detail(task, actor)


@router.get("/{task_id}/files/{file_id}/download", summary="Скачать вложение задачи")
async def download_task_file(task_id: uuid.UUID, file_id: uuid.UUID, session: SessionDep, actor: CurrentUser):
    task = await service.get_task(session, task_id, actor, with_details=False)
    row = next((f for f in task.files if f.id == file_id), None)
    if row is None:
        raise not_found("Файл")
    filename = quote(row.original_name)
    return FileResponse(
        storage.abspath(row.storage_path),
        media_type=row.mime_type,
        filename=row.original_name,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.delete("/{task_id}/files/{file_id}", response_model=TaskDetailOut, summary="Удалить вложение")
async def delete_task_file(
    task_id: uuid.UUID, file_id: uuid.UUID, session: SessionDep, actor: CurrentUser
) -> TaskDetailOut:
    task = await service.get_task(session, task_id, actor, with_details=False)
    await service.delete_file(session, actor, task, file_id)
    task = await service.get_task(session, task_id, actor)
    return _task_detail(task, actor)


# ----------------------------------------------------------------- прочее
@router.post("/{task_id}/comments", response_model=CommentOut, status_code=201, summary="Комментарий")
async def add_comment(
    task_id: uuid.UUID, payload: CommentIn, session: SessionDep, actor: CurrentUser
) -> CommentOut:
    task = await service.get_task(session, task_id, actor, with_details=False)
    comment = await service.add_comment(session, actor, task, payload.body)
    await session.refresh(comment)
    return CommentOut.model_validate(comment)


@router.get("/{task_id}/comments", response_model=list[CommentOut], summary="Комментарии задачи")
async def list_comments(task_id: uuid.UUID, session: SessionDep, actor: CurrentUser) -> list[CommentOut]:
    task = await service.get_task(session, task_id, actor)
    return [CommentOut.model_validate(c) for c in task.comments]


@router.delete("/{task_id}", status_code=204, summary="Удалить задачу (OWNER/ADMIN)")
async def delete_task(task_id: uuid.UUID, session: SessionDep, manager: ManagerDep) -> None:
    task = await service.get_task(session, task_id, manager, with_details=False)
    await service.delete_task(session, manager, task)
