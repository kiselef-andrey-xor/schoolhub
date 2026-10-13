"""Схемы Task Manager (v1.2: несколько исполнителей, отметки «выполнено», вложения)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.enums import TaskStatus
from app.schemas.user import UserOut


class TaskIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str | None = None
    assignee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    deadline: datetime | None = None
    priority: str = "NORMAL"


class TaskCreateIn(TaskIn):
    pass


class TaskUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = None
    assignee_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    deadline: datetime | None = None
    priority: str | None = None
    status: TaskStatus | None = None


class StatusChangeIn(BaseModel):
    status: TaskStatus
    note: str | None = Field(default=None, max_length=500)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    created_at: datetime
    author: UserOut | None = None


class StatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_status: str | None
    to_status: str
    note: str | None
    created_at: datetime
    actor: UserOut | None = None


class TaskAssigneeOut(BaseModel):
    """Исполнитель задачи + его личная отметка «выполнено»."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user: UserOut
    done_at: datetime | None = None


class TaskFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_name: str
    mime_type: str
    size_bytes: int
    checksum: str | None = None
    created_at: datetime
    uploaded_by: UserOut | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    status: TaskStatus                      # хранимый статус
    effective_status: str                   # NEW | IN_PROGRESS | DONE | OVERDUE (вычисляется)
    priority: str
    deadline: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    creator: UserOut | None = None
    assignees: list[TaskAssigneeOut] = []
    is_overdue: bool = False
    days_left: int | None = None
    can_edit: bool = False
    can_mark: bool = False                  # я — исполнитель и могу поставить/снять отметку
    my_done: bool = False                   # моя отметка «выполнено» уже стоит
    marks_done: int = 0                     # сколько исполнителей отметилось
    files_count: int = 0


class TaskDetailOut(TaskOut):
    comments: list[CommentOut] = []
    history: list[StatusHistoryOut] = []
    files: list[TaskFileOut] = []
