/**
 * Yuki Service Worker (Faz ε)
 *
 * Strateji:
 *   - Uygulama kabuğu (HTML, manifest) → Cache-first
 *   - Statik varlıklar (PNG, avatar) → Cache-first
 *   - API / WebSocket istekleri → Network-only (önbelleğe alınmaz)
 *   - Video (mp4) / Rive (.riv) → Network-first, cache'e ekle
 *   - CDN istekleri (unpkg, fonts) → Stale-while-revalidate
 */

// 🔴 Bu sayı index.html'deki `chat-modes.js?v=`'nin GERİSİNDE kalmamalı (eşit ya da ileri).
// "Üçü de aynı" DEĞİL: burası her frontend değişikliğinde artar (style.css, core.js dahil),
// mod zinciri ise yalnız mod varlıkları değişince → ikisi doğal olarak ayrışır.
// Zorunlu eşitlik ①=② arasında (index.html ?v= ↔ chat-modes.js ASSET_V).
// Mekanik bekçi: backend/tests/test_surum_zinciri.py
const CACHE_VERSION = 'yuki-v378'; // kopyala düğmesi çeviride (core 61, sözlük 102); önceki: kamera fotoğrafı yükleme (tab-switcher 4); önceki: 11-17 görsel model etiketi Flash-lite (core 60); önceki: 11-16 görsel model adı gemini-2.5-flash → gemini-3.5-flash-lite (core 59); önceki: 11-15 birleşik goz: avatar gizliyken üst çubuk ☰ payı (sohbet 24), galeri çekmece başlığı ☰ payı (tab-nav 34); önceki: 11-15 birleşik (oss/tam-hizala + oss/islev-farklari): sözlük 101 (dört yer); önceki: 11-15 son tur: HALKA HAFIZA liste kartı (ASSET_V 199 = chat-modes ?v=199; önce index 197 ≠ 198 kalmıştı), HQ sol menü üst örtüsü (hq 35), Plan hafta şeridi iki harf, sözlük 100; önceki: 11-15 işlev farkları: galeri kök ekle seçici (galeri.js 26, galeri.css 25), Yedek BULUTTA/AYARLAR/Kontrol/Kuru (yedek-rclone.js/css 1, yedekleme.js 8), avatar göster/gizle (core 58), sözlük 100; önceki: 11-15 HQ başlığı çerçevesiz 52/5 (hq 34) + şerit etkin çipi sol okun sağında (intro-sequences 85); 11-14 tam hizala: çerçeve kenardan kenara (kabuk 19), SAKİN 44 px + sahne 33vw (sohbet-sahne 11), telefon durum satırı (sohbet-kisisel 4), sihirbaz B3/B5/B13 (ilk-kurulum js 4 / css 3), B7 ücretsiz varsayılan (core 57), sözlük 99 + ja 5 (dört sayfa), ASSET_V 198 (halka B1/B2 + telefon tek widget); önceki: 11-14 birleşik (hizala a+b): telefonda TR düğmesi 44 px + anahtar yokken 'kurulum gerekli' kısalmaz (sohbet-kisisel 3), Yedek kişisel Drive düzeni (yedek.css 5, yedekleme.js 7), Galeri/Plan/Harita/Dosya kişisel başlık (map-hud 10, map-gozlemevi 3), sözlük 98 (dört sayfa); önceki: 11-14 Sohbet/HALKA kişisel düzen (üst çubuk, boş ekran, araç yayı, Hep dinle, kip seçici, sohbet-kisisel.css), açılış acilis-v4 Mühür + Döküm (opening-anim silindi), yalnız Yuki (diğer karakter görselleri silindi), sözlük ?v= birleştirmede (b ile birlikte), core 56, ASSET_V 197; önceki: 11-13 Komuta Paneli ön yüz izi silindi (core.js panel_* WS dalları + _kanvas + /api/panel/result bildirimi, ozellik.js komuta_kanvasi), sözlük 97, core 55, ozellik 3; önceki: 11-13 çip metni dar ekranda kesilmez; halka merkezi + durum satırı + kayan yazı + model çipi anahtar yokken 'kurulum gerekli' (core yukiAnahtarHazir/yuki-anahtar-durum), sözlük 96, ASSET_V 196; önceki: 11-13 son birleştirme: demo veri kipi (YUKI_DEMO=1) + sohbet rozeti üçüncü hâl ANAHTAR YOK (core.js _anahtarYokla, kabuk/sohbet.css; telefonda ses düğmesi çekilir; boştaki durum rozeti de ANAHTAR YOK) + HQ şeridi clip-path (maskeli düğme başlık altında tıklanmaz) + Plan BUGÜN sayacı bitmiş/toplam, sözlük 95 (mini dahil); önceki: 11-13 sekme başlıkları tek tarz: ortak .sekme-baslik (css/baslik-gozlemevi.css) 8 sekmede, sözlük 94; önceki: 11-13 goz düzeltmeleri: HQ telefon şeridi 68px (✕/☰ bant içinde), Bilgisayarım meta nowrap, HALKA telefonda bağlantı durum rozetinde, galeri tek ay omurgası, Dosya form yazısı + kurdele, Yedek sol kenar 64; önceki: 11-13 oss arayüz birleştirmesi: HALKA açılışı (A1), HQ Bilgisayarım + Harita Gözlemevi (A2), Plan Gözlemevi + Galeri eşiği + Dosya Gönder (B), sözlük 93; önceki: 11-13 arayüz turu ORTAK: PANEL sekmesi kalktı (panel-view/alice-canvas silindi), YEDEK ayrı sekme (yedek.css, yedekleme.js kökü #yedek-kok), kısayol 5=AJAN 6=YEDEK; önceki: 11-12 G4b: kamera görüşü + ses kimliği paneli (HQ › Sistem), dosya gönder + güvenli dosya/galeri işlemleri, tab-switcher ?v=3; önceki: 11-12 G4 entegre: Atölye+kanvas varsayılan açık, Fitnes v2 (HQ anahtarı), gündem kümeleme rozeti, sahne/duyuru tr-en; önceki: 11-12 Atölye: araştırma sahnesi ön yüzü + bitiş duyurusu + core.js gorev WS köprüsü; önceki: 11-12 ilk açılış hep koyu (tema.js 'sistem' kaydı) + Cihazlar kilitli izin anahtarı; önceki: 11-04 HQ › Cihazlar riskli eylem izinleri (tr/en sözlük damgası); önceki: 11-02 ilk sürümde olmayan Atölye/PANEL/FİTNES girişleri ozellik.js kapısıyla gizli; önceki: 11-02 galeri/dosya iframe'ine ☰ payı + harita ⌕ dar ekranda ezilmez; önceki: 11-01 Atölye görev şeridi (Halka Konsolu); önceki: 11-01 dosya sekmesi (salt okunur gezgin); önceki: 11-01 galeri sekmesi (salt okunur gezgin); önceki: 10-19 açık kaynak: cihaza komut çalıştırma kalktı; önceki: 10-18 birleştirme: ilk açılış sihirbazı + açılış sinematiği + ipucu kartı; önceki: 10-17 açık kaynak: JOBS sekmesi + mod kabuk komutları kalktı; önceki: geliştirici araçları, yerel ses, AJAN komutu, sonlandır kalktı; önceki: kademe kilidi + lisans paneli kaldırıldı, hq-lisans.css → hq-surum.css (eski sürüm notları git geçmişinde)
const CACHE_STATIC  = `${CACHE_VERSION}-static`;
const CACHE_MEDIA   = `${CACHE_VERSION}-media`;

// Install anında ön-önbelleklenecek kabuğa alınan dosyalar
const PRECACHE_URLS = [
  '/',
  '/ui/index.html',
  '/ui/manifest.json',
  '/ui/assets/characters/yuki_avatar.png',
  // Offline çekirdek: markdown/kod-highlight/font (ilk açılış offline olsa bile hazır)
  '/ui/vendor/marked.min.js?v=1',
  '/ui/vendor/dompurify.min.js?v=1',
  '/ui/vendor/prism.min.js?v=1',
  '/ui/vendor/prism-one-dark.min.css?v=1',
  '/ui/vendor/fonts.css?v=1',
  '/ui/vendor/fonts-mono.css?v=1',   // JetBrains Mono — A10 (2026-09-18)
  // Dil iskelesi (FAZ 2) — sözlükler <head>'de SENKRON yükleniyor, yani
  // çevrimdışı ilk açılışta da hazır olmaları gerekir; biri eksikse o dil
  // sessizce Türkçe'ye düşer.
  '/ui/js/dil.js?v=7',
  '/ui/js/diller/tr.js?v=102',
  '/ui/js/diller/ja.js?v=5',
  '/ui/js/diller/en.js?v=102',
  '/ui/js/ozellik.js?v=3',
  // Gözlemevi yazı tipleri (11-13): PLAN iskeleti; çevrimdışı ilk açılışta da yedeğe düşmesin.
  '/ui/css/fontlar-gozlemevi.css?v=1',
  '/ui/css/baslik-gozlemevi.css?v=1',   // sekme başlığı tek tarz (11-13)
  '/ui/assets/fonts/gozlemevi/fraunces-latin.woff2',
  '/ui/assets/fonts/gozlemevi/fraunces-latinext.woff2',
  '/ui/assets/fonts/gozlemevi/fraunces-italik-latin.woff2',
  '/ui/assets/fonts/gozlemevi/fraunces-italik-latinext.woff2',
  '/ui/assets/fonts/gozlemevi/figtree-latin.woff2',
  '/ui/assets/fonts/gozlemevi/figtree-latinext.woff2',
  '/ui/assets/fonts/gozlemevi/martian-mono-latin.woff2',
  '/ui/assets/fonts/gozlemevi/martian-mono-latinext.woff2',        // <head>'de SENKRON — kapalı özellik girişleri bir kare bile görünmesin
  '/ui/perf-adaptive.css?v=2',
  '/ui/css/gfx.css?v=1',          // <head>'de erken yüklenir — offline ilk açılışta da lazım
  '/ui/js/perf-tier.js?v=1',
  // Bildirim çevrimdışı çekirdeğe dahil: ağ koptuğunda sessiz kalmaması
  // gereken tek şey zaten "ağ koptu" mesajının kendisi.
  '/ui/js/bildirim.js?v=3',
  '/ui/js/gecmis-temizle.js?v=1',
  '/ui/js/mic-devices.js?v=3',
  '/ui/js/model-downloader.js?v=8',
  '/ui/js/updater-ui.js?v=10',
];

// ── Install ─────────────────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_STATIC)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

// ── Activate — eski cache'leri temizle ──────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k.startsWith('yuki-') && k !== CACHE_STATIC && k !== CACHE_MEDIA)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ── Fetch ────────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // WebSocket — SW geçirme (ws:// protokolü SW'ye düşmez zaten)
  if (request.url.startsWith('ws://') || request.url.startsWith('wss://')) return;

  // API istekleri → network-only
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) {
    event.respondWith(fetch(request));
    return;
  }

  // Harita tile CDN'leri → network-only (önbelleğe alınmaz, layout bozulmasın)
  if (url.hostname.includes('cartocdn.com') || url.hostname.includes('openstreetmap.org') || url.hostname.includes('tile.openstreetmap')) {
    event.respondWith(fetch(request).catch(() => new Response('', { status: 503 })));
    return;
  }

  // CDN (unpkg, fonts.googleapis.com) → stale-while-revalidate
  if (url.hostname !== self.location.hostname) {
    event.respondWith(_staleWhileRevalidate(request, CACHE_STATIC));
    return;
  }

  // HTML dosyaları → network-first (cache deadlock önle)
  // /ui/ ve /ui de index.html döndürür — cache-first'e düşmemeli
  if (/\.html$/i.test(url.pathname) || url.pathname === '/' || url.pathname === '/ui' || url.pathname === '/ui/' || url.pathname === '/ui/planner.html') {
    event.respondWith(_networkFirst(request, CACHE_STATIC));
    return;
  }

  // Video / .riv → network-first (büyük dosyalar)
  if (/\.(mp4|webm|riv)$/i.test(url.pathname)) {
    event.respondWith(_networkFirst(request, CACHE_MEDIA));
    return;
  }

  // Diğer statik varlıklar → cache-first
  event.respondWith(_cacheFirst(request, CACHE_STATIC));
});

// ── Strateji yardımcıları ────────────────────────────────────────────

async function _cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(cacheName);
    cache.put(request, response.clone());
  }
  return response;
}

async function _networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok && response.status !== 206) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response('Çevrimdışı — kaynak önbellekte yok.', { status: 503 });
  }
}

// ── Push (Faz 12 — Android Companion) ───────────────────────────────
self.addEventListener('push', (event) => {
  let data = { title: 'Yuki 🌸', body: 'Yeni mesaj var.', url: '/' };
  try { data = { ...data, ...JSON.parse(event.data?.text() || '{}') }; } catch {}

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/ui/assets/characters/yuki_avatar.png',
      badge: '/ui/assets/characters/yuki_avatar.png',
      tag: 'yuki-proactive',
      renotify: true,
      data: { url: data.url },
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = event.notification.data?.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      const existing = list.find((c) => c.url.includes(self.location.origin));
      if (existing) return existing.focus();
      return clients.openWindow(target);
    })
  );
});

// ── Strateji yardımcıları ────────────────────────────────────────────

async function _staleWhileRevalidate(request, cacheName) {
  const cache    = await caches.open(cacheName);
  const cached   = await cache.match(request);
  const fetchPr  = fetch(request).then((resp) => {
    if (resp.ok) cache.put(request, resp.clone());
    return resp;
  }).catch(() => null);
  return cached || (await fetchPr) || new Response('', { status: 503 });
}
