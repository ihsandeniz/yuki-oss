"""TOOLS tanımları, call_tool dispatcher ve GET_TOOLS_DEFINITION."""
import asyncio
from typing import Any

from app.services.tools.media import take_screenshot, send_screenshot_to_chat
from app.services.tools.files import list_directory, read_file, write_file, append_file, analyze_image, search_file, compress_file, extract_archive, diff_files
from app.services.tools.system import get_system_info, monitor_system, monitor_process, check_service, get_current_datetime
from app.services.tools.network import browse_web, web_search, send_notification, get_clipboard, set_clipboard, ping_host, get_public_ip
from app.services.tools.memory_tools import memory_search, memory_stats, memory_reflect
from app.services.tools.scheduler_tools import set_reminder, _list_reminders, _cancel_reminder
from app.services.tools.notes_tools import create_note, list_notes, get_note, delete_note, restore_note
from app.services.tools.media import control_media, open_application, launch_game, update_game, close_game, youtube_music
from app.services.tools.wiki import wiki_search, wiki_read, wiki_index, wiki_write
from app.services.tools.skills import skill_list, skill_run
from app.services.tools.arch import list_packages, check_updates, read_journal
from app.services.tools.calendar import get_calendar_events, create_calendar_event, delete_calendar_event
from app.services.tools.data import (
    get_weather, get_earthquake_alerts, get_exchange_rate,
    get_crypto_price, get_battery, git_status, git_log,
)
from app.services.tools.smart_home import smart_home_control, smart_home_discover
from app.services.tools.ui_tools import switch_tab, list_tabs, switch_character, list_characters
from app.services.tools.modes import start_mode, list_modes
from app.services.tools.vision_extra import ocr_image, read_qr, generate_image
from app.services.tools.finance_research import research_stock
from app.services.tools.todo_tools import (
    create_todo, complete_todo, list_todos, search_todos,
    delete_todo, update_todo, list_todo_lists, get_budget_summary,
)
from app.services.tools import gorus_tools as _gorus_tools
from app.services.tools.fitness_tools import (
    get_fitness_summary, log_meal, delete_meal, list_meals,
    log_workout_exercise, list_workout,
    get_fitness_config, update_fitness_config,
    save_fitness_template, list_fitness_templates, delete_fitness_template,
)


# --------------------------------------------------------------------------- #
# Dil şeması — `set_language` aracının enum'u KAYNAKTAN gelir (2026-09-18, FAZ 1)
#
# `config.LANGUAGES` dilin tek kaydıdır; buradaki enum elle tutulsaydı yeni bir
# dil eklendiğinde araç şeması geride kalırdı ve LLM o dili seçemezdi.
# `config` modül düzeyinde güvenle import edilir: `app.config` hiçbir `app.*`
# modülünü tepeden çekmez (`config_manager` importu fonksiyon içindedir).
# --------------------------------------------------------------------------- #
def _DIL_KODLARI() -> list[str]:
    from app.config import LANGUAGES
    return list(LANGUAGES)


def _DIL_ACIKLAMA() -> str:
    from app.config import LANGUAGES
    return ", ".join(f"'{k}' ({v['name']})" for k, v in LANGUAGES.items())


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Anlık ekran görüntüsü alır ve Vision LLM ile analiz eder. Kullanıcı 'ekranımda ne var', 'burayı incele', 'anlat' gibi şeyler sorduğunda kullan.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_screenshot_to_chat",
            "description": "Ekran görüntüsü alır ve chat ekranına görsel olarak gönderir (analiz YAPMAZ). Kullanıcı 'ekranı at', 'resmi gönder', 'ekran görüntüsünü at', 'paylaş' gibi şeyler söylediğinde kullan.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Verilen dizin yolundaki dosya ve klasörleri listeler.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Listelenecek dizin yolu (örneğin: /home/user/Documents)"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Belirtilen dosyanın içeriğini okur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Okunacak dosya yolu"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "switch_tab",
            "description": "Yuki uygulamasında bir sekmeye/bölüme geçer. Kullanıcı 'sohbete dön', 'ayarlara geç', 'planı aç', 'görev ekranını göster', 'zaman çizgisini aç' gibi UYGULAMA İÇİ bölüm değiştirme istediğinde kullan. Geçerli sekmeler: chat (Sohbet), planner (PLAN — görev/zaman çizgisi ekranı), hq (Ayarlar). Türkçe doğal isim de verilebilir (örn. 'sohbet', 'plan', 'ayarlar').",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab": {"type": "string", "description": "Geçilecek sekme. Kanonik ad (chat/planner/hq) veya Türkçe karşılığı (sohbet/plan/ayarlar)."}
                },
                "required": ["tab"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "map_goto",
            "description": "MAP sekmesindeki haritayı bir konuma götürür. Kullanıcı 'haritada Ankara'yı göster', 'oraya git', 'şu koordinata bak', 'haritayı Tokyo'ya al' gibi bir yer GÖSTERMEK istediğinde kullan. Yer adı verilebilir (çözümü harita yapar) ya da doğrudan lat/lon. NOT: switch_tab ile karıştırma — o sekmeyi açar, bu haritayı sürer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "yer": {"type": "string", "description": "Yer adı (ör. 'Ankara', 'Eyfel Kulesi'). lat/lon verilmiyorsa zorunlu."},
                    "lat": {"type": "number", "description": "Enlem — yer adı yerine doğrudan koordinat verilecekse."},
                    "lon": {"type": "number", "description": "Boylam — yer adı yerine doğrudan koordinat verilecekse."},
                    "zoom": {"type": "integer", "description": "Yakınlaştırma 1-18 (varsayılan: yere göre seçilir)."}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "map_layer",
            "description": "Harita katmanını açar/kapatır: deprem (sismik), yangın, volkan (yanardağ), ISS (uzay istasyonu), uçak (uçuş/adsb), uydu. Kullanıcı 'depremleri göster', 'yangın katmanını aç', 'uçakları kapat' dediğinde kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "katman": {"type": "string", "description": "Katman adı: deprem/yangın/volkan/iss/uçak/uydu."},
                    "ac": {"type": "boolean", "description": "true = aç (varsayılan), false = kapat."}
                },
                "required": ["katman"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "map_status",
            "description": "Haritada şu an ne görünüyor — merkez koordinatı, yakınlaştırma ve açık katmanlar. Kullanıcı 'harita nerede', 'şu an neye bakıyoruz', 'hangi katmanlar açık' diye sorduğunda kullan.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_media",
            "description": "GALERİ'deki resim/videoları ada göre arar ve listeler (ad · klasör · tür · id). Kullanıcı 'galeride X var mı', 'son çektiğim fotoğraflar', 'videolarımı listele' dediğinde kullan. Sorgu boşsa en yeni dosyalar gelir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ara": {"type": "string", "description": "Dosya adı parçası (boş = en yeniler)."},
                    "tip": {"type": "string", "enum": ["resim", "video"], "description": "Yalnız bu tür."},
                    "limit": {"type": "integer", "description": "En çok kaç dosya (1-50, varsayılan 20)."}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "show_media",
            "description": "Bir resmi/videoyu GALERİ sekmesinde açar. Kullanıcı 'şu fotoğrafı göster', 'X videosunu aç' dediğinde kullan. Tam yol, dosya adı ya da ad parçası verilebilir; emin değilsen önce list_media ile ara ve dönen id'yi ya da adı ver.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hedef": {"type": "string", "description": "Dosya adı, ad parçası ya da tam yol."}
                },
                "required": ["hedef"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_tabs",
            "description": "Yuki uygulamasındaki mevcut sekmeleri/bölümleri listeler. Kullanıcı 'hangi sekmeler var', 'neleri açabilirsin', 'bölümler neler' diye sorduğunda kullan.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_mode",
            "description": "Adlandırılmış MASAÜSTÜ otomasyon modunu başlatır: ilgili uygulamaları açar, çalışma alanına/özel alana geçer, kitty terminalinde komut çalıştırır. Kullanıcı 'X moduna geç', 'dosya yönetim modu', 'kod moduna geç', 'çalışma alanını aç', '[mod adı] başlat' gibi MOD/otomasyon istediğinde kullan. NOT: switch_tab (kendi arayüz sekmen) ile karıştırma — bu SİSTEM/masaüstü otomasyonu. Mod adı veya tetik kelimesi (modes.json) verilebilir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode_id": {"type": "string", "description": "Mod kimliği/adı (ör: 'dosya_yonetim', 'kodlama') veya tetik kelimesi (ör: 'dosya yönetim')."}
                },
                "required": ["mode_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_modes",
            "description": "Tanımlı tüm masaüstü otomasyon modlarını listeler. Kullanıcı 'hangi modlar var', 'mod listesi', 'hangi otomasyonlar' diye sorduğunda kullan.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "switch_character",
            "description": "Aktif karaktere/personaya geçer — kimlik, kişilik ve ses tonu değişir. Kullanıcı 'X karakterine geç', 'X ol' gibi KARAKTER değiştirme istediğinde kullan. Geçerli karakterler: list_characters ile görülür; olmayan bir karakteri uydurma.",
            "parameters": {
                "type": "object",
                "properties": {
                    "character": {"type": "string", "description": "Geçilecek karakterin kanonik adı (örn. yuki)."}
                },
                "required": ["character"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_characters",
            "description": "Seçilebilir karakterleri/personaları listeler. Kullanıcı 'hangi karakterler var', 'kimlere dönüşebilirsin', 'personalar neler' diye sorduğunda kullan.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Anlık tarih ve saati döner: gün, ay, yıl, saat, dakika, saniye. 'Saat kaç', 'bugün ne günü', 'tarih nedir', 'hangi gündeyiz' gibi sorularda kullan.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Sistem bilgilerini (İşletim sistemi, CPU, Bellek, çalışma dizini) getirir.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "monitor_system",
            "description": "Anlık sistem durumunu gösterir: CPU kullanımı (çekirdek bazında), RAM, disk, network ve en çok CPU kullanan 10 process. 'PC ne durumda', 'işlemci durumu', 'ne çalışıyor', 'hangi program açık' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browse_web",
            "description": "Verilen URL'yi tarayıcıda açar ve sayfanın metin içeriğini döndürür. Web araştırması, belge okuma veya URL kontrolü için kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Ziyaret edilecek tam URL (örn: https://example.com)"},
                    "task": {"type": "string", "description": "Bu sayfadan ne öğrenmek istediğini açıkla (isteğe bağlı)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_media",
            "description": "Müzik/video oynatıcıyı kontrol eder. 'Müziği durdur', 'sonraki şarkıya geç', 'sesi aç/kapat' gibi komutlar için kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "play_pause", "next", "prev", "stop", "volume_up", "volume_down", "mute"],
                        "description": "Medya aksiyonu"
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "masaustu_yuki",
            "description": "Masaüstü Yuki'yi (ekranın köşesinde ayakta duran tam boy SEN — aynı Yuki'nin ikinci bedeni, ayrı bir program değil) açar ya da kapatır. Kullanıcı 'masaüstüne gel', 'masaüstünde dur', 'yanıma gel', 'masaüstünden git/çekil', 'masaüstü Yuki'yi kapat', 'masaüstünde misin' dediğinde kullan. 'ac' ayarı da açar: Yuki her açılışta masaüstüne de gelir; 'kapat' ayarı kapatır. NOT: open_application ile karıştırma.",
            "parameters": {
                "type": "object",
                "properties": {
                    "islem": {
                        "type": "string",
                        "enum": ["ac", "kapat", "durum"],
                        "description": "ac = masaüstüne gel · kapat = masaüstünden çekil · durum = açık mı"
                    }
                },
                "required": ["islem"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Bir uygulamayı VEYA oyun istemcisini başlatır. 'Spotify'ı aç', 'VS Code'u başlat', 'Steam'i aç', 'Lutris'i aç', 'Firefox'ta YouTube'u aç' gibi komutlar için kullan. Steam/Lutris/Heroic gibi launcher'ın KENDİSİNİ açmak için bunu kullan (belirli bir oyunu başlatmak için launch_game kullan). Tarayıcılar için isteğe bağlı url parametresi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Başlatılacak uygulama adı (örn: spotify, code, firefox)"
                    },
                    "url": {
                        "type": "string",
                        "description": "Tarayıcıda açılacak URL (isteğe bağlı, sadece firefox/chromium/brave-browser için)"
                    }
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "launch_game",
            "description": "BELİRLİ bir Steam oyununu adıyla başlatır (gerekirse önce günceller, SONRA açar). 'Dota 2'yi aç', 'Dark Souls başlat', 'Satisfactory oynayalım' gibi kullanıcı OYNAMAK/AÇMAK istediğinde kullan. Kullanıcı sadece güncellensin, oyun açılmasın derse (örn. 'güncelle ama başlatma') bunun yerine update_game kullan. Kayıtlı oyunlar: Dota 2, Black Desert, Dark Souls III, Horizon Zero Dawn, Satisfactory, TerraTech, Stonehearth, Hacknet, VRoid Studio, Final Sentence. NOT: Steam istemcisinin kendisini açmak için (oyun değil) open_application('steam') kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "game_name": {
                        "type": "string",
                        "description": "Başlatılacak oyunun adı (örn: Dota 2, Dark Souls III, Satisfactory). Kısmi/yaklaşık ad da olur."
                    }
                },
                "required": ["game_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_game",
            "description": "BELİRLİ bir Steam oyununu SADECE günceller — güncelleme bitince oyunu AÇMAZ/BAŞLATMAZ. 'X güncellensin', 'X'i güncelle (başlatma)', 'sadece güncelle' gibi kullanıcı AÇIKÇA sadece güncelleme istediğinde kullan. Kullanıcı oynamak/açmak da istiyorsa (örn. 'başlat', 'aç', 'oynayalım') bunun yerine launch_game kullan — o zaten gerekirse otomatik günceller. Aynı GAME_REGISTRY'yi kullanır (launch_game ile aynı oyun adları).",
            "parameters": {
                "type": "object",
                "properties": {
                    "game_name": {
                        "type": "string",
                        "description": "Güncellenecek oyunun adı (örn: Black Desert, Dota 2). Kısmi/yaklaşık ad da olur."
                    }
                },
                "required": ["game_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "close_game",
            "description": "Açık olan bir oyunu kapatır. 'Oyunu kapat', 'Dota'yı kapat', 'Dark Souls'u kapat' gibi komutlar için kullan. Çalışan pencereyi adından bulup sonlandırır.",
            "parameters": {
                "type": "object",
                "properties": {
                    "game_name": {
                        "type": "string",
                        "description": "Kapatılacak oyunun adı (örn: Dota 2, Dark Souls III). Kısmi ad da olur."
                    }
                },
                "required": ["game_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_music",
            "description": "YouTube Music (masaüstü uygulaması) oynatma kontrolü. 'Müziği çal/duraklat', 'sonraki şarkı', 'önceki', 'şu an ne çalıyor', 'bu şarkıyı beğen', 'karıştır', 'tekrarla' gibi komutlar için kullan. NOT: Belirli bir şarkıyı/playlisti adıyla açma desteklenmiyor (sadece oynatma kontrolü ve mevcut şarkı bilgisi).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Aksiyon: çal, duraklat, toggle, sonraki, önceki, ileri, geri, beğen, beğenme, karıştır, tekrarla, durum (şu an çalan şarkı)."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_language",
            "description": "Konuşma dilini değiştirir (Türkçe ↔ Japonca ↔ İngilizce). Kullanıcı 'Japonca konuş', '日本語で話して', 'Türkçe'ye dön', 'speak Japanese', 'speak English', 'switch to English', 'İngilizce konuş' gibi dediğinde kullan. Hem senin yanıt dilini, hem sesini, hem de dinleme dilini değiştirir. Ekranın (arayüzün) dilini DEĞİŞTİRMEZ.",
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        # 🔑 Enum KAYNAKTAN türetilir (2026-09-18, FAZ 1). Elle yazılıydı
                        # ve `en` eklenince burası unutulsaydı model yeni dili HİÇ
                        # seçemezdi: `config.set_language('en')` çalışır, ama LLM'e
                        # sunulan şema onu geçersiz gösterirdi. Sessiz ve teşhisi zor.
                        "enum": _DIL_KODLARI(),
                        "description": "Hedef dil kodu: " + _DIL_ACIKLAMA() + "."
                    }
                },
                "required": ["language"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": (
                "Yerel diskteki bir resim dosyasını (jpg/png/gif/webp/bmp) Vision LLM ile analiz eder. "
                "Resimdeki nesneleri, renkleri, metni ve içeriği açıklar. "
                "Kullanıcı bir resim dosyası yolu verip 'içinde ne var', 'bunu analiz et' dediğinde kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Analiz edilecek resim dosyasının tam yolu (örn. /home/user/foto.jpg veya ~/Masaüstü/resim.png)",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Resim hakkında özel soru (opsiyonel). Boşsa genel açıklama yapılır.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Bir dosyaya metin içeriği yazar. Dosya yoksa oluşturur, varsa üzerine yazar. Not almak, kod kaydetmek veya içerik oluşturmak için kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Yazılacak dosya yolu (örn: ~/notlar.txt)"},
                    "content": {"type": "string", "description": "Dosyaya yazılacak metin içeriği"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "append_file",
            "description": "Mevcut bir dosyanın sonuna metin ekler. Log tutmak veya listeye eleman eklemek için kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "İçeriğin ekleneceği dosya yolu"},
                    "content": {"type": "string", "description": "Dosyanın sonuna eklenecek metin"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "DuckDuckGo ile web araması yapar. Güncel bilgi, tanım, haber veya genel bilgi soruları için kullan. URL yokken bile arama yapabilirsin.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Arama sorgusu (örn: 'Python asyncio nedir')"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_notification",
            "description": "Masaüstüne bildirim (notification) gönderir. Hatırlatıcı, uyarı veya bilgi iletmek için kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Bildirim başlığı"},
                    "body": {"type": "string", "description": "Bildirim içeriği (isteğe bağlı)"},
                    "urgency": {
                        "type": "string",
                        "enum": ["low", "normal", "critical"],
                        "description": "Bildirim önceliği (varsayılan: normal)"
                    }
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_clipboard",
            "description": "Panonun içeriğini okur. Kullanıcı 'panoda ne var', 'kopyaladığımı oku' dediğinde kullan.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_clipboard",
            "description": "Bir metni panoya kopyalar. Kullanıcı 'bunu kopyala', 'panoya al' dediğinde kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Panoya kopyalanacak metin"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "Yuki'nin uzun vadeli hafızasında semantik arama yapar. 'Bunu daha önce konuşmuş muyduk', 'tercihlerimi hatırlıyor musun' gibi durumlarda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Hafızada aranacak konu veya bilgi"},
                    "limit": {"type": "integer", "description": "Kaç sonuç getirilsin (varsayılan: 5, max: 10)"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_stats",
            "description": "Yuki'nin ne kadar öğrendiğini gösterir: kapsam başına kayıt sayısı ve önem ortalaması. 'Ne kadar şey biliyorsun', 'hafıza durumun nedir' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_reflect",
            "description": "Hafızayı optimize eder: benzer anıları birleştirir, duplikatları siler. 'Hafızanı temizle', 'hafızayı optimize et' gibi durumlarda kullan.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_search",
            "description": "Kullanıcının kişisel wiki bilgi tabanında arama yapar. Projeler, araçlar, metodolojiler, kararlar hakkında not/bilgi aranırken kullan. 'Wiki'de X hakkında ne var', 'X projesi hakkında ne biliyorsun' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Aranacak anahtar kelime veya konu"},
                    "max_results": {"type": "integer", "description": "Maksimum sonuç sayısı (varsayılan: 6)", "default": 6}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_read",
            "description": "Wiki'deki belirli bir sayfayı okur. wiki_search ile bulunan sayfa yolunu kullan. Örn: 'WIKI/sources/projects/2026-04-25-ornek-sayfa.md'",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "WIKI/ ile başlayan sayfa yolu"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_index",
            "description": "Wiki'nin index sayfasını okur — hangi kategoriler ve sayfalar var öğrenmek için kullan. wiki_search'ten önce genel bir bakış almak istediğinde çağır.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_write",
            "description": "Wiki'ye yeni sayfa yazar veya mevcut sayfaya içerik ekler. Not almak, proje güncellemesi kaydetmek, karar kaydetmek için kullan. Yol WIKI/ ile başlamalı, .md ile bitmeli.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "WIKI/ ile başlayan sayfa yolu, örn: 'WIKI/sources/projects/2026-05-17-not.md'"},
                    "content": {"type": "string", "description": "Yazılacak markdown içerik"},
                    "append": {"type": "boolean", "description": "True: dosyanın sonuna ekle, False: üzerine yaz (varsayılan: false)", "default": False}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "skill_list",
            "description": "Kullanılabilir skill'leri listeler. Kullanıcı 'hangi skill'ler var', 'ne yapabilirsin', 'yeteneklerin neler' diye sorduğunda çağır.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "skill_run",
            "description": "Bir skill'i çalıştırır — prompt şablonunu yükler ve $ARGUMENTS'ı kullanıcı girdisiyle değiştirir. 'Rakip analizi yap', 'teklif oluştur', 'iş analizi yap' gibi isteklerde kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill adı (uzantısız), örn: 'rakip-analizi', 'teklif', 'tam-is-analizi'"},
                    "arguments": {"type": "string", "description": "Skill'e geçirilecek kullanıcı girdisi, örn: 'yapay zeka destekli muhasebe uygulaması'", "default": ""}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Kullanıcıya alarm/hatırlatıcı kurar. İKİ TÜR VAR, kullanıcının ifadesine göre ayır et:\n(1) TEK SEFERLİK — 'beni 30 dakika sonra hatırlat', '14:30'da toplantım var' → repeat=false, when='30 dakika sonra' veya '14:30'. Bir kez çalar, biter.\n(2) TEKRARLI — 'her 20 dakikada bir alarm kur', 'her saat hatırlat', 'sürekli 10 dakikada bir uyar' → repeat=true, when='her 20 dakika'. Kullanıcı 'her', 'sürekli', '...da bir', 'düzenli' derse TEKRARLI kur; iptal edilene kadar çalar.\nAyrım kuralı: 'sonra' / 'saat X'te' = tek seferlik. 'her' / '...da bir' = tekrarlı.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Hatırlatıcı mesajı"},  # i18n-istisna: LLM'e giden araç şeması açıklaması
                    "when": {
                        "type": "string",
                        "description": "Tek seferlik için: '5 dakika sonra', '2 saat sonra', '14:30', '2026-05-05T15:00'. Tekrarlı için: 'her 20 dakika', 'her 2 saat', 'her gün'."
                    },
                    "repeat": {
                        "type": "boolean",
                        "description": "true → alarm iptal edilene kadar periyodik tekrarlar (kullanıcı 'her ... bir' / 'sürekli' dediğinde). false (varsayılan) → tek sefer çalar."
                    }
                },
                "required": ["message", "when"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "Aktif hatırlatıcıları listeler. 'Hatırlatıcılarım neler', 'ne zaman alarm kurdum' sorularında kullan.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_reminder",
            "description": "Bir alarmı/hatırlatıcıyı iptal eder (tekrarlı alarmı da durdurur). Kullanıcı 'alarmı kapat', 'hatırlatmayı durdur' derse kullan. job_id list_reminders çıktısından alınır; kullanıcı 'hepsini kapat' derse job_id='all' ver.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "İptal edilecek alarmın ID'si (örn. reminder_abc12345). Tümünü iptal için 'all'."}
                },
                "required": ["job_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_note",
            "description": "Kullanıcının not almasını sağlar. 'not al', 'bunu kaydet', 'hatırla' gibi ifadelerde kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Notun içeriği"},
                    "title": {"type": "string", "description": "Opsiyonel başlık (boş bırakılırsa içerikten otomatik üretilir)"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": "Kaydedilmiş notları listeler. 'notlarımı listele', 'notlarım ne', 'ne not almışım' gibi ifadelerde kullan.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_note",
            "description": "Belirli bir notun tam içeriğini gösterir. note_id, list_notes çıktısından alınır.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "Notun ID'si (örn. a1b2c3d4)"}
                },
                "required": ["note_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_note",
            "description": "Bir notu çöpe taşır (restore_note ile geri gelir). note_id, list_notes çıktısından alınır.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "Silinecek notun ID'si"}
                },
                "required": ["note_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "restore_note",
            "description": "Silinen notu çöpten geri getirir. 'Sildiğim notu geri getir' dendiğinde kullan; note_id, delete_note çıktısındaki ID'dir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "Geri getirilecek notun ID'si"}
                },
                "required": ["note_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "monitor_process",
            "description": "Belirli bir process'in anlık CPU, RAM ve durumunu gösterir. 'Firefox ne kadar RAM yiyor', 'python process durumu nedir' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_pid": {"type": "string", "description": "Process adı (kısmi eşleşir) veya PID numarası"}
                },
                "required": ["name_or_pid"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_file",
            "description": "Belirtilen dizinde dosya içi metin araması yapar (ripgrep). 'X kelimesini içeren dosyaları bul', 'hangi dosyada X var' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Aranacak metin veya regex"},
                    "path": {"type": "string", "description": "Aranacak dizin (varsayılan: ev dizini ~)"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compress_file",
            "description": "Bir dosya veya dizini zip arşivine sıkıştırır. 'Şu klasörü sıkıştır', 'zip yap' gibi isteklerde kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Sıkıştırılacak dosya veya dizin yolu"},
                    "output": {"type": "string", "description": "Çıktı zip dosyası yolu (opsiyonel, varsayılan: kaynak.zip)"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "extract_archive",
            "description": "Zip veya tar arşivini çıkarır. 'Şu arşivi aç', 'zip'i çıkar' gibi isteklerde kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Çıkarılacak arşiv dosyası yolu (.zip, .tar.gz vb.)"},
                    "dest": {"type": "string", "description": "Hedef dizin (opsiyonel, varsayılan: arşiv adıyla aynı dizin)"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "diff_files",
            "description": "İki metin dosyası arasındaki farkı gösterir (unified diff). 'Bu iki dosya arasındaki fark ne', 'eski ve yeni versiyonu karşılaştır' gibi isteklerde kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path1": {"type": "string", "description": "Birinci dosya yolu"},
                    "path2": {"type": "string", "description": "İkinci dosya yolu"}
                },
                "required": ["path1", "path2"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ping_host",
            "description": "Bir sunucu veya siteye ping atar, erişilebilirliği ve gecikmeyi ölçer. 'Google'a erişebiliyor muyum', 'sunucu çevrimiçi mi' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Host adresi (örn. 'google.com', '1.1.1.1')"}
                },
                "required": ["host"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_public_ip",
            "description": "Sistemin genel (dış) IP adresini öğrenir. 'IP adresim nedir', 'dış IP'im ne' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_service",
            "description": "systemd servisinin çalışıp çalışmadığını kontrol eder. 'Nginx çalışıyor mu', 'postgresql durumu nedir' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Servis adı (örn. 'nginx', 'postgresql', 'yuki')"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_packages",
            "description": "Arch Linux'ta yüklü paketleri listeler. 'Hangi paketler yüklü', 'python yüklü mü', 'neovim versiyonu ne' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_str": {"type": "string", "description": "Paket adını filtrele (boş bırakırsan hepsi gelir)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_updates",
            "description": "Arch Linux güncelleme kontrolü yapar. Bekleyen güncellemeleri listeler. 'Güncelleme var mı', 'sistem güncel mi' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_journal",
            "description": "systemd journal loglarını okur. 'Servis loglarını göster', 'backend hata veriyor ne yazıyor', 'journalctl çıktısı nedir' gibi durumlarda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "unit": {"type": "string", "description": "Servis adı (örn. 'nginx', 'postgresql', boş bırakırsan genel sistem logu)"},
                    "lines": {"type": "integer", "description": "Gösterilecek satır sayısı (varsayılan: 50, max: 200)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Google Takvim'deki yaklaşan etkinlikleri listeler. 'Bugün ne var', 'haftaki toplantılarım', 'takvimime bak' gibi isteklerde kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "description": "Döndürülecek maksimum etkinlik sayısı (varsayılan 10)"},
                    "time_min": {"type": "string", "description": "Bu tarihten itibaren etkinlikler (ISO 8601, örn. '2026-05-17T00:00:00Z'). Boşsa şu an."}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Google Takvim'e yeni etkinlik ekler. 'Yarın saat 10'a toplantı koy', 'takvime ekle' gibi isteklerde kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Etkinlik başlığı"},
                    "start": {"type": "string", "description": "Başlangıç (ISO 8601, örn. '2026-05-18T10:00:00+03:00')"},
                    "end": {"type": "string", "description": "Bitiş (ISO 8601, örn. '2026-05-18T11:00:00+03:00')"},
                    "description": {"type": "string", "description": "Etkinlik açıklaması (opsiyonel)"}
                },
                "required": ["summary", "start", "end"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": "Google Takvim'den bir etkinliği siler. Önce get_calendar_events ile ID'yi öğren, sonra bu araçla sil.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "Silinecek etkinliğin ID'si"}
                },
                "required": ["event_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Hava durumunu getirir: anlık sıcaklık, nem, rüzgar ve 3 günlük tahmin. 'Hava nasıl', 'Istanbul'da bugün hava', 'yarın yağmur var mı' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Şehir adı (Türkçe veya İngilizce, örn: 'İstanbul', 'Ankara', 'New York'). Varsayılan: 'Istanbul'"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_earthquake_alerts",
            "description": "Son depremleri listeler (USGS verisi). 'Deprem var mı', 'Türkiye'de son depremler', 'büyük depremler' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_magnitude": {
                        "type": "number",
                        "description": "Minimum büyüklük (varsayılan: 4.0)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Listelenecek deprem sayısı (varsayılan: 5, max: 20)"
                    },
                    "region": {
                        "type": "string",
                        "description": "'global' (dünya geneli) veya 'turkey' (Türkiye bölgesi). Varsayılan: 'global'"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": "Günlük döviz kurlarını getirir. 'Dolar kaç TL', 'euro kuru', 'döviz kurları' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "base": {
                        "type": "string",
                        "description": "Baz para birimi (örn: 'USD', 'EUR', 'TRY'). Varsayılan: 'USD'"
                    },
                    "currencies": {
                        "type": "string",
                        "description": "Hedef para birimleri, virgülle ayrılmış (örn: 'TRY,EUR,GBP'). Varsayılan: 'TRY,EUR,GBP'"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_crypto_price",
            "description": "Anlık kripto para fiyatlarını getirir. 'Bitcoin kaç dolar', 'ETH fiyatı', 'kripto fiyatları' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "coins": {
                        "type": "string",
                        "description": "Coin ID'leri virgülle ayrılmış (örn: 'bitcoin,ethereum,solana'). Varsayılan: 'bitcoin,ethereum'"
                    },
                    "currency": {
                        "type": "string",
                        "description": "Para birimi (örn: 'usd', 'eur', 'try'). Varsayılan: 'usd'"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_battery",
            "description": "Dizüstü batarya durumunu gösterir: şarj yüzdesi, şarj oluyor mu, tahmini süre. 'Batarya ne durumda', 'şarj var mı', 'pil yüzdesi' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Bir git reposunun durumunu gösterir: branch, staged/unstaged/untracked değişiklikler, son commitler. 'Git durumu nedir', 'hangi dosyalar değişti', 'commit gerekiyor mu' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Git repo dizin yolu (varsayılan: mevcut dizin '.')"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Git commit geçmişini listeler. 'Son commitler neler', 'git log göster', 'commit tarihçesi' gibi sorularda kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Git repo dizin yolu (varsayılan: '.')"
                    },
                    "n": {
                        "type": "integer",
                        "description": "Gösterilecek commit sayısı (varsayılan: 10, max: 50)"
                    }
                },
                "required": []
            }
        }
    },
    # ── UAI Agents Entegrasyonu ────────────────────────────────────────────────
    # ── Faz 22 — In-process Orkestrasyon (companion meclisi) ────────────────────
    {
        "type": "function",
        "function": {
            "name": "delegate_to_companion",
            "description": (
                "Tek bir uzman companion'a (persona) İZOLE bir alt-görev devret ve sonucunu al. "
                "Yuki koordinatör olarak kullanır. Uzmanlar: {uzmanlar}. "
                "Kullanıcı 'bir uzmana sor', '<uzman adı>'na sor' derse BU aracı kullan. "
                "Alt-görev arka planda izole ve SALT OKUNUR çalışır (dosya yazamaz, komut "
                "çalıştıramaz, ayar değiştiremez); ana konuşmayı ve AKTİF KARAKTERİ değiştirmez."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "persona": {
                        "type": "string",
                        "description": "Uzman companion anahtarı.",
                        # Uzman yokken araç hiç sunulmaz; enum + açıklamadaki
                        # {uzmanlar} `get_active_tools()`'ta PERSONAS'tan doldurulur.
                        "enum": [],
                    },
                    "subtask": {
                        "type": "string",
                        "description": "Bu companion'ın yapacağı tek, net alt-görev (Türkçe)."
                    }
                },
                "required": ["persona", "subtask"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_team",
            "description": (
                "Karmaşık/çok yönlü bir hedefi companion EKİBİNE dağıt: Yuki hedefi alt-görevlere "
                "böler, her birini uygun uzmana PARALEL delege eder, sonuçları "
                "tek yanıtta birleştirir. 'araştır + yaz + planla' gibi çok adımlı işlerde kullan. "
                "Kullanıcı 'ekiple çalış', 'ekibe sor', 'herkesin görüşünü al', 'ekip olarak bak' "
                "derse BU aracı kullan. Alt-ajanlar izole ve SALT OKUNUR çalışır (dosya yazamaz, "
                "komut çalıştıramaz); aktif karakteri/konuşmayı değiştirmez. Yapılması gereken bir "
                "iş varsa onu ekip değil sen yaparsın. Maliyetlidir: kullanıcıya onay penceresi çıkar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "Ekibe verilecek genel hedef (Türkçe)."
                    }
                },
                "required": ["goal"]
            }
        }
    },
    # ── Faz 23 — n8n webhook köprüsü (no-code otomasyon) ───────────────────────
    {
        "type": "function",
        "function": {
            "name": "trigger_n8n",
            "description": (
                "Bir n8n webhook iş akışını tetikler (no-code otomasyon köprüsü). "
                "workflow = webhook yolu/adı, payload = gönderilecek JSON gövde. "
                ".env → N8N_WEBHOOK_BASE tanımlı olmalı."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow": {
                        "type": "string",
                        "description": "n8n webhook yolu/adı (N8N_WEBHOOK_BASE'e eklenir)."
                    },
                    "payload": {
                        "type": "object",
                        "description": "Webhook'a gönderilecek JSON gövde (opsiyonel)."
                    }
                },
                "required": ["workflow"]
            }
        }
    },
    # ── Faz 25 — Rutinler (tekrarlı cron + aksiyon) ────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "create_routine",
            "description": (
                "Tekrarlı bir rutin kurar (restart-güvenli). Belirli bir zamanlamada bir aksiyonu "
                "otomatik çalıştırır. schedule: 'HH:MM' (günlük) veya 'every 30m'/'every 2h'/'every 1d'. "
                "action_type: team (companion ekibine hedef ver) | skill (bir skill'i çalıştır) | "
                "message (düz metin söyle). 'her sabah 9'da haberleri araştır' gibi isteklerde kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Rutin için kısa ad."},
                    "schedule": {"type": "string", "description": "'HH:MM' ya da 'every 30m|2h|1d'."},
                    "action_type": {"type": "string", "enum": ["team", "skill", "message"]},
                    "action": {"type": "string", "description": "team→hedef · skill→skill adı · message→metin."}
                },
                "required": ["name", "schedule", "action_type", "action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_routines",
            "description": "Kayıtlı tüm rutinleri listeler (id, ad, zamanlama, aksiyon).",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_routine",
            "description": "Bir rutini id ile siler (list_routines'ten alınır).",
            "parameters": {
                "type": "object",
                "properties": {"routine_id": {"type": "string", "description": "Silinecek rutin id'si."}},
                "required": ["routine_id"]
            }
        }
    },
    # ── Faz δ — Akıllı Ev Entegrasyonu ──────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "smart_home_control",
            "description": (
                "TP-Link Kasa akıllı ev cihazlarını (priz, ampul, çoklu priz) kontrol eder. "
                "'lambayı aç', 'televizyonu kapat', 'prizi toggle et', 'oturma odası ışığını %50 yap', "
                "'sıcak ışık aç', 'cihazları listele', 'ışık durumu' gibi komutlarda kullan. "
                "action=discover ile ağdaki tüm cihazları tarar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "device_name": {
                        "type": "string",
                        "description": "Cihaz alias adı (örn. 'salon lambası') veya IP adresi. action=discover için boş string."
                    },
                    "action": {
                        "type": "string",
                        "enum": ["on", "off", "toggle", "status", "discover"],
                        "description": "on=aç, off=kapat, toggle=tersine çevir, status=durum sorgula, discover=ağı tara"
                    },
                    "brightness": {
                        "type": "integer",
                        "description": "Parlaklık 0-100 (yalnızca akıllı ampul). Örn: 50 → %50",
                        "minimum": 0,
                        "maximum": 100
                    },
                    "color_temp": {
                        "type": "integer",
                        "description": "Renk sıcaklığı Kelvin (2500=sıcak sarı, 6500=soğuk beyaz). Ampul gerektirir.",
                        "minimum": 2500,
                        "maximum": 6500
                    },
                    "hue": {
                        "type": "integer",
                        "description": "Ton 0-360 (RGB ampul). saturation ile birlikte kullan.",
                        "minimum": 0,
                        "maximum": 360
                    },
                    "saturation": {
                        "type": "integer",
                        "description": "Doygunluk 0-100 (RGB ampul). hue ile birlikte kullan.",
                        "minimum": 0,
                        "maximum": 100
                    }
                },
                "required": ["device_name", "action"]
            }
        }
    },
    # ── Faz ζ — Görüntü Okuma Araçları ──────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "ocr_image",
            "description": (
                "Görüntü dosyasındaki yazıyı OCR ile okur ve metni döndürür. "
                "'bu fotoğraftaki yazıyı oku', 'ekran görüntüsündeki metni çıkar', "
                "'belgedeki yazılar neler' gibi komutlarda kullan. "
                "Kullanıcı sohbete görsel yükleyip 'bunu oku' dediyse path'i BOŞ "
                "bırak — en son yüklenen görsel okunur."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Görüntü dosyasının yolu (PNG/JPG/BMP/TIFF, ~ desteklenir) "
                            "ya da sohbete yüklenen dosyanın adı. BOŞ bırakılırsa en son "
                            "yüklenen görsel okunur — kullanıcı 'bunu/şunu oku' dediğinde "
                            "yol uydurma, boş bırak."
                        )
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_qr",
            "description": (
                "Görüntü dosyasındaki QR kodu veya barkodu okur ve içeriğini döndürür. "
                "'bu QR kodu oku', 'barkodun içeriği ne', 'karekoddaki URL nedir' gibi komutlarda kullan. "
                "Kullanıcı karekod fotoğrafını sohbete yüklediyse path'i BOŞ bırak."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "QR/barkod içeren görüntünün yolu (~ desteklenir) ya da sohbete "
                            "yüklenen dosyanın adı. BOŞ bırakılırsa en son yüklenen görsel okunur."
                        )
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": (
                "Yapay zeka ile görüntü / resim üretir. "
                "'bana bir kedi resmi çiz', 'Yuki'yi çiz', 'şu manzarayı görselleştir', "
                "'... hakkında görüntü oluştur' gibi isteklerde kullan. "
                "Görüntü chat ekranında otomatik görünür."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Görüntü açıklaması. Detaylı ve açıklayıcı olursa sonuç daha iyi olur."
                    },
                    "size": {
                        "type": "string",
                        "enum": ["1024x1024", "1792x1024", "1024x1792"],
                        "description": "Görüntü boyutu. Varsayılan: 1024x1024 (kare). 1792x1024=yatay, 1024x1792=dikey."
                    }
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "research_stock",
            "description": (
                "Hisse senedi veya kripto para için kapsamlı finansal araştırma raporu üretir. "
                "Fiyat verisi, son haberler, sosyal duyarlılık ve analist tahminlerini bir araya getirir. "
                "'AAPL'i araştır', 'Tesla analiz et', 'BTC hakkında ne düşünüyorlar', "
                "'Ethereum almak mantıklı mı', 'SOL analiz' gibi isteklerde kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Sembol veya isim. Örnekler: AAPL, TSLA, NVDA, BTC, ETH, SOL, bitcoin"
                    },
                    "lang": {
                        "type": "string",
                        "enum": ["tr", "en"],
                        "description": "Rapor dili. Varsayılan: tr"
                    }
                },
                "required": ["ticker"]
            }
        }
    },
    # ── Todo Araçları ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "create_todo",
            "description": (
                "Yeni yapılacaklar görevi oluşturur. "
                "'Yarın toplantı ekle', 'Alışveriş listesine süt ekle', "
                "'Saat 3'te randevu hatırlat', 'İş listesine yüksek öncelikli görev ekle' "
                "gibi isteklerde kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Görev başlığı"},
                    "list_name": {
                        "type": "string",
                        "description": "Liste adı, örn: 'gelen kutusu', 'alışveriş', 'iş'. Varsayılan: 'gelen kutusu'",
                        "default": "gelen kutusu",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Bitiş tarihi YYYY-MM-DD formatında, örn: '2026-05-25'. Opsiyonel."
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "mid", "low"],
                        "description": "Öncelik: 'high' (yüksek), 'mid' (orta), 'low' (düşük). Varsayılan: 'mid'",
                        "default": "mid",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Ek notlar. Opsiyonel."
                    },
                    "reminder_at": {
                        "type": "string",
                        "description": "Hatırlatma zamanı ISO 8601, örn: '2026-05-25T15:00:00'. Opsiyonel."
                    },
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_todo",
            "description": (
                "Bir görevi tamamlandı olarak işaretler. "
                "'Görevi tamamla', 'Bitti olarak işaretle' gibi isteklerde kullan. "
                "Önce search_todos ile görevi bul, sonra id ile tamamla."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Görev UUID'si"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_todos",
            "description": (
                "Görevleri listeler. "
                "'Bugün ne yapacağım', 'Haftalık görevlerim', 'Gecikmiş görevler', "
                "'Tüm görevleri göster' gibi isteklerde kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "enum": ["today", "week", "overdue", "all"],
                        "description": "'today'=bugün, 'week'=bu hafta, 'overdue'=gecikmiş, 'all'=tümü. Varsayılan: 'today'",
                        "default": "today",
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_todos",
            "description": (
                "Görevlerde arama yapar. "
                "'Toplantı görevini bul', 'Süt görevi nerede', "
                "bir görevi silmek/güncellemek/tamamlamak için önce bunu kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Arama metni"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_todo",
            "description": (
                "Bir görevi kalıcı olarak siler. "
                "'Doktor randevusunu sil', 'Alışveriş görevini kaldır' gibi isteklerde kullan. "
                "Önce search_todos ile görevi bul, sonra id ile sil."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Görev UUID'si (search_todos ile al)"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_todo",
            "description": (
                "Bir görevi günceller: başlık, öncelik, tarih, notlar veya durum değiştirilir. "
                "'Toplantının önceliğini yüksek yap', 'Randevuyu yarına al', "
                "'Görevi devam ediyor yap', 'Başlığı değiştir' gibi isteklerde kullan. "
                "Önce search_todos ile id'yi bul."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Görev UUID'si"},
                    "title": {"type": "string", "description": "Yeni başlık (opsiyonel)"},
                    "priority": {
                        "type": "string",
                        "enum": ["high", "mid", "low"],
                        "description": "Yeni öncelik (opsiyonel)"
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Yeni bitiş tarihi YYYY-MM-DD, temizlemek için '' (opsiyonel)"
                    },
                    "notes": {"type": "string", "description": "Yeni notlar (opsiyonel)"},
                    "reminder_at": {
                        "type": "string",
                        "description": "Yeni hatırlatma ISO 8601, temizlemek için '' (opsiyonel)"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["todo", "in_progress", "blocked", "done"],
                        "description": "'todo', 'in_progress', 'blocked' veya 'done' (opsiyonel)"
                    },
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_todo_lists",
            "description": (
                "Tüm görev listelerini gösterir (liste adları, aktif/tamamlanan görev sayıları). "
                "'Listelerimi göster', 'Hangi listelerim var', "
                "'Kaç listem var' gibi isteklerde kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_budget_summary",
            "description": (
                "Belirli bir ay için bütçe özetini getirir: toplam gelir, gider, bakiye ve en çok harcanan kategoriler. "
                "'Bu ay ne kadar harcadım', 'Bütçem nasıl', 'Ocakta ne kadar gelir elde ettim', "
                "'Mayıs ayı harcamaları neler', 'Bakiyem ne kadar' gibi sorularda kullan. "
                "month parametresi verilmezse bu ay kullanılır."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {
                        "type": "string",
                        "description": "Ay YYYY-MM formatında (örn: '2026-05'). Belirtilmezse bu ay kullanılır."
                    }
                },
                "required": []
            }
        }
    },
    # ── Kamera görüşü (GORUS, varsayılan kapalı; araç kendi bayrak + rıza kapısını da taşır) ──
    {
        "type": "function",
        "function": {
            "name": "kameraya_bak",
            "description": _gorus_tools.TANIM["description"],
            "parameters": {**_gorus_tools.TANIM["input_schema"], "required": []},
        }
    },
    # ── Fitness Araçları ──────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_fitness_summary",
            "description": (
                "Belirli gün için beslenme + antrenman özetini getirir. "
                "'Bugün ne kadar kalori aldım', 'Fitness özeti', 'Antrenman durumum', "
                "'Makrolarım nasıl', 'Fitness takibim' gibi sorularda kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD formatı. Belirtilmezse bugün kullanılır."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_meal",
            "description": (
                "Beslenme kaydı ekler. "
                "'Kahvaltıya yumurta ekle', '300 kalori tavuk göğsü yedim', "
                "'Öğün ekle', 'Kalori kaydet' gibi isteklerde kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Besin adı"},
                    "cal": {"type": "number", "description": "Kalori (kcal)"},
                    "meal": {
                        "type": "string",
                        "enum": ["kahvalti", "ogle", "aksam", "ara"],
                        "description": "Öğün tipi",
                        "default": "ara",
                    },
                    "protein": {"type": "number", "description": "Protein (g)", "default": 0},
                    "carb": {"type": "number", "description": "Karbonhidrat (g)", "default": 0},
                    "fat": {"type": "number", "description": "Yağ (g)", "default": 0},
                    "entry_date": {"type": "string", "description": "YYYY-MM-DD (opsiyonel)"},
                },
                "required": ["name", "cal"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_meals",
            "description": (
                "Belirli gün için öğün listesini döndürür. "
                "'Bugün ne yedim', 'Öğünlerimi listele' gibi sorularda kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_date": {"type": "string", "description": "YYYY-MM-DD (opsiyonel)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_meal",
            "description": "Öğün kaydını siler. Önce list_meals ile id bul.",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_id": {"type": "string", "description": "Öğün UUID'si"}
                },
                "required": ["meal_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_workout_exercise",
            "description": (
                "Antrenman seansına egzersiz ekler. "
                "'Bench press 4x10 80kg yaptım', 'Squat egzersizi ekle', "
                "'Antrenman kaydet' gibi isteklerde kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Egzersiz adı"},
                    "sets": {"type": "integer", "description": "Set sayısı", "default": 3},
                    "reps": {"type": "integer", "description": "Tekrar sayısı", "default": 10},
                    "weight": {"type": "number", "description": "Ağırlık kg (0=vücut)", "default": 0},
                    "session_date": {"type": "string", "description": "YYYY-MM-DD (opsiyonel)"},
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_workout",
            "description": (
                "Belirli gün antrenman seansını listeler. "
                "'Bugün ne antrenman yaptım', 'Antrenmanım neydi' gibi sorularda kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_date": {"type": "string", "description": "YYYY-MM-DD (opsiyonel)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fitness_config",
            "description": "Mevcut beslenme hedeflerini döndürür (kalori, protein, karb, yağ hedefleri).",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_fitness_config",
            "description": (
                "Beslenme hedeflerini günceller. "
                "'Kalori hedefimi 2500 yap', 'Protein hedefim 180g olsun' gibi isteklerde kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cal_goal":     {"type": "integer", "description": "Günlük kalori hedefi"},
                    "protein_goal": {"type": "integer", "description": "Protein hedefi (g)"},
                    "carb_goal":    {"type": "integer", "description": "Karbonhidrat hedefi (g)"},
                    "fat_goal":     {"type": "integer", "description": "Yağ hedefi (g)"},
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_fitness_templates",
            "description": "Kayıtlı antrenman şablonlarını listeler.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_fitness_template",
            "description": (
                "Antrenman şablonu kaydeder. "
                "'Bu antrenmanı şablon olarak kaydet', 'Push day şablonu oluştur' gibi isteklerde kullan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Şablon adı"},
                    "exercises": {
                        "type": "string",
                        "description": "JSON string: [{\"name\":\"Bench Press\",\"sets\":[{\"reps\":10,\"weight\":80}]}]"
                    },
                },
                "required": ["name", "exercises"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_fitness_template",
            "description": "Antrenman şablonunu siler. Önce list_fitness_templates ile id bul.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {"type": "string", "description": "Şablon UUID'si"}
                },
                "required": ["template_id"]
            }
        }
    },
    # ── Araç şeması alan seçici yedek yolu ───────────────────────────────
    # Şema tur başına daraltılıyor (alan_secici). Sunucunun alan tahmini
    # tutmazsa model eksik alanı burada açar; aynı turun içinde çalışır.
    {
        "type": "function",
        "function": {
            "name": "arac_alani_ac",
            "description": (
                "Bir işi yapmak için gereken aracı şu an görmüyorsan ilgili ALANI aç, "
                "sonra o alanın aracını çağır. Alanlar: takvim, todo, fitness, dosya, "
                "sistem, uygulama, medya, web, wiki, harita, hafiza, kripto, not, panel, otomasyon, "
                "gorsel, cevre, bildirim, konu_takibi, git, dil."
            ),
            "parameters": {
                "type": "object",
                "properties": {"alan": {"type": "string", "description": "Açılacak alan adı"}},
                "required": ["alan"],
            },
        }
    },
]


async def call_tool(name: str, args: dict[str, Any]) -> str:
    """Araç dispatcher + onay kapısı + beceri-kartı kancası."""
    if not _is_tool_allowed(name):
        return f"'{name}' aracı bu pakette kapalı."
    from app.config import TOOL_APPROVAL_ENABLED
    from app.services.tools.approval_gate import (
        ALWAYS_APPROVE, CRITICAL_TOOLS, request_approval, son_red_nedeni,
    )
    # ALWAYS_APPROVE ayardan BAĞIMSIZ onay ister — kullanıcı onay sistemini kapatsa
    # bile. Geri alınamaz işler için son emniyet kemeri.
    if name in ALWAYS_APPROVE or (TOOL_APPROVAL_ENABLED and name in CRITICAL_TOOLS):
        sunum = None
        if name == "delete_calendar_event":
            from app.services.tools.calendar import silme_sunumu
            sunum = await silme_sunumu(args)
        approved = await request_approval(name, args, sunum)
        if not approved:
            # i18n-istisna: LLM'e giden araç sonucu
            neden = son_red_nedeni()
            if neden == "kullanici":
                return (f"[ONAY REDDEDİLDİ] Kullanıcı '{name}' işlemini reddetti; işlem yapılmadı. "
                        "Reddedildiğini söyle: 'onay bekliyor' diye anlatma, aynı işlemi yeniden deneme.")
            if neden == "sure":
                return (f"[ONAY REDDEDİLDİ] '{name}' için onay süresi doldu, kimse cevaplamadı; işlem "
                        "yapılmadı. Kullanıcı reddetmedi: süresi dolduğunu söyle, isterse yeniden denersin.")
            return f"[ONAY REDDEDİLDİ] '{name}' aracı kullanıcı tarafından onaylanmadı veya süre doldu."

    res = await _call_tool_impl(name, args)
    try:
        from app.services.skill_events import note_tool_use
        await note_tool_use(name, res)
    except Exception:
        pass
    return res


async def _call_tool_impl(name: str, args: dict[str, Any]) -> str:
    """Araç çağrısı dispatcher. Blocking fonksiyonlar thread pool'a taşınır."""
    try:
        from app.api.intel import log_event
        log_event("tool", name)
    except Exception:
        pass
    if name == "arac_alani_ac":
        from app.services.tools.alan_secici import ALANLAR, alan_ac
        alan = str(args.get("alan", "")).strip()
        if alan not in ALANLAR:
            # Uydurulan alan adı sessizce "0 araç" dönmesin — geçerli listeyi söyle.
            return (f"'{alan}' diye bir alan yok. Geçerli alanlar: "
                    + ", ".join(sorted(ALANLAR)))
        n = alan_ac(alan, TOOLS)
        if n == 0:
            return (f"'{alan}' alanının araçları zaten açık — şemada görünüyorlar, "
                    "doğrudan çağırabilirsin.")
        return f"'{alan}' alanı açıldı: {n} araç eklendi. Şimdi gereken aracı çağır."
    elif name == "take_screenshot":
        return await asyncio.to_thread(take_screenshot)
    elif name == "send_screenshot_to_chat":
        return await send_screenshot_to_chat()
    elif name == "list_directory":
        return await asyncio.to_thread(list_directory, args["path"])
    elif name == "read_file":
        return await asyncio.to_thread(read_file, args["path"])
    elif name == "write_file":
        return await asyncio.to_thread(write_file, args["path"], args["content"])
    elif name == "append_file":
        return await asyncio.to_thread(append_file, args["path"], args["content"])
    elif name == "get_system_info":
        return await asyncio.to_thread(get_system_info)
    elif name == "monitor_system":
        return await asyncio.to_thread(monitor_system)
    elif name == "browse_web":
        return await browse_web(args["url"], args.get("task", ""))
    elif name == "web_search":
        return await web_search(args["query"])
    elif name == "send_notification":
        return await asyncio.to_thread(send_notification, args["title"], args.get("body", ""), args.get("urgency", "normal"))
    elif name == "get_clipboard":
        return await asyncio.to_thread(get_clipboard)
    elif name == "set_clipboard":
        return await asyncio.to_thread(set_clipboard, args["text"])
    elif name == "memory_search":
        return await memory_search(args["query"], args.get("limit", 5))
    elif name == "set_reminder":
        return await asyncio.to_thread(set_reminder, args["message"], args["when"], args.get("repeat", False))
    elif name == "list_reminders":
        return await asyncio.to_thread(_list_reminders)
    elif name == "cancel_reminder":
        return await asyncio.to_thread(_cancel_reminder, args["job_id"])
    elif name == "create_note":
        return await asyncio.to_thread(create_note, args["content"], args.get("title", ""))
    elif name == "list_notes":
        return await asyncio.to_thread(list_notes)
    elif name == "get_note":
        return await asyncio.to_thread(get_note, args["note_id"])
    elif name == "delete_note":
        return await asyncio.to_thread(delete_note, args["note_id"])
    elif name == "restore_note":
        return await asyncio.to_thread(restore_note, args["note_id"])
    elif name == "control_media":
        return await asyncio.to_thread(control_media, args["action"])
    elif name == "masaustu_yuki":   # anahtarla aynı yol (services/masaustu_yuki.ayarla)
        from app.services import masaustu_yuki as _masaustu
        return await asyncio.to_thread(_masaustu.arac, args.get("islem", "durum"))
    elif name == "open_application":
        return await asyncio.to_thread(open_application, args["app_name"], args.get("url", ""))
    elif name == "start_mode":
        return await start_mode(args["mode_id"])
    elif name == "list_modes":
        return await asyncio.to_thread(list_modes)
    elif name == "launch_game":
        return await asyncio.to_thread(launch_game, args["game_name"])
    elif name == "update_game":
        return await asyncio.to_thread(update_game, args["game_name"])
    elif name == "close_game":
        return await asyncio.to_thread(close_game, args["game_name"])
    elif name == "youtube_music":
        return await asyncio.to_thread(youtube_music, args["action"], args.get("value", ""))
    elif name == "set_language":
        from app.config import set_language as _set_language, get_lang_config, dil_durumu
        if _set_language(args["language"]):
            cfg = get_lang_config()
            try:
                from app.services.event_bus import bus
                # Yalnız KONUŞMA dili değişti; olay iki ekseni birlikte taşır ki ekran
                # arayüzü konuşma diline çevirmesin (2026-10-04). Eskiden ham argüman
                # ("japonca") yayınlanıyordu — kod değil, takma ad.
                await bus.publish("language_changed", dil_durumu())
            except Exception:
                pass
            # Sonraki yanıt yeni dilde üretilsin diye net talimat döndür
            return (
                f"Dil '{cfg['name']}' olarak ayarlandı. "
                f"Bundan sonra MUTLAKA {cfg['name']} dilinde yanıt ver. "
                f"Bu yanıtını da {cfg['name']} dilinde, kısa bir onayla ver."
            )
        # Seçenekler kaynaktan listelenir — sabit metin yeni dilde yalan söylerdi.
        return f"Geçersiz dil: '{args['language']}'. Seçenekler: {_DIL_ACIKLAMA()}."
    elif name == "analyze_image":
        return await analyze_image(args["path"], args.get("prompt", ""))
    elif name == "memory_stats":
        return await memory_stats()
    elif name == "memory_reflect":
        return await memory_reflect()
    elif name == "wiki_search":
        return await asyncio.to_thread(wiki_search, args["query"], args.get("max_results", 6))
    elif name == "wiki_read":
        return await asyncio.to_thread(wiki_read, args["path"])
    elif name == "wiki_index":
        return await asyncio.to_thread(wiki_index)
    elif name == "wiki_write":
        return await asyncio.to_thread(wiki_write, args["path"], args["content"], args.get("append", False))
    elif name == "skill_list":
        return await asyncio.to_thread(skill_list)
    elif name == "skill_run":
        return await asyncio.to_thread(skill_run, args["name"], args.get("arguments", ""))
    elif name == "monitor_process":
        return await asyncio.to_thread(monitor_process, args["name_or_pid"])
    elif name == "search_file":
        return await asyncio.to_thread(search_file, args["query"], args.get("path", "~"))
    elif name == "compress_file":
        return await asyncio.to_thread(compress_file, args["path"], args.get("output", ""))
    elif name == "extract_archive":
        return await asyncio.to_thread(extract_archive, args["path"], args.get("dest", ""))
    elif name == "diff_files":
        return await asyncio.to_thread(diff_files, args["path1"], args["path2"])
    elif name == "ping_host":
        return await asyncio.to_thread(ping_host, args["host"])
    elif name == "get_public_ip":
        return await get_public_ip()
    elif name == "check_service":
        return await asyncio.to_thread(check_service, args["name"])
    elif name == "list_packages":
        return await asyncio.to_thread(list_packages, args.get("filter_str", ""))
    elif name == "check_updates":
        return await asyncio.to_thread(check_updates)
    elif name == "read_journal":
        return await asyncio.to_thread(read_journal, args.get("unit", ""), args.get("lines", 50))
    elif name == "get_current_datetime":
        return await asyncio.to_thread(get_current_datetime)
    elif name == "get_calendar_events":
        return await get_calendar_events(args.get("max_results", 10), args.get("calendar_id", "primary"), args.get("time_min"))
    elif name == "create_calendar_event":
        return await create_calendar_event(args["summary"], args["start"], args["end"], args.get("description", ""), args.get("calendar_id", "primary"))
    elif name == "delete_calendar_event":
        return await delete_calendar_event(args["event_id"], args.get("calendar_id", "primary"))
    elif name == "get_weather":
        return await get_weather(args.get("city", "Istanbul"))
    elif name == "get_earthquake_alerts":
        return await get_earthquake_alerts(
            args.get("min_magnitude", 4.0),
            args.get("limit", 5),
            args.get("region", "global"),
        )
    elif name == "get_exchange_rate":
        return await get_exchange_rate(args.get("base", "USD"), args.get("currencies", "TRY,EUR,GBP"))
    elif name == "get_crypto_price":
        return await get_crypto_price(args.get("coins", "bitcoin,ethereum"), args.get("currency", "usd"))
    elif name == "get_battery":
        return await asyncio.to_thread(get_battery)
    elif name == "git_status":
        return await asyncio.to_thread(git_status, args.get("path", "."))
    elif name == "git_log":
        return await asyncio.to_thread(git_log, args.get("path", "."), args.get("n", 10))
    # ── UAI Agents ────────────────────────────────────────────────────────────
    # ── Faz 22 — In-process Orkestrasyon (companion meclisi) ──────────────────
    elif name == "delegate_to_companion":
        from app.services.orchestrator import companion_delegate
        return await companion_delegate(args["persona"], args["subtask"])
    elif name == "run_team":
        from app.services.orchestrator import run_team
        return await run_team(args["goal"])
    # ── Faz δ — Akıllı Ev ────────────────────────────────────────────────────
    elif name == "smart_home_control":
        return await smart_home_control(
            args.get("device_name", ""),
            args.get("action", "status"),
            args.get("brightness"),
            args.get("color_temp"),
            args.get("hue"),
            args.get("saturation"),
        )
    # ── Faz ζ — Görüntü Okuma ────────────────────────────────────────────────
    elif name == "ocr_image":
        return await ocr_image(args.get("path", ""))
    elif name == "read_qr":
        return await read_qr(args.get("path", ""))
    elif name == "generate_image":
        return await generate_image(args.get("prompt", ""), args.get("size", "1024x1024"))
    # ── Finansal Araştırma ───────────────────────────────────────────────────
    elif name == "research_stock":
        return await research_stock(args["ticker"], args.get("lang", "tr"))
    # ── Todo Araçları ─────────────────────────────────────────────────────────
    elif name == "create_todo":
        return await create_todo(
            args["title"],
            args.get("list_name", "gelen kutusu"),
            args.get("due_date"),
            args.get("priority", "mid"),
            args.get("notes", ""),
            args.get("reminder_at"),
        )
    elif name == "complete_todo":
        return await complete_todo(args["task_id"])
    elif name == "list_todos":
        return await list_todos(args.get("filter", "today"))
    elif name == "search_todos":
        return await search_todos(args["query"])
    elif name == "delete_todo":
        return await delete_todo(args["task_id"])
    elif name == "update_todo":
        return await update_todo(
            args["task_id"],
            title=args.get("title"),
            priority=args.get("priority"),
            due_date=args.get("due_date"),
            notes=args.get("notes"),
            reminder_at=args.get("reminder_at"),
            status=args.get("status"),
        )
    elif name == "list_todo_lists":
        return await list_todo_lists()
    elif name == "get_budget_summary":
        return await get_budget_summary(args.get("month"))
    elif name == "kameraya_bak":
        return await _gorus_tools.kameraya_bak(str(args.get("soru") or ""))
    # ── Fitness Araçları ──────────────────────────────────────────────────────
    elif name == "get_fitness_summary":
        return await get_fitness_summary(args.get("target_date"))
    elif name == "log_meal":
        return await log_meal(
            args["name"], args["cal"],
            args.get("meal", "ara"),
            args.get("protein", 0), args.get("carb", 0), args.get("fat", 0),
            args.get("entry_date"),
        )
    elif name == "list_meals":
        return await list_meals(args.get("target_date"))
    elif name == "delete_meal":
        return await delete_meal(args["meal_id"])
    elif name == "log_workout_exercise":
        return await log_workout_exercise(
            args["name"],
            args.get("sets", 3), args.get("reps", 10), args.get("weight", 0),
            args.get("session_date"),
        )
    elif name == "list_workout":
        return await list_workout(args.get("session_date"))
    elif name == "get_fitness_config":
        return await get_fitness_config()
    elif name == "update_fitness_config":
        return await update_fitness_config(
            args.get("cal_goal"), args.get("protein_goal"),
            args.get("carb_goal"), args.get("fat_goal"),
        )
    elif name == "list_fitness_templates":
        return await list_fitness_templates()
    elif name == "save_fitness_template":
        return await save_fitness_template(args["name"], args["exercises"])
    elif name == "delete_fitness_template":
        return await delete_fitness_template(args["template_id"])
    elif name == "switch_tab":
        return await switch_tab(args["tab"])
    elif name == "list_tabs":
        return await list_tabs()
    elif name == "map_goto":
        from app.services.tools.harita import map_goto
        return await map_goto(args.get("yer", ""), args.get("lat"),
                              args.get("lon"), args.get("zoom"))
    elif name == "map_layer":
        from app.services.tools.harita import map_layer
        return await map_layer(args["katman"], args.get("ac", True))
    elif name == "map_status":
        from app.services.tools.harita import map_status
        return await map_status()
    elif name == "list_media":
        from app.services.tools.galeri import list_media
        return await list_media(args.get("ara", ""), args.get("tip"), args.get("limit", 20))
    elif name == "show_media":
        from app.services.tools.galeri import show_media
        return await show_media(args.get("hedef", ""))
    elif name == "switch_character":
        return await switch_character(args["character"])
    elif name == "list_characters":
        return await list_characters()
    # ── Faz 23 — n8n webhook ──────────────────────────────────────────────────
    elif name == "trigger_n8n":
        from app.services.mcp_client import trigger_n8n
        return await trigger_n8n(args["workflow"], args.get("payload"))
    # ── Faz 25 — Rutinler (tekrarlı cron + aksiyon, restart-güvenli) ──────────
    elif name == "create_routine":
        from app.services.routines import create_routine
        return create_routine(args["name"], args["schedule"], args["action_type"], args["action"])
    elif name == "list_routines":
        from app.services.routines import list_routines
        return list_routines()
    elif name == "delete_routine":
        from app.services.routines import delete_routine
        return delete_routine(args["routine_id"])
    # ── Faz 24 — Skill (bileşik) araçları (skill__<ad>) ───────────────────────
    if name.startswith("skill__"):
        from app.services.skill_registry import run_skill
        return await run_skill(name, args)
    # ── Faz 23 — MCP dinamik araçları (mcp__<sunucu>__<araç>) ─────────────────
    if name.startswith("mcp__"):
        from app.services.mcp_client import get_manager
        return await get_manager().call(name, args)
    return "Hata: Geçersiz araç."


def register_tools(schemas: list) -> None:
    """Dinamik araç şemalarını TOOLS'a ekler (idempotent, isim çakışması atlanır). MCP + skill kaydı kullanır."""
    existing = {t["function"]["name"] for t in TOOLS}
    for s in schemas:
        nm = s.get("function", {}).get("name")
        if nm and nm not in existing:
            TOOLS.append(s)
            existing.add(nm)


# Geriye-uyumlu alias — mcp_client `register_mcp_tools` bekliyor
register_mcp_tools = register_tools


def _is_tool_allowed(name: str) -> bool:
    """Ürün paketi/lisans araç kilidi → entitlement otoritesi (runtime, lisansla değişir).

    Yetki kaynağı: YUKI_ENABLED_TOOLS/YUKI_PACKAGE env > imzalı lisans > Free.
    Entitlement başlatılmamışsa (import sırası) config.ENABLED_TOOLS'a düş (parite)."""
    try:
        from app.services import yetki
        return yetki.tool_allowed(name)
    except Exception:  # pragma: no cover — güvenli geri düşüş
        from app.config import ENABLED_TOOLS
        return (not ENABLED_TOOLS) or (name in ENABLED_TOOLS)


def _ekip_semasi(t: dict, ekip: list[str]) -> dict:
    """`delegate_to_companion` şemasının uzman listesini canlı PERSONAS'tan doldurur.

    Kopya döner — global `TOOLS` mutasyona uğramaz (persona eklenince/çıkınca
    bir sonraki çağrı doğru listeyi görür)."""
    if t["function"]["name"] != "delegate_to_companion":
        return t
    import copy
    from app.services.personas import get_persona_meta
    t = copy.deepcopy(t)
    fn = t["function"]
    fn["description"] = fn["description"].replace("{uzmanlar}", ", ".join(
        f"{k} ({get_persona_meta(k).get('title', k)})" for k in ekip))
    fn["parameters"]["properties"]["persona"]["enum"] = list(ekip)
    return t


def get_active_tools() -> list:
    """LLM'e sunulacak araç şemaları — mevcut pakete göre filtrelenmiş (ENABLED_TOOLS).

    Ekip araçları (`orchestrator.EKIP_ARACLARI`) yalnız Yuki dışında en az bir
    persona (uzman) varken sunulur — 2026-11-14'ten beri yoktur. Olmayan bir
    yeteneği modele vaat etmek, onu kullanıcıya vaat etmektir."""
    from app.services import orchestrator
    ekip = orchestrator.uzmanlar()
    return [
        _ekip_semasi(t, ekip) for t in TOOLS
        if _is_tool_allowed(t["function"]["name"])
        and (ekip or t["function"]["name"] not in orchestrator.EKIP_ARACLARI)
    ]


def GET_TOOLS_DEFINITION() -> str:
    """Returns a textual description of available tools for LLM prompts."""
    return str(get_active_tools())
