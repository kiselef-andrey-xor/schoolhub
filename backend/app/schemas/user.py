"""Схемы аутентификации и пользователей."""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.enums import Role


# --------------------------------------------------------------------- auth
LOGIN_RE = re.compile(r"^[A-Za-z0-9._@\\-]{2,254}$")


class LoginIn(BaseModel):
    """Логин: e-mail SchoolHub **или** доменная учётка (`ivanov`, `ivanov@school.local`, `SCHOOL\\ivanov`).
    Валидатор намеренно строгий: значение уходит в LDAP-фильтр, поэтому допускаются
    только безопасные символы (дополнительно экранируется в `escape_filter_chars`).
    """

    email: str = Field(min_length=2, max_length=254, examples=["owner@schoolhub.ru", "ivanov@school.local"])
    password: str = Field(min_length=1, max_length=128)
    remember: bool = Field(default=True, description="Держать сессию 14 дней; иначе — до закрытия браузера")

    @field_validator("email")
    @classmethod
    def _validate_login(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not LOGIN_RE.match(cleaned):
            raise ValueError("Логин содержит недопустимые символы")
        return cleaned


class TokenPair(BaseModel):
    """Refresh-токен в теле НЕ отдаётся — он приходит в httpOnly-cookie
    (Set-Cookie на /auth/login и /auth/refresh), недоступной документу и XSS."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1800


class MeOut(BaseModel):
    """Профиль + набор возможностей (capabilities) для управления UI."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str                          # не EmailStr: адрес может прийти из AD (любой домен школы)
    full_name: str
    position: str | None = None
    phone: str | None = None
    role: Role
    is_active: bool
    auth_source: str = "local"          # local | ldap
    domain_account: str | None = None
    ad_groups: list[Any] | None = None
    last_ad_sync_at: datetime | None = None
    capabilities: list[str] = []


# -------------------------------------------------------------------- users
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str                          # см. MeOut: адрес из AD не обязан проходить строгую валидацию
    full_name: str
    position: str | None = None
    phone: str | None = None
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None
    auth_source: str = "local"          # local | ldap
    domain_account: str | None = None
    ad_groups: list[Any] | None = None
    last_ad_sync_at: datetime | None = None


class UserCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    role: Role = Role.TEACHER
    position: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)


class UserUpdateIn(BaseModel):
    """PATCH-семантика: None = не менять (password отдельно)."""

    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    position: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ----------------------------------------------------------------------- AD
class LoginOptionsOut(BaseModel):
    """Публичная информация о способах входа (для экрана логина)."""

    ldap_enabled: bool = False
    local_enabled: bool = True
    login_hint: str = ""
    password_managed_by: str = "SchoolHub"


class ADUserOut(BaseModel):
    """Пользователь домена, найденный в каталоге (для импорта)."""

    username: str
    full_name: str
    email: str
    position: str | None = None
    phone: str | None = None
    dn: str | None = None
    disabled: bool = False
    groups: list[str] = []


class ADImportIn(BaseModel):
    usernames: list[str] = Field(min_length=1, max_length=200)
    role: Role | None = None


class ADImportOut(BaseModel):
    created: list[str] = []
    skipped: list[str] = []
    failed: list[dict[str, str]] = []
    total: int = 0
