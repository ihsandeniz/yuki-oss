# Product

> Yuki'nin tasarım ilkeleri: kullanıcılar, anti-referanslar, erişilebilirlik eşikleri.
> Arayüze dokunan her katkı bu ilkelere uyar; kod yorumları ve testler buraya bağlanır.

## Register

product

## Users

**Yuki'yi kendi bilgisayarında çalıştıran kişi** — teknik olması gerekmeyen, kendi LLM
anahtarını (BYOK) ya da yerel bir modeli bağlayıp masaüstünde bir AI yoldaş isteyen kişi.
Yuki açık kaynaktır (MIT); bütün özellikler herkese açıktır, kilitli ya da ücretli bölüm yoktur.

Kullanım bağlamı çok çeşitli, ve tasarımı asıl zorlayan da bu:

- **Tam ekran, uzun oturum** — koyu oda, sohbet ve plan aynı anda açık
- **Köşe paneli** — Yuki monitörün sağ kenarında dar bir şerit; kullanıcı başka işte,
  Yuki eşlik ediyor
- **Mini pencere** — yalnız sohbet, 320px, başka her şey kapalı

Aynı arayüz üçünde de çalışmak zorunda. Tasarımın birinci kısıtı budur.

## Product Purpose

Yuki, sesli konuşan, hafızalı, karakterli bir masaüstü AI companion'ı
(FastAPI backend + Vanilla JS frontend + Electron 44).

Üç sekme:
- **Sohbet** — mesajlaşma, sesli giriş, karakter/avatar, görsel modlar
- **Plan** — görevler, takvim, bütçe, fitnes
- **HQ** — anahtar, ayarlar, sağlık, hafıza yönetimi

Başarı ölçütü: **yoğunluk korunurken arayüz sakin kalması.** Bilgi kaybetmeden
sessizleşmek — az göstermek değil, gürültüsüz göstermek.

## Brand Personality

**Sessiz operasyon odası · zarif-taktiksel · sinematik.**
Güç gösterisi değil, kontrollü sükûnet.

Yuki'nin *kendisi* ifadeli olabilir — avatarı durum taşır, karakteri vardır.
Ama **arayüz sakin kalır**. Kişilik karakterde, disiplin arayüzde.

## Anti-references

- **Sıkışık askeri HUD:** kalın cyan border'lar, her kartta köşe bracket dekorasyonu,
  her şeyin aynı anda bağırması. *(2026-08 öncesi tasarımın kendisi anti-referanstır.)*
- **Cyberpunk neon aşırılığı** — magenta/cyan glow her yerde.
- **Generic SaaS panosu** — beyaz kartlar, gölge yığını, hero-metric şablonu.
- **Kart yığını** — hiyerarşiyi kutu çizerek kurmak. Kart içinde kart her zaman yanlıştır.
- **Emoji ikonografi** — Lucide SVG kullanılır.
- **Modal'ı ilk çözüm sanmak** — modal çoğu zaman tembelliktir.

## Design Principles

1. **Ekranda yer kaplayan her şey bir işe yarar.** Görsel dolgu yok. Bir öğe bilgi
   taşımıyorsa ya bilgiye bağlanır ya kaldırılır — statik "EMO: neutral" göstergesi
   gibi süsler buna dahildir.
   **İstisna — mikrofonun boştaki süs halkası (2026-10-11, geliştirici kararı):** mikrofonun
   çevresindeki ince kesikli halka boştayken de görünür. Gerekçe: sohbet çubuğu Halka
   Konsolu tasarımıyla birebir aynı kalır; halka mikrofonu "dokunulacak yer"
   olarak işaretliyor ve kayıtta aynı yerde ses seviyesini çiziyor, yani boştaki hâl
   kayıttaki göstergenin yerini önden tutuyor. Sınırı: ince (1px), kesikli, soluk mor —
   eski düz/kalın 52px halka (2026-10-04'te bu ilkeyle kaldırılmıştı) geri gelmez.
   Kapı: `frontend/tests/test_birebir_konsol.py`.

2. **Mor kimliktir, altın nadirdir, kırmızı yalnız tehlikedir.** Mor: aktif sekme,
   birincil eylem, odak halkası, seçili durum. Altın: ekran başına **en çok iki** öğe —
   başarı onayı gibi nadir anlar. Kırmızı vurgu için harcanmaz; harcanırsa gerçek hata
   geldiğinde söyleyecek renk kalmaz.

3. **Çizgi inceldikçe güven artar.** 1px, düşük opasite sınırlar; bracket ve kalın glow
   yok. Hiyerarşi renkle değil **yüzey tonu ve boşlukla** kurulur.

4. **Yoğunluk ≠ gürültü.** Kalabalık ekran katlanır, budanmaz. Kullanıcının aradığı şey
   asla katlanmış olmaz; ikincil analiz ve uzun listeler olur.

5. **Durum değişimi hissedilir, dekore edilmez.** 90–260ms geçişler, üstel ease-out,
   zıplama yok. Durum taşımayan hareket yoktur. "Hareketi azalt" açıkken hepsi durur.

6. **Menü uygulamanın parçasıdır.** Kenara yapıştırılmış ayrı bir çubuk değil, yüzeyin
   içinde duran bir kart. Menü ile içerik arasında çizgi yok — boşluk ve yüzey farkı ayırır.

7. **Aynı iş = aynı görünüm.** İki ekranda farklı görünen "Kaydet" düğmesi varsa biri
   yanlıştır. Yeni bir bileşen tipi eklemek isteyen, önce mevcutların neden yetmediğini yazar.

## Accessibility & Inclusion

- Gövde metni **≥4.5:1** — koyu zeminde açık gri değil, ölçülmüş beyaz tonları.
  Yer tutucu metni de 4.5:1'e tabidir; tarayıcının varsayılan solgun grisi kabul edilmez.
- Kontrol sınırı (input, seçim) **≥3:1** — WCAG 1.4.11.
- Dokunma/tıklama hedefi **≥24px** (WCAG 2.5.8), hedeflenen **44px**. Mini pencerede
  görsel 40px olabilir ama tıklama alanı 44'te kalır.
- Her ikon düğmesinde `aria-label`.
- `:focus-visible` halkası **her yerde aynı** — 2px mor, 2px offset. İstisnası yok.
- `prefers-reduced-motion` kapsaması **%100**; View Transitions dahil.
- Renk asla tek bilgi kanalı değildir: durum noktasının yanında daima metin, aktif
  sekmede renk + arka plan + gösterge çizgisi birlikte.
- Tema **yalnız koyu**. Açık tema kaldırıldı — ölçüldü: açıkken bile ekran koyu kalıyordu
  ve OS açık temada kendiliğinden devreye giriyordu.
