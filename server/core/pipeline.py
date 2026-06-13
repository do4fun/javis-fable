"""Pipeline temps réel de conversation (F5.1).

Chef d'orchestre d'un tour de parole : machine à états
``idle → listening → thinking → speaking`` diffusée au client, chaînage
streaming intégral (STT → LLM → découpe en phrases → TTS → audio+timings) avec
mesure de latence par maillon (``trace_id`` par tour), et barge-in robuste
(annulation à n'importe quel stade, sans fuite de tâches asyncio).

Découplé du transport : il reçoit un ``manager`` (qui sait ``send`` une
:class:`Envelope` à un client) et un objet ``ws`` opaque servant de clé de
session. Cela permet de le tester avec un faux client (cf. tests/test_pipeline).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
import uuid
from dataclasses import dataclass, field

from core.protocol import Envelope, ServerMsg
from modules import tools
from modules.brain import Brain
from modules.memory import Memory
from modules.stt import STTService
from modules.tags import (
    EmotionEvent,
    GestureEvent,
    StreamTagParser,
    TextEvent,
    ToolEvent,
)
from modules.tts import TTSChunk, TTSService

log = logging.getLogger("jarvis.pipeline")


class State:
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


# --- Commandes mémoire (F4.2) ------------------------------------------------

_RE_FORGET = re.compile(r"\boublie tout\b|\befface tout\b|\boublie ce que tu sais\b", re.I)
_RE_NAME = re.compile(r"\b(?:je m'appelle|mon prénom est|appelle-moi)\s+([\wÀ-ÿ-]+)", re.I)
_RE_REMEMBER = re.compile(r"\b(?:souviens-toi que|rappelle-toi que|retiens que)\s+(.+)", re.I)
_RE_ASK_NAME = re.compile(r"\b(?:comment je m'appelle|quel est mon prénom|mon nom)\b", re.I)


def handle_memory_command(text: str, memory: Memory) -> str | None:
    """Traite les commandes mémoire explicites. Renvoie une réponse balisée ou None."""
    if _RE_FORGET.search(text):
        memory.purge_all()
        return "[emo:neutre] C'est fait, j'ai tout effacé. On repart de zéro."
    if m := _RE_NAME.search(text):
        prenom = m.group(1).strip().capitalize()
        memory.set_profile("prenom", prenom)
        return f"[emo:joie][geste:salut] Enchanté, {prenom} !"
    if _RE_ASK_NAME.search(text):
        prenom = memory.get_profile().get("prenom")
        if prenom:
            return f"[emo:joie] Tu t'appelles {prenom}, bien sûr."
        return "[emo:reflexion] Tu ne me l'as pas encore dit. Comment tu t'appelles ?"
    if m := _RE_REMEMBER.search(text):
        fact = m.group(1).strip().rstrip(".")
        prefs = memory.get_profile().get("preferences", "")
        prefs = (prefs + " | " + fact).strip(" |") if prefs else fact
        memory.set_profile("preferences", prefs)
        return "[emo:neutre] D'accord, je m'en souviens."
    return None


def build_history(memory: Memory) -> list[dict]:
    """Historique glissant (12 tours) + contexte profil/résumé en tête."""
    history: list[dict] = []
    profile = memory.get_profile()
    summary = memory.get_summary()
    bits = []
    if profile.get("prenom"):
        bits.append(f"L'utilisateur s'appelle {profile['prenom']}.")
    if profile.get("preferences"):
        bits.append(f"Préférences déclarées : {profile['preferences']}.")
    if summary:
        bits.append(f"Résumé de la conversation précédente : {summary}")
    if bits:
        history.append({"role": "system", "content": " ".join(bits)})
    history.extend(memory.recent_turns(12))
    return history


def tts_audio_envelope(chunk: TTSChunk, corr_id: str | None = None) -> Envelope:
    """Trame ``tts_audio`` : PCM int16 base64 + timings au mot."""
    res = chunk.result
    return Envelope.make(
        ServerMsg.TTS_AUDIO,
        {
            "index": chunk.index,
            "text": chunk.text,
            "sample_rate": res.sample_rate,
            "audio": base64.b64encode(res.to_int16_bytes()).decode("ascii"),
            "words": [{"word": w.word, "start": w.start, "end": w.end} for w in res.words],
        },
        id=corr_id,
    )


@dataclass
class Turn:
    """Trace d'un tour de parole : identifiant + jalons de latence."""

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    t0: float = field(default_factory=time.perf_counter)
    marks: dict[str, float] = field(default_factory=dict)

    def mark(self, name: str) -> None:
        self.marks[name] = time.perf_counter() - self.t0

    def metrics(self) -> dict[str, float]:
        return {k: round(v * 1000) for k, v in self.marks.items()}  # ms


class Pipeline:
    def __init__(
        self,
        manager,
        brain: Brain,
        tts: TTSService,
        stt: STTService,
        memory: Memory,
        allow_network: bool = False,
    ) -> None:
        self.manager = manager
        self.brain = brain
        self.tts = tts
        self.stt = stt
        self.memory = memory
        self.allow_network = allow_network
        # Annulation et tâches en cours, par session (clé = ws).
        self._cancels: dict[int, asyncio.Event] = {}
        self._tasks: dict[int, set[asyncio.Task]] = {}

    # --- Gestion d'état / session ------------------------------------------

    def _cancel(self, ws) -> asyncio.Event:
        return self._cancels.setdefault(id(ws), asyncio.Event())

    async def set_state(self, ws, state: str, extra: dict | None = None) -> None:
        payload = {"state": state}
        if extra:
            payload.update(extra)
        await self.manager.send(ws, Envelope.make(ServerMsg.STATE, payload))

    def track(self, ws, coro) -> asyncio.Task:
        """Suit une tâche pour pouvoir l'annuler proprement (barge-in)."""
        task = asyncio.ensure_future(coro)
        s = self._tasks.setdefault(id(ws), set())
        s.add(task)
        task.add_done_callback(lambda t: s.discard(t))
        return task

    async def interrupt(self, ws) -> None:
        """Barge-in : annule génération LLM, file TTS et tâches en cours."""
        self._cancel(ws).set()
        self.tts.cancel()
        for task in list(self._tasks.get(id(ws), ())):
            task.cancel()
        # Laisse les tâches se terminer (annulation propre, pas de fuite).
        await asyncio.gather(*self._tasks.get(id(ws), ()), return_exceptions=True)
        await self.set_state(ws, State.IDLE)

    def cleanup(self, ws) -> None:
        self._cancels.pop(id(ws), None)
        self._tasks.pop(id(ws), None)

    # --- Entrées -----------------------------------------------------------

    async def on_user_text(self, ws, text: str, corr_id: str | None = None) -> None:
        turn = Turn()
        await self.converse(ws, text, turn, corr_id)

    async def on_speech_segment(self, ws, audio: bytes, sample_rate: int = 16000) -> None:
        """Segment de parole (F3.1) → STT → conversation."""
        turn = Turn()
        await self.set_state(ws, State.THINKING)
        text = await self.stt.transcribe_segment(audio, sample_rate)
        turn.mark("stt")
        await self.manager.send(
            ws, Envelope.make(ServerMsg.TRANSCRIPT, {"text": text, "final": True})
        )
        if not text:
            await self.set_state(ws, State.IDLE)
            return
        await self.converse(ws, text, turn)

    # --- Tour de parole ----------------------------------------------------

    async def converse(self, ws, text: str, turn: Turn, corr_id: str | None = None) -> None:
        if not text.strip():
            return

        cancel = self._cancel(ws)
        cancel.clear()
        self.tts._cancel.clear()

        parser = StreamTagParser()
        state = {"sentence": "", "spoke": False, "full": ""}

        await self.set_state(ws, State.THINKING)

        async def flush_sentence(force: bool = False) -> None:
            chunk = state["sentence"].strip()
            if not chunk or (not force and chunk[-1] not in ".!?…"):
                return
            state["sentence"] = ""
            if not state["spoke"]:
                turn.mark("first_token")
                await self.set_state(ws, State.SPEAKING, {"trace": turn.trace_id})
                state["spoke"] = True
            async for tts_chunk in self.tts.stream(chunk):
                if cancel.is_set():
                    return
                if "first_audio" not in turn.marks:
                    turn.mark("first_audio")
                    log.info(
                        "trace=%s latences(ms)=%s", turn.trace_id, turn.metrics()
                    )
                await self.manager.send(ws, tts_audio_envelope(tts_chunk))

        async def speak_text(t: str) -> None:
            await self.manager.send(ws, Envelope.make(ServerMsg.LLM_TOKEN, {"token": t}))
            state["sentence"] += t
            state["full"] += t
            await flush_sentence()

        command_reply = handle_memory_command(text, self.memory)
        if command_reply is not None:
            token_source = _as_stream(command_reply)
        else:
            token_source = self.brain.stream(
                text, history=build_history(self.memory), cancel=cancel
            )

        self.memory.add_turn("user", text)

        try:
            async for tok in token_source:
                if cancel.is_set():
                    break
                for ev in parser.feed(tok):
                    await self._dispatch_event(ws, ev, speak_text)
            for ev in parser.flush():
                if isinstance(ev, TextEvent) and ev.text:
                    await speak_text(ev.text)
            if not cancel.is_set():
                await flush_sentence(force=True)
        except asyncio.CancelledError:
            raise  # annulation propre (barge-in via task.cancel)
        except Exception:
            log.exception("trace=%s échec conversation", turn.trace_id)
            await self.manager.send(ws, Envelope.make(ServerMsg.ERROR, {"reason": "brain_failed"}))
        finally:
            if state["full"].strip():
                self.memory.add_turn("assistant", state["full"].strip())
            self._maybe_summarize()
            await self.set_state(
                ws, State.IDLE, {"trace": turn.trace_id, "metrics": turn.metrics()}
            )

    async def _dispatch_event(self, ws, ev, speak_text) -> None:
        if isinstance(ev, TextEvent):
            if ev.text:
                await speak_text(ev.text)
        elif isinstance(ev, EmotionEvent):
            await self.manager.send(
                ws,
                Envelope.make(ServerMsg.EMOTION, {"name": ev.name, "intensity": ev.intensity}),
            )
        elif isinstance(ev, GestureEvent):
            await self.manager.send(ws, Envelope.make(ServerMsg.GESTURE, {"name": ev.name}))
        elif isinstance(ev, ToolEvent):
            await self._run_tool(ws, ev.raw, speak_text)

    async def _run_tool(self, ws, raw: str, speak_text) -> None:
        seconds = tools.parse_minuteur_seconds(raw)
        if seconds:
            self.track(ws, self._timer_task(ws, seconds))
            mins = int(seconds // 60)
            label = (
                f"{mins} minute{'s' if mins > 1 else ''}" if mins else f"{int(seconds)} secondes"
            )
            await speak_text(f"C'est parti pour {label}. ")
            return
        result = tools.execute(raw, allow_network=self.allow_network)
        if result:
            await speak_text(result + " ")

    async def _timer_task(self, ws, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
            await self.manager.send(
                ws, Envelope.make(ServerMsg.EMOTION, {"name": "surprise", "intensity": 0.7})
            )
            await self.manager.send(
                ws, Envelope.make(ServerMsg.STATE, {"state": State.SPEAKING})
            )
            async for tts_chunk in self.tts.stream("Ding ! Ton minuteur est terminé."):
                await self.manager.send(ws, tts_audio_envelope(tts_chunk))
            await self.set_state(ws, State.IDLE)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # connexion fermée : best-effort

    def _maybe_summarize(self, keep_last: int = 12) -> None:
        old = self.memory.turns_before(keep_last)
        if len(old) < 4:
            return
        digest = " ".join(f"{t['role']}: {t['content']}" for t in old)
        if len(digest) > 600:
            digest = digest[:600] + "…"
        prev = self.memory.get_summary()
        self.memory.set_summary((prev + " " + digest).strip()[-1200:])
        self.memory.prune_to(keep_last)


async def _as_stream(text: str):
    """Adapte une chaîne en flux de tokens (réponses directes/repli)."""
    yield text
