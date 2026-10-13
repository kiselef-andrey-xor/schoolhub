"""Работа с документами приказов: отдача файла, превью, (опц.) конвертация DOCX→PDF.

Политика:
  * PDF отдаётся как есть с Content-Disposition: inline → нативное превью в браузере.
  * DOCX отдаётся как attachment (браузеры не рендерят docx). Для инлайн-просмотра
    включите конвертер: LibreOffice headless (`soffice --headless --convert-to pdf`).
    Конвертация выполняется один раз при загрузке, результат кэшируется рядом с файлом.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from app.services.storage import storage

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOC_MIME = "application/msword"

SOFFICE_CANDIDATES = ("/usr/bin/soffice", "/usr/bin/libreoffice", "soffice")


def soffice_available() -> bool:
    for candidate in SOFFICE_CANDIDATES:
        if shutil.which(candidate):
            return True
    return False


def convert_to_pdf(storage_path: str, timeout: int = 90) -> str | None:
    """Конвертирует DOCX/DOC в PDF, возвращает storage_path PDF или None, если конвертер недоступен.

    Требуется в образе: `apt-get install -y libreoffice-writer --no-install-recommends`.
    """
    src = storage.abspath(storage_path)
    if src.suffix.lower() not in {".docx", ".doc"}:
        return None
    if not soffice_available():
        return None

    cache = src.with_suffix(".preview.pdf")
    if cache.exists():
        return str(Path(*Path(storage_path).with_suffix(".preview.pdf").parts))

    soffice = next((c for c in SOFFICE_CANDIDATES if shutil.which(c)), None)
    if not soffice:  # pragma: no cover
        return None

    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [soffice, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", tmp, str(src)],
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode != 0:  # pragma: no cover
            return None
        produced = list(Path(tmp).glob("*.pdf"))
        if not produced:  # pragma: no cover
            return None
        shutil.copy2(produced[0], cache)

    return str(Path(*Path(storage_path).with_suffix(".preview.pdf").parts))


def preview_info(mime_type: str, storage_path: str) -> dict:
    """Что отдать фронту: inline-превью (pdf) или только скачивание (docx)."""
    if mime_type == PDF_MIME:
        return {"preview": "inline", "mime": PDF_MIME, "path": storage_path}
    converted = convert_to_pdf(storage_path) if mime_type in (DOCX_MIME, DOC_MIME) else None
    if converted:
        return {"preview": "inline", "mime": PDF_MIME, "path": converted, "converted": True}
    return {"preview": "download", "mime": mime_type, "path": storage_path}
