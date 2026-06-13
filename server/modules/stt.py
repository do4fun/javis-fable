"""Transcription vocale locale (F3.2).

Comprend la parole française sur la machine, via faster-whisper. Architecture
enfichable (comme le TTS) :

- ``WhisperEngine`` : faster-whisper, modèle ``small`` par défaut (ou ``base``
  selon le CPU/GPU), langue forcée ``fr``, poids stockés localement ;
- ``DummySTTEngine`` : moteur sans modèle (renvoie un texte vide ou fixé), pour
  les tests et le mode hors-modèle. **Toujours disponible.**

Le buffer audio entrant est du PCM int16 mono 16 kHz (cf. F3.1). On le convertit
en float32 [-1,1] pour Whisper. La sortie est normalisée (ponctuation, nombres,
suppression des hésitations).

Le téléchargement unique du modèle est documenté dans ``docs/install.md``.
"""

from __future__ import annotations

import logging
import re

import numpy as np

log = logging.getLogger("jarvis.stt")


# --- Normalisation -----------------------------------------------------------

# Hésitations courantes à retirer (mot entier, insensible à la casse).
_HESITATIONS = re.compile(
    r"\b(euh+|heu+|hum+|ben|bah|hein)\b[ ,]*", re.IGNORECASE | re.UNICODE
)
_MULTISPACE = re.compile(r"\s{2,}")


def normalize_transcript(text: str) -> str:
    """Nettoie une transcription : hésitations, espaces, capitale, ponctuation."""
    if not text:
        return ""
    text = _HESITATIONS.sub("", text)
    text = _MULTISPACE.sub(" ", text).strip()
    text = re.sub(r"\s+([,.!?])", r"\1", text)  # espace avant ponctuation
    if text:
        text = text[0].upper() + text[1:]
        # Ajoute un point final si la phrase n'a pas de ponctuation terminale.
        if text[-1] not in ".!?…":
            text += "."
    return text


def pcm16_to_float(pcm: bytes) -> np.ndarray:
    """Convertit un buffer PCM int16 little-endian en float32 [-1,1]."""
    if not pcm:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


# --- Moteurs -----------------------------------------------------------------


class STTEngine:
    name = "base"

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        raise NotImplementedError


class DummySTTEngine(STTEngine):
    """Moteur de repli sans modèle. Renvoie un texte configurable (tests)."""

    name = "dummy"

    def __init__(self, canned: str = "") -> None:
        self.canned = canned

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        return normalize_transcript(self.canned)


class WhisperEngine(STTEngine):
    """faster-whisper, langue française forcée, chargé au démarrage."""

    name = "whisper"

    def __init__(self, model_size: str = "small", device: str = "auto") -> None:
        from faster_whisper import WhisperModel  # import local : optionnel

        compute = "int8" if device in ("cpu", "auto") else "float16"
        self._model = WhisperModel(model_size, device=device, compute_type=compute)
        self.model_size = model_size

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        if audio.size == 0:
            return ""
        segments, _info = self._model.transcribe(
            audio,
            language="fr",
            beam_size=5,
            vad_filter=False,  # le VAD est déjà fait côté client (F3.1)
        )
        text = " ".join(seg.text.strip() for seg in segments)
        return normalize_transcript(text)


def make_stt_engine(cfg: dict | None = None) -> STTEngine:
    """Fabrique le moteur STT avec repli automatique sur Dummy."""
    cfg = cfg or {}
    try:
        return WhisperEngine(
            model_size=cfg.get("model", "small"),
            device=cfg.get("device", "auto"),
        )
    except Exception as e:  # pragma: no cover - dépend de l'install locale
        log.warning("faster-whisper indisponible (%s) → STT dummy.", e)
        return DummySTTEngine()


# --- Service -----------------------------------------------------------------


class STTService:
    """Transcrit des segments de parole (PCM int16 16 kHz)."""

    def __init__(self, engine: STTEngine | None = None) -> None:
        self.engine = engine or DummySTTEngine()

    async def transcribe_segment(self, pcm: bytes, sample_rate: int = 16000) -> str:
        import asyncio

        audio = pcm16_to_float(pcm)
        # Whisper attend du 16 kHz ; si autre, on laisse Whisper rééchantillonner
        # (faster-whisper accepte un ndarray ; on suppose 16 kHz côté client).
        return await asyncio.to_thread(self.engine.transcribe, audio, sample_rate)
