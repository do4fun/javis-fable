"""Mémoire de conversation locale (F4.2).

Persistance SQLite dans ``server/data/memory.sqlite`` (créé au premier
lancement, ignoré par git). Stocke :
- l'historique des tours de parole (glissant, résumé au-delà du contexte) ;
- un profil utilisateur léger (prénom, préférences déclarées) ;
- un résumé automatique de la conversation ancienne.

Tout est en clair, en local. La commande « oublie tout » purge la base.
Accès synchrone (SQLite) ; les appelants asynchrones l'enveloppent dans
``asyncio.to_thread``.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "memory.sqlite"


class Memory:
    def __init__(self, path: Path | str = DEFAULT_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS profile (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self._db.commit()

    # --- Historique ---------------------------------------------------------

    def add_turn(self, role: str, content: str) -> None:
        self._db.execute(
            "INSERT INTO turns (role, content, ts) VALUES (?, ?, ?)",
            (role, content, time.time()),
        )
        self._db.commit()

    def recent_turns(self, n: int = 12) -> list[dict]:
        """Les ``n`` derniers tours, ordre chronologique."""
        rows = self._db.execute(
            "SELECT role, content FROM turns ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def count_turns(self) -> int:
        return self._db.execute("SELECT COUNT(*) AS c FROM turns").fetchone()["c"]

    def turns_before(self, keep_last: int) -> list[dict]:
        """Tours plus anciens que les ``keep_last`` derniers (à résumer)."""
        total = self.count_turns()
        if total <= keep_last:
            return []
        rows = self._db.execute(
            "SELECT role, content FROM turns ORDER BY id ASC LIMIT ?",
            (total - keep_last,),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def prune_to(self, keep_last: int) -> None:
        """Supprime les tours au-delà des ``keep_last`` derniers."""
        self._db.execute(
            """
            DELETE FROM turns WHERE id NOT IN (
                SELECT id FROM turns ORDER BY id DESC LIMIT ?
            )
            """,
            (keep_last,),
        )
        self._db.commit()

    # --- Profil utilisateur -------------------------------------------------

    def set_profile(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO profile (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._db.commit()

    def get_profile(self) -> dict[str, str]:
        rows = self._db.execute("SELECT key, value FROM profile").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # --- Résumé -------------------------------------------------------------

    def set_summary(self, text: str) -> None:
        self.set_meta("summary", text)

    def get_summary(self) -> str:
        return self.get_meta("summary", "")

    def set_meta(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._db.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        row = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    # --- Purge --------------------------------------------------------------

    def purge_all(self) -> None:
        """Efface tout : historique, profil, résumé (« oublie tout »)."""
        self._db.executescript(
            "DELETE FROM turns; DELETE FROM profile; DELETE FROM meta;"
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()
