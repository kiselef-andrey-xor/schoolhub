"""Пользователи: справочник для назначения задач и управление учётными записями.

Доступ:
  GET  /users          — OWNER, ADMIN (ADMIN не видит владельца)
  POST /users          — OWNER (создание админов), ADMIN (только учителей)
  PATCH /users/{id}    — OWNER; ADMIN — только учителей и без повышения роли
  POST /users/{id}/reset-password — OWNER/ADMIN в рамках своих прав
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.enums import ROLE_LEVEL, Role
from app.errors import bad_request, conflict, forbidden, not_found
from app.models.user import User
from app.schemas.common import Page
from app.schemas.user import (
    ADImportIn,
    ADImportOut,
    ADUserOut,
    UserCreateIn,
    UserOut,
    UserUpdateIn,
)
from app.security import CurrentUser, SessionDep, can_manage_role, hash_password, require_role
from app.services import sessions as session_service
from app.dbutils import ilike
from app.services import ad_users, audit
from app.types import enum_value

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_role(Role.ADMIN))])


async def _get_user_or_404(session, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise not_found("Пользователь")
    return user


def _visible_scope(actor: User):
    """Админ не управляет и не видит владельца; владелец видит всех."""
    if actor.role == Role.OWNER:
        return None
    return User.role != Role.OWNER


def _assert_can_touch(actor: User, target: User, *, changing_role: Role | None = None) -> None:
    if actor.id == target.id and changing_role and changing_role != actor.role:
        raise conflict("Нельзя изменить собственную роль")

    if actor.role == Role.OWNER:
        return  # владелец может всё

    # ADMIN
    if target.role == Role.OWNER:
        raise forbidden("Управление учётной записью Владельца доступно только Владельцу")
    if changing_role is not None and ROLE_LEVEL[changing_role] >= ROLE_LEVEL[actor.role]:
        raise forbidden("Администрация не может назначать роль своего уровня или выше")


@router.get("", response_model=Page[UserOut], summary="Список пользователей")
async def list_users(
    session: SessionDep,
    actor: CurrentUser,
    search: str | None = Query(default=None, max_length=120),
    role: Role | None = None,
    is_active: bool | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> Page[UserOut]:
    stmt = select(User)
    conds = []
    scope = _visible_scope(actor)
    if scope is not None:
        conds.append(scope)
    if role:
        conds.append(User.role == role.value)
    if is_active is not None:
        conds.append(User.is_active.is_(is_active))
    if search:
        conds.append(or_(ilike(User.full_name, search), ilike(User.email, search), ilike(User.position, search)))
    if conds:
        stmt = stmt.where(*conds)

    total = int((await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one())
    rows = (
        await session.execute(stmt.order_by(User.role.desc(), User.full_name).limit(per_page).offset((page - 1) * per_page))
    ).scalars().all()

    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in rows],
        total=total,
        page=page,
        per_page=per_page,
        pages=max(1, (total + per_page - 1) // per_page),
    )


@router.get("/options", response_model=list[UserOut], summary="Компактный список для селектов (исполнители)")
async def user_options(session: SessionDep, actor: CurrentUser, role: Role | None = None) -> list[UserOut]:
    stmt = select(User).where(User.is_active.is_(True))
    scope = _visible_scope(actor)
    if scope is not None:
        stmt = stmt.where(scope)
    if role:
        stmt = stmt.where(User.role == role)
    rows = (await session.execute(stmt.order_by(User.full_name))).scalars().all()
    return [UserOut.model_validate(u) for u in rows]


@router.get("/{user_id}", response_model=UserOut, summary="Карточка пользователя")
async def get_user(user_id: uuid.UUID, session: SessionDep, actor: CurrentUser) -> UserOut:
    target = await _get_user_or_404(session, user_id)
    if actor.role != Role.OWNER and target.role == Role.OWNER:
        raise forbidden()
    return UserOut.model_validate(target)


@router.post("", response_model=UserOut, status_code=201, summary="Создать пользователя")
async def create_user(payload: UserCreateIn, session: SessionDep, actor: CurrentUser) -> UserOut:
    # Право на выдачу роли: нельзя выдать роль своего уровня или выше (анти-эскалация).
    # OWNER -> может создавать OWNER/ADMIN/TEACHER, ADMIN -> только TEACHER.
    if not can_manage_role(actor.role, payload.role):
        raise forbidden("Недостаточно прав для назначения такой роли")

    exists = (
        await session.execute(select(func.count()).select_from(User).where(User.email == payload.email.lower().strip()))
    ).scalar_one()
    if exists:
        raise conflict("Пользователь с таким e-mail уже существует")

    user = User(
        email=payload.email.lower().strip(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        position=payload.position,
        phone=payload.phone,
        role=payload.role,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await audit.write_audit(
        session, actor=actor, action="USER_CREATE", entity_type="user", entity_id=user.id,
        changes={"email": user.email, "role": enum_value(user.role), "full_name": user.full_name},
    )
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut, summary="Обновить пользователя (роль, активность, данные)")
async def update_user(
    user_id: uuid.UUID, payload: UserUpdateIn, session: SessionDep, actor: CurrentUser
) -> UserOut:
    target = await _get_user_or_404(session, user_id)
    _assert_can_touch(actor, target, changing_role=payload.role)

    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        raise bad_request("Пустой запрос на обновление")

    before = {"email": target.email, "full_name": target.full_name, "role": enum_value(target.role),
              "is_active": target.is_active, "position": target.position, "phone": target.phone}

    if "password" in patch:
        password = patch.pop("password")
        if password:
            if target.auth_source == "ldap":
                raise conflict(
                    "Пароль доменной учётной записи меняется в Active Directory, а не в SchoolHub"
                )
            target.password_hash = hash_password(password)
            # сброс пароля администрацией рвёт ВСЕ сессии пользователя
            await session_service.revoke_all_for_user(session, target.id, "password_reset")

    if "email" in patch and patch["email"]:
        new_email = str(patch["email"]).lower().strip()
        dup = (
            await session.execute(
                select(func.count()).select_from(User).where(User.email == new_email, User.id != target.id)
            )
        ).scalar_one()
        if dup:
            raise conflict("E-mail уже занят")
        target.email = new_email

    for field in ("full_name", "position", "phone"):
        if field in patch and patch[field] is not None:
            setattr(target, field, str(patch[field]).strip())

    if "role" in patch and patch["role"] is not None:
        new_role = Role(patch["role"]) if not isinstance(patch["role"], Role) else patch["role"]
        if target.id == actor.id and new_role != actor.role:
            raise conflict("Нельзя изменить собственную роль")
        if actor.role == Role.ADMIN and new_role != Role.TEACHER:
            raise forbidden("Администрация может назначать только роль Учителя")
        if target.role == Role.OWNER and actor.role != Role.OWNER:
            raise forbidden("Снять роль Владельца может только Владелец")
        owners_left = (
            await session.execute(
                select(func.count()).select_from(User).where(
                    User.role == Role.OWNER, User.is_active.is_(True), User.id != target.id
                )
            )
        ).scalar_one()
        if target.role == Role.OWNER and new_role != Role.OWNER and owners_left == 0:
            raise conflict("В школе должен остаться хотя бы один активный Владелец")
        target.role = new_role

    if "is_active" in patch and patch["is_active"] is not None:
        if target.id == actor.id and patch["is_active"] is False:
            raise conflict("Нельзя заблокировать собственную учётную запись")
        if target.role == Role.OWNER and patch["is_active"] is False:
            owners_left = (
                await session.execute(
                    select(func.count()).select_from(User).where(
                        User.role == Role.OWNER, User.is_active.is_(True), User.id != target.id
                    )
                )
            ).scalar_one()
            if owners_left == 0:
                raise conflict("Нельзя заблокировать единственного Владельца")
        target.is_active = bool(patch["is_active"])
        if not target.is_active:
            await session_service.revoke_all_for_user(session, target.id, "deactivated")

    await session.flush()
    after = {"email": target.email, "full_name": target.full_name, "role": enum_value(target.role),
             "is_active": target.is_active, "position": target.position, "phone": target.phone}
    await audit.write_audit(
        session, actor=actor, action="USER_UPDATE", entity_type="user", entity_id=target.id,
        changes=audit.diff(before, after),
    )
    return UserOut.model_validate(target)


@router.delete("/{user_id}", status_code=204, summary="Деактивировать пользователя (мягкое удаление)")
async def deactivate_user(user_id: uuid.UUID, session: SessionDep, actor: CurrentUser) -> None:
    """Исторические данные (приказы, задачи, ознакомления) должны оставаться —
    поэтому удаление мягкое: is_active=false."""
    if actor.role != Role.OWNER:
        raise forbidden("Только Владелец может деактивировать учётные записи")
    target = await _get_user_or_404(session, user_id)
    if target.id == actor.id:
        raise conflict("Нельзя деактивировать собственную учётную запись")
    target.is_active = False
    await session_service.revoke_all_for_user(session, target.id, "deactivated")
    await session.flush()
    await audit.write_audit(
        session, actor=actor, action="USER_DEACTIVATE", entity_type="user", entity_id=target.id
    )


# ------------------------------------------------------------------ Active Directory
@router.get("/ad/search", response_model=list[ADUserOut], summary="Поиск пользователей в домене (для импорта)")
async def ad_search(
    session: SessionDep,
    actor: CurrentUser,
    q: str = Query(min_length=2, max_length=120, description="Часть ФИО, логина или e-mail"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ADUserOut]:
    """Работает только при настроенной сервисной учётке LDAP (чтение каталога)."""
    principals = await ad_users.search_ad_users(q, limit=limit)
    return [
        ADUserOut(
            username=p.username,
            full_name=p.full_name,
            email=p.email,
            position=p.position or None,
            phone=p.phone or None,
            dn=p.dn or None,
            disabled=p.disabled,
            groups=p.groups[:50],
        )
        for p in principals
    ]


@router.post("/ad/import", response_model=ADImportOut, summary="Импортировать учётки из домена")
async def ad_import(
    payload: ADImportIn, session: SessionDep, actor: CurrentUser, request: Request
) -> ADImportOut:
    """Создаёт записи SchoolHub для выбранных доменных пользователей.

    Нужно, чтобы назначить роль ДО первого входа (иначе пользователь получит роль
    по умолчанию — Учитель). Пароль не создаётся: вход идёт через AD.
    """
    result = await ad_users.import_ad_users(
        session, actor, payload.usernames, role=payload.role, request=request
    )
    return ADImportOut(**result)
