"""Logs structurés (clé=valeur) pour Jarvis.

Format compact et lisible, horodaté, avec le nom du logger. Suffisant pour
tracer le pipeline (un ``trace_id`` par tour de parole sera ajouté en F5.1).

Les logs sont écrits simultanément sur la console et dans ``logs/server.log``
(à la racine du projet) via un ``RotatingFileHandler`` (5 Mo, 3 fichiers).
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Racine du projet : server/core/logging_setup.py → ../../
_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "server.log"
_FMT = logging.Formatter(
    "%(asctime)s %(levelname)-7s %(name)-16s %(message)s",
    datefmt="%H:%M:%S",
)


def setup_logging(level: int = logging.INFO) -> None:
    # Sur Windows, la console est souvent en cp1252 : on force l'UTF-8 pour
    # éviter les « Logging error » sur les caractères accentués / flèches.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_FMT)

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(_FMT)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)
    root.setLevel(level)

    # Uvicorn duplique sinon ses propres logs d'accès.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
