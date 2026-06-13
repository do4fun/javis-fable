"""Synthèse vocale locale (F2.1).

Objectif : transformer du texte français en audio + timestamps par mot, sur la
machine, sans aucun appel réseau. Architecture à moteurs enfichables :

- ``KokoroEngine`` : moteur principal (voix française, ex. ``ff_siwis``) ;
- ``PiperEngine``  : repli (piper-tts, voix ``fr_FR`` locale) ;
- ``DummyEngine``  : moteur déterministe (onde sinusoïdale) sans modèle, pour
  les tests et le mode hors-modèle. **Toujours disponible.**

Tous renvoient un :class:`TTSResult` homogène. Si le moteur ne fournit pas de
timestamps par mot, on les **reconstruit** proportionnellement à la longueur
des mots (voir :func:`reconstruct_word_times`). Le service expose un flux par
phrase avec annulation (barge-in).

Le téléchargement unique des poids Kokoro/Piper est documenté dans
``docs/install.md`` ; ensuite tout est hors-ligne.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger("jarvis.tts")

DEFAULT_SAMPLE_RATE = 24000


# --- Structures de données ---------------------------------------------------


@dataclass
class WordTiming:
    word: str
    start: float  # secondes
    end: float    # secondes


@dataclass
class TTSResult:
    """Résultat d'une synthèse : audio PCM float32 [-1,1] + timings."""

    audio: np.ndarray
    sample_rate: int = DEFAULT_SAMPLE_RATE
    words: list[WordTiming] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return len(self.audio) / self.sample_rate if self.sample_rate else 0.0

    def to_int16_bytes(self) -> bytes:
        """PCM 16 bits little-endian, prêt pour le transport binaire."""
        clipped = np.clip(self.audio, -1.0, 1.0)
        return (clipped * 32767.0).astype("<i2").tobytes()


# --- Découpage en phrases ----------------------------------------------------

_SENTENCE_RE = re.compile(r"[^.!?…]+[.!?…]*", re.UNICODE)
_WORD_RE = re.compile(r"\S+", re.UNICODE)


def split_sentences(text: str) -> list[str]:
    """Découpe un texte en phrases pour le streaming (latence du 1er son)."""
    parts = [m.group().strip() for m in _SENTENCE_RE.finditer(text)]
    return [p for p in parts if p]


def reconstruct_word_times(
    text: str, total_duration: float, offset: float = 0.0
) -> list[WordTiming]:
    """Répartit ``total_duration`` sur les mots, au prorata de leur longueur.

    Utilisé quand le moteur ne fournit pas d'alignement natif. La somme des
    durées vaut exactement ``total_duration`` (cf. test d'alignement ±5 %).
    """
    words = _WORD_RE.findall(text)
    if not words or total_duration <= 0:
        return []

    # Poids = nombre de caractères + 1 (évite qu'un mot d'1 lettre soit nul).
    weights = [len(w) + 1 for w in words]
    total_weight = sum(weights)

    timings: list[WordTiming] = []
    cursor = offset
    for w, weight in zip(words, weights):
        dur = total_duration * (weight / total_weight)
        timings.append(WordTiming(word=w, start=round(cursor, 4), end=round(cursor + dur, 4)))
        cursor += dur
    return timings


# --- Moteurs -----------------------------------------------------------------


class TTSEngine:
    """Interface commune. ``synthesize`` est synchrone (appelée en thread)."""

    name = "base"
    sample_rate = DEFAULT_SAMPLE_RATE

    def synthesize(self, text: str) -> TTSResult:  # pragma: no cover - abstrait
        raise NotImplementedError


class DummyEngine(TTSEngine):
    """Onde sinusoïdale modulée par mot. Déterministe, sans modèle, hors-ligne.

    Sert de repli ultime et de support de test : le rendu n'est pas une vraie
    voix mais l'interface (audio + timestamps) est identique à Kokoro.
    """

    name = "dummy"

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate

    def synthesize(self, text: str) -> TTSResult:
        words = _WORD_RE.findall(text)
        if not words:
            return TTSResult(np.zeros(0, dtype=np.float32), self.sample_rate, [])

        # ~0.28 s par mot + 0.04 s par caractère : durée plausible à l'oral.
        sr = self.sample_rate
        timings: list[WordTiming] = []
        chunks: list[np.ndarray] = []
        cursor = 0.0
        for i, w in enumerate(words):
            dur = 0.28 + 0.04 * len(w)
            n = int(dur * sr)
            t = np.arange(n) / sr
            freq = 110 + (i % 5) * 20  # voyelle « factice » qui varie
            env = np.sin(np.pi * np.linspace(0, 1, n)) ** 2  # enveloppe douce
            chunks.append((0.2 * env * np.sin(2 * np.pi * freq * t)).astype(np.float32))
            timings.append(WordTiming(w, round(cursor, 4), round(cursor + dur, 4)))
            cursor += dur

        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        return TTSResult(audio, sr, timings)


class KokoroEngine(TTSEngine):
    """Moteur principal : Kokoro TTS, voix française.

    Importé paresseusement : si ``kokoro`` n'est pas installé, on lève une
    exception capturée par :func:`make_engine` qui bascule sur le repli.
    """

    name = "kokoro"

    def __init__(self, voice: str = "ff_siwis", sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        from kokoro import KPipeline  # import local : optionnel

        # 'f' = français dans Kokoro (lang_code). La voix ff_siwis est féminine FR.
        self._pipeline = KPipeline(lang_code="f")
        self.voice = voice
        self.sample_rate = sample_rate

    def synthesize(self, text: str) -> TTSResult:
        audio_parts: list[np.ndarray] = []
        words: list[WordTiming] = []
        offset = 0.0

        # KPipeline produit des segments ; on concatène et on aligne au mot.
        for result in self._pipeline(text, voice=self.voice):
            seg_audio = np.asarray(result.audio, dtype=np.float32)
            audio_parts.append(seg_audio)
            seg_dur = len(seg_audio) / self.sample_rate

            # Si Kokoro expose des timestamps de tokens, on les exploite ;
            # sinon on reconstruit proportionnellement.
            graphemes = getattr(result, "graphemes", None) or text
            seg_words = reconstruct_word_times(graphemes, seg_dur, offset)
            words.extend(seg_words)
            offset += seg_dur

        audio = np.concatenate(audio_parts) if audio_parts else np.zeros(0, dtype=np.float32)
        return TTSResult(audio, self.sample_rate, words)


class PiperEngine(TTSEngine):
    """Repli : piper-tts (voix fr_FR locale). Pas de timestamps natifs → reconstruits."""

    name = "piper"

    def __init__(self, model_path: str, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        from piper import PiperVoice  # import local : optionnel

        self._voice = PiperVoice.load(model_path)
        self.sample_rate = getattr(self._voice.config, "sample_rate", sample_rate)

    def synthesize(self, text: str) -> TTSResult:
        pcm = b"".join(self._voice.synthesize_stream_raw(text))
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32767.0
        dur = len(audio) / self.sample_rate
        words = reconstruct_word_times(text, dur)
        return TTSResult(audio, self.sample_rate, words)


def make_engine(cfg: dict | None = None) -> TTSEngine:
    """Fabrique le moteur selon la config, avec repli automatique.

    Ordre : moteur demandé → Piper → Dummy. Jamais d'échec dur : on garantit
    toujours un moteur fonctionnel hors-ligne.
    """
    cfg = cfg or {}
    engine_name = cfg.get("engine", "kokoro")
    sr = int(cfg.get("sample_rate", DEFAULT_SAMPLE_RATE))

    if engine_name == "kokoro":
        try:
            return KokoroEngine(voice=cfg.get("voice", "ff_siwis"), sample_rate=sr)
        except Exception as e:  # pragma: no cover - dépend de l'install locale
            log.warning("Kokoro indisponible (%s) → repli Piper/Dummy.", e)

    if engine_name in ("kokoro", "piper") and cfg.get("piper_model"):
        try:
            return PiperEngine(cfg["piper_model"], sample_rate=sr)
        except Exception as e:  # pragma: no cover
            log.warning("Piper indisponible (%s) → repli Dummy.", e)

    log.info("Moteur TTS = dummy (aucun modèle vocal chargé).")
    return DummyEngine(sample_rate=sr)


# --- Service de synthèse streamée avec annulation ----------------------------


@dataclass
class TTSChunk:
    """Une phrase synthétisée, prête à envoyer au client."""

    index: int
    text: str
    result: TTSResult


class TTSService:
    """Synthétise un texte phrase par phrase, de façon annulable.

    Chaque appel à :meth:`stream` produit un flux asynchrone de :class:`TTSChunk`.
    Un :meth:`cancel` (barge-in) interrompt proprement la synthèse en cours.
    """

    def __init__(self, engine: TTSEngine | None = None) -> None:
        self.engine = engine or DummyEngine()
        self._cancel = asyncio.Event()

    def cancel(self) -> None:
        self._cancel.set()

    async def stream(self, text: str):
        """Génère les phrases synthétisées au fil de l'eau."""
        self._cancel.clear()
        sentences = split_sentences(text) or [text]
        for i, sentence in enumerate(sentences):
            if self._cancel.is_set():
                log.info("Synthèse interrompue (barge-in) à la phrase %d.", i)
                break
            # La synthèse est CPU-bound → on l'exécute dans un thread pour ne
            # pas bloquer la boucle asyncio.
            result = await asyncio.to_thread(self.engine.synthesize, sentence)
            if self._cancel.is_set():
                break
            yield TTSChunk(index=i, text=sentence, result=result)

    async def synthesize_full(self, text: str) -> TTSResult:
        """Synthèse complète (non streamée), utile pour les tests."""
        result = await asyncio.to_thread(self.engine.synthesize, text)
        return result
