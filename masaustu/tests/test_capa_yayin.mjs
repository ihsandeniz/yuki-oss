// Ön yüz çapa yayıncısı (frontend/js/masaustu-capa.js) — sahte DOM ile. Kullanım: node tests/test_capa_yayin.mjs
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

let gecti = 0, kaldi = 0;
const kontrol = (ad, kosul, ayrinti = '') => {
  if (kosul) { gecti++; console.log('  ✓', ad); } else { kaldi++; console.log('  ✗', ad, ayrinti); }
};
const KOD = readFileSync(new URL('../../frontend/js/masaustu-capa.js', import.meta.url), 'utf8');

function sayfa({ electron = true, oge = {}, gizli = false, soket = null, widget = [] } = {}) {
  const araliklar = [];
  const el = sec => oge[sec] ? { r: oge[sec].r, st: oge[sec].st || {} } : null;
  const ctx = {
    innerWidth: 1900, innerHeight: 1015,
    document: { get hidden() { return ctx._gizli; }, querySelector: sec => el(sec) && { getBoundingClientRect: () => el(sec).r, _st: el(sec).st },
                // .hr-widget seçicisi: gizli sınıflılar yalnız seçici :not(.hr-w-hidden) içeriyorsa dışarıda kalır
                querySelectorAll: sec => sec.startsWith('.hr-widget') ? widget.filter(w => !(w.gizliSinif && sec.includes(':not(.hr-w-hidden)')))
                  .map(w => ({ getBoundingClientRect: () => w.r, _st: w.st || {} })) : [] },
    getComputedStyle: e => Object.assign({ display: 'block', visibility: 'visible', opacity: '1' }, e._st),
    setInterval: (f, ms) => araliklar.push([f, ms]),
    JSON, Math, Date,
    socket: soket,
    _gizli: gizli,
  };
  ctx.window = ctx;
  if (electron) ctx.yukiApp = {};
  vm.createContext(ctx);
  vm.runInContext(KOD, ctx);
  return { ctx, araliklar };
}
const R = (l, t, w, h) => ({ left: l, top: t, width: w, height: h, right: l + w, bottom: t + h });
const OGE = { '#hr-side': { r: R(1350, 300, 268, 476) }, '#giris-hap': { r: R(600.4, 930, 650, 48) } };

console.log('— ölçüm');
{
  const { ctx } = sayfa({ oge: OGE });
  const m = ctx.MasaustuCapa.olc();
  kontrol('kutular yuvarlanmış CSS px', JSON.stringify(m.panel) === '[1350,300,268,476]' && JSON.stringify(m.cubuk) === '[600,930,650,48]', JSON.stringify(m));
  kontrol('görünüm boyu eklenir', m.vw === 1900 && m.vh === 1015 && m.type === 'masaustu_capa');
}
{
  const { ctx } = sayfa({ oge: { '#hr-side': { r: R(1350, 300, 268, 476), st: { display: 'none' } }, '#giris-hap': { r: R(0, 0, 0, 0) } } });
  const m = ctx.MasaustuCapa.olc();
  kontrol('gizli PANEL ve sıfır boy hap → null', m.panel === null && m.cubuk === null, JSON.stringify(m));
  const { ctx: c2 } = sayfa({ oge: { '#hr-side': { r: R(1350, 1200, 268, 476) } } });
  kontrol('görünüm dışındaki öğe → null', c2.MasaustuCapa.olc().panel === null);
}

console.log('— paneller');
{
  const widget = [{ r: R(40, 80, 320, 460) }, { r: R(400, 80, 300, 360), st: { display: 'none' } },
                  { r: R(800, 80, 300, 360), gizliSinif: true }, { r: R(900, 2000, 300, 360) }];
  const { ctx } = sayfa({ oge: OGE, widget });
  const m = ctx.MasaustuCapa.olc();
  kontrol('açık panel gider; gizli/gizli sınıflı/görünüm dışı gitmez', JSON.stringify(m.paneller) === '[[40,80,320,460]]', JSON.stringify(m.paneller));
  const cok = Array.from({ length: 20 }, (_, i) => ({ r: R(10 + i, 80, 300, 300) }));
  kontrol('en çok 12 panel', sayfa({ oge: OGE, widget: cok }).ctx.MasaustuCapa.olc().paneller.length === 12);
  const giden = [], gonder = m2 => (giden.push(m2), true);
  ctx.MasaustuCapa.tur(0, gonder);
  widget[0].r = R(60, 80, 320, 460);
  ctx.MasaustuCapa.tur(1000, gonder);
  kontrol('panel kayınca hemen yollanır', giden.length === 2 && giden[1].paneller[0][0] === 60, giden.length);
  widget.push({ r: R(500, 500, 300, 300) });
  ctx.MasaustuCapa.tur(2000, gonder);
  kontrol('panel açılınca hemen yollanır', giden.length === 3 && giden[2].paneller.length === 2, giden.length);
}

console.log('— gönderim sıklığı');
{
  const { ctx } = sayfa({ oge: OGE });
  const giden = [], gonder = m => (giden.push(m), true);
  ctx.MasaustuCapa.tur(0, gonder);
  ctx.MasaustuCapa.tur(1000, gonder);
  kontrol('değişmediyse 1 sn sonra yollanmaz', giden.length === 1, giden.length);
  OGE['#hr-side'].r = R(1351, 300, 268, 476);
  ctx.MasaustuCapa.tur(2000, gonder);
  kontrol('1 px oynama yollanmaz (eşik 2 px)', giden.length === 1);
  OGE['#hr-side'].r = R(1370, 300, 268, 476);
  ctx.MasaustuCapa.tur(3000, gonder);
  kontrol('20 px kayınca hemen yollanır', giden.length === 2 && giden[1].panel[0] === 1370);
  ctx.MasaustuCapa.tur(8100, gonder);
  kontrol('değişmese de 5 sn sonra tazelenir', giden.length === 3);
  ctx._gizli = true;
  ctx.MasaustuCapa.tur(20000, gonder);
  kontrol('sayfa gizliyken yollanmaz', giden.length === 3);
  ctx._gizli = false;
  ctx.MasaustuCapa.tur(21000, () => false);
  ctx.MasaustuCapa.tur(21500, gonder);
  kontrol('soket kapalıyken gidemeyen ileti sonraki turda yeniden denenir', giden.length === 4);
}

console.log('— yalnız Electron');
{
  const { araliklar } = sayfa({ electron: false, oge: OGE });
  kontrol('tarayıcı/telefonda zamanlayıcı kurulmaz', araliklar.length === 0);
  const giden = [];
  const { araliklar: a2 } = sayfa({ oge: OGE, soket: { readyState: 1, send: m => giden.push(JSON.parse(m)), addEventListener() {} } });
  kontrol('Electron\'da 1 sn\'lik zamanlayıcı', a2.length === 1 && a2[0][1] === 1000);
  a2[0][0]();
  kontrol('açık sokete JSON gider', giden.length === 1 && giden[0].type === 'masaustu_capa', JSON.stringify(giden));
}

console.log('— yankı kapısı (eski backend iletiyi sohbet turu sayar)');
{
  const { ctx } = sayfa({ oge: OGE });
  const C = ctx.MasaustuCapa;
  function soket() {
    const s = { readyState: 1, giden: 0, dinle: null, send() { s.giden++; }, addEventListener(t, f) { s.dinle = f; } };
    return s;
  }
  const eski = soket(), M = { type: 'masaustu_capa' };
  C.soketGonder(M, 0, eski);
  for (let t = 1000; t <= 20000; t += 1000) C.soketGonder(M, t, eski);
  kontrol('eski backend (yankı yok): yalnız 1 yoklama, sonra susar', eski.giden === 1 && C.kapi.durum === false, [eski.giden, C.kapi.durum]);
  const yeni = soket();
  C.soketGonder(M, 30000, yeni);
  yeni.dinle({ data: JSON.stringify({ type: 'masaustu_capa', vw: 1, vh: 1 }) });
  for (let t = 31000; t <= 40000; t += 1000) C.soketGonder(M, t, yeni);
  kontrol('yeni soket (backend yeniden başladı) yeniden yoklar; yankı gelince sürekli yollar', yeni.giden === 11 && C.kapi.durum === true, [yeni.giden, C.kapi.durum]);
  const kapali = soket(); kapali.readyState = 3;
  kontrol('kapalı sokete yollanmaz', C.soketGonder(M, 50000, kapali) === false && kapali.giden === 0);
  yeni.dinle({ data: '{"type":"text","chunk":"masaustu"}' });
  kontrol('başka tipteki ileti yankı sayılmaz', C.kapi.soket === yeni);
}

console.log(`\nçapa yayını: ${gecti} geçti, ${kaldi} kaldı`);
process.exit(kaldi ? 1 : 0);
