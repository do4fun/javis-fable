# Makefile racine de Jarvis (F5.3). Orchestre frontend (/web) et serveur (/server).
# Sous Windows sans `make`, utilise start.ps1 / les commandes équivalentes.
.PHONY: help install build start check check-web check-server clean

PY ?= python

help:
	@echo "Cibles : install | build | start | check | clean"

# Installe les dépendances front + back.
install:
	cd web && npm install
	cd server && $(PY) -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt

# Build du frontend (bundle autonome dans web/dist).
build:
	cd web && npm run build

# Démarrage en un clic : vérifie les prérequis, build si besoin, lance le serveur.
start:
	$(PY) scripts/start.py

# Suite qualité locale : lint + tests des deux côtés.
check: check-web check-server

check-web:
	cd web && npm run lint && npm run test && npm run build

check-server:
	cd server && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m pytest -q

clean:
	rm -rf web/dist web/node_modules server/.venv server/data
