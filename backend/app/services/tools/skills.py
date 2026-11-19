"""Skill çalıştırma araçları — $ARGUMENTS ikameli prompt şablonları."""
import os
import re
from pathlib import Path

# Ürün: kişisel yol yok. YUKI_SKILLS_DIR override; yoksa ~/.config/yuki-oss/skills.
SKILLS_DIR = Path(os.getenv("YUKI_SKILLS_DIR") or (Path.home() / ".config" / "yuki-oss" / "skills"))


def _validate_skill_name(name: str) -> bool:
    """Skill adını doğrula: .. veya / içermemeli, sadece [a-z0-9-] karakterleri."""
    if not name:
        return False
    if ".." in name or "/" in name or "\\" in name:
        return False
    return bool(re.match(r"^[a-z0-9_-]+$", name, re.IGNORECASE))


def _kayitli_skiller() -> dict[str, dict]:
    """backend/skills/*.yaml — Yuki'nin gerçek skill kaydı (`skill__<ad>` araçları)."""
    try:
        from app.services import skill_registry
        if not skill_registry._SKILLS:
            skill_registry.load_skills()
        return skill_registry._SKILLS
    except Exception:
        return {}


def skill_list() -> str:
    """Kullanılabilir skill'leri listeler: gerçek kayıt önce, prompt şablonları ayrı başlıkta.

    Eskiden yalnız şablon dizinine bakıyordu: dizin yoksa "bulunamadı" diyor, kayıtlı
    `skill__*` araçlarını hiç göstermiyordu → model var olan skill'i "yok" diye anlatıyordu.
    """
    bolumler = []
    kayitli = _kayitli_skiller()
    if kayitli:
        bolumler.append("Kayıtlı skill'ler (`skill__<ad>` aracıyla çağrılır):\n\n" + "\n".join(
            f"• skill__{ad} — {str(sk.get('description') or '').strip()}".rstrip(" —")
            for ad, sk in sorted(kayitli.items())))

    sablonlar = []
    for f in sorted(SKILLS_DIR.glob("*.md")) if SKILLS_DIR.exists() else []:
        try:
            first_line = f.read_text(encoding="utf-8").split("\n")[0].lstrip("#").strip()
        except Exception:
            first_line = ""
        sablonlar.append(f"• {f.stem} — {first_line}" if first_line else f"• {f.stem}")
    if sablonlar:
        bolumler.append("Prompt şablonları (`skill_run` ile yüklenir):\n\n" + "\n".join(sablonlar))

    return "\n\n".join(bolumler) if bolumler else "Kayıtlı skill yok."


def skill_run(name: str, arguments: str = "") -> str:
    """Skill dosyasını okur, $ARGUMENTS'ı kullanıcı girdisiyle değiştirir.

    Dönen metin: skill'in tam talimatları — Yuki bunları doğrudan uygular.
    name: dosya adı (uzantısız), örn: 'rakip-analizi'
    arguments: skill'e geçirilecek girdi

    Güvenlik:
    - name parametresi path traversal için doğrulanır (.. ve mutlak yol reddedilir)
    - arguments parametresi HTML encode'lenerek prompt injection riskinden korunur
    """
    # .md uzantısı varsa kaldır
    name = name.removesuffix(".md")

    # Path traversal koruması: name'i doğrula
    if not _validate_skill_name(name):
        return f"Hata: Geçersiz skill adı '{name}'. Sadece [a-z0-9_-] karakterleri ve '..' olmayan adlar geçerli."

    skill_file = SKILLS_DIR / f"{name}.md"

    # Canonical path kontrolü: skill_file SKILLS_DIR altında olmalı
    try:
        skill_file.resolve().relative_to(SKILLS_DIR.resolve())
    except ValueError:
        return f"Hata: Skill '{name}' izin verilen dizin dışında."

    if not skill_file.exists():
        # skill_list bu adı gösterdi: "bulunamadı" deyip listeye geri yollama.
        if name in _kayitli_skiller():
            return f"'{name}' kayıtlı bir skill: `skill__{name}` aracıyla çağır."
        # Yakın eşleşme ara
        candidates = [f.stem for f in SKILLS_DIR.glob("*.md") if name.lower() in f.stem.lower()]
        if candidates:
            return f"Skill '{name}' bulunamadı. Benzer skill'ler: {', '.join(candidates)}"
        return f"Skill '{name}' bulunamadı. Mevcut skill'leri görmek için skill_list kullan."

    content = skill_file.read_text(encoding="utf-8")

    # $ARGUMENTS ikamesi. Metin modele düz metin gider: HTML kodlamak korumaz, tırnağı ve < işaretini
    # bozar (`"` → `&quot;`). Gizli talimata karşı koruma dış içerik katmanında (dis_icerik), burada değil.
    if "$ARGUMENTS" in content:
        if not arguments.strip():
            return f"Bu skill bir girdi gerektiriyor. Kullanım: skill_run('{name}', '<girdin>')"
        content = content.replace("$ARGUMENTS", arguments)

    return f"[SKILL: {name}]\n\n{content}"
