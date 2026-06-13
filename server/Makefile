# Raccourcis serveur Jarvis. Sous Windows sans `make`, utilise run.ps1.
.PHONY: venv install run dev test

PY ?= python

venv:
	$(PY) -m venv .venv

install:
	$(PY) -m pip install -r requirements.txt

# Lance le serveur (sert /web/dist + WebSocket /ws sur http://localhost:8000).
run:
	$(PY) -m uvicorn app:app --host 127.0.0.1 --port 8000

# Mode dev : rechargement à chaud.
dev:
	$(PY) -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload

test:
	$(PY) -m pytest -q
