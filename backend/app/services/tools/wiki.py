"""Wiki bilgi tabanı araçları: arama, okuma, yazma, index."""
from pathlib import Path
import datetime
import os

# Ürün: kişisel vault yolu yok. Kullanıcı isterse YUKI_WIKI_ROOT ile kendi
# not dizinini gösterir; yoksa ~/.config/yuki-oss/wiki (P1'de bu araç kapalı).
WIKI_ROOT = Path(os.getenv("YUKI_WIKI_ROOT") or (Path.home() / ".config" / "yuki-oss" / "wiki"))
_BASE = WIKI_ROOT.parent
_MAX_READ = 10_000


def _safe_wiki_path(path: str) -> Path | None:
    """path'in WIKI dizini içinde olduğunu doğrula, resolve edilmiş Path döndür."""
    try:
        target = (_BASE / path).resolve()
    except Exception:
        return None
    # `startswith` kardeş dizini (`WIKI-disari`) de içeride sayıyordu.
    if not target.is_relative_to(WIKI_ROOT.resolve()):
        return None
    return target


def wiki_search(query: str, max_results: int = 10) -> str:
    """Wiki'de çok-kelimeli arama yapar. Başlık eşleşmeleri önce gelir."""
    if not WIKI_ROOT.exists():
        return "Wiki dizini bulunamadı."

    words = [w.strip() for w in query.lower().split() if w.strip()]
    if not words:
        return "Arama sorgusu boş."

    scored: list[tuple[int, str, str]] = []  # (skor, rel_path, excerpt)

    for md_file in WIKI_ROOT.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            content_lower = content.lower()
            name_lower = md_file.name.lower()

            # Kaç kelime eşleşiyor?
            matched = sum(1 for w in words if w in content_lower)
            if matched == 0:
                continue

            # Başlık/dosya adında eşleşme varsa bonus puan
            title_bonus = sum(2 for w in words if w in name_lower)
            score = matched + title_bonus

            # İlk eşleşen satırı excerpt olarak al
            excerpt = ""
            for line in content.split("\n"):
                stripped = line.strip()
                if any(w in stripped.lower() for w in words) and len(stripped) > 10:
                    excerpt = stripped[:140]
                    break

            rel_path = str(md_file.relative_to(_BASE))
            scored.append((score, rel_path, excerpt))
        except Exception:
            continue

    if not scored:
        return f"Wiki'de '{query}' için sonuç bulunamadı."

    # Yüksek skor önce
    scored.sort(key=lambda x: x[0], reverse=True)
    lines = []
    for score, rel_path, excerpt in scored[:max_results]:
        lines.append(f"📄 {rel_path}\n  ↳ {excerpt}")

    return f"Wiki arama sonuçları ({len(lines)}/{len(scored)} sayfa):\n\n" + "\n\n".join(lines)


def wiki_read(path: str) -> str:
    """Wiki sayfasını okur. path: WIKI/sources/projects/2026-04-25-ornek-sayfa.md formatında."""
    target = _safe_wiki_path(path)
    if target is None:
        return "Hata: Yalnızca WIKI dizinine erişilebilir veya geçersiz yol."
    if not target.exists():
        return f"Sayfa bulunamadı: {path}"

    content = target.read_text(encoding="utf-8")
    if len(content) > _MAX_READ:
        content = content[:_MAX_READ] + f"\n\n[... sayfa kesildi ({len(content)} karakter toplam). Bölüm adı belirterek devamını iste ...]"
    return content


def wiki_index() -> str:
    """Wiki index sayfasını ve bilgi-arsivi _index.md'sini okur. Hangi sayfaların var olduğunu öğrenmek için kullan."""
    parts = []
    for idx_path in [
        WIKI_ROOT / "index.md",
        WIKI_ROOT / "bilgi-arsivi" / "_index.md",
        WIKI_ROOT / "hot.md",
    ]:
        if idx_path.exists():
            content = idx_path.read_text(encoding="utf-8")
            if len(content) > 3000:
                content = content[:3000] + "\n[kesildi...]"
            rel = str(idx_path.relative_to(_BASE))
            parts.append(f"=== {rel} ===\n{content}")

    if not parts:
        return "Wiki index sayfaları bulunamadı."
    return "\n\n".join(parts)


def wiki_write(path: str, content: str, append: bool = False) -> str:
    """Wiki'ye yeni sayfa yazar veya mevcut sayfaya ekler.

    path: WIKI/ ile başlamalı (örn. WIKI/sources/projects/2026-05-17-yeni-not.md)
    append: True ise dosyanın sonuna ekler, False ise üzerine yazar.
    """
    target = _safe_wiki_path(path)
    if target is None:
        return "Hata: Yalnızca WIKI dizinine yazılabilir veya geçersiz yol."
    if not path.startswith("WIKI/"):
        return "Hata: Yol WIKI/ ile başlamalı."
    if not path.endswith(".md"):
        return "Hata: Yalnızca .md dosyaları yazılabilir."

    # Kritik index/log dosyalarına doğrudan yazma izni yok
    # Çözülmüş yolla karşılaştırılır: ham metin `WIKI/./index.md` ve `WIKI//index.md` ile atlanıyordu.
    protected = {WIKI_ROOT.resolve() / ad for ad in ("index.md", "log.md", "hot.md")}
    if target in protected and not append:
        return f"Hata: {path} korumalı bir dosya — üzerine yazılamaz. Eklemek için append=true kullan."

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if append and target.exists():
            existing = target.read_text(encoding="utf-8")
            target.write_text(existing + "\n" + content, encoding="utf-8")
            return f"OK: {path} dosyasına eklendi ({len(content)} karakter)."
        else:
            target.write_text(content, encoding="utf-8")
            return f"OK: {path} dosyası yazıldı ({len(content)} karakter)."
    except Exception as e:
        return f"Hata: {e}"
