# ============================================================================
#  SchoolHub backend. Мультиархитектурный базовый образ (amd64 + arm64),
#  поэтому сборка работает и на x86-сервере, и на Synology DS223 (Realtek ARMv8).
# ============================================================================
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /code

# curl — для healthcheck; tzdata — корректные даты/логи в локальной зоне.
# build-essential нужен только на этапе сборки wheel'ов (удаляем после установки).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tzdata ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential

# ---- опционально: инлайн-превью DOCX (конвертация в PDF через LibreOffice) ----
# Раскомментируйте, если нужен просмотр .docx прямо в браузере.
# На DS223 (2 ГБ RAM) НЕ рекомендуется: libreoffice-writer добавляет ~400 МБ
# в образ и заметно нагружает систему при конвертации.
# RUN apt-get update \
#     && apt-get install -y --no-install-recommends libreoffice-writer fonts-dejavu-core \
#     && rm -rf /var/lib/apt/lists/*

COPY . .

# каталог загрузок и права непривилегированного пользователя
RUN mkdir -p /data/uploads /data/secrets \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /data /code
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
  CMD curl -fsS http://localhost:8000/health || exit 1

# один воркер: экономия памяти (актуально для NAS с 2 ГБ RAM)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
