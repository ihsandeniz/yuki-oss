"""ChatGPT hesabıyla resmî giriş ("Continue with ChatGPT") — BYOK anahtarına ek, ikinci yol.

Yalnız OpenAI'nin açık kaynak uygulamalar için yayımladığı "Sign in with ChatGPT"
token paylaşımı akışı: uygulama kendi adıyla (`agent_name_hint=Yuki`) kaydolur,
tarayıcıda giriş yapılır, çıkarım `api.openai.com/v1` Responses ucuna gider.
Başka bir istemcinin kimliğine bürünülmez; üçüncü taraf istemci başlığı gönderilmez.

  kimlik.py — kayıt, PKCE, kod değişimi, ID token doğrulama, 0600 yerel kayıt, yenileme, çıkış
  giris.py  — 127.0.0.1 geri dönüş dinleyicisi + tarayıcı
  istemci.py — Chat Completions biçimini Responses'a çeviren istemci (OpenAI SDK `responses`)

OpenAI'nin ticari olmayan lisanslı DevKit kodu bu pakete kopyalanmamıştır.
API anahtarı (BYOK) yolu bundan bağımsız, olduğu gibi açıktır.
"""
