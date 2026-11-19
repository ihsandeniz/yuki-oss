/* ============================================================================
   YUKI · SÖZLÜK — 日本語
   2026-09-18 · FAZ 2 → FAZ 3

   🟠 BU SÖZLÜK BİLEREK KISMİDİR — ve bu bir eksiklik değil, KAYITLI bir karardır.

   FAZ 3'ün kapsam kararı (geliştirici, 2026-09-18) **yalnız `en`**'di. `ja` üründe
   2026'dan beri kayıtlı bir asistan dili ama arayüzü hiç çevrilmemişti; bu
   turda çevrilmedi de. Sebep ölçülebilirlik: Japonca çıktıyı bu vault'ta
   doğrulayamıyoruz, doğrulanmamış 300 satır **çeviri gibi görünen** bir
   yüzey üretirdi — bayat belgenin dil hâli (§ Bağlam Hijyeni kural 5).

   🔑 Eksik anahtar Türkçe'ye DEĞİL İNGİLİZCE'ye düşer (`dil.js::YEDEK`).
   Japonca konuşan bir kullanıcının Türkçe okuma olasılığı yok denecek kadar
   azdır; İngilizce hem okunur hem dürüsttür.

   ⚠️ Kapsam CIRCIR KAPISIYLA korunuyor (`test_faz3_ja_kapsami_dusmuyor`):
   bu sözlüğün kapsadığı anahtar oranı **düşerse test kırmızı yanar**. Yani
   gecikme görünür kalır; sessizce büyüyemez. Anahtar eklerken sil-baştan
   çevirmen gerekmez, ama var olanı da kaybetmemen gerekir.
   ========================================================================= */
window.YukiSozluk = window.YukiSozluk || {};
window.YukiSozluk.ja = {
  // ── Dil seçici ─────────────────────────────────────────────────────────
  'dil.baslik': '会話の言語:',
  'dil.degistirilemedi': '言語を変更できませんでした: {sebep}',
  'dil.apiHatasi': '言語APIエラー: {mesaj}',
  'dil.bilinmeyen': '不明',
  // İlk açılış sihirbazı (ilk-kurulum.js)
  'ik.etiket': '初期設定',
  'ik.atla': 'あとで',
  'ik.adimlar': '設定の手順',
  'ik.adim.dil': '言語',
  'ik.adim.saglayici': 'モデル',
  'ik.adim.anahtar': '接続',
  'ik.adim.hazir': '完了',
  'ik.dil.baslik': 'どの言語で話しますか？',
  'ik.dil.tr': 'Türkçe',
  'ik.dil.en': 'English',
  'ik.dil.ja': '日本語',
  'ik.ileri': '次へ',
  'ik.geri': '戻る',
  'ik.saglayici.baslik': 'Yuki が使うモデルを選んでください',
  'ik.saglayici.aciklama': 'このパソコンで動くローカルモデル（キー不要）か、自分のキーで使うクラウドサービスを選びます。',
  'ik.rozet.yerel': 'ローカル',
  'ik.rozet.ucretsiz': '無料プランあり',
  'ik.yerel.baslik': 'ローカルモデルをテスト',
  'ik.yerel.aciklama': '{ad} がこのパソコンで動いている必要があります。テストで実際にリクエストを送り、応答があった場合のみ保存します。',
  'ik.anahtar.baslik': 'キーを入力',
  'ik.anahtar.aciklama': '{ad} のキーはこのパソコンにのみ保存されます。先にテストし、失敗したら保存しません。',
  'ik.anahtar.al': 'キーを取得',
  'ik.anahtar.yer-tutucu': 'API キー',
  'ik.anahtar.bos': '先にキーを貼り付けてください。',
  'ik.sina': 'テストして保存',
  'ik.siniyor': 'テスト中…',
  'ik.hata.genel': 'うまくいきませんでした。内容を確認してもう一度お試しください。',
  'ik.hata.anahtar': 'キーが受け付けられませんでした。キー全体をコピーしたか、正しいプロバイダーを選んだか確認してください。',
  'ik.hazir.baslik': '準備完了',
  'ik.hazir.aciklama': '接続できました。設定 → API キー からいつでも変更できます。',
  'ik.basla': 'チャットを始める',
};
