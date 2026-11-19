# Third-party licenses

Yuki's own source code is MIT (see [`LICENSE`](LICENSE)). The Yuki character and
artwork are **not** MIT — see [`NOTICE`](NOTICE). This file lists the third-party
components that are bundled in this repository or downloaded at runtime.

## Bundled in this repository

### Fonts — SIL Open Font License 1.1

| Font | Files | Source |
|---|---|---|
| Inter | `frontend/fonts/UcC73Fwr…woff2` (`frontend/vendor/fonts.css`) | Google Fonts / rsms/inter |
| Outfit | `frontend/fonts/QGYvz_MV…woff2` (`frontend/vendor/fonts.css`) | Google Fonts |
| Space Mono | `frontend/fonts/i7d…woff2` (`frontend/vendor/fonts.css`) | Google Fonts |
| JetBrains Mono | `frontend/fonts/JetBrainsMono-*.woff2` (`frontend/vendor/fonts-mono.css`) | JetBrains |
| Chakra Petch | `frontend/assets/fonts/ChakraPetch-*.woff2` | Google Fonts / Cadson Demak |
| Fraunces | `frontend/assets/fonts/gozlemevi/fraunces-*.woff2` (`frontend/css/fontlar-gozlemevi.css`) | Google Fonts / Undercase Type — `OFL-fraunces.txt` |
| Figtree | `frontend/assets/fonts/gozlemevi/figtree-*.woff2` | Google Fonts / Erik Kennedy — `OFL-figtree.txt` |
| Martian Mono | `frontend/assets/fonts/gozlemevi/martian-mono-*.woff2` | Google Fonts / Evil Martians — `OFL-martian-mono.txt` |
| Noto Sans Runic / Symbols / Math (subsets) | `frontend/acilis-v4/ortak/font/{run,sem,mat}.ttf` | The Noto Project Authors / Google LLC — `OFL-noto.txt`, `KAYNAK.md` |

Full license text: https://openfontlicense.org/open-font-license-official-text/

### JavaScript libraries (`frontend/vendor/`)

| Library | Version | License |
|---|---|---|
| three.js | 0.160.0 | MIT |
| @pixiv/three-vrm | 3.1.6 | MIT |
| Leaflet | 1.9.4 | BSD-2-Clause |
| Leaflet.markercluster | 1.5.3 | MIT |
| MapLibre GL JS | 4.x | BSD-3-Clause |
| DOMPurify | 3.2.4 | Apache-2.0 OR MPL-2.0 |
| marked | 15.0.12 | MIT |
| Prism | 1.29.0 | MIT |
| SortableJS | 1.15.2 | MIT |
| mesh-avatar | — | MIT (see `frontend/vendor/mesh-avatar/LICENSE`) |

`frontend/vendor/qr-uret.js` is original code (MIT, part of this project).

## Installed by package managers (not in this repository)

- **Python** (`backend/requirements-product.txt`): FastAPI, Pydantic, faster-whisper,
  CTranslate2, onnxruntime, opencv-python-headless, anthropic, openai, google-genai and
  others. They are permissive (MIT / BSD / Apache-2.0 / MPL-2.0). `rapidocr` also pulls in
  `opencv-python` (Apache-2.0; its Linux wheel bundles Qt and FFmpeg libraries under LGPL). **edge-tts** is
  LGPL-3.0 and is used as an unmodified, separately installed library.
- **Node** (`electron/package.json`): Electron and electron-builder (MIT) plus their
  dependency tree (MIT / ISC / BSD / Apache-2.0; no GPL/AGPL packages at the time of the
  last audit). Electron ships Chromium and FFmpeg under their own licenses.

## Optional external services (you install them yourself)

- **Local TTS — Fish Speech** (`USE_FISH_TTS`, off by default). Yuki only talks to a
  Fish Speech server you run yourself, over HTTP; Fish code and weights are **not**
  bundled, downloaded or installed by Yuki. Fish Speech code is under the
  *Fish Audio Community License* (non-commercial / revenue-capped commercial use) and the
  S2-Pro weights under the *Fish Audio Research License* (no commercial use). If you
  enable it, those terms apply to you. Install from the official repository:
  https://github.com/fishaudio/fish-speech — Built with Fish Audio.

## Downloaded at runtime (only if you choose to)

- **Face login — InsightFace `buffalo_l` model.** The InsightFace *code* is MIT, but the
  pretrained `buffalo_l` model weights are released for **non-commercial research use
  only**. Yuki downloads them only when you enable face login. If you use Yuki
  commercially, do not enable face login, or replace the model with one you are licensed
  to use.
- **Speech-to-text — faster-whisper models** (MIT; OpenAI Whisper weights are MIT).
- **Semantic memory — ONNX embedding model**: an int8 ONNX export of
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (Apache-2.0), downloaded from
  the `v0.4.0-models` release of this repository (URLs in `electron/models-manifest.json`).
- **Cloud services you configure with your own keys** (OpenRouter, OpenAI, Anthropic,
  Google, ElevenLabs, Microsoft Edge TTS, …) are governed by those providers' terms.
