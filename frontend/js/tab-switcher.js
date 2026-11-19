// ── Upload: 📁 DOSYA YÜKLE (galeri modalı) → çoklu dosya yükleme ─────────────
// TEK kanonik change listener: _gpUploadSelected (aşağıda tanımlı).
// Eski tekil "görsel yükle + anında sohbete gönder" listener'ı kaldırıldı —
// yeni handler'la birlikte ÇİFT yükleme yapıyor ve dokümanlarda send-to-chat
// 400 dönüyordu. Görsel paylaşımı: galeri kartına tıkla ya da 📸 webcam.

function _tst(anahtar, degerler) {
  return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
}

document.getElementById('mediaFileInput').addEventListener('change', () => _gpUploadSelected());

function _appendUserImage(src, name) {
  const msgs = document.getElementById('messages');
  if (!msgs) return;
  const div = document.createElement('div');
  div.className = 'message user-message';
  div.style.cssText = 'display:flex;justify-content:flex-end;padding:4px 0;';
  const img = document.createElement('img');
  img.src = src;
  img.alt = name;
  img.style.cssText = 'max-width:260px;max-height:180px;border-radius:8px;cursor:pointer;border:1px solid #2a2a2a;';
  img.onclick = () => { if (typeof openLightbox === 'function') openLightbox(src, name); };
  div.appendChild(img);
  msgs.appendChild(div);
  div.scrollIntoView({ behavior: 'smooth' });
}

// ── Camera Capture ───────────────────────────────────────────────────────────
let _camStream = null;
let _capturedBlob = null;

async function openCameraCapture() {
  document.getElementById('camera-capture-modal').style.display = 'block';
  _capturedBlob = null;
  const video = document.getElementById('camera-video');
  const preview = document.getElementById('camera-preview');
  preview.style.display = 'none';
  video.style.display = 'block';
  document.getElementById('camera-snap-btn').style.display = 'inline-block';
  document.getElementById('camera-retake-btn').style.display = 'none';
  document.getElementById('camera-send-btn').style.display = 'none';
  try {
    _camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 1280, height: 720 }, audio: false });
    video.srcObject = _camStream;
  } catch (err) {
    console.error('[camera]', err);
    showToast(_tst('tab-switcher.kamera-acilamadi') + ' ' + err.message, 'err', 3000);
    closeCameraCapture();
  }
}

function closeCameraCapture() {
  if (_camStream) { _camStream.getTracks().forEach(t => t.stop()); _camStream = null; }
  document.getElementById('camera-video').srcObject = null;
  document.getElementById('camera-capture-modal').style.display = 'none';
  _capturedBlob = null;
}

function _cameraSnap() {
  const video = document.getElementById('camera-video');
  const canvas = document.getElementById('camera-canvas');
  canvas.width = video.videoWidth || 1280;
  canvas.height = video.videoHeight || 720;
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  canvas.toBlob(blob => {
    _capturedBlob = blob;
    const preview = document.getElementById('camera-preview');
    preview.src = URL.createObjectURL(blob);
    preview.style.display = 'block';
    video.style.display = 'none';
    document.getElementById('camera-snap-btn').style.display = 'none';
    document.getElementById('camera-retake-btn').style.display = 'inline-block';
    document.getElementById('camera-send-btn').style.display = 'inline-block';
    if (_camStream) { _camStream.getTracks().forEach(t => t.stop()); _camStream = null; }
  }, 'image/jpeg', 0.92);
}

function _cameraRetake() {
  _capturedBlob = null;
  const video = document.getElementById('camera-video');
  const preview = document.getElementById('camera-preview');
  preview.style.display = 'none';
  video.style.display = 'block';
  document.getElementById('camera-snap-btn').style.display = 'inline-block';
  document.getElementById('camera-retake-btn').style.display = 'none';
  document.getElementById('camera-send-btn').style.display = 'none';
  navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 1280, height: 720 }, audio: false })
    .then(s => { _camStream = s; video.srcObject = s; })
    .catch(err => { showToast(_tst('tab-switcher.kamera-hatasi') + ' ' + err.message, 'err', 3000); closeCameraCapture(); });
}

async function _cameraSend() {
  if (!_capturedBlob) return;
  // closeCameraCapture() _capturedBlob'u sıfırlar → fotoğrafı ÖNCE yerel değişkene al,
  // yoksa yükleme boş dosyayla patlar ve fotoğraf Yuki'ye hiç gitmez.
  const blob = _capturedBlob;
  const filename = `photo_${Date.now()}.jpg`;
  const localUrl = URL.createObjectURL(blob);
  _appendUserImage(localUrl, filename);
  closeCameraCapture();
  try {
    const fd = new FormData();
    fd.append('file', blob, filename);
    const up = await authFetch('/api/media/upload', { method: 'POST', body: fd });
    if (!up.ok) throw new Error(_tst('tab-switcher.yukleme-basarisiz', { durum: up.status }));
    const { filename: savedName } = await up.json();
    await authFetch(`/api/media/send-to-chat/${savedName}`, { method: 'POST' });
  } catch (err) {
    console.error('[camera send]', err);
    showToast(_tst('tab-switcher.fotograf-gonderilemedi'), 'err', 2500);
  }
}

// ── Gallery Picker ───────────────────────────────────────────────────────────
// Doküman türü → ikon (görsel olmayanlar için)
const _DOC_ICONS = { '.pdf': '📕', '.xlsx': '📊', '.xls': '📊', '.csv': '📊',
                     '.docx': '📝', '.txt': '📄', '.md': '📄', '.json': '⚙️', '.log': '📜' };

function _gpStatus(msg) {
  const el = document.getElementById('gp-upload-status');
  if (!el) return;
  el.textContent = msg || '';
  el.style.display = msg ? 'block' : 'none';
}

// 📁 DOSYA YÜKLE — gizli file input'u tetikle (PC: dosya diyaloğu, telefon: dosya seçici)
function gpPickFiles() {
  const input = document.getElementById('mediaFileInput');
  if (!input) return;
  input.value = '';   // aynı dosyayı ikinci kez seçebilmek için sıfırla
  input.click();      // change → _gpUploadSelected (dosya başındaki tek listener)
}

async function _gpUploadSelected() {
  const input = document.getElementById('mediaFileInput');
  const files = Array.from(input.files || []);
  if (!files.length) return;
  let ok = 0, fail = 0;
  for (let i = 0; i < files.length; i++) {
    _gpStatus(_tst('tab-switcher.yukleniyor', { sayi: i + 1, toplam: files.length, ad: files[i].name }));
    try {
      const fd = new FormData();
      fd.append('file', files[i], files[i].name);
      const up = await authFetch('/api/media/upload', { method: 'POST', body: fd });
      if (!up.ok) {
        const d = await up.json().catch(() => ({}));
        throw new Error(d.detail || up.status);
      }
      ok++;
    } catch (err) {
      fail++;
      console.error('[gallery upload]', files[i].name, err);
      showToast(`${files[i].name}: ${err.message}`, 'err', 3000);
    }
  }
  _gpStatus('');
  input.value = '';
  if (ok) showToast(_tst('tab-switcher.dosya-yuklendi', { sayi: ok }), 'ok', 2000);
  openGalleryPicker();   // listeyi tazele (modal kapalıysa açar — yüklenen görünsün)
}

// Dokümanı oku → içeriği sohbet kanalından Yuki'ye ilet
async function _gpSendDocToChat(filename) {
  _gpStatus(_tst('tab-switcher.okunuyor', { ad: filename }));
  try {
    const res = await authFetch(`/api/media/extract/${encodeURIComponent(filename)}`);
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(d.detail || _tst('tab-switcher.metin-cikarilmadi'));
    }
    const { text, truncated } = await res.json();
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      showToast(_tst('tab-switcher.baglanti-bekleniyor'), 'err', 2500);
      return;
    }
    // Ekranda kısa kart; sokete tam içerik (LLM okusun)
    addMessage('user', `📄 ${filename} — ${_tst('tab-switcher.dosya-iletildi')}${truncated ? ' ' + _tst('tab-switcher.uzun-kirpildi') : ''}`);
    updateState('thinking');
    socket.send(JSON.stringify({
      type: 'text',
      /* bu metin sohbete KULLANICI mesajı olarak gider (LLM okur) —
         kullanıcının dilinde yazılır ki EN kullanıcı Yuki'ye Türkçe konuşmuş olmasın.
         Dosya içeriği yer tutucuya konmaz, araya eklenir. */
      message: _tst('tab-switcher.llm-giris', { ad: filename }) + '\n\n'
        + _tst('tab-switcher.llm-icerik-bas', { ad: filename }) + '\n' + text + '\n'
        + _tst('tab-switcher.llm-icerik-son'),
    }));
    closeGalleryPicker();
  } catch (err) {
    console.error('[gallery doc]', err);
    showToast(`${filename}: ${err.message}`, 'err', 3500);
  } finally {
    _gpStatus('');
  }
}

async function openGalleryPicker() {
  document.getElementById('gallery-picker-modal').style.display = 'block';
  const grid = document.getElementById('gallery-picker-grid');
  grid.innerHTML = '<span style="color:#555;font-size:12px;" data-tst="genel.yukleniyor">' + _tst('genel.yukleniyor') + '</span>';
  try {
    const res = await authFetch('/api/media/list');
    const { files } = await res.json();
    grid.innerHTML = '';
    if (!files || !files.length) {
      grid.innerHTML = '<span style="color:#555;font-size:12px;" data-tst="tab-switcher.dosya-yok">' + _tst('tab-switcher.dosya-yok') + '</span>';
      return;
    }
    files.forEach(f => {
      const thumb = document.createElement('div');
      thumb.className = 'gp-thumb';
      const ext = '.' + f.filename.split('.').pop().toLowerCase();
      if (f.kind === 'doc') {
        // Doküman kartı: ikon + ad; tıkla → oku + sohbete ilet
        thumb.classList.add('gp-doc');
        thumb.setAttribute('data-tst-title', 'tab-switcher.belge-title');
        thumb.setAttribute('data-ad', f.filename);
        thumb.title = _tst('tab-switcher.belge-title', { ad: f.filename });
        thumb.innerHTML = `<div class="gp-doc-icon">${_DOC_ICONS[ext] || '📄'}</div>
          <div class="gp-thumb-label">${f.filename.slice(0, 22)}</div>`;
        thumb.addEventListener('click', () => _gpSendDocToChat(f.filename));
      } else {
        const imgSrc = _mediaUrl(f.filename);
        thumb.setAttribute('data-tst-title', 'tab-switcher.gorsel-title');
        thumb.setAttribute('data-ad', f.filename);
        thumb.title = _tst('tab-switcher.gorsel-title', { ad: f.filename });
        thumb.innerHTML = `<img src="${imgSrc}" loading="lazy">
          <div class="gp-thumb-label">${f.filename.slice(0, 22)}</div>`;
        thumb.addEventListener('click', async () => {
          try {
            await authFetch(`/api/media/send-to-chat/${encodeURIComponent(f.filename)}`, { method: 'POST' });
          } catch(err) { console.error('[gallery send]', err); }
          closeGalleryPicker();
        });
      }
      grid.appendChild(thumb);
    });
  } catch (err) {
    grid.innerHTML = '<span style="color:#f44;font-size:12px;" data-tst="tab-switcher.galeri-yuklenemedi">' + _tst('tab-switcher.galeri-yuklenemedi') + '</span>';
    console.error('[gallery list]', err);
  }
}

function closeGalleryPicker() {
  document.getElementById('gallery-picker-modal').style.display = 'none';
}

function _mediaUrl(filename) {
  const base = `/api/media/file/${filename}`;
  return _authToken ? `${base}?token=${_authToken}` : base;
}

/*  · dil tazeleyici — galeri seçicide ŞU AN çizili olan metinler
   (yükleniyor / dosya yok / hata satırı + kartların title'ı). Listeyi yeniden
   çekmez (ağ yok), yalnız mevcut düğümlerin metnini yeni dile çevirir. */
window.addEventListener('yuki-dil-degisti', () => {
  const grid = document.getElementById('gallery-picker-grid');
  if (!grid) return;
  grid.querySelectorAll('[data-tst]').forEach(el => { el.textContent = _tst(el.getAttribute('data-tst')); });
  grid.querySelectorAll('[data-tst-title]').forEach(el => {
    el.title = _tst(el.getAttribute('data-tst-title'), { ad: el.getAttribute('data-ad') || '' });
  });
});

/* ── Dosya gönder: DOSYA sekmesinden "Yuki'ye gönder" ─────────────────────
   dosya.html (iframe) yalnız kimlik + ad yollar; dosyayı BURADA, kabuk tarafında
   alırız: bilet (auth'lu GET) → bilet akışı → /api/media/upload → sohbet.
   Dosya gezgini salt okunur kalır — yazma mevcut medya yükleme ucundan olur.
   Kapı: mesaj aynı kökenden VE yalnız #dosya-iframe'in penceresinden kabul edilir. */
var DOSYA_GONDER_AZAMI = 10;
var DOSYA_GONDER_BOYUT = 15 * 1024 * 1024;          // media.py MAX_BYTES ile aynı
var _DG_IMG = /\.(jpe?g|png|gif|webp)$/i;

function _dosyaGonderMesaji(e) {
  if (e.origin !== location.origin) return null;
  var f = document.getElementById('dosya-iframe');
  if (!f || !f.contentWindow || e.source !== f.contentWindow) return null;
  var v = e.data;
  if (!v || v.tur !== 'yuki-dosya-gonder' || !Array.isArray(v.ogeler)) return null;
  var ogeler = v.ogeler.filter(function (o) {
    return o && typeof o.id === 'string' && /^[0-9a-f]{16}$/.test(o.id) && typeof o.ad === 'string' && o.ad.length <= 255;
  });
  if (!ogeler.length || ogeler.length !== v.ogeler.length) return null;
  return { ogeler: ogeler, gizli: v.gizli === true };
}

// Birden çok belgeyi TEK sohbet mesajında ilet (her biri ayrı tur açmasın)
async function _gpSendDocsToChat(adlar) {
  if (adlar.length === 1) return _gpSendDocToChat(adlar[0]);
  var parcalar = [], kirpik = false;
  for (var i = 0; i < adlar.length; i++) {
    var res = await authFetch('/api/media/extract/' + encodeURIComponent(adlar[i]));
    if (!res.ok) {
      var d = await res.json().catch(function () { return {}; });
      throw new Error(adlar[i] + ': ' + (d.detail || _tst('tab-switcher.metin-cikarilmadi')));
    }
    var j = await res.json();
    if (j.truncated) kirpik = true;
    parcalar.push(_tst('tab-switcher.llm-icerik-bas', { ad: adlar[i] }) + '\n' + j.text + '\n' + _tst('tab-switcher.llm-icerik-son'));
  }
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    showToast(_tst('tab-switcher.baglanti-bekleniyor'), 'err', 2500);
    return;
  }
  var liste = adlar.join(', ');
  addMessage('user', '📄 ' + liste + ' — ' + _tst('tab-switcher.dosya-iletildi') + (kirpik ? ' ' + _tst('tab-switcher.uzun-kirpildi') : ''));
  updateState('thinking');
  socket.send(JSON.stringify({ type: 'text', message: _tst('tab-switcher.llm-giris', { ad: liste }) + '\n\n' + parcalar.join('\n\n') }));
}

async function _dosyaGonder(ogeler, gizli) {
  if (ogeler.length > DOSYA_GONDER_AZAMI) {        // dosya.js zaten engeller ve kullanıcıya söyler
    console.warn('[dosya gönder] en çok', DOSYA_GONDER_AZAMI, 'dosya:', ogeler.length);
    return;
  }
  var cokBuyuk = _tst('tab-switcher.yukleme-basarisiz', { durum: '> 15 MB' });
  var belgeler = [], gorseller = [], hata = 0;
  for (var i = 0; i < ogeler.length; i++) {
    var o = ogeler[i];
    _gpStatus(_tst('tab-switcher.yukleniyor', { sayi: i + 1, toplam: ogeler.length, ad: o.ad }));
    try {
      if (typeof o.boyut === 'number' && o.boyut > DOSYA_GONDER_BOYUT) throw new Error(cokBuyuk);
      var b = await authFetch('/api/dosya/bilet/' + o.id + (gizli ? '?gizli=1' : ''));
      if (!b.ok) { var bd = await b.json().catch(function () { return {}; }); throw new Error(bd.detail || b.status); }
      var bilet = await b.json();
      var akis = await fetch(bilet.url, { credentials: 'same-origin' });
      if (!akis.ok) throw new Error(akis.status);
      var blob = await akis.blob();
      if (blob.size > DOSYA_GONDER_BOYUT) throw new Error(cokBuyuk);
      var fd = new FormData();
      fd.append('file', blob, o.ad);
      var up = await authFetch('/api/media/upload', { method: 'POST', body: fd });
      if (!up.ok) { var ud = await up.json().catch(function () { return {}; }); throw new Error(ud.detail || up.status); }
      var y = await up.json();
      (y.kind === 'image' || _DG_IMG.test(y.filename) ? gorseller : belgeler).push(y.filename);
    } catch (err) {
      hata++;
      console.error('[dosya gönder]', o.ad, err);
      showToast(o.ad + ': ' + (err.message || err), 'err', 3500);
    }
  }
  _gpStatus('');
  if (!belgeler.length && !gorseller.length) return;
  if (typeof switchTab === 'function') switchTab('chat');
  for (var k = 0; k < gorseller.length; k++) {
    try { await authFetch('/api/media/send-to-chat/' + encodeURIComponent(gorseller[k]), { method: 'POST' }); }
    catch (err) { console.error('[dosya gönder görsel]', err); }
  }
  if (belgeler.length) {
    try { await _gpSendDocsToChat(belgeler); }
    catch (err) { console.error('[dosya gönder belge]', err); showToast(err.message, 'err', 3500); }
  }
  showToast(_tst('tab-switcher.dosya-yuklendi', { sayi: belgeler.length + gorseller.length }), 'ok', 2200);
}

window.addEventListener('message', function (e) {
  var m = _dosyaGonderMesaji(e);
  if (m) _dosyaGonder(m.ogeler, m.gizli);
});
