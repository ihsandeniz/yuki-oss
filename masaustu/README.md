# Masaüstü Yuki

Yuki'nin masaüstündeki bedeni: ekranın köşesinde ayakta duran, baştan ayağa **aynı Yuki** (backend'e `/ws/realtime`
üzerinden bağlanır, kendi LLM çağrısı yok). **Varsayılan KAPALI**: HQ › AYARLAR › Sistem › *Masaüstü Yuki* anahtarı ya da
sohbette "masaüstüne gel / git" (`masaustu_yuki` aracı) açar; `MASAUSTU_YUKI` ayarı tek durumdur.

## Model: senin VRM'in

Depoda model **yok** (`.vrm` dağıtım hakkı olmayan varlıktır). `MASAUSTU_VRM` ayarına (HQ › Sistem ya da `.env`)
kendi `.vrm` dosyanın tam yolunu yaz; elle çalıştırırken `--model yol.vrm` / `YUKI_MASAUSTU_VRM`.
Model yoksa özellik **"model yok"** der ve açılmaz (çıkış 6). Model yerel sunucudan `/_yuki/model.vrm` olarak sayfaya
gider; hiçbir yere kopyalanmaz.

Beden klipleri (VRMA) bu kopyada **gelmez** (dağıtım lisansı yok). Klipsiz de çalışır: yüz, göz kırpma, nefes, bakış,
konuşma ağzı kemik katmanında (`web/hareket.js`) sürer. Kendi klip dizinin varsa `YUKI_MASAUSTU_VRMA_DIZINI` verilir
(`idle.vrma`, `selam.vrma`, …) ve sayfaya `@pixiv/three-vrm-animation` modülü eklenir (varsayılan importmap'te yok).

## Hangi masaüstünde çalışır

| Ortam | Yüzey |
|---|---|
| wlroots / KDE Wayland (gtk-layer-shell var) | katman yüzeyi: çerçevesiz, her alanda görünür, marj ile konumlanır |
| X11 (ya da GNOME Wayland + XWayland) | normal çerçevesiz, üstte kalan, görev çubuğunda görünmeyen pencere |
| GNOME Wayland katmansız ve DISPLAY yok · macOS · Windows | **"bu masaüstünde desteklenmiyor"**: özellik KAPALI kalır, hata atmaz (çıkış 3) |

Gerekenler: sistem Python'u + `python3-gi`, GTK 3, WebKit2GTK 4.1, `websockets` (yalnız bağlantı için);
katman yüzeyi için `gtk-layer-shell` (yoksa X11 yoluna düşer). Backend sistem Python'unu `MASAUSTU_PYTHON` ile değiştirir.

## Kullanım

```bash
./run.sh --model ~/yuki.vrm              # sağ alt · boy ekranın %45'i
./run.sh --model ~/yuki.vrm --boyut 0.6  # ekranın %60'ı (600 = piksel)
python3 masaustu.py --model m.vrm --kuru --sure 3   # ekrana çıkmadan başlat, ölç, JSON özet
```

Sol tık → gülümser + el sallar · başa tık → utangaç · art arda 3. → şaşkın, 5. → kızgın · uzun bas → sevinç ·
basılı tut + sürükle → yer (XDG durum dizininde `yuki-masaustu.json`'a kaydedilir) · çift tık → yaz · orta tık / `SIGUSR2` →
sonraki monitör · `SIGUSR1` → göster/gizle · sağ tık → kapan. Ayar dosyası: `$XDG_CONFIG_HOME/yuki-masaustu.json`
(`{"gl": "acik"}` arayüz GL'ini açar; varsayılan kapalı).

## Neleri YAPMAZ (bilinçli)

- Fare/klavye/pencere denetimi, tıklama işareti, başka pencereyi yönetme: yok.
- Pencere-kaynağı yok: Wayland başka pencerenin konumunu vermez. `etkilesim.pencere_json` bu yüzden `None` döner;
  "panele otur / el salla" tetiklenmez, Yuki ayakta kalır (`frontend/js/masaustu-capa.js` çapayı yine yayınlar).
  İmleç yalnız X11'de küresel okunur; Wayland'de bakış varsayılana döner, sürükleme yerel farkla yapılır.
- Chibi sprite ve portre kipleri yok; yalnız kip tam.

## Donma dersi

Sayfa durumunu `POST /_yuki/durum` ile yollar, host komutları `SSE /_yuki/komut`'tan gönderir. Canlıda
`evaluate_javascript` ile sonuç okunmaz, periyodik yoklama yoktur (JSC çöp toplamasında arayüz sürecinin kilitlenmesi).
`--kuru` ölçümü bu kuralın dışındadır (ekrana çıkmaz, yalnız test/ölçüm).

## Testler

```bash
cd masaustu/tests
/usr/bin/python3 test_etkilesim.py && /usr/bin/python3 test_uzan_kapali.py && /usr/bin/python3 test_baglanti.py
/usr/bin/python3 test_takilma.py && /usr/bin/python3 test_masaustu.py && /usr/bin/python3 test_tek_ornek.py
node test_hareket.mjs && node test_poz.mjs && node test_takilma.mjs && node test_capa_yayin.mjs
# gerçek WebView ölçümü için: YUKI_TEST_VRM=/yol/model.vrm /usr/bin/python3 test_baglanti.py
cd ../../backend && python -m pytest -q tests/test_masaustu_yuki.py
```
