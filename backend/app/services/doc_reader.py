"""Doküman metin çıkarma servisi — media galerisinden sohbete dosya iletme.

Desteklenen türler ve okuyucular:
  .pdf                → pypdf
  .xlsx               → openpyxl (values_only, sekme başlıklı)
  .xls                → xlrd (eski Excel formatı)
  .docx               → python-docx (paragraflar + tablolar)
  .csv .txt .md .json .log → düz metin (utf-8, hatalıysa latin-1 fallback)

Çıktı LLM bağlamına gideceği için MAX_CHARS ile kırpılır (token koruması).
"""
from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

from app.mesajlar import M

logger = logging.getLogger(__name__)

MAX_CHARS = 24_000          # LLM bağlam koruması — aşarsa kırpılır
_XLS_MAX_ROWS = 400         # tablo başına satır sınırı
_XLS_MAX_COLS = 30

DOC_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".docx", ".csv", ".txt", ".md", ".json", ".log"}


def _read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception as e:  # tek sayfa hatası tümünü düşürmesin
            txt = f"[sayfa {i + 1} okunamadı: {e}]"  # i18n-istisna: modele giden belge metni (işaret), kullanıcıya gösterilmez
        if txt.strip():
            parts.append(f"--- Sayfa {i + 1} ---\n{txt.strip()}")
        if sum(len(p) for p in parts) > MAX_CHARS:
            parts.append(f"[... kalan {len(reader.pages) - i - 1} sayfa kırpıldı]")  # i18n-istisna: modele giden belge metni (işaret), kullanıcıya gösterilmez
            break
    return "\n\n".join(parts)


def _rows_to_text(rows, sheet_name: str) -> str:
    lines = [f"=== Sayfa: {sheet_name} ==="]
    for r_i, row in enumerate(rows):
        if r_i >= _XLS_MAX_ROWS:
            lines.append(f"[... satır sınırı ({_XLS_MAX_ROWS}) aşıldı, kırpıldı]")  # i18n-istisna: modele giden belge metni (işaret), kullanıcıya gösterilmez
            break
        cells = ["" if c is None else str(c) for c in row[:_XLS_MAX_COLS]]
        if any(c.strip() for c in cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def _read_xlsx(path: Path) -> str:
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=True)
    parts = []
    for ws in wb.worksheets:
        parts.append(_rows_to_text(ws.iter_rows(values_only=True), ws.title))
        if sum(len(p) for p in parts) > MAX_CHARS:
            break
    wb.close()
    return "\n\n".join(parts)


def _read_xls(path: Path) -> str:
    import xlrd
    wb = xlrd.open_workbook(str(path))
    parts = []
    for ws in wb.sheets():
        rows = (ws.row_values(r) for r in range(ws.nrows))
        parts.append(_rows_to_text(rows, ws.name))
        if sum(len(p) for p in parts) > MAX_CHARS:
            break
    return "\n\n".join(parts)


def _read_docx(path: Path) -> str:
    import docx
    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for t_i, table in enumerate(d.tables):
        lines = [f"--- Tablo {t_i + 1} ---"]
        for row in table.rows:
            lines.append(" | ".join(c.text.strip() for c in row.cells))
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _read_csv(path: Path) -> str:
    text = _read_text_file(path)
    # csv'yi hizalı boru formatına çevir (LLM tablo okuması kolaylaşır)
    try:
        rows = list(csv.reader(io.StringIO(text)))
        return _rows_to_text(rows, path.name)
    except Exception:
        return text


_READERS = {
    ".pdf": _read_pdf,
    ".xlsx": _read_xlsx,
    ".xls": _read_xls,
    ".docx": _read_docx,
    ".csv": _read_csv,
    ".txt": _read_text_file,
    ".md": _read_text_file,
    ".json": _read_text_file,
    ".log": _read_text_file,
}


def extract_text(path: Path) -> dict:
    """Dosyadan metin çıkarır.

    Döner: {"text": str, "truncated": bool, "chars": int, "error": str | None}
    """
    ext = path.suffix.lower()
    reader = _READERS.get(ext)
    if reader is None:
        return {"text": "", "truncated": False, "chars": 0,
                "error": M("belge.desteklenmeyen", uzanti=ext)}
    try:
        text = reader(path).strip()
    except Exception as e:
        logger.warning("[doc_reader] %s okunamadı: %s", path.name, e)
        return {"text": "", "truncated": False, "chars": 0, "error": str(e)}

    truncated = len(text) > MAX_CHARS
    if truncated:
        text = text[:MAX_CHARS] + "\n[... içerik kırpıldı]"  # i18n-istisna: modele giden belge metni işareti
    if not text:
        return {"text": "", "truncated": False, "chars": 0,
                "error": M("belge.metin-yok")}
    return {"text": text, "truncated": truncated, "chars": len(text), "error": None}
