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


def test_user_text_triggers_speech():
    # user_text → state:speaking → tts_audio(s) → state:idle (démo « il parle »).
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # state initial
            env = Envelope.make(ClientMsg.USER_TEXT, {"text": "Bonjour Jarvis."})
            ws.send_text(env.to_json())

            speaking = ws.receive_json()
            assert speaking["type"] == ServerMsg.STATE
            assert speaking["payload"]["state"] == "speaking"
            assert speaking["id"] == env.id  # id de corrélation préservé

            audio = ws.receive_json()
            assert audio["type"] == ServerMsg.TTS_AUDIO
            assert audio["payload"]["sample_rate"] > 0
            assert len(audio["payload"]["audio"]) > 0  # base64 non vide
            assert len(audio["payload"]["words"]) > 0

            # On consomme jusqu'à l'état idle final.
            last = audio
            while last["type"] != ServerMsg.STATE:
                last = ws.receive_json()
            assert last["payload"]["state"] == "idle"


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
