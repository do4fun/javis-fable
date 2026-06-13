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

import logging
from contextlib import asynccontextmanager
from pathlib import Path

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
    log.info("Jarvis démarré. Frontend attendu dans %s", WEB_DIST)
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
        # Stub : on accuse réception. F4.1 branchera ici le LLM via le bus.
        text = env.payload.get("text", "")
        log.info("user_text reçu: %r", text)
        await bus.publish("user_text", {"text": text, "ws": ws})
        await manager.send(
            ws,
            Envelope.make(ServerMsg.STATE, {"state": "thinking", "ack": True}, id=env.id),
        )

    elif env.type == ClientMsg.INTERRUPT:
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
