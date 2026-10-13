"""Task Manager: задача, исполнители (несколько), вложения, комментарии, история статусов.

Модель v1.2: у задачи НЕСКОЛЬКО исполнителей (task_assignees), у каждого — своя
отметка «выполнено» (done_at). Когда отметки поставили все — задача автоматически
закрывается (DONE); снятие отметки возвращает задачу в IN_PROGRESS.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import TaskStatus
from app.models.user import User
from app.types import GUID, EnumString


class TaskPriority:
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"

    ALL = (LOW, NORMAL, HIGH, URGENT)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    status: Mapped[TaskStatus] = mapped_column(
        EnumString(TaskStatus, 20), nullable=False, default=TaskStatus.NEW, index=True
    )
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default=TaskPriority.NORMAL, index=True)

    creator_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Может быть пустым для «общих» задач без дедлайна; OVERDUE вычисляется только при его наличии.
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- relations ---
    creator: Mapped["User | None"] = relationship(back_populates="created_tasks", foreign_keys=[creator_id], lazy="joined")
    assignees: Mapped[list["TaskAssignee"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TaskAssignee.created_at",
    )
    files: Mapped[list["TaskFile"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TaskFile.created_at",
    )
    comments: Mapped[list["TaskComment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskComment.created_at"
    )
    history: Mapped[list["TaskStatusHistory"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskStatusHistory.created_at"
    )

    # --- derived ---
    @property
    def assignee_users(self) -> list["User"]:
        return [a.user for a in self.assignees if a.user is not None]

    @property
    def assignee_ids(self) -> list[uuid.UUID]:
        return [a.user_id for a in self.assignees]

    @property
    def marks_done(self) -> int:
        return sum(1 for a in self.assignees if a.done_at is not None)

    def mark_of(self, user_id: uuid.UUID) -> "TaskAssignee | None":
        for a in self.assignees:
            if a.user_id == user_id:
                return a
        return None


class TaskAssignee(Base):
    """Исполнитель задачи + его личная отметка «выполнено» (done_at).

    Одна строка на (задача × сотрудник). done_at=None — отметки нет.
    """

    __tablename__ = "task_assignees"
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_task_assignee"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["Task"] = relationship(back_populates="assignees")
    user: Mapped["User"] = relationship(lazy="joined")


class TaskFile(Base):
    """Вложение задачи (методичка, ведомость, фото…). Файл неизменяем: замена = новая строка."""

    __tablename__ = "task_files"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum: Mapped[str | None] = mapped_column(String(64))          # sha256
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["Task"] = relationship(back_populates="files")
    uploaded_by: Mapped["User | None"] = relationship(lazy="joined")


class TaskComment(Base):

    __tablename__ = "task_comments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["Task"] = relationship(back_populates="comments")
    author: Mapped["User | None"] = relationship(lazy="joined")


class TaskStatusHistory(Base):
    """Аудит-след по жизненному циклу задачи (кто и когда перевёл статус)."""

    __tablename__ = "task_status_history"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["Task"] = relationship(back_populates="history")
    actor: Mapped["User | None"] = relationship(lazy="joined")
