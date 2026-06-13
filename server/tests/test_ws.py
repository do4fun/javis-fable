"""Tests du WebSocket /ws (F0.2).

Vérifient le contrat du protocole d'enveloppe sans aucune dépendance réseau
externe : on utilise le client de test natif de Starlette/FastAPI.
"""

import sys
from pathlib import Path

# Permet d'importer `app` et `core` quel que soit le cwd de pytest.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402
from core.protocol import ClientMsg, Envelope, ServerMsg  # noqa: E402


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_ws_state_on_connect():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            first = ws.receive_json()
            assert first["type"] == ServerMsg.STATE
            assert first["payload"]["state"] == "idle"


def test_user_text_ack():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # state initial
            env = Envelope.make(ClientMsg.USER_TEXT, {"text": "Bonjour"})
            ws.send_text(env.to_json())
            reply = ws.receive_json()
            assert reply["type"] == ServerMsg.STATE
            assert reply["payload"].get("ack") is True
            # L'id de corrélation doit être préservé.
            assert reply["id"] == env.id


def test_unknown_type_errors():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # state initial
            ws.send_text(Envelope.make("type_bidon").to_json())
            reply = ws.receive_json()
            assert reply["type"] == ServerMsg.ERROR


def test_invalid_json_errors():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # state initial
            ws.send_text("ceci n'est pas du json")
            reply = ws.receive_json()
            assert reply["type"] == ServerMsg.ERROR
