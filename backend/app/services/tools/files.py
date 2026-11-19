"""Dosya sistemi araçları: okuma, yazma, listeleme, görüntü analizi, arama."""
import base64
import difflib
import os
import subprocess
import tarfile
import zipfile
from pathlib import Path

from app.services.tools._base import (
    _is_safe_path, _is_safe_write_path, _is_sensitive_read_path, _HOME_DIR,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
IMAGE_MIMES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp", ".bmp": "image/bmp",
}

# P1 E (H5): kimlik/token dosyaları modele okunmaz — yol listesi `_base._is_sensitive_read_path`.
_HASSAS_OKUMA = ("Hata: Güvenlik — bu dosya kimlik/anahtar bilgisi taşıyor, okunamaz. "  # i18n-istisna: LLM'e giden araç sonucu
                 "İçeriğine ihtiyaç varsa kullanıcı kendisi açabilir.")


def _okuma_kapisi(p: Path) -> str | None:
    """read_file ile aynı kapı: kök dışı ya da kimlik/anahtar dosyası → hata metni, yoksa None."""
    if not _is_safe_path(p):
        return f"Hata: Güvenlik — sadece {_HOME_DIR} ve /tmp altındaki dosyalara erişilebilir."
    if _is_sensitive_read_path(p) or _is_sensitive_read_path(p.resolve()):
        return _HASSAS_OKUMA
    return None


# Önbellek yok: yazma araçları önbelleği temizlemediği için az önce yazılan dosya 15 sn görünmüyordu.
def list_directory(path: str) -> str:
    """Lists files and directories in a given path."""
    try:
        p = Path(path).expanduser().resolve()
        if not _is_safe_path(p):
            return f"Hata: Güvenlik — sadece {_HOME_DIR} ve /tmp altındaki yollara erişilebilir."
        if not p.exists():
            return f"Hata: '{path}' yolu bulunamadı."
        if not p.is_dir():
            return f"Hata: '{path}' bir dizin değil."
        items = os.listdir(p)
        if not items:
            return f"'{path}' dizini boş."
        return "\n".join([f"- {'[DIR] ' if (p / item).is_dir() else '[FILE]'} {item}" for item in items])
    except Exception as e:
        return f"Hata: {str(e)}"


def read_file(path: str) -> str:
    """Reads the content of a file."""
    try:
        p = Path(path).expanduser().resolve()
        if not _is_safe_path(p):
            return f"Hata: Güvenlik — sadece {_HOME_DIR} ve /tmp altındaki dosyalar okunabilir."
        if _is_sensitive_read_path(Path(path).expanduser()) or _is_sensitive_read_path(p):
            return _HASSAS_OKUMA
        if not p.exists():
            return f"Hata: '{path}' dosyası bulunamadı."
        if not p.is_file():
            return f"Hata: '{path}' bir dosya değil."
        if p.stat().st_size > 1024 * 1024:
            return "Hata: Dosya çok büyük (1MB sınırı)."
        if b"\0" in p.read_bytes():
            return f"Hata: '{path}' ikili dosya, metin olarak okunamaz. Görselse analyze_image kullan."
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        return f"Hata: {str(e)}"


def write_file(path: str, content: str) -> str:
    """Dosyaya içerik yazar. Yoksa oluşturur, varsa üzerine yazar."""
    try:
        p = Path(path).expanduser().resolve()
        ok, err = _is_safe_write_path(p)
        if not ok:
            return f"Hata: {err}"
        if len(content.encode("utf-8")) > 1024 * 1024:
            return "Hata: İçerik çok büyük (1MB sınırı)."
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return f"'{path}' dosyasına {len(content)} karakter yazıldı."
    except Exception as e:
        return f"Hata: {str(e)}"


def append_file(path: str, content: str) -> str:
    """Dosyanın sonuna içerik ekler. Dosya yoksa oluşturur."""
    try:
        p = Path(path).expanduser().resolve()
        ok, err = _is_safe_write_path(p)
        if not ok:
            return f"Hata: {err}"
        if p.exists() and p.stat().st_size > 1024 * 1024:
            return "Hata: Dosya zaten 1MB sınırını aşıyor, ekleme yapılamaz."
        with open(p, "a", encoding="utf-8") as f:
            f.write(content)
        return f"'{path}' dosyasına {len(content)} karakter eklendi."
    except Exception as e:
        return f"Hata: {str(e)}"


async def analyze_image(path: str, prompt: str = "") -> str:
    """Yerel resim dosyasını Vision LLM ile analiz et."""
    from app.config import VISION_MODEL
    from app.services.llm import _get_client

    # Görsel buluttaki modele gider: read_file'ın yol ve hassas dosya kapısı burada da geçerli.
    hata = _okuma_kapisi(Path(path).expanduser())
    if hata:
        return hata
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Hata: Dosya bulunamadı: {path}"
    if not p.is_file():
        return f"Hata: Bu bir dosya değil: {path}"
    ext = p.suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        return f"Hata: Desteklenmeyen uzantı '{ext}'. Desteklenenler: {', '.join(sorted(IMAGE_EXTENSIONS))}"

    try:
        raw = p.read_bytes()
    except Exception as e:
        return f"Hata: Dosya okunamadı: {e}"

    mime = IMAGE_MIMES.get(ext, "image/jpeg")
    b64 = base64.b64encode(raw).decode()
    question = prompt or "Bu resimde ne var? Detaylıca açıkla."

    client = _get_client()
    try:
        response = await client.chat.completions.create(
            model=VISION_MODEL,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": question},
                ],
            }],
        )
        return response.choices[0].message.content or "Yanıt alınamadı."
    except Exception as e:
        return f"Hata: Vision LLM çağrısı başarısız: {e}"


def compress_file(path: str, output: str = "") -> str:
    """Dosya veya dizini zip arşivine sıkıştır."""
    try:
        p = Path(path).expanduser().resolve()
        if not _is_safe_path(p):
            return f"Hata: Güvenlik — sadece {_HOME_DIR} ve /tmp altındaki yollara erişilebilir."
        if not p.exists():
            return f"Hata: '{path}' bulunamadı."
        out = Path(output).expanduser().resolve() if output else p.with_suffix(".zip")
        ok, err = _is_safe_write_path(out)
        if not ok:
            return f"Hata: {err}"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            if p.is_file():
                zf.write(p, p.name)
            else:
                for f in p.rglob("*"):
                    if f.is_file() and f.resolve() != out:  # çıktı kaynağın içindeyse kendini içermesin
                        zf.write(f, f.relative_to(p.parent))
        size_kb = out.stat().st_size // 1024
        return f"Sıkıştırıldı: {out} ({size_kb} KB)"
    except Exception as e:
        return f"Hata: {e}"


def extract_archive(path: str, dest: str = "") -> str:
    """zip veya tar arşivini çıkar (path traversal + symlink güvenliği)."""
    try:
        p = Path(path).expanduser().resolve()
        if not _is_safe_path(p):
            return f"Hata: Güvenlik — sadece {_HOME_DIR} ve /tmp altındaki yollara erişilebilir."
        if not p.exists():
            return f"Hata: '{path}' bulunamadı."
        d = Path(dest).expanduser().resolve() if dest else p.parent / p.stem
        if not _is_safe_path(d):
            return f"Hata: Güvenlik — hedef dizin {_HOME_DIR} veya /tmp altında olmalı."
        d.mkdir(parents=True, exist_ok=True)
        d_resolved = d.resolve()
        suffix = p.suffix.lower()
        if suffix == ".zip":
            with zipfile.ZipFile(p, "r") as zf:
                for member in zf.infolist():
                    # Güvenli üye doğrulaması — path traversal veya absolute path kontrolü
                    member_path = (d_resolved / member.filename).resolve()
                    if not member_path.is_relative_to(d_resolved):
                        return f"Hata: Güvenlik — path traversal tespit edildi: {member.filename}"
                zf.extractall(d)
        elif suffix in (".tar", ".gz", ".bz2", ".xz") or p.suffixes[-2:] in ([".tar", ".gz"], [".tar", ".bz2"]):
            with tarfile.open(p, "r:*") as tf:
                for member in tf.getmembers():
                    # Symlink/hardlink reddi + path traversal kontrolü
                    if member.issym() or member.islnk():
                        return f"Hata: Güvenlik — symlink/hardlink izin verilmiyor: {member.name}"
                    member_path = (d_resolved / member.name).resolve()
                    if not member_path.is_relative_to(d_resolved):
                        return f"Hata: Güvenlik — path traversal tespit edildi: {member.name}"
                tf.extractall(d)
        else:
            return f"Hata: Desteklenmeyen arşiv formatı '{suffix}'. Desteklenenler: .zip, .tar, .tar.gz, .tar.bz2"
        return f"Çıkarıldı: {d}"
    except Exception as e:
        return f"Hata: {e}"


def diff_files(path1: str, path2: str) -> str:
    """İki metin dosyası arasındaki farkı göster (unified diff)."""
    try:
        p1 = Path(path1).expanduser().resolve()
        p2 = Path(path2).expanduser().resolve()
        for p in (p1, p2):
            if not _is_safe_path(p):
                return f"Hata: Güvenlik — '{p}' erişilemez."
            if _is_sensitive_read_path(p):
                return _HASSAS_OKUMA
            if not p.exists():
                return f"Hata: '{p}' bulunamadı."
            if p.stat().st_size > 512 * 1024:
                return f"Hata: '{p.name}' çok büyük (512KB sınırı)."
        lines1 = p1.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
        lines2 = p2.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
        diff = list(difflib.unified_diff(lines1, lines2, fromfile=str(p1), tofile=str(p2), n=3))
        if not diff:
            return "Dosyalar aynı — fark yok."
        result = "".join(diff[:200])  # 200 satır ile sınırla
        if len(diff) > 200:
            result += f"\n... ({len(diff) - 200} satır daha)"
        return result
    except Exception as e:
        return f"Hata: {e}"


def search_file(query: str, path: str = "~") -> str:
    """Dosya içinde metin arar (ripgrep). path: aranacak dizin."""
    search_path = os.path.expanduser(path)
    # read_file ile aynı kapı: dönen dosya adı da içeriğin varlığını sızdırır.
    # `/_` eki: hassas dizin denetimi dizinin kendisini değil içini yakalar (`~/.ssh` aranmasın).
    hata = _okuma_kapisi(Path(search_path) / "_")
    if hata:
        return hata
    if not os.path.exists(search_path):
        return f"Hata: Dizin bulunamadı: {path}"
    try:
        result = subprocess.run(
            ["rg", "--max-count=5", "--max-filesize=1M", "-l", "--", query, search_path],
            capture_output=True, text=True, timeout=15
        )
        files = [f for f in result.stdout.strip().splitlines() if not _is_sensitive_read_path(Path(f))]
        if not files:
            result2 = subprocess.run(
                ["find", search_path, "-maxdepth", "5", "-name", f"*{query}*", "-type", "f"],
                capture_output=True, text=True, timeout=10
            )
            files = [f for f in result2.stdout.strip().splitlines()
                     if not _is_sensitive_read_path(Path(f))][:10]
            if not files:
                return f"'{query}' için eşleşme bulunamadı: {path}"
            return f"Dosya adı eşleşmeleri ({len(files)}):\n" + "\n".join(files)
        return f"İçerik eşleşmeleri ({len(files)} dosya):\n" + "\n".join(files[:15])
    except FileNotFoundError:
        return "Hata: ripgrep (rg) bulunamadı. Yükle: sudo pacman -S ripgrep"
    except Exception as e:
        return f"Hata: {e}"
