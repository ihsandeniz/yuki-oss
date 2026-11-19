"""Fitnes araçları: Yuki için beslenme + antrenman yönetimi.

2026-11-12 (Fitnes v2): araçlar eskiden yalnız Postgres'e yazıyordu; ekran ise artık tek kaynak
olan gömülü depoyu (`fitness_store`) okuyor. Yuki'nin eklediği öğün ekranda görünsün diye araçlar
da aynı depoya bağlandı. Doğrulama depoya gitmeden ÖNCE yapılır (geçersiz girdi hiçbir şey yazmaz).
"""
import json
from typing import Optional

_OGUN_ETIKET = {"kahvalti": "kahvaltı", "ogle": "öğle", "aksam": "akşam", "ara": "ara öğün"}
_OGUN_SIMGE = {"kahvalti": "🌅", "ogle": "☀️", "aksam": "🌙", "ara": "🍎"}


async def _pool():
    """Depo erişim noktası (adı eski: testler bu tek kapıyı sahteyle değiştirip "depoya gidildi mi"yi ölçer)."""
    from app.services import fitness_store
    return fitness_store


def _gun(deger: Optional[str], depo) -> str:
    from datetime import date
    if not deger:
        return depo._bugun()
    return date.fromisoformat(str(deger)[:10]).isoformat()


async def get_fitness_summary(target_date: Optional[str] = None) -> str:
    """Belirli bir gün için beslenme + antrenman özetini döndürür.

    Args:
        target_date: YYYY-MM-DD formatı (opsiyonel, varsayılan: bugün)
    """
    try:
        depo = await _pool()
        d = _gun(target_date, depo)
        ogunler = depo.list_meals(d)
        toplam = {k: sum(float(m.get(k) or 0) for m in ogunler) for k in ("cal", "protein", "carb", "fat")}
        cfg = depo.get_config()
        exercises = [e["name"] for e in depo.get_workout(d).get("exercises", [])]
        cal_goal = cfg.get("calGoal", 2000)
        cal_pct = int(toplam["cal"] / cal_goal * 100) if cal_goal > 0 else 0
        lines = [
            f"📊 {d} Fitness Özeti:",
            f"  🍽️  Beslenme ({len(ogunler)} öğün): {toplam['cal']:.0f} / {cal_goal} kcal ({cal_pct}%)",
            f"  💪 Makro: Protein {toplam['protein']:.0f}g / Karb {toplam['carb']:.0f}g / Yağ {toplam['fat']:.0f}g",
        ]
        if exercises:
            lines.append(f"  🏋️  Antrenman ({len(exercises)} egzersiz): {', '.join(exercises)}")
        else:
            lines.append("  🏋️  Antrenman: kayıt yok")
        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Fitness özeti alınamadı. {e}"


async def log_meal(
    name: str,
    cal: float,
    meal: str = "ara",
    protein: float = 0,
    carb: float = 0,
    fat: float = 0,
    entry_date: Optional[str] = None,
) -> str:
    """Yeni öğün / besin kaydı ekler.

    Args:
        name: Besin adı
        cal: Kalori (kcal)
        meal: Öğün tipi — 'kahvalti', 'ogle', 'aksam', 'ara'
        protein: Protein (g)
        carb: Karbonhidrat (g)
        fat: Yağ (g)
        entry_date: YYYY-MM-DD (opsiyonel, varsayılan: bugün)
    """
    if min(cal, protein, carb, fat) < 0:
        return "Hata: Kalori ve besin değerleri negatif olamaz. Kayıt eklenmedi."
    try:
        depo = await _pool()
        meal = meal if meal in _OGUN_ETIKET else "ara"
        k = depo.create_meal(meal, name, cal, protein, carb, fat, _gun(entry_date, depo))
        return f"Öğün eklendi: '{k['name']}' — {k['cal']:.0f} kcal ({_OGUN_ETIKET[meal]}) [id: {k['id']}]"
    except Exception as e:
        return f"Hata: Öğün eklenemedi. {e}"


async def delete_meal(meal_id: str) -> str:
    """Öğün kaydını siler.

    Args:
        meal_id: Öğün UUID'si (önce list_meals ile bul)
    """
    try:
        depo = await _pool()
        kayit = next((m for m in depo.oku()["meals"] if m.get("id") == meal_id), None)
        if kayit is None or not depo.delete_meal(meal_id):
            return f"Öğün bulunamadı: {meal_id}"
        return f"Öğün silindi: '{kayit['name']}' ({float(kayit['cal']):.0f} kcal)"
    except Exception as e:
        return f"Hata: Öğün silinemedi. {e}"


async def list_meals(target_date: Optional[str] = None) -> str:
    """Belirli gün için öğün listesini döndürür.

    Args:
        target_date: YYYY-MM-DD (opsiyonel, varsayılan: bugün)
    """
    try:
        depo = await _pool()
        d = _gun(target_date, depo)
        rows = depo.list_meals(d)
        if not rows:
            return f"{d}: Öğün kaydı yok."
        lines = [f"{d} öğünleri ({len(rows)} kayıt):"]
        for r in rows:
            lines.append(f"  {_OGUN_SIMGE.get(r['meal'], '🍽️')} {r['name']} — {r['cal']:.0f} kcal "
                         f"(P:{r['protein']:.0f}g K:{r['carb']:.0f}g Y:{r['fat']:.0f}g) [id: {r['id']}]")
        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Öğünler listelenemedi. {e}"


async def log_workout_exercise(
    name: str,
    sets: int = 3,
    reps: int = 10,
    weight: float = 0,
    session_date: Optional[str] = None,
) -> str:
    """Antrenman seansına egzersiz ekler. Setler "yapıldı" olarak işaretlenir (Yuki'ye "yaptım" denmiştir).

    Args:
        name: Egzersiz adı (örn: 'Bench Press', 'Squat')
        sets: Set sayısı
        reps: Her set için tekrar sayısı (süreli harekette saniye; adına "(sn)" ekle)
        weight: Ağırlık (kg, 0 = vücut ağırlığı)
        session_date: YYYY-MM-DD (opsiyonel, varsayılan: bugün)
    """
    # Tekrar 0 ve eksi ağırlık (destekli barfiks) geçerli.
    if sets < 1 or reps < 0:
        return "Hata: Set en az 1, tekrar negatif olmamalı. Egzersiz eklenmedi."
    try:
        depo = await _pool()
        d = _gun(session_date, depo)
        ex = depo.add_exercise(name, [{"reps": reps, "weight": weight, "completed": True}] * min(sets, 50), d)
        weight_str = f" @ {weight}kg" if weight > 0 else " (vücut ağırlığı)"
        return f"Egzersiz eklendi: '{name}' — {sets}x{reps}{weight_str} [id: {ex['id']}]"
    except Exception as e:
        return f"Hata: Egzersiz eklenemedi. {e}"


async def list_workout(session_date: Optional[str] = None) -> str:
    """Belirli gün antrenman seansını listeler.

    Args:
        session_date: YYYY-MM-DD (opsiyonel, varsayılan: bugün)
    """
    try:
        depo = await _pool()
        d = _gun(session_date, depo)
        w = depo.get_workout(d)
        if not w.get("id"):
            return f"{d}: Antrenman kaydı yok."
        lines = [f"{d} antrenmanı ({len(w['exercises'])} egzersiz):"]
        for ex in w["exercises"]:
            done = sum(1 for s in ex["sets"] if depo.yapildi_mi(s))
            set_str = ", ".join(f"{s['reps']}x{s['weight']:g}kg" for s in ex["sets"])
            lines.append(f"  🏋️  {ex['name']} [{done}/{len(ex['sets'])} set] — {set_str} [id: {ex['id']}]")
        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Antrenman listelenemedi. {e}"


async def get_fitness_config() -> str:
    """Mevcut beslenme hedeflerini döndürür (kalori, protein, karb, yağ)."""
    try:
        cfg = (await _pool()).get_config()
        return (
            f"Beslenme hedefleri:\n"
            f"  Kalori: {cfg['calGoal']} kcal\n"
            f"  Protein: {cfg['proteinGoal']} g\n"
            f"  Karbonhidrat: {cfg['carbGoal']} g\n"
            f"  Yağ: {cfg['fatGoal']} g"
        )
    except Exception as e:
        return f"Hata: Config alınamadı. {e}"


async def update_fitness_config(
    cal_goal: Optional[int] = None,
    protein_goal: Optional[int] = None,
    carb_goal: Optional[int] = None,
    fat_goal: Optional[int] = None,
) -> str:
    """Beslenme hedeflerini günceller.

    Args:
        cal_goal: Günlük kalori hedefi (kcal)
        protein_goal: Günlük protein hedefi (g)
        carb_goal: Günlük karbonhidrat hedefi (g)
        fat_goal: Günlük yağ hedefi (g)
    """
    if any(h is not None and h < 0 for h in (cal_goal, protein_goal, carb_goal, fat_goal)):
        return "Hata: Hedefler negatif olamaz. Değişiklik yapılmadı."
    updates = {"calGoal": cal_goal, "proteinGoal": protein_goal, "carbGoal": carb_goal, "fatGoal": fat_goal}
    changed = [f"{k}→{v}" for k, v in updates.items() if v is not None]
    if not changed:
        return "Hata: Güncellenecek değer belirtilmedi."
    try:
        (await _pool()).update_config(**updates)
        return f"Hedefler güncellendi: {', '.join(changed)}"
    except Exception as e:
        return f"Hata: Config güncellenemedi. {e}"


async def save_fitness_template(name: str, exercises: str) -> str:
    """Antrenman şablonu kaydeder.

    Args:
        name: Şablon adı
        exercises: JSON string — [{\"name\":\"Bench Press\",\"sets\":[{\"reps\":10,\"weight\":80}]}]
    """
    try:
        ex_list = json.loads(exercises)
    except Exception:
        return "Hata: exercises geçerli JSON olmalı."
    if not isinstance(ex_list, list) or not all(isinstance(e, dict) for e in ex_list):
        return "Hata: exercises egzersiz nesnelerinden oluşan bir liste olmalı."
    try:
        k = (await _pool()).create_template(name, ex_list)
        return f"Şablon kaydedildi: '{name}' [id: {k['id']}]"
    except Exception as e:
        return f"Hata: Şablon kaydedilemedi. {e}"


async def list_fitness_templates() -> str:
    """Kayıtlı antrenman şablonlarını listeler."""
    try:
        rows = (await _pool()).list_templates()
        if not rows:
            return "Kayıtlı şablon yok."
        lines = [f"Antrenman şablonları ({len(rows)}):"]
        for r in rows:
            exs = r.get("exercises") or []
            ex_names = [e.get("name", "?") for e in exs[:4] if isinstance(e, dict)]
            more = f" +{len(exs) - 4}" if len(exs) > 4 else ""
            lines.append(f"  📋 {r['name']} — {', '.join(ex_names)}{more} [id: {r['id']}]")
        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Şablonlar listelenemedi. {e}"


async def delete_fitness_template(template_id: str) -> str:
    """Antrenman şablonunu siler.

    Args:
        template_id: Şablon UUID'si
    """
    try:
        depo = await _pool()
        kayit = next((x for x in depo.list_templates() if x["id"] == template_id), None)
        if kayit is None or not depo.delete_template(template_id):
            return f"Şablon bulunamadı: {template_id}"
        return f"Şablon silindi: '{kayit['name']}'"
    except Exception as e:
        return f"Hata: Şablon silinemedi. {e}"
