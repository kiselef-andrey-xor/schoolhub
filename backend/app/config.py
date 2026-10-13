"""Конфигурация приложения (12-factor: всё из ENV)."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.enums import Role


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- app ---
    app_name: str = "SchoolHub API"
    app_env: str = "dev"                     # dev | staging | prod
    api_prefix: str = "/api/v1"
    debug: bool = True

    # --- db ---
    database_url: str = "postgresql+asyncpg://schoolhub:schoolhub@localhost:5432/schoolhub"
    db_echo: bool = False
    # применять Alembic-миграции при старте приложения (на NAS — обязательно true;
    # в крупных контурах можно выключить и накатывать миграции вручную: alembic upgrade head)
    auto_migrate: bool = True

    # --- security ---
    # SECRET_KEY можно не задавать: при старте сгенерируется и сохранится в файл
    # (см. app/services/bootstrap.py::resolve_secret_key). Файл лежит в постоянном
    # каталоге данных, поэтому ключ переживает пересоздание контейнера.
    secret_key: str = Field(default="")
    secret_key_file: str = "./storage/secret_key"
    setup_token: str = ""                  # задать свой код настройки (иначе сгенерируется)
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 30
    refresh_token_ttl_days: int = 14
    password_min_length: int = 8

    # --- refresh-cookie (httpOnly вместо localStorage) ---
    refresh_cookie_name: str = "schoolhub_refresh"
    # `auto` (по умолчанию) — включать флаг Secure автоматически, когда запрос пришёл
    # по HTTPS или за TLS-терминатором (X-Forwarded-Proto: https). Явно задаётся
    # COOKIE_SECURE=true/false. См. app/services/sessions.py::cookie_options.
    cookie_secure: bool | str = "auto"
    cookie_same_site: str = "strict"       # strict | lax — защита от CSRF на /auth/refresh
    refresh_reuse_grace_sec: int = 30      # льготное окно ротации для параллельных вкладок

    # --- files ---
    upload_dir: str = "./storage/uploads"
    max_upload_mb: int = 25
    allowed_doc_mimes: List[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ]
    # Вложения задач — шире, чем документы приказов: офисные файлы, изображения, архивы.
    allowed_task_file_mimes: List[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain",
        "text/csv",
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/zip",
        "application/x-7z-compressed",
        "application/x-rar-compressed",
    ]

    # --- Active Directory / LDAP -------------------------------------------------
    # Аутентификация bind'ом под учёткой пользователя (пароль в БД не хранится).
    ldap_enabled: bool = False
    ldap_server: str = ""                    # dc01.school.local:636  или  ldaps://dc01.school.local
    ldap_use_ssl: bool = True                # true = LDAPS(636); false = LDAP(389) + StartTLS
    ldap_use_starttls: bool = True           # применяется только при ldap_use_ssl=false
    ldap_tls_verify: str = "required"        # required | none  (none — только для отладки!)
    ldap_ca_cert: str = ""                   # путь к PEM-файлу с корневым CA домена (если самоподписанный)
    ldap_bind_template: str = "{username}@{domain}"   # UPN; альтернатива: "{domain}\\{username}"
    ldap_domain: str = ""                    # SCHOOL.LOCAL — подставляется в шаблон и как суффикс e-mail
    ldap_base_dn: str = ""                   # DC=school,DC=local
    ldap_user_filter: str = "(&(objectClass=user)(objectCategory=person))"
    ldap_group_filter: str = "(objectClass=group)"
    # Сервисная учётка — ТОЛЬКО для чтения (поиск пользователя, групп, импорт из AD).
    # Для самого bind'а используется пароль, введённый пользователем.
    ldap_bind_dn: str = ""                   # CN=svc_schoolhub,OU=Service,DC=school,DC=local
    ldap_bind_password: str = ""
    ldap_login_format: str = "upn"           # upn | downlevel | both
    ldap_provisioning: str = "auto"          # auto = создавать учётку при первом входе | manual
    ldap_default_role: Role = Role.TEACHER   # роль нового пользователя из домена
    ldap_allowed_groups: List[str] = []      # пусто = разрешён весь домен; иначе whitelist групп (sAMAccountName или DN)
    ldap_admin_groups: List[str] = []        # группы AD, участники которых получают роль ADMIN
    ldap_owner_groups: List[str] = []        # группы AD для роли OWNER (используйте крайне осторожно)
    ldap_attr_map: dict = {                  # соответствие атрибутов AD → поля SchoolHub
        "username": "sAMAccountName",
        "upn": "userPrincipalName",
        "email": "mail",
        "full_name": "displayName",
        "first_name": "givenName",
        "last_name": "sn",
        "position": "title",
        "phone": "telephoneNumber",
        "groups": "memberOf",
    }
    ldap_timeout_sec: int = 10
    ldap_sync_groups_on_login: bool = True   # обновлять список групп AD при каждом входе
    ldap_sync_attrs_on_login: bool = True    # подтягивать ФИО/должность/телефон/e-mail из AD при входе
    ldap_role_from_groups: str = "upgrade"   # upgrade = группы AD могут только повышать роль; off = роли только вручную
    ldap_resolve_group_sids: bool = False    # резолвить SID групп (tokenGroups) в имена — даёт вложенные группы

    # --- защита от перебора (важно: чужой брутфорс может заблокировать доменные учётки) ---
    login_rate_limit: int = 10               # попыток
    login_rate_window_min: int = 15          # за период

    # --- misc ---
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:4173"]
    auto_seed: bool = False                  # засеять демо-данные при старте (только dev)
    trust_proxy_headers: bool = False        # брать IP клиента из X-Forwarded-For (за nginx/DSM reverse proxy)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    # --- производные значения LDAP ---
    @property
    def ldap_port(self) -> int:
        """Порт из ldap_server (или дефолт по признаку SSL)."""
        if ":" in self.ldap_server and "//" not in self.ldap_server.split(":")[0]:
            try:
                return int(self.ldap_server.rsplit(":", 1)[1])
            except ValueError:
                pass
        return 636 if self.ldap_use_ssl else 389

    @property
    def ldap_host(self) -> str:
        host = self.ldap_server.split("//")[-1].split("/")[0]
        return host.rsplit(":", 1)[0] if ":" in host else host


def _resolve_secret_key(cfg: Settings) -> str:
    """Ключ подписи JWT: ENV → файл → автогенерация.

    Автогенерация делает установку «без секретов»: администратору не нужно ничего
    придумывать, а ключ сохраняется в постоянном каталоге данных и переживает
    пересоздание контейнера (сессии пользователей не сбрасываются).
    """
    import logging
    import secrets
    from pathlib import Path

    log = logging.getLogger("schoolhub.config")

    env_key = (os.getenv("SECRET_KEY") or "").strip()
    if env_key:
        if len(env_key) < 32:
            raise RuntimeError("SECRET_KEY короче 32 символов — задайте надёжнее или удалите переменную")
        return env_key

    key_file = Path(cfg.secret_key_file).expanduser()
    try:
        key_file.parent.mkdir(parents=True, exist_ok=True)
        if key_file.exists():
            stored = key_file.read_text(encoding="utf-8").strip()
            if len(stored) >= 32:
                return stored
        generated = secrets.token_urlsafe(48)
        key_file.write_text(generated, encoding="utf-8")
        try:
            os.chmod(key_file, 0o600)
        except OSError:  # pragma: no cover
            pass
        log.info("SECRET_KEY сгенерирован автоматически и сохранён: %s", key_file)
        return generated
    except OSError as exc:  # pragma: no cover
        log.warning("Не удалось сохранить SECRET_KEY (%s) — используется временный", exc)
        return secrets.token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    cfg = Settings()
    resolved = _resolve_secret_key(cfg)
    if resolved != cfg.secret_key:
        object.__setattr__(cfg, "secret_key", resolved)
    return cfg


settings = get_settings()
