# Contributing to Yuki

Thanks for your interest! Yuki is a desktop AI companion: a FastAPI backend, a
vanilla-JS frontend and an Electron shell.

## Before you start

- Open an issue first for anything bigger than a small fix, so we can agree on the
  approach.
- **Scope.** Some things are intentionally *not* part of this project and PRs adding them
  will be declined: running shell commands or arbitrary programs, remote desktop control
  (mouse/keyboard), local voice cloning models with non-commercial licenses, and
  security/pentest tooling. `scripts/test_temizlik.py` enforces this.
- **Artwork.** The Yuki character, avatars, sprites, animations and icons are *not* MIT
  (see `NOTICE`). Do not submit derivatives of them; new artwork must come with a
  license that allows inclusion.

## Development setup

See the README (*Run from source*). Then:

```bash
cd backend && venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q                    # backend tests
cd ../electron && npm ci && npm test            # shell tests
python3 scripts/test_temizlik.py                # repo hygiene gates (needs gitleaks)
```

### Pre-commit hook

The hygiene gate and secret scan also run locally on staged changes before each commit
(`.pre-commit-config.yaml` → `scripts/pre-commit` + `scripts/test_profil_adi.py`):

```bash
pip install pre-commit && pre-commit install      # once per clone
pre-commit run --all-files                        # optional: run it now
# without the pre-commit tool:
ln -sf ../../scripts/pre-commit .git/hooks/pre-commit
```

The full-history scan still runs in CI (`.github/workflows/temizlik.yml`).

Some memory tests need the ONNX embedding model; `scripts/ci-yerel.sh` downloads it and
runs the same steps as CI in a clean copy.

## Pull requests

- One topic per PR; describe *what* and *why*, and how you tested it.
- Keep CI green: pytest, electron tests, gitleaks and the hygiene gates.
- **Never commit secrets** — API keys belong in the app's key settings / OS keyring, not
  in code or `.env` files in the repo.
- If you change a cached frontend file, bump its `?v=` stamp in `index.html`,
  `planner.html`, `mini.html` **and** the `sw.js` precache list (tests check they match).
- UI text lives in `frontend/js/diller/{tr,en,ja}.js` (frontend) and
  `backend/app/mesajlar/{tr,en}.py` (backend); add both Turkish and English.

## Security

Please do not open public issues for vulnerabilities — see `SECURITY.md`.

By contributing you agree that your code is released under the MIT License.
