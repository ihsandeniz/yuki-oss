"""Fitnes oyun metinleri (tr/en) — olay kartları, lig/beceri/unvan/ödül adları, kural sebepleri.

Neden ayrı katalog: bu metinler hem ön yüze (kart, bildirim) hem push'a gider ve yalnız Fitnes'e aittir.
Genel katalog (`app/mesajlar`) yerine burada tutulur; dil seçimi yine genel katalogla AYNI kaynaktan
(`mesajlar.mevcut_dil()` — arayüz dili) okunur, yani ikisi ayrışamaz. Eksik İngilizce anahtar
Türkçeye, eksik Türkçe anahtar anahtarın kendisine düşer (kayıp metin görünür kalsın).
"""
from __future__ import annotations

TR: dict[str, str] = {
    # ligler
    "lig.E": "Kül", "lig.D": "Kıvılcım", "lig.C": "Ay Taşı", "lig.B": "Gümüş Hilal",
    "lig.A": "Takımyıldız", "lig.S": "Tutulma",
    # seviye ödülleri
    "odul.uyanan": "Uyanan", "odul.gece_moru": "Gece Moru vurgu", "odul.ince_gumus": "İnce gümüş halka",
    "odul.yolcu": "Yolcu", "odul.sigil_1": "Sigil I", "odul.buz_mavisi": "Buz Mavisi vurgu",
    "odul.demir_cirak": "Demir Çırak", "odul.cift_halka": "Çift halka çerçeve",
    "odul.halka_genisleme": "Tören: halka genişlemesi", "odul.cizgili": "Çizgili XP rayı",
    "odul.gece_talimcisi": "Gece Talimcisi", "odul.sigil_2": "Sigil II", "odul.ay_gumusu": "Ay Gümüşü vurgu",
    "odul.sessiz_guc": "Sessiz Güç", "odul.isaretli_halka": "İşaretli halka", "odul.yildiz_tozu": "Tören: yıldız tozu",
    "odul.yuku_tasiyan": "Yükü Taşıyan", "odul.sigil_3": "Sigil III", "odul.takimyildiz": "Takımyıldız XP rayı",
    "odul.golgesini_asan": "Gölgesini Aşan", "odul.altin_cizgi": "Soluk altın çizgili halka",
    "odul.gece_yarisi": "Gece Yarısı Mavisi vurgu", "odul.tutulma_gecisi": "Tören: tutulma geçişi",
    "odul.yildiz_doven": "Yıldız Döven", "odul.sigil_4": "Sigil IV", "odul.yorunge": "Yörünge çerçevesi",
    "odul.tutulma_bekcisi": "Tutulma Bekçisi", "odul.sigil_5": "Sigil V", "odul.tam_toren": "Tam tören",
    # beceriler (+ evrimler)
    "beceri.agir_yuk": "Ağır Yük", "beceri.dev_gucu": "Dev Gücü",
    "beceri.rekor_avcisi": "Rekor Avcısı", "beceri.sinir_kirici": "Sınır Kırıcı",
    "beceri.hacim_bilgesi": "Hacim Bilgesi", "beceri.bitmeyen_nefes": "Bitmeyen Nefes",
    "beceri.uzun_soluk": "Uzun Soluk",
    "beceri.demir_tutus": "Demir Tutuş", "beceri.celik_irade": "Çelik İrade",
    "beceri.seri_ustasi": "Seri Ustası", "beceri.kirilmaz": "Kırılmaz",
    "beceri.kayit_tutucu": "Kayıt Tutucu",
    "beceri.protein_sezgisi": "Protein Sezgisi", "beceri.metabolik_hakim": "Metabolik Hâkim",
    "beceri.golge_yarisi": "Gölge Yarışı", "beceri.golgesiz": "Gölgesiz",
    "beceri.donus": "Dönüş",
    "kosul.agir_yuk": "Bir katalog hareketinde e1RM ≥ 100 kg", "kosul.dev_gucu": "En iyi 3 katalog e1RM toplamı ≥ 300",
    "kosul.rekor_avcisi": "10 rekor", "kosul.sinir_kirici": "50 rekor",
    "kosul.hacim_bilgesi": "Tek günde 10.000 kg tonaj", "kosul.bitmeyen_nefes": "7 günde 40.000 kg tonaj",
    "kosul.uzun_soluk": "Tek günde 25 set",
    "kosul.demir_tutus": "10 antrenman günü", "kosul.celik_irade": "50 antrenman günü",
    "kosul.seri_ustasi": "4 hafta üst üste haftalık hedef", "kosul.kirilmaz": "12 hafta üst üste",
    "kosul.kayit_tutucu": "30 farklı günde öğün kaydı",
    "kosul.protein_sezgisi": "7 gün üst üste protein hedefi", "kosul.metabolik_hakim": "30 günde 25 gün protein hedefi",
    "kosul.golge_yarisi": "4 hafta üst üste Gölge × 1,10", "kosul.golgesiz": "Tutulma ligine ulaş",
    "kosul.donus": "14+ gün aradan sonra ilk antrenman",
    # unvanlar (seviye unvanları ödül adlarıyla aynı)
    "unvan.uyanan": "Uyanan", "unvan.yolcu": "Yolcu", "unvan.demir_cirak": "Demir Çırak",
    "unvan.gece_talimcisi": "Gece Talimcisi", "unvan.sessiz_guc": "Sessiz Güç", "unvan.yuku_tasiyan": "Yükü Taşıyan",
    "unvan.golgesini_asan": "Gölgesini Aşan", "unvan.yildiz_doven": "Yıldız Döven",
    "unvan.tutulma_bekcisi": "Tutulma Bekçisi",
    "unvan.kor_tasiyici": "Kor Taşıyıcı", "unvan.ay_yuruyuscusu": "Ay Yürüyüşçüsü",
    "unvan.hilal_muhafizi": "Hilal Muhafızı", "unvan.yildiz_okuyucu": "Yıldız Okuyucu", "unvan.tutulmus": "Tutulmuş",
    "unvan.celik_irade": "Çelik İrade", "unvan.dev_gucu": "Dev Gücü", "unvan.sinir_kirici": "Sınır Kırıcı",
    "unvan.kirilmaz": "Kırılmaz", "unvan.metabolik_hakim": "Metabolik Hâkim",
    "unvan.bitmeyen_nefes": "Bitmeyen Nefes", "unvan.golgesiz": "Gölgesiz", "unvan.geri_donen": "Geri Dönen",
    # lig sebepleri
    "sebep.dondurma": "dondurma haftası", "sebep.deload": "deload haftası", "sebep.gecmis-yok": "yeterli geçmiş yok",
    "sebep.oran": "Gölge'nin %{yuzde}'i", "sebep.seri": "hedef tuttu, {seri}. hafta seri", "sebep.suruyor": "hafta sürüyor",
    # hafta türü
    "hafta.tur-gecersiz": "Tür deload ya da dondurma olmalı.", "hafta.pazartesi": "Hafta pazartesi tarihiyle verilmeli.",
    "hafta.bitmis": "Bitmiş hafta işaretlenemez.", "hafta.dondurma-dolu": "Bu ay dondurma hakkı kullanıldı.",
    "hafta.deload-dolu": "4 haftada en çok 1 deload.",
    # günlük görevler
    "gorev.antrenman": "Antrenman {n} set", "gorev.dinlenme": "Dinlen + öğünleri kaydet",
    "gorev.protein": "Protein {g} g", "gorev.ogun": "Öğünleri kaydet",
    # olay kartları
    "olay.rekor": "Bildirim: {ad} kişisel rekoru güncellendi — {kg} kg × {tekrar}.",
    "olay.seviye": "Bildirim: Seviye {sv}'{ek} ulaşıldı.", "olay.seviye-acilan": "Açılan: {liste}.",
    "olay.lig-terfi": "Bildirim: Lig yükseldi — {eski} → {yeni}. Tebrikler.",
    "olay.lig-dusme": "Bildirim: Lig {eski} → {yeni}. Bu hafta Gölge'ye yetiş.",
    "olay.uyanis": ("Bildirim: Kalibrasyon tamamlandı. Başlangıç değerleri: GÜÇ {guc} · DAY {day} · "
                    "DİS {dis} · BES {bes}. Lig: {lig}."),
    "olay.beceri": "Bildirim: «{ad}» becerisi edinildi.",
    "olay.evrim": "Bildirim: «{ad}», «{evrim}»e evrimleşti. Tebrikler.",
    "olay.ozet-golge": "Bildirim: Haftalık rapor hazır — {xp} XP · Gölge {golge} · Lig: {lig}.",
    "olay.ozet": "Bildirim: Haftalık rapor hazır — {xp} XP · Lig: {lig}.",
    "olay.gorev": "Bildirim: Günlük görevler tamamlandı. Ödül: 150 XP.",
    "olay.hedef": "Bildirim: Haftalık hedef tuttu — {n}/{n} antrenman. Lig güvende.",
    "olay.golge": "Bildirim: Bu hafta Gölge'yi geçtin — {xp} / {golge} XP. Terfi bölgesindesin.",
    "olay.dondurma": "Bildirim: Bu hafta dondu. Değerlendirilmez, seri korunur.",
    "olay.deload": "Bildirim: Bu hafta yük boşaltma haftası. Değerlendirilmez, set hedefi yarıya iner.",
    "olay.hatirlatma": "Uyarı: {acik} görev açık, gün 3 saat sonra kapanıyor.",
    "olay.surum": "Bildirim: Kayıtlar yeniden hesaplandı. Seviye {sv} · Lig: {lig}.",
    "bildirim.baslik": "Yuki · Fitnes",
    "hata.set-sayi": "reps/weight sayı olmalı", "hata.set-aralik": "reps 0-9999, weight sonlu olmalı",
    "hata.set-nesne": "set nesne olmalı", "hata.set-id": "Geçersiz set kimliği",
    "hata.drop-liste": "drops en çok {n} öğelik liste olmalı", "hata.drop-bicim": "drop {kg, tekrar} olmalı",
    "hata.drop-tekrar": "drop tekrarı tamsayı olmalı", "hata.drop-aralik": "drop kg 0-2000, tekrar 0-999 olmalı",
    "hata.gun-yok": "Bu gün antrenman yok", "hata.aralik": "Aralık 1-62 gün olmalı (bas ≤ bit)",
    "hata.egzersiz-ad": "Her egzersizin adı olmalı", "hata.set-yok": "{ad}: en az bir set olmalı",
    "hata.aralik-bicim": "{ad}: tekrar aralığı '8' ya da '8-10' biçiminde olmalı",
    "hata.sablon-ad": "Şablona bir ad ver", "hata.sablon-kimlik": "Şablon UUID ya da hazir-<slug> olmalı",
    "hata.hazir-govde": "Hazır şablon gövdesi (exercises) gerekli", "hata.olay-yok": "Olay yok",
    "hata.pazartesi": "hafta bir pazartesi tarihi olmalı", "hata.unvan-yok": "Bu unvan kazanılmadı",
    "hata.hafta-tur": "tur: deload | dondurma | null",
}

EN: dict[str, str] = {
    "lig.E": "Ash", "lig.D": "Spark", "lig.C": "Moonstone", "lig.B": "Silver Crescent",
    "lig.A": "Constellation", "lig.S": "Eclipse",
    "odul.uyanan": "Awakened", "odul.gece_moru": "Night Violet accent", "odul.ince_gumus": "Thin silver ring",
    "odul.yolcu": "Wayfarer", "odul.sigil_1": "Sigil I", "odul.buz_mavisi": "Ice Blue accent",
    "odul.demir_cirak": "Iron Apprentice", "odul.cift_halka": "Double ring frame",
    "odul.halka_genisleme": "Ceremony: ring expansion", "odul.cizgili": "Striped XP bar",
    "odul.gece_talimcisi": "Night Drillmaster", "odul.sigil_2": "Sigil II", "odul.ay_gumusu": "Moon Silver accent",
    "odul.sessiz_guc": "Silent Strength", "odul.isaretli_halka": "Marked ring", "odul.yildiz_tozu": "Ceremony: stardust",
    "odul.yuku_tasiyan": "Load Bearer", "odul.sigil_3": "Sigil III", "odul.takimyildiz": "Constellation XP bar",
    "odul.golgesini_asan": "Beyond the Shadow", "odul.altin_cizgi": "Pale gold striped ring",
    "odul.gece_yarisi": "Midnight Blue accent", "odul.tutulma_gecisi": "Ceremony: eclipse passage",
    "odul.yildiz_doven": "Star Forger", "odul.sigil_4": "Sigil IV", "odul.yorunge": "Orbit frame",
    "odul.tutulma_bekcisi": "Eclipse Warden", "odul.sigil_5": "Sigil V", "odul.tam_toren": "Full ceremony",
    "beceri.agir_yuk": "Heavy Load", "beceri.dev_gucu": "Giant's Strength",
    "beceri.rekor_avcisi": "Record Hunter", "beceri.sinir_kirici": "Limit Breaker",
    "beceri.hacim_bilgesi": "Volume Sage", "beceri.bitmeyen_nefes": "Endless Breath",
    "beceri.uzun_soluk": "Long Haul",
    "beceri.demir_tutus": "Iron Grip", "beceri.celik_irade": "Steel Will",
    "beceri.seri_ustasi": "Streak Master", "beceri.kirilmaz": "Unbreakable",
    "beceri.kayit_tutucu": "Record Keeper",
    "beceri.protein_sezgisi": "Protein Sense", "beceri.metabolik_hakim": "Metabolic Master",
    "beceri.golge_yarisi": "Shadow Race", "beceri.golgesiz": "Shadowless",
    "beceri.donus": "Comeback",
    "kosul.agir_yuk": "e1RM ≥ 100 kg in one catalog lift", "kosul.dev_gucu": "Best 3 catalog e1RM total ≥ 300",
    "kosul.rekor_avcisi": "10 records", "kosul.sinir_kirici": "50 records",
    "kosul.hacim_bilgesi": "10,000 kg volume in one day", "kosul.bitmeyen_nefes": "40,000 kg volume in 7 days",
    "kosul.uzun_soluk": "25 sets in one day",
    "kosul.demir_tutus": "10 training days", "kosul.celik_irade": "50 training days",
    "kosul.seri_ustasi": "Weekly goal 4 weeks in a row", "kosul.kirilmaz": "12 weeks in a row",
    "kosul.kayit_tutucu": "Meals logged on 30 different days",
    "kosul.protein_sezgisi": "Protein goal 7 days in a row", "kosul.metabolik_hakim": "Protein goal on 25 of 30 days",
    "kosul.golge_yarisi": "Shadow × 1.10 for 4 weeks in a row", "kosul.golgesiz": "Reach the Eclipse league",
    "kosul.donus": "First workout after a 14+ day break",
    "unvan.uyanan": "Awakened", "unvan.yolcu": "Wayfarer", "unvan.demir_cirak": "Iron Apprentice",
    "unvan.gece_talimcisi": "Night Drillmaster", "unvan.sessiz_guc": "Silent Strength", "unvan.yuku_tasiyan": "Load Bearer",
    "unvan.golgesini_asan": "Beyond the Shadow", "unvan.yildiz_doven": "Star Forger",
    "unvan.tutulma_bekcisi": "Eclipse Warden",
    "unvan.kor_tasiyici": "Ember Bearer", "unvan.ay_yuruyuscusu": "Moonwalker",
    "unvan.hilal_muhafizi": "Crescent Guardian", "unvan.yildiz_okuyucu": "Star Reader", "unvan.tutulmus": "Eclipsed",
    "unvan.celik_irade": "Steel Will", "unvan.dev_gucu": "Giant's Strength", "unvan.sinir_kirici": "Limit Breaker",
    "unvan.kirilmaz": "Unbreakable", "unvan.metabolik_hakim": "Metabolic Master",
    "unvan.bitmeyen_nefes": "Endless Breath", "unvan.golgesiz": "Shadowless", "unvan.geri_donen": "Returner",
    "sebep.dondurma": "freeze week", "sebep.deload": "deload week", "sebep.gecmis-yok": "not enough history",
    "sebep.oran": "{yuzde}% of Shadow", "sebep.seri": "goal met, {seri}-week streak", "sebep.suruyor": "week in progress",
    "hafta.tur-gecersiz": "Type must be deload or freeze.", "hafta.pazartesi": "Week must be given as a Monday date.",
    "hafta.bitmis": "A finished week can't be marked.", "hafta.dondurma-dolu": "This month's freeze is already used.",
    "hafta.deload-dolu": "At most 1 deload every 4 weeks.",
    "gorev.antrenman": "Train {n} sets", "gorev.dinlenme": "Rest + log meals",
    "gorev.protein": "Protein {g} g", "gorev.ogun": "Log meals",
    "olay.rekor": "{ad}: new personal record — {kg} kg × {tekrar}.",
    "olay.seviye": "Level {sv} reached.", "olay.seviye-acilan": "Unlocked: {liste}.",
    "olay.lig-terfi": "League up — {eski} → {yeni}. Well done.",
    "olay.lig-dusme": "League {eski} → {yeni}. Catch your Shadow this week.",
    "olay.uyanis": ("Calibration complete. Starting values: STR {guc} · END {day} · "
                    "DIS {dis} · NUT {bes}. League: {lig}."),
    "olay.beceri": "Skill «{ad}» unlocked.",
    "olay.evrim": "«{ad}» evolved into «{evrim}». Well done.",
    "olay.ozet-golge": "Weekly report ready — {xp} XP · Shadow {golge} · League: {lig}.",
    "olay.ozet": "Weekly report ready — {xp} XP · League: {lig}.",
    "olay.gorev": "Daily quests complete. Reward: 150 XP.",
    "olay.hedef": "Weekly goal met — {n}/{n} workouts. League safe.",
    "olay.golge": "You passed your Shadow this week — {xp} / {golge} XP. You're in the promotion zone.",
    "olay.dondurma": "This week is frozen. Not evaluated, streak kept.",
    "olay.deload": "Deload week. Not evaluated, set goal halved.",
    "olay.hatirlatma": "Heads up: {acik} quests open, the day ends in 3 hours.",
    "olay.surum": "Records recalculated. Level {sv} · League: {lig}.",
    "bildirim.baslik": "Yuki · Fitness",
    "hata.set-sayi": "reps/weight must be numbers", "hata.set-aralik": "reps 0-9999, weight must be finite",
    "hata.set-nesne": "each set must be an object", "hata.set-id": "Invalid set id",
    "hata.drop-liste": "drops must be a list of at most {n} items", "hata.drop-bicim": "drop must be {kg, tekrar}",
    "hata.drop-tekrar": "drop reps must be an integer", "hata.drop-aralik": "drop kg 0-2000, reps 0-999",
    "hata.gun-yok": "No workout on this day", "hata.aralik": "Range must be 1-62 days (bas ≤ bit)",
    "hata.egzersiz-ad": "Every exercise needs a name", "hata.set-yok": "{ad}: at least one set",
    "hata.aralik-bicim": "{ad}: rep range must look like '8' or '8-10'",
    "hata.sablon-ad": "Give the template a name", "hata.sablon-kimlik": "Template must be a UUID or hazir-<slug>",
    "hata.hazir-govde": "Built-in template body (exercises) required", "hata.olay-yok": "No such event",
    "hata.pazartesi": "week must be a Monday date", "hata.unvan-yok": "This title hasn't been earned",
    "hata.hafta-tur": "tur: deload | dondurma | null",
}

KATALOG = {"tr": TR, "en": EN}


def dil() -> str:
    try:
        from app.mesajlar import mevcut_dil
        d = mevcut_dil()
    except Exception:  # noqa: BLE001
        return "tr"
    return d if d in KATALOG else "en" if d == "ja" else "tr"


def t(anahtar: str, dil_: str | None = None, **kw) -> str:
    kaynak = KATALOG.get(dil_ or dil(), TR)
    metin = kaynak.get(anahtar) or TR.get(anahtar) or anahtar
    return metin.format(**kw) if kw else metin
