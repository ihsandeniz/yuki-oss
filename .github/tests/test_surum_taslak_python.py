"""surum-taslak linux işi: test_install_betigi.py'den önce Python 3.12 kurulmalı."""
import sys, pathlib, yaml
YOL = pathlib.Path(__file__).resolve().parents[1] / "workflows" / "surum-taslak.yml"

def kontrol(metin):
    adimlar = yaml.safe_load(metin)["jobs"]["linux"]["steps"]
    hedef = next((i for i, a in enumerate(adimlar) if "test_install_betigi.py" in str(a.get("run", ""))), None)
    if hedef is None:
        return "test_install_betigi adımı yok"
    for a in adimlar[:hedef]:
        if str(a.get("uses", "")).startswith("actions/setup-python@"):
            v = str((a.get("with") or {}).get("python-version", ""))
            parca = v.split(".")
            if len(parca) >= 2 and parca[0] == "3" and parca[1].isdigit() and int(parca[1]) >= 12:
                return None
            return f"setup-python sürümü yetersiz: {v!r}"
    return "test_install_betigi'den önce setup-python yok"

if __name__ == "__main__":
    hata = kontrol((sys.argv[1] and open(sys.argv[1]).read()) if len(sys.argv) > 1 else YOL.read_text())
    print("GEÇTİ" if hata is None else f"KALDI: {hata}")
    sys.exit(0 if hata is None else 1)
