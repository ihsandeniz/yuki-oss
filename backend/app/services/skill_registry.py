"""Skill/plugin kaydı (Faz 24) — deklaratif YAML skill → çalıştırılabilir bileşik araç.

Her skill `backend/skills/<ad>.yaml`:
    name: arastir-ozetle
    description: "..."
    parameters:
      konu: {type: string, required: true, description: "..."}
    steps:
      - delegate: <persona>          # Yuki dışı bir persona (uzman) gerekir
        subtask: "{{konu}} araştır"
      - tool: web_search
        args: {query: "{{konu}}"}
      - say: "Bitti: {{last}}"

Skill `skill__<ad>` aracı olarak TOOLS'a kaydolur. Çağrılınca adımlar SIRAYLA
çalışır; `{{param}}` / `{{steps.N}}` / `{{last}}` ikame edilir. Son adım çıktısı döner.

Güvenlik: skill'ler yerel dosyalardır (kullanıcı yazar). Adımlar yalnızca mevcut
dispatcher araçlarını çağırabilir — YENİ yetki yok. Bozuk skill ATLANIR (boot-güvenli).
Recursion: skill-derinliği contextvar ile sınırlı (MAX_SKILL_DEPTH).
"""
from __future__ import annotations

import contextvars
import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
_SKILLS: dict[str, dict] = {}  # name -> skill def

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,48}$", re.IGNORECASE)
_skill_depth: contextvars.ContextVar[int] = contextvars.ContextVar("skill_depth", default=0)
MAX_SKILL_DEPTH = 3


def _valid_name(n) -> bool:
    return bool(n) and bool(_NAME_RE.match(str(n)))


def load_skills() -> list[dict]:
    """skills/*.yaml oku, doğrula, _SKILLS'e yükle. Bozuk skill atlanır."""
    _SKILLS.clear()
    if not _SKILLS_DIR.exists():
        return []
    out = []
    for f in sorted(_SKILLS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            name = str(data.get("name") or f.stem).strip()
            if not _valid_name(name):
                logger.warning("skill '%s': geçersiz ad, atlandı", f.name)
                continue
            steps = data.get("steps")
            if not isinstance(steps, list) or not steps:
                logger.warning("skill '%s': adım yok, atlandı", name)
                continue
            data["name"] = name
            _SKILLS[name] = data
            out.append(data)
        except Exception as e:  # noqa: BLE001
            logger.warning("skill '%s' yüklenemedi: %s", f.name, e)
    return out


def build_schemas() -> list[dict]:
    """Yüklü skill'leri `skill__<ad>` araç şemalarına çevirir."""
    schemas = []
    for name, sk in _SKILLS.items():
        props, required = {}, []
        for pn, pd in (sk.get("parameters") or {}).items():
            pd = pd or {}
            props[pn] = {"type": pd.get("type", "string"), "description": pd.get("description", pn)}
            if pd.get("required"):
                required.append(pn)
        schemas.append({"type": "function", "function": {
            "name": f"skill__{name}",
            "description": ((sk.get("description") or f"{name} skill'i") + " (bileşik skill)")[:1024],
            "parameters": {"type": "object", "properties": props, "required": required},
        }})
    return schemas


def _subst(text, params: dict, outputs: list[str]):
    if not isinstance(text, str):
        return text

    def repl(m):
        key = m.group(1).strip()
        if key == "last":
            return outputs[-1] if outputs else ""
        if key.startswith("steps."):
            try:
                return outputs[int(key.split(".", 1)[1])]
            except (ValueError, IndexError):
                return ""
        return str(params.get(key, ""))

    def metin(m):
        # Görüntü yalnız tek başına kalırsa modele görsel gider (runner); metne gömülünce base64 döküm olur.
        cikti = repl(m)
        if cikti.startswith("SCREENSHOT_DATA:") and m.group(0) != text.strip():
            return "[ekran görüntüsü]"
        return cikti

    return re.sub(r"\{\{([^}]+)\}\}", metin, text)


def _subst_deep(val, params: dict, outputs: list[str]):
    if isinstance(val, dict):
        return {k: _subst_deep(v, params, outputs) for k, v in val.items()}
    if isinstance(val, list):
        return [_subst_deep(v, params, outputs) for v in val]
    return _subst(val, params, outputs)


async def run_skill(full_name: str, args: dict) -> str:
    """Skill adımlarını sırayla çalıştır; ikame yap; son çıktıyı döndür."""
    name = full_name[len("skill__"):] if full_name.startswith("skill__") else full_name
    sk = _SKILLS.get(name)
    if not sk:
        return f"Hata: bilinmeyen skill '{name}'"
    # Eksik zorunlu girdiyle adımlar boş metinle koşar (ör. boş web araması), sonuç uydurulur.
    eksik = [p for p, d in (sk.get("parameters") or {}).items()
             if isinstance(d, dict) and d.get("required") and not str((args or {}).get(p) or "").strip()]
    if eksik:
        return f"Hata: '{name}' için zorunlu parametre eksik: {', '.join(eksik)}"
    if _skill_depth.get() >= MAX_SKILL_DEPTH:
        return f"(skill '{name}': maksimum iç içe derinlik aşıldı)"

    tok = _skill_depth.set(_skill_depth.get() + 1)
    params = args or {}
    outputs: list[str] = []
    try:
        from app.services.tools import call_tool
        for i, step in enumerate(sk["steps"]):
            try:
                if "delegate" in step:
                    from app.services.orchestrator import delegate_to_persona
                    res = await delegate_to_persona(
                        str(step["delegate"]), _subst(step.get("subtask", ""), params, outputs))
                elif "team" in step:
                    from app.services.orchestrator import run_team
                    res = await run_team(_subst(step.get("team", ""), params, outputs))
                elif "tool" in step:
                    targs = _subst_deep(step.get("args", {}) or {}, params, outputs)
                    res = await call_tool(str(step["tool"]), targs)
                elif "say" in step:
                    res = _subst(step["say"], params, outputs)
                else:
                    res = f"(adım {i}: bilinmeyen tip)"
            except Exception as e:  # noqa: BLE001
                res = f"(adım {i} hata: {e})"
            outputs.append(str(res))
        return outputs[-1] if outputs else "(skill boş çıktı)"
    finally:
        _skill_depth.reset(tok)


async def startup() -> None:
    skills = load_skills()
    if not skills:
        logger.info("skill kaydı: skills/ boş veya yok")
        return
    from app.services.tools.dispatcher import register_tools
    register_tools(build_schemas())
    logger.info("skill kaydı: %d skill → araç", len(skills))
