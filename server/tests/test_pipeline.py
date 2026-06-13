"""Tests d'intégration du pipeline temps réel (F5.1).

Pilotés par un faux client (FakeManager) — aucun réseau, aucun navigateur. On
vérifie la machine à états, le chaînage complet, et le barge-in robuste (pas de
fuite de tâches asyncio).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from core.pipeline import Pipeline, State  # noqa: E402
from core.protocol import ServerMsg  # noqa: E402
from modules.brain import Brain  # noqa: E402
from modules.memory import Memory  # noqa: E402
from modules.stt import DummySTTEngine, STTService  # noqa: E402
from modules.tts import DummyEngine, TTSService  # noqa: E402


class FakeWS:
    """Clé de session opaque (le pipeline n'utilise que son identité)."""


class FakeManager:
    """Capture les enveloppes envoyées au lieu de les transmettre au réseau."""

    def __init__(self):
        self.sent = []

    async def send(self, ws, env):
        self.sent.append(env)

    def types(self):
        return [e.type for e in self.sent]


def make_pipeline(tmp_path, brain=None):
    mgr = FakeManager()
    brain = brain or Brain({"host": "http://127.0.0.1:1"})  # injoignable → repli
    pipe = Pipeline(
        mgr,
        brain,
        TTSService(DummyEngine()),
        STTService(DummySTTEngine(canned="bonjour")),
        Memory(tmp_path / "m.sqlite"),
    )
    return pipe, mgr


@pytest.mark.asyncio
async def test_state_machine_full_turn(tmp_path):
    pipe, mgr = make_pipeline(tmp_path)
    ws = FakeWS()
    await pipe.on_user_text(ws, "Bonjour")

    types = mgr.types()
    # On a traversé thinking → speaking → idle.
    states = [e.payload["state"] for e in mgr.sent if e.type == ServerMsg.STATE]
    assert State.THINKING in states
    assert State.SPEAKING in states
    assert states[-1] == State.IDLE
    # Émotion (repli) + audio synthétisé.
    assert ServerMsg.EMOTION in types
    assert ServerMsg.TTS_AUDIO in types
    # Métriques de latence présentes dans l'état final.
    final = [e for e in mgr.sent if e.type == ServerMsg.STATE][-1]
    assert "metrics" in final.payload


@pytest.mark.asyncio
async def test_five_turn_conversation(tmp_path):
    pipe, mgr = make_pipeline(tmp_path)
    ws = FakeWS()
    for i in range(5):
        await pipe.on_user_text(ws, f"Question {i}")
    # 5 tours → au moins 5 passages en SPEAKING et 5 retours IDLE.
    states = [e.payload["state"] for e in mgr.sent if e.type == ServerMsg.STATE]
    assert states.count(State.SPEAKING) >= 5
    assert states.count(State.IDLE) >= 5
    # L'historique contient les 10 tours (5 user + 5 assistant), bornés à 12.
    assert pipe.memory.count_turns() >= 10


@pytest.mark.asyncio
async def test_speech_segment_transcribes_and_responds(tmp_path):
    pipe, mgr = make_pipeline(tmp_path)
    ws = FakeWS()
    pcm = b"\x00\x01" * 16000  # 1 s de PCM factice
    await pipe.on_speech_segment(ws, pcm, 16000)
    assert ServerMsg.TRANSCRIPT in mgr.types()
    assert ServerMsg.TTS_AUDIO in mgr.types()


@pytest.mark.asyncio
async def test_barge_in_no_task_leak(tmp_path):
    # Cerveau lent pour avoir le temps d'interrompre.
    class SlowBrain(Brain):
        async def stream(self, user_text, history=None, cancel=None):
            for _ in range(50):
                if cancel and cancel.is_set():
                    return
                await asyncio.sleep(0.02)
                yield "[emo:neutre] mot "

    pipe, mgr = make_pipeline(tmp_path, brain=SlowBrain({"host": "http://127.0.0.1:1"}))
    ws = FakeWS()

    task = asyncio.ensure_future(pipe.on_user_text(ws, "raconte une longue histoire"))
    await asyncio.sleep(0.1)
    await pipe.interrupt(ws)
    await asyncio.gather(task, return_exceptions=True)

    # Aucune tâche en cours ne doit subsister pour cette session.
    assert not pipe._tasks.get(id(ws))
    # L'état final est idle.
    states = [e.payload["state"] for e in mgr.sent if e.type == ServerMsg.STATE]
    assert states[-1] == State.IDLE
