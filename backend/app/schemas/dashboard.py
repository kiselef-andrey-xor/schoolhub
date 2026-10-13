from __future__ import annotations

from pydantic import BaseModel

from app.schemas.order import OrderListOut
from app.schemas.plan import PlanOut
from app.schemas.task import TaskOut


class OrderStats(BaseModel):
    total: int = 0
    published: int = 0
    drafts: int = 0
    pending_ack: int = 0        # сколько приказов ждёт МОЕГО ознакомления (учитель) / всего неподтверждённых (админ)


class TaskStats(BaseModel):
    total: int = 0
    new: int = 0
    in_progress: int = 0
    done: int = 0
    overdue: int = 0


class UserStats(BaseModel):
    total: int = 0
    teachers: int = 0
    admins: int = 0
    active: int = 0


class DashboardSummary(BaseModel):
    scope: str                  # "personal" (учитель) | "global" (админ/владелец)
    orders: OrderStats
    tasks: TaskStats
    users: UserStats | None = None


class DashboardOut(BaseModel):
    summary: DashboardSummary
    current_plan: PlanOut | None = None      # план работы текущей недели (виджет на дашборде)
    pending_acks: list[OrderListOut] = []      # приказы, требующие ознакомления (для учителя)
    my_tasks: list[TaskOut] = []               # ближайшие задачи (для учителя) / просроченные (для админа)
    recent_orders: list[OrderListOut] = []
    recent_tasks: list[TaskOut] = []
