"""Not alma araçları: oluştur, listele, sil."""

import json
import uuid
from datetime import datetime
from pathlib import Path

from app.config import DATA_DIR
from app.services import guvenli_json

_NOTES_FILE = DATA_DIR / "notes.json"
# Silinen notlar geri getirilebilsin diye burada bekler (görev silme de çöpe atar).
_COP_SINIRI = 50


def _load() -> list[dict]:
    return guvenli_json.oku(_NOTES_FILE, [], list)


def _save(notes: list[dict]) -> None:
    guvenli_json.yaz(_NOTES_FILE, notes)


def create_note(content: str, title: str = "") -> str:
    """Yeni not oluşturur."""
    if not (content or "").strip():
        return "Hata: Boş not kaydedilmez, içerik gerekli."
    notes = _load()
    note = {
        "id": uuid.uuid4().hex[:8],
        "title": title or content[:40],
        "content": content,
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    notes.append(note)
    _save(notes)
    return f"Not kaydedildi: [{note['id']}] {note['title']}"


def list_notes() -> str:
    """Tüm notları listeler."""
    notes = _load()
    if not notes:
        return "Henüz hiç not yok."
    lines = []
    for n in notes:
        lines.append(f"• [{n['id']}] {n['created_at']} — {n['title']}")
    return "\n".join(lines)


def get_note(note_id: str) -> str:
    """Belirli bir notun tam içeriğini getirir."""
    notes = _load()
    for n in notes:
        if n["id"] == note_id:
            return f"[{n['id']}] {n['title']}\n{n['created_at']}\n\n{n['content']}"
    return f"Not bulunamadı: {note_id}"


def _cop_dosyasi():
    return _NOTES_FILE.with_name("notes_trash.json")


def delete_note(note_id: str) -> str:
    """Notu çöpe taşır; restore_note ile geri gelir."""
    notes = _load()
    silinen = [n for n in notes if n["id"] == note_id]
    if not silinen:
        return f"Not bulunamadı: {note_id}"
    cop = guvenli_json.oku(_cop_dosyasi(), [], list)
    cop = (cop + silinen)[-_COP_SINIRI:]
    guvenli_json.yaz(_cop_dosyasi(), cop)
    _save([n for n in notes if n["id"] != note_id])
    return f"Not silindi: {note_id} (çöpte; restore_note ile geri getirilebilir)"


def restore_note(note_id: str) -> str:
    """Çöpteki notu geri getirir."""
    cop = guvenli_json.oku(_cop_dosyasi(), [], list)
    bulunan = [n for n in cop if n.get("id") == note_id]
    if not bulunan:
        return f"Hata: Çöpte bu kimlikle not yok: {note_id}"
    notes = _load()
    if not any(n["id"] == note_id for n in notes):
        notes.append(bulunan[-1])
        _save(notes)
    guvenli_json.yaz(_cop_dosyasi(), [n for n in cop if n.get("id") != note_id])
    return f"Not geri getirildi: [{note_id}] {bulunan[-1].get('title', '')}"
