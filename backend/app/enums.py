"""Доменные enum'ы — единый источник правды для backend и контракта frontend."""
from __future__ import annotations

import enum


class Role(str, enum.Enum):
    OWNER = "OWNER"        # Владелец школы: полный доступ + управление пользователями/ролями
    ADMIN = "ADMIN"        # Администрация: приказы, задачи, все учителя
    TEACHER = "TEACHER"    # Учитель: свои задачи, ознакомление с приказами


# Числовая иерархия ролей (используется в require_role и в guard'ах «не выше своего уровня»)
ROLE_LEVEL: dict[Role, int] = {Role.TEACHER: 1, Role.ADMIN: 2, Role.OWNER: 3}


class OrderType(str, enum.Enum):
    HR = "HR"                        # По личному составу (приём/увольнение/отпуска)
    STUDENTS = "STUDENTS"            # По обучающимся (зачисление, перевод, отчисление)
    EDUCATION = "EDUCATION"          # По учебной деятельности (УП, расписание, аттестация)
    SAFETY = "SAFETY"                # По охране труда и безопасности
    ADMIN = "ADMIN"                  # Административно-хозяйственные
    OTHER = "OTHER"


class OrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"                  # черновик (виден только OWNER/ADMIN)
    PUBLISHED = "PUBLISHED"          # опубликован — требует ознакомления
    ARCHIVED = "ARCHIVED"            # архив (read-only)


class AckStatus(str, enum.Enum):
    PENDING = "PENDING"              # не ознакомлен
    ACKNOWLEDGED = "ACKNOWLEDGED"    # ознакомлен (подтверждено, есть метаданные)


class TaskStatus(str, enum.Enum):
    NEW = "NEW"                      # Новая
    IN_PROGRESS = "IN_PROGRESS"      # В работе
    DONE = "DONE"                    # Выполнена
    # OVERDUE («Просрочена») — ВЫЧИСЛЯЕМОЕ состояние: status != DONE && deadline < now.
    # Хранить его в БД нельзя: оно устаревает само по себе и требует cron'а.
    # См. app/services/tasks.py::is_overdue и effective_status().


OVERDUE = "OVERDUE"                  # виртуальный статус для API/UI


class PlanStatus(str, enum.Enum):
    DRAFT = "DRAFT"                  # черновик недели (виден только OWNER/ADMIN)
    PUBLISHED = "PUBLISHED"          # опубликован — видят все, ответственные уведомлены
    ARCHIVED = "ARCHIVED"            # архив прошлых недель (read-only)


# Разрешённые переходы статусов задачи (state machine)
TASK_TRANSITIONS: dict[str, set[str]] = {
    TaskStatus.NEW.value: {TaskStatus.IN_PROGRESS.value, TaskStatus.DONE.value},
    TaskStatus.IN_PROGRESS.value: {TaskStatus.DONE.value, TaskStatus.NEW.value},
    TaskStatus.DONE.value: {TaskStatus.IN_PROGRESS.value},   # откат, если принято неверно
}
