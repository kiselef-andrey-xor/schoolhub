"""Уведомления, аудит-лог, дашборд, справочники (meta)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select, update

from app import capabilities as caps
from app.enums import AckStatus, OrderStatus, OrderType, Role, TaskStatus, PlanStatus
from app.errors import not_found
from app.models.audit import AuditLog
from app.models.notification import Notification
from app.models.order import Order, OrderAcknowledgement
from app.models.task import Task
from app.models.user import User
from app.schemas.audit import AuditOut
from app.schemas.common import EnumItem, Page
from app.schemas.dashboard import DashboardOut, DashboardSummary, OrderStats, TaskStats, UserStats
from app.schemas.notification import NotificationOut
from app.security import CurrentUser, SessionDep, require_role
from app.services import orders as orders_service
from app.services import tasks as tasks_service
from app.types import enum_value

# ------------------------------------------------------------------ notifications
notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])


@notifications_router.get("", response_model=Page[NotificationOut], summary="Мои уведомления")
async def list_notifications(
    session: SessionDep,
    actor: CurrentUser,
    unread_only: bool = False,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> Page[NotificationOut]:
    conds = [Notification.user_id == actor.id]
    if unread_only:
        conds.append(Notification.is_read.is_(False))

    total = int(
        (await session.execute(select(func.count()).select_from(Notification).where(and_(*conds)))).scalar_one()
    )
    rows = (
        await session.execute(
            select(Notification)
            .where(and_(*conds))
            .order_by(Notification.created_at.desc())
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    ).scalars().all()

    return Page[NotificationOut](
        items=[NotificationOut.model_validate(n) for n in rows],
        total=total,
        page=page,
        per_page=per_page,
        pages=max(1, (total + per_page - 1) // per_page),
    )


@notifications_router.get("/unread-count", summary="Счётчик непрочитанных")
async def unread_count(session: SessionDep, actor: CurrentUser) -> dict:
    count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Notification)
                .where(Notification.user_id == actor.id, Notification.is_read.is_(False))
            )
        ).scalar_one()
    )
    return {"unread": count}


@notifications_router.post("/{notification_id}/read", status_code=204, summary="Отметить прочитанным")
async def mark_read(notification_id: uuid.UUID, session: SessionDep, actor: CurrentUser) -> None:
    n = await session.get(Notification, notification_id)
    if n is None or n.user_id != actor.id:
        raise not_found("Уведомление")
    n.is_read = True
    await session.flush()


@notifications_router.post("/read-all", status_code=204, summary="Отметить все прочитанными")
async def mark_all_read(session: SessionDep, actor: CurrentUser) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.user_id == actor.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )


# ------------------------------------------------------------------------ audit
audit_router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    dependencies=[Depends(require_role(Role.ADMIN))],   # OWNER/ADMIN
)


@audit_router.get("", response_model=Page[AuditOut], summary="Журнал значимых действий")
async def list_audit(
    session: SessionDep,
    actor: CurrentUser,
    action: Annotated[str | None, Query(max_length=60)] = None,
    entity_type: Annotated[str | None, Query(max_length=30)] = None,
    actor_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> Page[AuditOut]:
    conds = []
    if action:
        conds.append(AuditLog.action == action)
    if entity_type:
        conds.append(AuditLog.entity_type == entity_type)
    if actor_id:
        conds.append(AuditLog.actor_id == actor_id)
    if date_from:
        conds.append(AuditLog.created_at >= datetime(date_from.year, date_from.month, date_from.day))
    if date_to:
        conds.append(AuditLog.created_at < datetime.combine(date_to + timedelta(days=1), time.min))

    stmt = select(AuditLog)
    if conds:
        stmt = stmt.where(and_(*conds))

    total = int((await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one())
    rows = (
        await session.execute(stmt.order_by(AuditLog.created_at.desc()).limit(per_page).offset((page - 1) * per_page))
    ).scalars().all()

    return Page[AuditOut](
        items=[AuditOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
        pages=max(1, (total + per_page - 1) // per_page),
    )


@audit_router.get("/actions", response_model=list[str], summary="Справочник действий (для фильтра)")
async def audit_actions(session: SessionDep) -> list[str]:
    rows = (await session.execute(select(AuditLog.action).distinct().order_by(AuditLog.action))).scalars().all()
    return list(rows)


# -------------------------------------------------------------------- dashboard
dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@dashboard_router.get("", response_model=DashboardOut, summary="Сводка по роли")
async def dashboard(session: SessionDep, actor: CurrentUser) -> DashboardOut:
    is_staff = actor.role in (Role.OWNER, Role.ADMIN)
    now = tasks_service.utcnow()

    # --- задачи ---
    task_counts = await tasks_service.status_counts(session, actor)

    # --- приказы ---
    order_conds = [] if is_staff else [Order.status == OrderStatus.PUBLISHED.value]
    orders_total_stmt = select(func.count()).select_from(Order)
    if order_conds:
        orders_total_stmt = orders_total_stmt.where(and_(*order_conds))
    orders_total = int((await session.execute(orders_total_stmt)).scalar_one())
    orders_published = int(
        (
            await session.execute(
                select(func.count()).select_from(Order).where(Order.status == OrderStatus.PUBLISHED)
            )
        ).scalar_one()
    )
    orders_drafts = int(
        (await session.execute(select(func.count()).select_from(Order).where(Order.status == OrderStatus.DRAFT))).scalar_one()
    ) if is_staff else 0

    if is_staff:
        pending_ack = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(OrderAcknowledgement)
                    .where(OrderAcknowledgement.status == AckStatus.PENDING)
                )
            ).scalar_one()
        )
    else:
        pending_ack = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(OrderAcknowledgement)
                    .where(
                        OrderAcknowledgement.user_id == actor.id,
                        OrderAcknowledgement.status == AckStatus.PENDING,
                    )
                )
            ).scalar_one()
        )

    # --- пользователи (только staff) ---
    user_stats = None
    if is_staff:
        users_total = int((await session.execute(select(func.count()).select_from(User))).scalar_one())
        teachers = int(
            (await session.execute(select(func.count()).select_from(User).where(User.role == Role.TEACHER))).scalar_one()
        )
        admins = int(
            (
                await session.execute(
                    select(func.count()).select_from(User).where(User.role.in_([Role.ADMIN, Role.OWNER]))
                )
            ).scalar_one()
        )
        active = int(
            (await session.execute(select(func.count()).select_from(User).where(User.is_active.is_(True)))).scalar_one()
        )
        user_stats = UserStats(total=users_total, teachers=teachers, admins=admins, active=active)

    # --- списки ---
    pending_orders, _ = await orders_service.list_orders(
        session, actor, mine_pending=not is_staff, page=1, per_page=5,
        status=None if is_staff else OrderStatus.PUBLISHED,
    )
    recent_orders, _ = await orders_service.list_orders(session, actor, page=1, per_page=5)

    my_tasks_rows, _, _ = await tasks_service.list_tasks(
        session,
        actor,
        status=None if not is_staff else "OVERDUE",
        assignee_id=None if is_staff else actor.id,
        sort="deadline",
        order="asc",
        page=1,
        per_page=6,
    )
    recent_tasks, _, _ = await tasks_service.list_tasks(
        session, actor, sort="created", order="desc", page=1, per_page=6
    )

    # --- план работы текущей недели (виджет) ---
    from app.api.plans import _plan_out
    from app.services import plans as plans_service

    plan = await plans_service.current_plan(session, actor)
    plan_out = None
    if plan is not None:
        plan_users = await plans_service.load_resp_users(session, plan)
        plan_out = _plan_out(plan, actor, plan_users)

    from app.api.orders import _order_list_out
    from app.api.tasks import _task_out

    return DashboardOut(
        current_plan=plan_out,
        summary=DashboardSummary(
            scope="global" if is_staff else "personal",
            orders=OrderStats(
                total=orders_total,
                published=orders_published,
                drafts=orders_drafts,
                pending_ack=pending_ack,
            ),
            tasks=TaskStats(
                total=task_counts["all"],
                new=task_counts[TaskStatus.NEW.value],
                in_progress=task_counts[TaskStatus.IN_PROGRESS.value],
                done=task_counts[TaskStatus.DONE.value],
                overdue=task_counts["OVERDUE"],
            ),
            users=user_stats,
        ),
        pending_acks=[_order_list_out(o, actor) for o in pending_orders],
        my_tasks=[_task_out(t, actor) for t in my_tasks_rows],
        recent_orders=[_order_list_out(o, actor) for o in recent_orders],
        recent_tasks=[_task_out(t, actor) for t in recent_tasks],
    )


# ------------------------------------------------------------------------- meta
meta_router = APIRouter(prefix="/meta", tags=["meta"])

RUS_LABELS = {
    "OWNER": "Владелец",
    "ADMIN": "Администрация",
    "TEACHER": "Учитель",
    "HR": "По личному составу",
    "STUDENTS": "По обучающимся",
    "EDUCATION": "По учебной деятельности",
    "SAFETY": "Охрана труда и безопасность",
    "ADMIN_TYPE": "Административно-хозяйственный",
    "OTHER": "Прочее",
    "DRAFT": "Черновик",
    "PUBLISHED": "Опубликован",
    "ARCHIVED": "Архив",
    "PENDING": "Не ознакомлен",
    "ACKNOWLEDGED": "Ознакомлен",
    "NEW": "Новая",
    "IN_PROGRESS": "В работе",
    "DONE": "Выполнена",
    "OVERDUE": "Просрочена",
    "LOW": "Низкий",
    "NORMAL": "Обычный",
    "HIGH": "Высокий",
    "URGENT": "Срочный",
}


@meta_router.get("/enums", summary="Справочники для селектов (значения + подписи на русском)")
async def enums() -> dict[str, list[EnumItem]]:
    def items(values, key_map=None) -> list[EnumItem]:
        out = []
        for v in values:
            key = key_map(v) if key_map else v
            out.append(EnumItem(value=v, label=RUS_LABELS.get(key, v)))
        return out

    return {
        "roles": items([r.value for r in Role]),
        "order_types": items([t.value for t in OrderType], lambda v: "ADMIN_TYPE" if v == "ADMIN" else v),
        "order_statuses": items([s.value for s in OrderStatus]),
        "ack_statuses": items([s.value for s in AckStatus]),
        "task_statuses": items([s.value for s in TaskStatus] + ["OVERDUE"]),
        "plan_statuses": items([s.value for s in PlanStatus]),
        "priorities": items(["LOW", "NORMAL", "HIGH", "URGENT"]),
    }


@meta_router.get("/permissions", summary="Матрица прав (RBAC) — документация и отладка")
async def permissions_matrix(_: CurrentUser) -> dict:
    return caps.full_matrix()


# --------------------------------------------------------------------- health
health_router = APIRouter(tags=["system"])


@health_router.get("/health", summary="Healthcheck (дублирует корневой /health под префиксом API)")
async def health_api() -> dict:
    from app.config import settings as _settings
    from app.main import VERSION

    return {"status": "ok", "app": _settings.app_name, "env": _settings.app_env, "version": VERSION}
