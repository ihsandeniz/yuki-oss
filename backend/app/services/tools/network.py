"""Ağ araçları: web, arama, ping, IP, bildirim, pano."""
import asyncio
import os
import re
import subprocess
import time
from html.parser import HTMLParser

from app.config import BROWSER_ENABLED

# browse_web TTL cache
_browse_cache: dict[str, tuple[float, str]] = {}
_BROWSE_CACHE_TTL = 300  # 5 dakika


class _TextExtractor(HTMLParser):
    """HTML → okunabilir metin. Yalnız stdlib — pakete tek bayt eklemez.

    script/style/nav/footer gibi gürültü etiketlerinin İÇERİĞİ atılır; blok
    etiketlerinde satır sonu bırakılır ki LLM'e giden metin paragraf yapısını
    korusun.
    """

    _SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}
    _BLOCK = {
        "p", "div", "br", "li", "tr", "section", "article", "header",
        "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "td",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data.strip()
            return
        if self._skip_depth == 0 and data.strip():
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r"\n\s*\n\s*\n+", "\n\n", raw)
        return "\n".join(line.strip() for line in raw.splitlines()).strip()


def _html_to_text(html: str) -> tuple[str, str]:
    """(başlık, metin) döndürür. Ayrıştırma patlarsa kaba etiket temizliğine düşer."""
    try:
        p = _TextExtractor()
        p.feed(html)
        p.close()
        return p.title, p.text()
    except Exception:  # noqa: BLE001
        stripped = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
        stripped = re.sub(r"(?s)<[^>]+>", " ", stripped)
        return "", re.sub(r"\s+", " ", stripped).strip()


# ── SSRF kapısı (P1 E, denetim 10-06 H5) ─────────────────────────────────────
# Eskiden `follow_redirects=True` + hiç adres denetimi yoktu: okutulan bir sayfadaki gizli
# talimat `browse_web("http://127.0.0.1:8791/api/...")` ya da dış bir adresten 302 ile
# kullanıcının yerel ağını (modem, NAS) ve Yuki'nin kendi uçlarını okutabiliyordu.
# Harita vekilindeki desen (`api/map.py::_vekil_ac`): yönlendirme ELLE izlenir, HER adımda
# `ozel_adres_mi` sorulur (DNS çözümü dahil, fail-closed).
_YONLENDIRME_SINIRI = 5
# Araç hata verince model açamadığı sayfayı kaynak gösterebiliyordu (kişisel kopyada ölçüldü,
# 4 koşunun 1'i): not hatanın yanında dursun, karar anında okunsun.
_OKUNMADI = " Bu içerik okunmadı: kaynak gösterme, hatayı kullanıcıya söyle."  # i18n-istisna: LLM'e giden araç sonucu
_YEREL_RED = ("Hata: Güvenlik — bu adres bu bilgisayara ya da yerel ağa gidiyor; "  # i18n-istisna: LLM'e giden araç sonucu
              "web aracı yalnız internetteki sayfaları açar." + _OKUNMADI)


def _red_mesaji(url: str) -> str:
    """`ozel_adres_mi` reddinin yalnız METNİ; karar orada verildi, burası bir şey açmaz.

    Çözülemeyen ad da fail-closed reddedilir ama sebep ağdır: "yerel ağa gidiyor" denince
    model DNS kesintisini "güvenlik filtresi engelledi" diye anlatıyordu.
    """
    import socket
    from urllib.parse import urlparse
    try:
        p = urlparse(url)
        if p.scheme in ("http", "https") and p.hostname:
            socket.getaddrinfo(p.hostname, None)
    except socket.gaierror:
        return (f"Hata: Ağ — '{p.hostname}' adı çözülemedi (böyle bir ad yok ya da DNS/internet "  # i18n-istisna: LLM'e giden araç sonucu
                "sorunu var); sayfa açılmadı." + _OKUNMADI)
    except Exception:
        pass
    return _YEREL_RED


async def _guvenli_get(client, url: str):
    """(yanıt, None) ya da (None, hata_metni). Yönlendirme her adımda kapıdan geçer."""
    from urllib.parse import urljoin

    from app.services.adres_kapisi import ozel_adres_mi
    for _ in range(_YONLENDIRME_SINIRI + 1):
        if ozel_adres_mi(url):
            return None, await asyncio.to_thread(_red_mesaji, url)
        resp = await client.get(url)
        if not resp.is_redirect:
            return resp, None
        hedef = resp.headers.get("location", "")
        if not hedef:
            return None, "Hata: Sayfa açılamadı (boş yönlendirme)." + _OKUNMADI  # i18n-istisna: LLM'e giden araç sonucu
        url = urljoin(str(resp.url), hedef)
    return None, "Hata: Sayfa açılamadı (çok fazla yönlendirme)." + _OKUNMADI  # i18n-istisna: LLM'e giden araç sonucu


async def browse_web(url: str, task: str = "") -> str:
    """Verilen URL'yi ziyaret eder ve sayfanın içeriğini okur. 5 dakika TTL cache.

    ÜRÜN YOLU = düz HTTP isteği + stdlib HTML→metin. Sebep: satılan pakette
    tarayıcı ikilisi (chromium ~170 MB/platform) YOK ve Windows tarafı bu
    makinede doğrulanamıyor → "aracı listeye koy ama çalışmasın" durumu doğuyordu.
    Bu yol Linux+Windows'ta aynı şekilde çalışır ve pakete tek bayt eklemez.
    Bedeli: içeriğini yalnız JS ile üreten sayfalar boş görünür → o durumda
    kullanıcıya dürüstçe söylenir. Geliştirici makinesinde playwright kuruluysa
    (BROWSER_ENABLED=true) JS'li sayfalar için yükseltme yolu denenir.
    """
    now = time.monotonic()
    if url in _browse_cache:
        ts, cached = _browse_cache[url]
        if now - ts < _BROWSE_CACHE_TTL:
            return cached

    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url

    try:
        import httpx
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=15.0,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; Yuki/1.0)",
                "Accept-Language": "tr,en;q=0.8",
            },
        ) as client:
            resp, hata = await _guvenli_get(client, url)
        if hata:
            return hata
        if resp.status_code >= 400:
            return f"Hata: Sayfa açılamadı (HTTP {resp.status_code}).{_OKUNMADI}"

        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype:
            return f"Hata: Bu adres metin değil ({ctype or 'bilinmeyen tür'}) — okuyamam.{_OKUNMADI}"

        title, content = _html_to_text(resp.text)
    except Exception as e:  # noqa: BLE001
        return f"Hata: Sayfa açılamadı. {e}.{_OKUNMADI}"

    # JS ile üretilen sayfa → metin neredeyse boş. Playwright varsa yükselt.
    if len(content) < 200 and BROWSER_ENABLED:
        upgraded = await _browse_with_browser(str(resp.url))
        if upgraded:
            content = upgraded

    # Kısa ama gerçek metin (ör. example.com ~150 karakter) HATA DEĞİLDİR —
    # yalnız neredeyse tamamen boşsa dürüstçe söyle.
    if len(content) < 30:
        return (
            f"Sayfa açıldı ama okunabilir metin çıkmadı{f' (başlık: {title})' if title else ''} — "
            "içeriğini tarayıcıda JavaScript ile üreten bir sayfa olabilir. "
            "İstersen `web_search` ile bu konuyu arayabilirim."
        )

    if title:
        content = f"{title}\n\n{content}"
    if len(content) > 4000:
        content = content[:4000] + "\n...[içerik kesildi]"
    _browse_cache[url] = (time.monotonic(), content)
    return content


async def _browse_with_browser(url: str) -> str:
    """Yalnız geliştirici kurulumu: playwright varsa JS'li sayfayı render et."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            content = await page.inner_text("body")
            await browser.close()
        return content.strip()
    except Exception:  # noqa: BLE001
        return ""


async def web_search(query: str) -> str:
    """DuckDuckGo ile web araması yapar (gerçek arama sonuçları)."""
    try:
        import asyncio
        from ddgs import DDGS

        def _search() -> list[dict]:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=5))

        results = await asyncio.to_thread(_search)

        if not results:
            return f"'{query}' için sonuç bulunamadı.{_OKUNMADI}"

        lines: list[str] = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            lines.append(f"**{title}**\n{body}\n{href}")

        return "\n\n".join(lines)
    except Exception as e:
        return f"Hata: Web araması başarısız. {str(e)}.{_OKUNMADI}"


def ping_host(host: str) -> str:
    """Bir host'a ping atar ve gecikmeyi ölçer."""
    host = host.strip()
    if not re.match(r'^[a-zA-Z0-9.\-]+$', host):
        return "Hata: Geçersiz host adresi."
    try:
        result = subprocess.run(
            ["ping", "-c", "4", "-W", "3", host],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode != 0:
            return f"'{host}' erişilemiyor (ping başarısız)."
        lines = result.stdout.strip().splitlines()
        stats = next((l for l in reversed(lines) if "rtt" in l or "min/avg" in l), "")
        loss_line = next((l for l in lines if "packet loss" in l), "")
        return f"Ping: {host}\n{loss_line}\n{stats}".strip()
    except subprocess.TimeoutExpired:
        return f"Hata: Ping zaman aşımı — '{host}' yanıt vermiyor."
    except Exception as e:
        return f"Hata: {e}"


async def get_public_ip() -> str:
    """Sistemin dış (genel) IP adresini öğrenir."""
    from app import demo_kip
    if demo_kip.acik():   # demo: dış IP (→ konum) sorgusu yapılmaz
        return f"Genel IP: {demo_kip.BELGELEME_IP} (demo)"
    import httpx
    urls = [
        "https://api.ipify.org",
        "https://icanhazip.com",
        "https://ifconfig.me/ip",
    ]
    async with httpx.AsyncClient(timeout=5.0) as client:
        for url in urls:
            try:
                resp = await client.get(url)
                ip = resp.text.strip()
                if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', ip):
                    return f"Genel IP: {ip}"
            except Exception:
                continue
    return "Hata: IP adresi alınamadı (internet bağlantısını kontrol et)."


def send_notification(title: str, body: str = "", urgency: str = "normal") -> str:
    """notify-send ile masaüstü bildirimi gönderir."""
    if urgency not in ("low", "normal", "critical"):
        urgency = "normal"
    try:
        args = ["notify-send", "-u", urgency, "--", title]
        if body:
            args.append(body)
        subprocess.run(args, timeout=5, check=True, capture_output=True)
        return f"Bildirim gönderildi: '{title}'"
    except FileNotFoundError:
        return "Hata: notify-send bulunamadı (libnotify-tools yüklü değil)."
    except subprocess.CalledProcessError as e:
        return f"Hata: Bildirim gönderilemedi. {e.stderr.decode(errors='ignore')}"
    except Exception as e:
        return f"Hata: {str(e)}"


def _is_windows() -> bool:
    return os.name == "nt"


def get_clipboard() -> str:
    """Pano içeriğini okur. Windows: PowerShell · Wayland: wl-paste · X11: xclip.

    ⚠️ Windows dalı 2026-07-29'da eklendi: öncesinde satılan Windows paketinde
    `xclip` aranıyor, bulunamayınca kullanıcıya *"Paketi yükle: xclip"* deniyordu
    — Windows'ta anlamsız bir öneri. Bu dal **gerçek Windows'ta çalıştırılarak
    doğrulanmadı** (bu makine Arch); mantık standart PowerShell çağrısı.
    """
    if _is_windows():
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return "Pano boş veya erişilemiyor."
            content = result.stdout.rstrip("\r\n")
            if len(content) > 2000:
                content = content[:2000] + "\n...[pano içeriği kesildi]"
            return content if content else "Pano boş."
        except FileNotFoundError:
            return "Hata: PowerShell bulunamadı, pano okunamadı."
        except Exception as e:  # noqa: BLE001
            return f"Hata: Pano okunamadı. {e}"

    is_wayland = bool(
        os.environ.get("XDG_SESSION_TYPE") == "wayland"
        or os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    )
    try:
        if is_wayland:
            result = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, text=True, timeout=5)
        else:
            result = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            return "Pano boş veya erişilemiyor."

        content = result.stdout
        if len(content) > 2000:
            content = content[:2000] + "\n...[pano içeriği kesildi]"
        return content if content else "Pano boş."
    except FileNotFoundError:
        tool = "wl-paste" if is_wayland else "xclip"
        return f"Hata: {tool} bulunamadı. Paketi yükle: {'wl-clipboard' if is_wayland else 'xclip'}"
    except Exception as e:
        return f"Hata: Pano okunamadı. {str(e)}"


def set_clipboard(text: str) -> str:
    """Metni panoya kopyalar. Windows: PowerShell · Wayland: wl-copy · X11: xclip.

    ⚠️ Windows dalı gerçek Windows'ta çalıştırılarak doğrulanmadı (bkz. get_clipboard).
    """
    if len(text.encode("utf-8")) > 512 * 1024:
        return "Hata: Pano içeriği çok büyük (512KB sınırı)."

    if _is_windows():
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                input=text, text=True, timeout=10, capture_output=True,
            )
            if proc.returncode != 0:
                return f"Hata: Panoya yazılamadı. {proc.stderr.strip()}"
            return f"Metin panoya kopyalandı ({len(text)} karakter)."
        except FileNotFoundError:
            return "Hata: PowerShell bulunamadı, panoya yazılamadı."
        except Exception as e:  # noqa: BLE001
            return f"Hata: {e}"

    is_wayland = bool(
        os.environ.get("XDG_SESSION_TYPE") == "wayland"
        or os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    )
    # ⚠️ wl-copy VE xclip, panonun sahibi olarak arka planda YAŞAMAYA DEVAM EDER.
    # `subprocess.run(..., timeout=5)` bu yüzden kopyalama BAŞARILI olsa bile her
    # seferinde TimeoutExpired atıp kullanıcıya "Hata: timed out" gösteriyordu
    # (Wayland'da bizzat ölçüldü: metin panoya geçmişti, araç hata döndürdü).
    # Doğrusu: veriyi yaz, süreci bırak, kısa bir bekleyişle yalnız ANINDA çöken
    # durumu hata say.
    cmd = ["wl-copy"] if is_wayland else ["xclip", "-selection", "clipboard"]
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        try:
            proc.communicate(input=text, timeout=2)
        except subprocess.TimeoutExpired:
            pass          # normal: pano sahibi olarak yaşıyor
        rc = proc.poll()
        if rc is not None and rc != 0:
            return "Hata: Panoya yazılamadı."
        return f"Metin panoya kopyalandı ({len(text)} karakter)."
    except FileNotFoundError:
        tool = "wl-copy" if is_wayland else "xclip"
        return f"Hata: {tool} bulunamadı. Paketi yükle: {'wl-clipboard' if is_wayland else 'xclip'}"
    except Exception as e:
        return f"Hata: {str(e)}"
