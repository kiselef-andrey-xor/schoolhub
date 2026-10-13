"""Ограничение частоты попыток входа.

Зачем нужно именно здесь: при аутентификации через домен каждая неудачная попытка
идёт в Active Directory и приближает **блокировку доменной учётки** (lockout policy).
Локальный троттлинг защищает и школу, и чужие учётные записи от случайного/злонамеренного
перебора.

Реализация — in-memory (на один процесс uvicorn). Для кластера из нескольких реплик
замените хранилище на Redis с тем же интерфейсом (см. docs/DEPLOY-NAS.md).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from app.config import settings
from app.errors import AppError


@dataclass
class _Bucket:
    attempts: deque[float]


class LoginRateLimiter:
    def __init__(self, max_attempts: int | None = None, window_sec: int | None = None) -> None:
        self.max_attempts = max_attempts if max_attempts is not None else settings.login_rate_limit
        self.window = window_sec if window_sec is not None else settings.login_rate_window_min * 60
        self._by_ip: dict[str, deque[float]] = defaultdict(deque)
        self._by_account: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, bucket: deque[float], now: float) -> None:
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()

    def check(self, ip: str | None, account: str) -> None:
        """Бросает 429, если лимит исчерпан. Вызывается ДО обращения в каталог."""
        if self.max_attempts <= 0:
            return
        now = time.monotonic()
        key = account.lower()

        if ip:
            self._prune(self._by_ip[ip], now)
            if len(self._by_ip[ip]) >= self.max_attempts * 3:      # по IP лимит мягче (NAT/весь класс)
                raise self._too_many(ip)
        self._prune(self._by_account[key], now)
        if len(self._by_account[key]) >= self.max_attempts:
            raise self._too_many(key)

    def register_failure(self, ip: str | None, account: str) -> None:
        now = time.monotonic()
        self._by_account[account.lower()].append(now)
        if ip:
            self._by_ip[ip].append(now)

    def register_success(self, ip: str | None, account: str) -> None:
        self._by_account.pop(account.lower(), None)
        # счётчик по IP не сбрасываем: успех одного не отменяет перебор другого

    def _too_many(self, key: str) -> AppError:
        return AppError(
            status_code=429,
            detail=(
                f"Слишком много неудачных попыток входа. Повторите через "
                f"{settings.login_rate_window_min} мин. Если пароль забыт — обратитесь к администратору домена."
            ),
            code="RATE_LIMITED",
        )

    def stats(self) -> dict[str, int]:
        now = time.monotonic()
        return {
            "tracked_accounts": sum(1 for b in self._by_account.values() if b and now - b[-1] < self.window),
            "tracked_ips": sum(1 for b in self._by_ip.values() if b and now - b[-1] < self.window),
        }


login_limiter = LoginRateLimiter()
