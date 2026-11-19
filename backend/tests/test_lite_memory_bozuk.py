"""Sohbet geçmişi — bozuk dosya sessizce EZİLMESİN (2026-11-10 gizli hata turu).

`_read` bozuk JSON'da `{}` dönüyordu; sonraki `save_history` dosyayı yalnız o anki
karakterle yeniden yazıyordu → okunamayan (ama çoğu kez elle kurtarılabilir) geçmişin
TAMAMI yedeksiz siliniyordu. Geçersiz UTF-8 bayt ise yakalanmıyor, sohbeti düşürüyordu.
"""
import pytest

from app.services import lite_memory as lm


@pytest.fixture
def dosyalar(tmp_path, monkeypatch):
    monkeypatch.setattr(lm, "_HISTORY_FILE", tmp_path / "chat_history.json")
    monkeypatch.setattr(lm, "_PROFILE_FILE", tmp_path / "user_profile.json")
    return tmp_path


@pytest.mark.parametrize("bozuk", [
    '{"yuki": [{"role": "user", "content": "üç yıllık sohbet"}], "eski": [',   # yarım JSON
    b'{"yuki": [{"role": "user", "content": "\xff\xfe"}]}',                       # geçersiz UTF-8
    '["liste", "sözlük değil"]',
])
def test_bozuk_gecmis_ezilmeden_ONCE_yedeklenir(dosyalar, bozuk):
    yol = dosyalar / "chat_history.json"
    (yol.write_bytes if isinstance(bozuk, bytes) else yol.write_text)(bozuk)
    ham = yol.read_bytes()

    lm.save_history("yuki", [{"role": "user", "content": "yeni"}])

    yedekler = list(dosyalar.glob("chat_history.json.bozuk*"))
    assert yedekler, "bozuk geçmiş yedeklenmeden ezildi — eski sohbetlerin tamamı kayıp"
    assert yedekler[0].read_bytes() == ham
    assert lm.load_history("yuki") == [{"role": "user", "content": "yeni"}]


def test_bozuk_profil_de_yedeklenir(dosyalar):
    yol = dosyalar / "user_profile.json"
    yol.write_text('{"yuki": {"summary": "adı Ayşe, kedisi var"')
    lm.note_user_message("yuki")
    assert list(dosyalar.glob("user_profile.json.bozuk*"))


def test_saglam_dosyada_yedek_URETILMEZ(dosyalar):
    lm.save_history("yuki", [{"role": "user", "content": "a"}])
    lm.save_history("yuki", [{"role": "user", "content": "b"}])
    assert not list(dosyalar.glob("*.bozuk*"))
