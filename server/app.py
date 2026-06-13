"""Application FastAPI de Jarvis — colonne vertébrale d'orchestration (F0.2).

Responsabilités à ce stade :
- exposer un WebSocket ``/ws`` parlant le protocole d'enveloppe typé ;
- servir le build frontend (``/web/dist``) en statique ;
- offrir un bus d'événements asyncio prêt à chaîner STT → LLM → TTS ;
- gérer proprement les déconnexions, avec logs structurés et CORS localhost.

Les types de messages sont déclarés (stubs) mais leur logique métier arrive
dans les fonctionnalités suivantes (F2.1, F3.x, F4.x, F5.1).
"""

from __future__ import annotations

import asyncio
import base64
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from core.bus import EventBus
from core.logging_setup import setup_logging
from core.protocol import (
    KNOWN_CLIENT_TYPES,
    ClientMsg,
    Envelope,
    ServerMsg,
)
from modules import tools
from modules.brain import Brain
from modules.memory import Memory
from modules.stt import STTService, make_stt_engine
from modules.tags import (
    EmotionEvent,
    GestureEvent,
    StreamTagParser,
    TextEvent,
    ToolEvent,
)
from modules.tts import TTSChunk, TTSService, make_engine

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}

setup_logging()
log = logging.getLogger("jarvis.app")

# Emplacement du build frontend (produit par `npm run build` dans /web).
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"

# CORS : strictement localhost (le projet ne sort jamais de la machine).
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://localhost:5173",  # serveur de dev Vite
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5173",
]


class ConnectionManager:
    """Suit les WebSockets actifs et permet une diffusion simple."""

    def __init__(self) -> None:
        self._active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.add(ws)
        log.info("client connecté (%d actif·s)", len(self._active))

    def disconnect(self, ws: WebSocket) -> None:
        self._active.discard(ws)
        log.info("client déconnecté (%d actif·s)", len(self._active))

    async def send(self, ws: WebSocket, env: Envelope) -> None:
        await ws.send_text(env.to_json())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bus partagé pour toute l'application.
    app.state.bus = EventBus()
    app.state.manager = ConnectionManager()
    app.state.config = load_config()
    # Services : TTS (F2.1), STT (F3.2), cerveau LLM (F4.1).
    app.state.tts = TTSService(make_engine(app.state.config.get("tts")))
    app.state.stt = STTService(make_stt_engine(app.state.config.get("stt")))
    app.state.brain = Brain(app.state.config.get("llm"))
    app.state.memory = Memory()  # F4.2 : SQLite local
    app.state.allow_network = bool(app.state.config.get("allow_network", False))

    # Abonnement bus : un segment de parole (F3.1) → transcription (F3.2).
    app.state.bus.subscribe("speech_segment", _on_speech_segment)

    # Vérifie Ollama sans bloquer le démarrage (repli rule-based sinon).
    ok, msg = await app.state.brain.available()
    if ok:
        log.info("Cerveau Ollama prêt (modèle %s).", app.state.brain.model)
    else:
        log.warning("Cerveau LLM indisponible : %s", msg)

    log.info(
        "Jarvis démarré (TTS=%s, STT=%s). Frontend attendu dans %s",
        app.state.tts.engine.name,
        app.state.stt.engine.name,
        WEB_DIST,
    )
    yield
    log.info("Arrêt de Jarvis.")


async def _on_speech_segment(payload: dict) -> None:
    """Transcrit un segment de parole et renvoie le transcript au client.

    Le transcript final est aussi publié sur le bus (``transcript_final``) à
    destination du cerveau LLM (F4.1). En attendant F4.1, on fait parler
    l'avatar avec le texte transcrit (boucle voix↔voix de démonstration).
    """
    ws: WebSocket = payload["ws"]
    audio: bytes = payload["audio"]
    sr: int = payload.get("sample_rate", 16000)
    manager: ConnectionManager = ws.app.state.manager
    stt: STTService = ws.app.state.stt
    bus: EventBus = ws.app.state.bus

    await manager.send(ws, Envelope.make(ServerMsg.STATE, {"state": "thinking"}))
    text = await stt.transcribe_segment(audio, sr)
    await manager.send(
        ws, Envelope.make(ServerMsg.TRANSCRIPT, {"text": text, "final": True})
    )

    if not text:
        await manager.send(ws, Envelope.make(ServerMsg.STATE, {"state": "idle"}))
        return

    # F4.1 : la parole transcrite alimente le cerveau LLM.
    await bus.publish("transcript_final", {"text": text, "ws": ws})
    await _converse(ws, text)


def _cancel_event(ws: WebSocket) -> "asyncio.Event":
    """Event d'annulation par connexion (barge-in)."""
    ev = getattr(ws, "_cancel", None)
    if ev is None:
        ev = asyncio.Event()
        ws._cancel = ev
    return ev


# --- Commandes mémoire (F4.2) ------------------------------------------------

import re as _re  # local, pour rester groupé avec la logique mémoire

_RE_FORGET = _re.compile(r"\boublie tout\b|\befface tout\b|\boublie ce que tu sais\b", _re.I)
_RE_NAME = _re.compile(r"\b(?:je m'appelle|mon prénom est|appelle-moi)\s+([\wÀ-ÿ-]+)", _re.I)
_RE_REMEMBER = _re.compile(r"\b(?:souviens-toi que|rappelle-toi que|retiens que)\s+(.+)", _re.I)
_RE_ASK_NAME = _re.compile(r"\b(?:comment je m'appelle|quel est mon prénom|mon nom)\b", _re.I)


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
    context_bits = []
    if profile.get("prenom"):
        context_bits.append(f"L'utilisateur s'appelle {profile['prenom']}.")
    if profile.get("preferences"):
        context_bits.append(f"Préférences déclarées : {profile['preferences']}.")
    if summary:
        context_bits.append(f"Résumé de la conversation précédente : {summary}")
    if context_bits:
        history.append({"role": "system", "content": " ".join(context_bits)})
    history.extend(memory.recent_turns(12))
    return history


async def _converse(ws: WebSocket, text: str, corr_id: str | None = None) -> None:
    """Tour de parole complet : LLM (streaming + balises) → émotion/geste/TTS.

    - relaie les tokens « propres » au client (``llm_token``) ;
    - extrait les balises au vol : émotions/gestes → messages dédiés (jamais
      lus à voix haute) ;
    - synthétise les phrases complètes au fil de l'eau (latence du 1er son).
    """
    if not text.strip():
        return

    manager: ConnectionManager = ws.app.state.manager
    brain: Brain = ws.app.state.brain
    tts: TTSService = ws.app.state.tts
    memory: Memory = ws.app.state.memory

    cancel = _cancel_event(ws)
    cancel.clear()
    tts._cancel.clear()  # réarme le TTS (un interrupt précédent a pu l'armer)

    parser = StreamTagParser()
    sentence = ""
    spoke = False
    full_text = ""  # texte propre accumulé (pour la mémoire)

    await manager.send(ws, Envelope.make(ServerMsg.STATE, {"state": "thinking"}, id=corr_id))

    async def speak_text(t: str) -> None:
        """Envoie du texte propre au client + le synthétise par phrase."""
        nonlocal sentence, spoke, full_text
        await manager.send(ws, Envelope.make(ServerMsg.LLM_TOKEN, {"token": t}))
        sentence += t
        full_text += t
        await flush_sentence()

    async def flush_sentence(force: bool = False) -> None:
        nonlocal sentence, spoke
        chunk = sentence.strip()
        if not chunk:
            return
        if not force and chunk[-1] not in ".!?…":
            return
        sentence = ""
        if not spoke:
            await manager.send(ws, Envelope.make(ServerMsg.STATE, {"state": "speaking"}))
            spoke = True
        async for tts_chunk in tts.stream(chunk):
            if cancel.is_set():
                return
            await manager.send(ws, tts_audio_envelope(tts_chunk))

    # Commande mémoire explicite (oublie tout, prénom…) → réponse directe.
    command_reply = handle_memory_command(text, memory)
    token_source = (
        _as_token_stream(command_reply)
        if command_reply is not None
        else brain.stream(text, history=build_history(memory), cancel=cancel)
    )

    memory.add_turn("user", text)

    try:
        async for tok in token_source:
            if cancel.is_set():
                break
            for ev in parser.feed(tok):
                if isinstance(ev, TextEvent):
                    if ev.text:
                        await speak_text(ev.text)
                elif isinstance(ev, EmotionEvent):
                    await manager.send(
                        ws,
                        Envelope.make(
                            ServerMsg.EMOTION, {"name": ev.name, "intensity": ev.intensity}
                        ),
                    )
                elif isinstance(ev, GestureEvent):
                    await manager.send(ws, Envelope.make(ServerMsg.GESTURE, {"name": ev.name}))
                elif isinstance(ev, ToolEvent):
                    await _run_tool(ws, ev.raw, speak_text)

        for ev in parser.flush():
            if isinstance(ev, TextEvent) and ev.text:
                await speak_text(ev.text)
        if not cancel.is_set():
            await flush_sentence(force=True)
    except Exception:
        log.exception("échec de la conversation")
        await manager.send(ws, Envelope.make(ServerMsg.ERROR, {"reason": "brain_failed"}))
    finally:
        # Mémorise la réponse et résume si l'historique devient long.
        if full_text.strip():
            memory.add_turn("assistant", full_text.strip())
        _maybe_summarize(memory)
        await manager.send(ws, Envelope.make(ServerMsg.STATE, {"state": "idle"}, id=corr_id))


async def _as_token_stream(text: str):
    """Adapte une chaîne en flux de tokens (pour réponses directes/repli)."""
    yield text


async def _run_tool(ws: WebSocket, raw: str, speak_text) -> None:
    """Exécute un outil local et fait dire le résultat (F4.2)."""
    allow_network = ws.app.state.allow_network

    seconds = tools.parse_minuteur_seconds(raw)
    if seconds:
        asyncio.create_task(_timer_task(ws, seconds))
        mins = int(seconds // 60)
        label = f"{mins} minute{'s' if mins > 1 else ''}" if mins else f"{int(seconds)} secondes"
        await speak_text(f"C'est parti pour {label}. ")
        return

    result = tools.execute(raw, allow_network=allow_network)
    if result:
        await speak_text(result + " ")


async def _timer_task(ws: WebSocket, seconds: float) -> None:
    """Minuteur : attend puis notifie l'utilisateur à l'oral."""
    await asyncio.sleep(seconds)
    try:
        await ws.app.state.manager.send(
            ws, Envelope.make(ServerMsg.EMOTION, {"name": "surprise", "intensity": 0.7})
        )
        await _speak(ws, "Ding ! Ton minuteur est terminé.")
    except Exception:
        pass  # connexion fermée : best-effort


def _maybe_summarize(memory: Memory, keep_last: int = 12) -> None:
    """Résume grossièrement les tours anciens et les élague (F4.2).

    Résumé local et simple (concaténation condensée), sans appel réseau : on
    garde une trace compacte de ce qui dépasse la fenêtre glissante.
    """
    old = memory.turns_before(keep_last)
    if len(old) < 4:
        return
    snippets = [f"{t['role']}: {t['content']}" for t in old]
    digest = " ".join(snippets)
    if len(digest) > 600:
        digest = digest[:600] + "…"
    prev = memory.get_summary()
    memory.set_summary((prev + " " + digest).strip()[-1200:])
    memory.prune_to(keep_last)


def tts_audio_envelope(chunk: TTSChunk, corr_id: str | None = None) -> Envelope:
    """Construit une trame ``tts_audio`` (PCM int16 base64 + timings au mot)."""
    res = chunk.result
    return Envelope.make(
        ServerMsg.TTS_AUDIO,
        {
            "index": chunk.index,
            "text": chunk.text,
            "sample_rate": res.sample_rate,
            # PCM 16 bits little-endian, encodé base64 pour le transport JSON.
            "audio": base64.b64encode(res.to_int16_bytes()).decode("ascii"),
            "words": [
                {"word": w.word, "start": w.start, "end": w.end} for w in res.words
            ],
        },
        id=corr_id,
    )


app = FastAPI(title="Jarvis", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "jarvis", "local": True})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    manager: ConnectionManager = ws.app.state.manager
    await manager.connect(ws)

    # On annonce l'état initial dès la connexion.
    await manager.send(ws, Envelope.make(ServerMsg.STATE, {"state": "idle"}))

    # Buffer audio par connexion : les trames binaires PCM 16 kHz (F3.1) y sont
    # accumulées entre les marqueurs VAD start/end (consommées par le STT, F3.2).
    ws.state_audio = bytearray()

    try:
        while True:
            # Accepte texte (enveloppes JSON) ET binaire (chunks audio).
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if (text := msg.get("text")) is not None:
                await _handle_message(ws, text)
            elif (data := msg.get("bytes")) is not None:
                ws.state_audio.extend(data)
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:  # robustesse : on ne laisse jamais une connexion tuer le serveur
        log.exception("erreur inattendue sur /ws")
        manager.disconnect(ws)
        try:
            await ws.close()
        except RuntimeError:
            pass


async def _handle_message(ws: WebSocket, raw: str) -> None:
    """Valide l'enveloppe entrante et route selon son type.

    À ce stade, la plupart des types sont des *stubs* : on accuse réception
    par un ``state`` afin que le client (et les tests) puisse vérifier le
    chemin de bout en bout. Les fonctionnalités suivantes brancheront la
    vraie logique sur le bus.
    """
    manager: ConnectionManager = ws.app.state.manager

    try:
        env = Envelope.model_validate_json(raw)
    except Exception:
        await manager.send(
            ws,
            Envelope.make(ServerMsg.ERROR, {"reason": "enveloppe JSON invalide"}),
        )
        return

    if env.type not in KNOWN_CLIENT_TYPES:
        await manager.send(
            ws,
            Envelope.make(
                ServerMsg.ERROR,
                {"reason": f"type inconnu: {env.type}"},
                id=env.id,
            ),
        )
        return

    bus: EventBus = ws.app.state.bus

    if env.type == ClientMsg.USER_TEXT:
        # F4.1 : texte utilisateur → cerveau LLM → balises + TTS.
        text = env.payload.get("text", "")
        log.info("user_text reçu: %r", text)
        await bus.publish("user_text", {"text": text, "ws": ws})
        await _converse(ws, text, corr_id=env.id)

    elif env.type == ClientMsg.INTERRUPT:
        # Barge-in : on annule la génération LLM ET la synthèse en cours.
        _cancel_event(ws).set()
        ws.app.state.tts.cancel()
        await bus.publish("interrupt", {"ws": ws})
        await manager.send(
            ws, Envelope.make(ServerMsg.STATE, {"state": "idle"}, id=env.id)
        )

    elif env.type == ClientMsg.CONFIG:
        log.info("config reçue: %r", env.payload)
        await manager.send(
            ws, Envelope.make(ServerMsg.STATE, {"state": "idle", "ack": True}, id=env.id)
        )

    elif env.type == ClientMsg.AUDIO_CHUNK:
        # Marqueurs VAD du client (F3.1) : 'start' ouvre un segment, 'end' le
        # clôt. Les trames PCM elles-mêmes arrivent en binaire (cf. boucle /ws)
        # et sont accumulées dans ws.state_audio.
        event = env.payload.get("event")
        if event == "start":
            ws.state_audio = bytearray()
            await manager.send(
                ws, Envelope.make(ServerMsg.STATE, {"state": "listening"}, id=env.id)
            )
        elif event == "end":
            audio = bytes(getattr(ws, "state_audio", b""))
            ws.state_audio = bytearray()
            # F3.2 (STT) s'abonnera à 'speech_segment' pour transcrire ce buffer.
            await bus.publish(
                "speech_segment",
                {"audio": audio, "sample_rate": env.payload.get("sample_rate", 16000), "ws": ws},
            )
        else:
            await bus.publish("audio_chunk", {"payload": env.payload, "ws": ws})


async def _speak(ws: WebSocket, text: str, corr_id: str | None = None) -> None:
    """Synthétise ``text`` phrase par phrase et streame l'audio au client.

    États émis : ``speaking`` au début, ``idle`` à la fin (ou si interrompu).
    """
    manager: ConnectionManager = ws.app.state.manager
    tts: TTSService = ws.app.state.tts

    if not text.strip():
        await manager.send(ws, Envelope.make(ServerMsg.STATE, {"state": "idle"}, id=corr_id))
        return

    await manager.send(ws, Envelope.make(ServerMsg.STATE, {"state": "speaking"}, id=corr_id))
    try:
        async for chunk in tts.stream(text):
            await manager.send(ws, tts_audio_envelope(chunk, corr_id))
    except Exception:
        log.exception("échec de synthèse")
        await manager.send(ws, Envelope.make(ServerMsg.ERROR, {"reason": "tts_failed"}, id=corr_id))
    finally:
        await manager.send(ws, Envelope.make(ServerMsg.STATE, {"state": "idle"}, id=corr_id))


# Service statique du frontend (monté en dernier pour ne pas masquer /ws).
# Si le build n'existe pas encore, on ne monte rien et on prévient dans /health.
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
else:
    log.warning(
        "Build frontend absent (%s). Lance `cd web && npm run build`, "
        "ou utilise le serveur de dev Vite sur le port 5173.",
        WEB_DIST,
    )
