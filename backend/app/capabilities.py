"""Матрица возможностей (capabilities) — ЕДИНЫЙ источник правды для RBAC в UI.

Backend проверяет права жёстко (зависимости require_role + проверки в сервисах).
Фронтенд НЕ является границей безопасности: он использует тот же словарь,
полученный с бэкенда (GET /auth/me -> capabilities), чтобы скрывать/показывать
контролы. Даже если UI обмануть, API вернёт 403.
"""
from __future__ import annotations

from app.enums import Role
from app.models.user import User
from app.types import enum_value

# --- справочник возможностей -------------------------------------------------
ORDERS_READ = "orders:read"            # просмотр опубликованных приказов и документов
ORDERS_MANAGE = "orders:manage"        # создание/редактирование/публикация/загрузка файлов
ORDERS_ACK = "orders:ack"              # подтверждение ознакомления
ORDERS_ACK_REPORT = "orders:ack-report"  # лист ознакомления по всем сотрудникам

TASKS_READ_OWN = "tasks:read-own"      # только свои задачи
TASKS_READ_ALL = "tasks:read-all"      # все задачи школы
TASKS_CREATE = "tasks:create"
TASKS_ASSIGN = "tasks:assign"          # назначение/переназначение исполнителя, смена дедлайна
TASKS_DELETE = "tasks:delete"

PLANS_READ = "plans:read"            # просмотр опубликованных планов работы на неделю
PLANS_MANAGE = "plans:manage"        # создание/редактирование/публикация/архивирование планов

USERS_READ = "users:read"
USERS_MANAGE = "users:manage"          # создание/блокировка, смена роли
USERS_MANAGE_ADMINS = "users:manage-admins"  # управление админами и владельцем

AUDIT_READ = "audit:read"
DASHBOARD_GLOBAL = "dashboard:global"

ROLE_CAPABILITIES: dict[Role, tuple[str, ...]] = {
    Role.OWNER: (
        ORDERS_READ, ORDERS_MANAGE, ORDERS_ACK, ORDERS_ACK_REPORT,
        TASKS_READ_ALL, TASKS_CREATE, TASKS_ASSIGN, TASKS_DELETE,
        PLANS_READ, PLANS_MANAGE,
        USERS_READ, USERS_MANAGE, USERS_MANAGE_ADMINS,
        AUDIT_READ, DASHBOARD_GLOBAL,
    ),
    Role.ADMIN: (
        ORDERS_READ, ORDERS_MANAGE, ORDERS_ACK, ORDERS_ACK_REPORT,
        TASKS_READ_ALL, TASKS_CREATE, TASKS_ASSIGN, TASKS_DELETE,
        PLANS_READ, PLANS_MANAGE,
        USERS_READ, USERS_MANAGE,
        AUDIT_READ, DASHBOARD_GLOBAL,
    ),
    Role.TEACHER: (
        ORDERS_READ, ORDERS_ACK,
        TASKS_READ_OWN,
        PLANS_READ,
    ),
}


def capabilities_for(role: Role | str) -> list[str]:
    role = Role(role) if isinstance(role, str) else role
    return list(ROLE_CAPABILITIES.get(role, ()))


def can(user: User, capability: str) -> bool:
    return capability in capabilities_for(enum_value(user.role))


def full_matrix() -> dict[str, list[dict[str, object]]]:
    """Матрица для документации/экрана отладки: возможность × роль."""
    roles = [Role.OWNER, Role.ADMIN, Role.TEACHER]
    caps = sorted({c for r in roles for c in ROLE_CAPABILITIES[r]})
    return {
        "roles": [r.value for r in roles],
        "capabilities": [
            {"capability": c, "grants": {r.value: (c in ROLE_CAPABILITIES[r]) for r in roles}} for c in caps
        ],
    }
