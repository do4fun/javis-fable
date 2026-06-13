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
    # Service TTS (F2.1) : moteur enfichable avec repli automatique.
    app.state.tts = TTSService(make_engine(app.state.config.get("tts")))
    log.info(
        "Jarvis démarré (TTS=%s). Frontend attendu dans %s",
        app.state.tts.engine.name,
        WEB_DIST,
    )
    yield
    log.info("Arrêt de Jarvis.")


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

    try:
        while True:
            raw = await ws.receive_text()
            await _handle_message(ws, raw)
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
        # F2.1 (démo « il parle ») : on synthétise directement le texte reçu.
        # En F4.1, le LLM s'intercalera (texte utilisateur → réponse → TTS).
        text = env.payload.get("text", "")
        log.info("user_text reçu: %r", text)
        await bus.publish("user_text", {"text": text, "ws": ws})
        await _speak(ws, text, corr_id=env.id)

    elif env.type == ClientMsg.INTERRUPT:
        # Barge-in : on coupe la synthèse en cours.
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
        # Stub : F3.1/F3.2 brancheront le VAD/STT. On ne renvoie rien ici pour
        # ne pas inonder le client (les chunks arrivent toutes les ~30 ms).
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
