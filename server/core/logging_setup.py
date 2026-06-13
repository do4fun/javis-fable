"""Logs structurés (clé=valeur) pour Jarvis.

Format compact et lisible, horodaté, avec le nom du logger. Suffisant pour
tracer le pipeline (un ``trace_id`` par tour de parole sera ajouté en F5.1).
"""

from __future__ import annotations

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    # Sur Windows, la console est souvent en cp1252 : on force l'UTF-8 pour
    # éviter les « Logging error » sur les caractères accentués / flèches.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)-16s %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn duplique sinon ses propres logs d'accès.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
