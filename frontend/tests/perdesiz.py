"""Tarayıcı testlerinde açılış perdelerini atla — 28 e2e düşüşünün kök nedeni (2026-11-04).

Bu testler 10-11'de yazıldı. 10-18 birleştirmesi açılışa İKİ perde ekledi, ikisi de tıklamayı keser:
  1. Açılış sinematiği `#yuki-opening` (js/opening-anim.js) — ~4 sn tam ekran, `pointer-events:auto`.
     Oturum başına bir kez oynar; bayrak `sessionStorage['yukiAcilis_v1']`.
  2. İlk kurulum sihirbazı `.ilk-kurulum` (js/ilk-kurulum.js) — temiz veride (sağlayıcı yok) KALICI modal.
     Bayrak `localStorage['yuki-ilk-kurulum_v1']`.
Geçici veriyle açılan test sunucusunda ikisi de açılır: `elementFromPoint` perdeyi döndürür, `click`
30 sn "intercepts pointer events" bekler, koordinatlı `mouse.click` sessizce perdeye gider.
İki perdenin KENDİ davranışı `test_acilis_animasyonu.py` ve `test_ilk_kurulum_e2e.py`'de ölçülür; burada
yalnız başka şeyi ölçen testlerin yolundan çekilirler.

Kullanım: `pg.add_init_script(PERDESIZ_JS)` — `goto`'dan ÖNCE.
"""

PERDESIZ_JS = (
    "try { sessionStorage.setItem('yukiAcilis_v1', '1'); } catch (e) {}"
    "try { if (!localStorage.getItem('yuki-ilk-kurulum_v1')) localStorage.setItem('yuki-ilk-kurulum_v1', 'test'); } catch (e) {}"
)
