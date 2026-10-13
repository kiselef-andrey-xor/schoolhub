"""Пользователь + роли.

Роль хранится как строковый enum (а не FK на таблицу roles) осознанно:
ролей три, они зафиксированы бизнес-требованием, а проверки прав должны быть
дешёвыми и типизированными. Расширение до динамических прав — через таблицу
permissions + many-to-many (миграция описана в README).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base
from app.enums import Role
from app.types import GUID, EnumString


# Маркер «пароль не применим»: для доменных учётках проверка пароля всегда неуспешна.
UNUSABLE_PASSWORD = "!ldap"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str | None] = mapped_column(String(255))       # должность (директор, завуч, учитель физики…)
    phone: Mapped[str | None] = mapped_column(String(40))
    role: Mapped[Role] = mapped_column(EnumString(Role, 20), nullable=False, default=Role.TEACHER, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # --- интеграция с доменом (Active Directory / LDAP) ---
    # auth_source='local'  -> пароль в password_hash (bcrypt), вход только локальный
    # auth_source='ldap'   -> пароль проверяет контроллер домена, password_hash = UNUSABLE_PASSWORD
    auth_source: Mapped[str] = mapped_column(String(16), nullable=False, default="local", index=True)
    domain_account: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)  # sAMAccountName
    dn: Mapped[str | None] = mapped_column(String(512))                                       # distinguishedName
    ad_groups: Mapped[list[Any] | None] = mapped_column(JSONB().with_variant(JSON, "sqlite")) # имена групп AD
    last_ad_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- relations ---
    created_tasks: Mapped[list["Task"]] = relationship(  # noqa: F821
        back_populates="creator", foreign_keys="Task.creator_id"
    )
    task_assignments: Mapped[list["TaskAssignee"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    acknowledgements: Mapped[list["OrderAcknowledgement"]] = relationship(  # noqa: F821
        back_populates="user"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email} {self.role}>"
