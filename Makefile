# Yuki — Makefile (README'deki komutların kısayolları)
# Kullanım: make <hedef>
#
# Denetim 2026-11-16: eski dosya başka bir kurulumdan kalmaydı (port 8000, var olmayan `start.sh --electron`,
# make'in /bin/sh'inde çalışmayan `source`, eski log yolu). Her hedef artık README'deki bir komutu çağırır.
# Bekçisi: backend/tests/test_makefile.py

ROOT_DIR    := $(CURDIR)
BACKEND_DIR := $(ROOT_DIR)/backend
PYTHON      := $(BACKEND_DIR)/venv/bin/python
YUKI_PORT   ?= 8001

.PHONY: help install start start-backend stop test db-up db-down web electron

help:
	@echo ""
	@echo "  Yuki — make hedefleri"
	@echo "  ─────────────────────────────────────────"
	@echo "  make install        Bağımlılıkları kur (backend venv + electron)"
	@echo "  make start          Backend + masaüstü uygulaması (./start.sh)"
	@echo "  make start-backend  Yalnız backend (./start.sh --no-ui)"
	@echo "  make stop           Durdur (./stop.sh)"
	@echo "  make test           Backend testleri"
	@echo "  make db-up          İsteğe bağlı Postgres (docker compose up -d postgres)"
	@echo "  make db-down        Postgres'i durdur"
	@echo "  make web            Arayüzü tarayıcıda aç (http://127.0.0.1:$(YUKI_PORT)/ui)"
	@echo "  make electron       Masaüstü kabuğunu aç (electron: npm start)"
	@echo ""

install:
	cd $(BACKEND_DIR) && python3 -m venv venv
	$(PYTHON) -m pip install -r $(BACKEND_DIR)/requirements.txt
	cd $(ROOT_DIR)/electron && npm install

start:
	./start.sh

start-backend:
	./start.sh --no-ui

stop:
	./stop.sh

test:
	cd $(BACKEND_DIR) && $(PYTHON) -m pytest -q

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

web:
	xdg-open http://127.0.0.1:$(YUKI_PORT)/ui

electron:
	cd $(ROOT_DIR)/electron && npm start
