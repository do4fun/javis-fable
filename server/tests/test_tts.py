"""Tests du module TTS (F2.1).

On valide la logique d'interface et l'alignement des timestamps avec le moteur
``DummyEngine`` (toujours dispo, sans modèle, hors-ligne). Le test d'alignement
exigé par la fonctionnalité vérifie que la somme des durées de mots ≈ durée
audio (±5 %).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from modules.tts import (  # noqa: E402
    DummyEngine,
    TTSService,
    reconstruct_word_times,
    split_sentences,
)


def test_split_sentences():
    s = split_sentences("Bonjour. Comment vas-tu ? Très bien !")
    assert s == ["Bonjour.", "Comment vas-tu ?", "Très bien !"]


def test_reconstruct_alignment_exact():
    words = reconstruct_word_times("un deux trois", total_duration=3.0)
    assert len(words) == 3
    # La somme des durées vaut exactement la durée totale.
    total = sum(w.end - w.start for w in words)
    assert abs(total - 3.0) < 1e-6
    # Les bornes s'enchaînent sans trou ni recouvrement.
    assert words[0].start == 0.0
    for a, b in zip(words, words[1:]):
        assert abs(a.end - b.start) < 1e-6


def test_dummy_engine_words_match_audio_duration():
    eng = DummyEngine()
    res = eng.synthesize("Jarvis parle français couramment aujourd'hui")
    assert res.sample_rate == 24000
    assert res.duration > 0
    assert len(res.words) == 5
    # Alignement : fin du dernier mot ≈ durée audio (±5 %).
    last_end = res.words[-1].end
    assert abs(last_end - res.duration) / res.duration < 0.05


def test_int16_bytes_roundtrip():
    res = DummyEngine().synthesize("test")
    raw = res.to_int16_bytes()
    # 2 octets par échantillon.
    assert len(raw) == len(res.audio) * 2


@pytest.mark.asyncio
async def test_service_stream_sentences():
    svc = TTSService(DummyEngine())
    chunks = []
    async for c in svc.stream("Salut. Ça va ? Oui."):
        chunks.append(c)
    assert [c.text for c in chunks] == ["Salut.", "Ça va ?", "Oui."]
    assert all(c.result.duration > 0 for c in chunks)


@pytest.mark.asyncio
async def test_service_cancel():
    svc = TTSService(DummyEngine())
    out = []
    async for c in svc.stream("Phrase une. Phrase deux. Phrase trois."):
        out.append(c)
        svc.cancel()  # on coupe après la première phrase
    assert len(out) == 1
