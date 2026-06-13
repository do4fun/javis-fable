"""Tests du module STT (F3.2).

Valident la normalisation et la conversion audio sans nécessiter le modèle
Whisper (le moteur Dummy suffit). Le WER réel est mesuré par bench_stt.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from modules.stt import (  # noqa: E402
    DummySTTEngine,
    STTService,
    normalize_transcript,
    pcm16_to_float,
)


def test_normalize_removes_hesitations():
    assert normalize_transcript("euh bonjour heu ça va") == "Bonjour ça va."


def test_normalize_capitalizes_and_punctuates():
    assert normalize_transcript("merci beaucoup") == "Merci beaucoup."
    # L'espace avant la ponctuation (artefact Whisper) est retiré.
    assert normalize_transcript("ça va ?") == "Ça va?"


def test_normalize_empty():
    assert normalize_transcript("") == ""
    assert normalize_transcript("   ") == ""


def test_pcm16_to_float_range():
    pcm = np.array([0, 32767, -32768], dtype="<i2").tobytes()
    f = pcm16_to_float(pcm)
    assert f.dtype == np.float32
    assert -1.0 <= f.min() and f.max() <= 1.0
    assert abs(f[1] - 1.0) < 1e-3


@pytest.mark.asyncio
async def test_service_dummy_transcribe():
    svc = STTService(DummySTTEngine(canned="euh bonjour jarvis"))
    pcm = np.zeros(16000, dtype="<i2").tobytes()
    text = await svc.transcribe_segment(pcm, 16000)
    assert text == "Bonjour jarvis."
