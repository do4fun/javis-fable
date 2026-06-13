"""Protocole WebSocket typé de Jarvis.

Toutes les trames échangées entre le navigateur et le serveur utilisent une
enveloppe JSON commune : ``{type, id, payload, ts}``.

- ``type``    : nom de l'événement (voir les énumérations ci-dessous) ;
- ``id``      : identifiant de corrélation (relie une réponse à sa requête) ;
- ``payload`` : charge utile spécifique au type (objet libre) ;
- ``ts``      : horodatage epoch en millisecondes (posé par l'émetteur).

Ce module ne contient que des définitions et des aides de (dé)sérialisation.
La logique métier vit dans les modules dédiés (stt, brain, tts, pipeline…).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field


# --- Types de messages -------------------------------------------------------
# On garde de simples constantes de chaînes (sérialisées telles quelles) plutôt
# qu'une Enum lourde, pour rester lisible côté JSON et côté JS.


class ClientMsg:
    """Messages client → serveur."""

    USER_TEXT = "user_text"      # texte saisi au clavier
    AUDIO_CHUNK = "audio_chunk"  # fragment PCM (F3.1)
    INTERRUPT = "interrupt"      # barge-in : couper la parole de l'avatar
    CONFIG = "config"            # réglages (voix, modèle, mode micro…)


class ServerMsg:
    """Messages serveur → client."""

    STATE = "state"          # idle | listening | thinking | speaking
    LLM_TOKEN = "llm_token"  # token de réponse en flux (F4.1)
    TTS_AUDIO = "tts_audio"  # audio synthétisé + timings (F2.1)
    VISEMES = "visemes"      # visèmes pour le lip-sync (F2.2)
    TRANSCRIPT = "transcript"  # transcription STT (F3.2)
    EMOTION = "emotion"      # déclenche une émotion d'avatar (F1.4)
    ERROR = "error"          # erreur lisible côté client


# Ensemble des types client acceptés en entrée (validation défensive).
KNOWN_CLIENT_TYPES = {
    ClientMsg.USER_TEXT,
    ClientMsg.AUDIO_CHUNK,
    ClientMsg.INTERRUPT,
    ClientMsg.CONFIG,
}


def now_ms() -> int:
    """Horodatage courant en millisecondes."""
    return int(time.time() * 1000)


class Envelope(BaseModel):
    """Enveloppe commune à toutes les trames JSON."""

    type: str
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: int = Field(default_factory=now_ms)

    @classmethod
    def make(cls, type: str, payload: dict[str, Any] | None = None,
             id: str | None = None) -> "Envelope":
        """Fabrique une enveloppe, en réutilisant un ``id`` de corrélation."""
        data: dict[str, Any] = {"type": type, "payload": payload or {}}
        if id is not None:
            data["id"] = id
        return cls(**data)

    def to_json(self) -> str:
        return self.model_dump_json()
