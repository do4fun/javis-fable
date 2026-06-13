"""Application FastAPI de Jarvis — transport + wiring (F0.2, étendu jusqu'à F5.1).

Responsabilités :
- exposer le WebSocket ``/ws`` (protocole d'enveloppe typé, texte + binaire) ;
- servir le build frontend (``web/dist``) en statique ;
- instancier les services (TTS, STT, cerveau, mémoire) et le :class:`Pipeline`
  temps réel qui orchestre les tours de parole (machine à états, barge-in,
  métriques de latence).

La logique conversationnelle vit dans ``core/pipeline.py``. Ce module se limite
au routage des messages et au cycle de vie.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# Désactive les vérifications de mise à jour HuggingFace Hub à l'exécution.
# Les modèles (Kokoro, Whisper) sont assumés en cache local après la première
# installation. Pour forcer un re-téléchargement, commentez ces deux lignes.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from core.bus import EventBus
from core.logging_setup import setup_logging
from core.pipeline import Pipeline
from core.protocol import (
    KNOWN_CLIENT_TYPES,
    ClientMsg,
    Envelope,
    ServerMsg,
)
from modules.brain import Brain
from modules.memory import Memory
from modules.stt import STTService, make_stt_engine
from modules.tts import TTSService, make_engine

setup_logging()
log = logging.getLogger("jarvis.app")

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://localhost:5173",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5173",
]


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


class ConnectionManager:
    """Suit les WebSockets actifs et sait leur envoyer une enveloppe."""

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
    cfg = load_config()
    app.state.config = cfg
    app.state.bus = EventBus()
    app.state.manager = ConnectionManager()

    # Services locaux (moteurs enfichables, repli automatique).
    tts = TTSService(make_engine(cfg.get("tts")))
    stt = STTService(make_stt_engine(cfg.get("stt")))
    brain = Brain(cfg.get("llm"))
    memory = Memory()
    app.state.tts, app.state.stt, app.state.brain, app.state.memory = tts, stt, brain, memory

    # Pipeline temps réel (F5.1).
    app.state.pipeline = Pipeline(
        app.state.manager, brain, tts, stt, memory,
        allow_network=bool(cfg.get("allow_network", False)),
    )

    # Segment de parole (F3.1) → pipeline (STT + conversation).
    app.state.bus.subscribe(
        "speech_segment",
        lambda p: app.state.pipeline.on_speech_segment(
            p["ws"], p["audio"], p.get("sample_rate", 16000)
        ),
    )

    # Préchauffage TTS : charge la voix en mémoire au démarrage pour que
    # le premier tour de parole ne paie pas le coût de chargement du .pt.
    try:
        await asyncio.to_thread(tts.engine.synthesize, "Bonjour.")
        log.info("TTS préchauffé (%s).", tts.engine.name)
    except Exception as exc:
        log.warning("Warmup TTS ignoré : %s", exc)

    ok, msg = await brain.available()
    log.info("Cerveau Ollama : %s", "prêt" if ok else msg)
    log.info("Jarvis démarré (TTS=%s, STT=%s).", tts.engine.name, stt.engine.name)
    yield
    log.info("Arrêt de Jarvis.")


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
    await manager.send(ws, Envelope.make(ServerMsg.STATE, {"state": "idle"}))

    ws.state_audio = bytearray()  # buffer PCM des trames binaires (F3.1)
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if (text := msg.get("text")) is not None:
                await _handle_message(ws, text)
            elif (data := msg.get("bytes")) is not None:
                ws.state_audio.extend(data)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("erreur inattendue sur /ws")
    finally:
        ws.app.state.pipeline.cleanup(ws)
        manager.disconnect(ws)
        try:
            await ws.close()
        except RuntimeError:
            pass


async def _handle_message(ws: WebSocket, raw: str) -> None:
    manager: ConnectionManager = ws.app.state.manager
    pipeline: Pipeline = ws.app.state.pipeline
    bus: EventBus = ws.app.state.bus

    try:
        env = Envelope.model_validate_json(raw)
    except Exception:
        await manager.send(
            ws, Envelope.make(ServerMsg.ERROR, {"reason": "enveloppe JSON invalide"})
        )
        return

    if env.type not in KNOWN_CLIENT_TYPES:
        await manager.send(
            ws, Envelope.make(ServerMsg.ERROR, {"reason": f"type inconnu: {env.type}"}, id=env.id)
        )
        return

    if env.type == ClientMsg.USER_TEXT:
        text = env.payload.get("text", "")
        log.info("user_text: %r", text)
        await pipeline.on_user_text(ws, text, corr_id=env.id)

    elif env.type == ClientMsg.INTERRUPT:
        await pipeline.interrupt(ws)

    elif env.type == ClientMsg.CONFIG:
        log.info("config: %r", env.payload)
        await manager.send(
            ws, Envelope.make(ServerMsg.STATE, {"state": "idle", "ack": True}, id=env.id)
        )

    elif env.type == ClientMsg.AUDIO_CHUNK:
        event = env.payload.get("event")
        if event == "start":
            ws.state_audio = bytearray()
            await manager.send(
                ws, Envelope.make(ServerMsg.STATE, {"state": "listening"}, id=env.id)
            )
        elif event == "end":
            audio = bytes(getattr(ws, "state_audio", b""))
            ws.state_audio = bytearray()
            await bus.publish(
                "speech_segment",
                {"audio": audio, "sample_rate": env.payload.get("sample_rate", 16000), "ws": ws},
            )
        else:
            await bus.publish("audio_chunk", {"payload": env.payload, "ws": ws})


# Service statique du frontend (monté en dernier pour ne pas masquer /ws).
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
else:
    log.warning(
        "Build frontend absent (%s). Lance `cd web && npm run build`, "
        "ou utilise le serveur de dev Vite (port 5173).",
        WEB_DIST,
    )
