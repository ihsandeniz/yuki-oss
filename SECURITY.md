# Güvenlik Politikası · Security Policy

> Bu politika açık kaynak depo için geçerlidir. Hazır paket ya da uygulama içi güncelleme dağıtımı henüz yok.
> This policy covers this open-source repository. There are no prebuilt packages or in-app update releases yet.
>
> Geliştirici notu / developer note: BYOK API anahtarları işletim sistemi anahtarlığında saklanır (`backend/app/services/sirlar.py`); anahtarlık yoksa kullanıcı veri dizinindeki `.env` dosyasına izin 600 ile düşülür. API keys live in the OS keyring; without one they fall back to a mode-600 `.env` in the user data directory.

## Türkçe

### Güvenlik açığı bildirme
Yuki'de bir güvenlik açığı bulduysan lütfen **herkese açık bir issue açma**. Bunun yerine GitHub'daki **Security → Report a vulnerability** (özel güvenlik bildirimi) yolunu kullan. Bildirime şunları ekle:
- etkilenen sürüm (Yuki → ⚙ Ayarlar → Hakkında) ve işletim sistemi,
- açığı yeniden üretme adımları,
- olası etkisi.

**İlk yanıt:** 7 gün içinde. Açık doğrulanırsa düzeltme takvimi seninle paylaşılır. İstersen sürüm notlarında adınla teşekkür edilir.

### Desteklenen sürümler
Güvenlik düzeltmeleri `main` dalının **son kaydına** gelir; kaynaktan çalıştıranlar `git pull` ile alır.

| Sürüm | Destek |
|---|---|
| en son sürüm | ✅ |
| daha eskiler | ❌ (güncelle) |

### Kapsam
- Yuki masaüstü uygulaması (Linux; Windows yalnız CI'da sınandı) ve birlikte gelen yerel motor (`127.0.0.1`).
- Kendi anahtarını getir (BYOK) yapay zekâ anahtarının bilgisayarda **yerel olarak saklanması**. Anahtar Yuki'nin sunucusuna gönderilmez, yalnız seçtiğin sağlayıcıya gider.
- Güncelleme ve indirme zinciri (bu deponun sürümleri).

**Kapsam dışı:** üçüncü taraf yapay zekâ sağlayıcılarının (OpenRouter, OpenAI, Anthropic, Google …) kendi hizmetleri. Onlara ait açıkları doğrudan sağlayıcıya bildir.

**Kullanıcı sorumluluğu (kapsam dışı):** `backend/mcp_servers.json` dosyasına elle eklediğin MCP sunucularının başlattığı programlar ve Claude CLI sağlayıcısının çağırdığı, bilgisayarında kurulu `claude` programının kendi davranışı. MCP sunucuları varsayılan kapalıdır, arayüzden açılmaz.

## English

### Reporting a vulnerability
Please **do not open a public issue**. Use GitHub **Security → Report a vulnerability** (private advisory) with the affected version (Yuki → ⚙ Settings → About), your OS, steps to reproduce and the possible impact.

**First response:** within 7 days. If confirmed, we will share a fix timeline and, if you wish, credit you in the release notes.

### Supported versions
Security fixes land on the **latest commit of `main`**; if you run from source, `git pull` to get them.

### Scope
The Yuki desktop app (Linux; Windows tested in CI only) with its bundled local engine (`127.0.0.1`), **local storage of your BYOK AI key** (never sent to Yuki's servers, only to the provider you choose), and the update/download chain (this repository's releases). Third-party AI providers' own services are out of scope; report those to the provider.

**User responsibility (out of scope):** programs started by MCP servers you add by hand to `backend/mcp_servers.json`, and the behaviour of the locally installed `claude` program called by the Claude CLI provider. MCP servers are disabled by default and cannot be enabled from the UI.
