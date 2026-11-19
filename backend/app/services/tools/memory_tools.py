"""Hafıza araçları: arama, istatistik, optimizasyon.

Faz 17: character_key=None → aktif persona'nın anılarında işlem yapar.
"""


async def memory_search(query: str, limit: int = 5) -> str:
    """Yuki'nin uzun vadeli hafızasında semantik arama yapar."""
    from app.config import MEMORY_ENABLED, SESSION_ID
    if not MEMORY_ENABLED:
        return "Hafıza devre dışı (MEMORY_ENABLED=false veya DATABASE_URL eksik)."
    # Gömme modeli yokken arama ModuleNotFoundError'la "Hata: …" dönüyordu; model LLM'e ham
    # istisna metni okuyordu. Kapı api/memory.py::_motor_hazir ile aynı kaynak.
    from app.services.llm import _embedding_engine_ready
    if not _embedding_engine_ready():
        return ("Uzun vadeli hafıza araması bu kurulumda kullanılamıyor: hafıza anlama modeli "
                "kurulu değil (EMBED_ONNX_DIR). Kısa dönem sohbet hafızası çalışıyor.")
    try:
        from app.services.memory import get_memory_service, _get_active_character
        from app.config import MEMORY_GLOBAL_CHARACTERS
        mem = get_memory_service()
        char_key = _get_active_character()
        is_global = char_key in MEMORY_GLOBAL_CHARACTERS
        results = await mem.search(
            query,
            limit=min(limit, 10),
            session_id=SESSION_ID,
            min_similarity=0.3,
            character_key=None if is_global else char_key,
            cross_character=is_global,
        )
        scope_label = "tüm karakterler" if is_global else char_key
        if not results:
            return f"'{query}' için {scope_label} hafızasında eşleşme bulunamadı."

        lines = [f"[{scope_label} hafızası — {len(results)} sonuç]"]
        for r in results:
            score = f"{r.similarity:.2f}" if hasattr(r, "similarity") else "?"
            src = f"({r.character_key}) " if is_global and r.character_key and r.character_key != char_key else ""
            lines.append(f"[{r.category}|skor:{score}] {src}{r.role}: {r.content}")
        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Hafıza araması başarısız. {str(e)}"


async def memory_stats() -> str:
    """Yuki'nin hafıza istatistiklerini döner: kapsam başına kayıt sayısı ve önem ortalaması."""
    from app.config import MEMORY_ENABLED, SESSION_ID
    if not MEMORY_ENABLED:
        return "Hafıza devre dışı."
    try:
        from app.services.memory import get_memory_service
        mem = get_memory_service()
        data = await mem.stats(session_id=SESSION_ID)
        char_key = data.get("character_key", "?")
        total = data.get("total", 0)
        scopes = data.get("scopes", {})
        if not total:
            return f"[{char_key}] Hafızada henüz kayıt yok."
        lines = [f"[{char_key}] Toplam: {total} anı"]
        for scope, info in scopes.items():
            lines.append(f"  [{scope}] {info['count']} kayıt — ort. önem: {info['avg_importance']:.2f}")
        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Hafıza istatistikleri alınamadı. {str(e)}"


async def memory_reflect() -> str:
    """Hafızayı optimize eder: benzer fact/preference anılarını birleştirir (dedup)."""
    from app.config import MEMORY_ENABLED, SESSION_ID
    if not MEMORY_ENABLED:
        return "Hafıza devre dışı."
    try:
        from app.services.memory import get_memory_service, _get_active_character
        mem = get_memory_service()
        char_key = _get_active_character()
        deleted = await mem.consolidate_facts(session_id=SESSION_ID, threshold=0.92, character_key=char_key)
        total = await mem.count(session_id=SESSION_ID, character_key=char_key)
        if deleted == 0:
            return f"[{char_key}] Hafıza zaten temiz — duplikat bulunamadı. Toplam: {total} anı."
        return f"[{char_key}] Hafıza optimize edildi: {deleted} duplikat anı silindi. Kalan: {total} anı."
    except Exception as e:
        return f"Hata: Hafıza optimizasyonu başarısız. {str(e)}"
