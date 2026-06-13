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


def test_user_text_triggers_conversation():
    # user_text → cerveau (repli rule-based, Ollama absent en test) → balises
    # (emotion/geste) + llm_token + tts_audio → state idle.
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # state initial
            env = Envelope.make(ClientMsg.USER_TEXT, {"text": "Bonjour Jarvis."})
            ws.send_text(env.to_json())

            types = []
            payloads = []
            # On collecte jusqu'à l'état idle final.
            for _ in range(60):
                msg = ws.receive_json()
                types.append(msg["type"])
                payloads.append(msg)
                if msg["type"] == ServerMsg.STATE and msg["payload"]["state"] == "idle":
                    break

            assert ServerMsg.STATE in types
            # Le cerveau de repli émet une émotion en tête.
            assert ServerMsg.EMOTION in types
            # On a parlé (audio synthétisé).
            assert ServerMsg.TTS_AUDIO in types
            # Les balises ne sont jamais dans le texte parlé (llm_token).
            tokens = "".join(
                m["payload"].get("token", "")
                for m in payloads
                if m["type"] == ServerMsg.LLM_TOKEN
            )
            assert "[emo:" not in tokens and "[geste:" not in tokens
            # État final idle.
            assert payloads[-1]["payload"]["state"] == "idle"


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
