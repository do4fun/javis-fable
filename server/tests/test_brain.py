"""Tests du cerveau et du parseur de balises (F4.1).

Le parseur est testé en streaming (balises coupées entre tokens). Le repli
rule-based est testé sans réseau. Le client Ollama n'est pas sollicité ici.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import fallback_brain  # noqa: E402
from modules.tags import (  # noqa: E402
    EmotionEvent,
    GestureEvent,
    StreamTagParser,
    TextEvent,
)


def _collect(parser, chunks):
    events = []
    for c in chunks:
        events.extend(parser.feed(c))
    events.extend(parser.flush())
    return events


def test_parser_emotion_head_and_text():
    p = StreamTagParser()
    evs = _collect(p, ["[emo:joie] Salut !"])
    assert isinstance(evs[0], EmotionEvent) and evs[0].name == "joie"
    text = "".join(e.text for e in evs if isinstance(e, TextEvent))
    assert text.strip() == "Salut !"


def test_parser_tag_split_across_tokens():
    # La balise [geste:salut] arrive en plusieurs morceaux.
    p = StreamTagParser()
    evs = _collect(p, ["Bonjour [ges", "te:sal", "ut] à toi"])
    gestures = [e for e in evs if isinstance(e, GestureEvent)]
    assert len(gestures) == 1 and gestures[0].name == "salut"
    text = "".join(e.text for e in evs if isinstance(e, TextEvent))
    assert "[geste" not in text
    assert "Bonjour" in text and "à toi" in text


def test_parser_emotion_split_at_boundary():
    p = StreamTagParser()
    evs = _collect(p, ["[emo:", "reflexion", "] Hmm."])
    emos = [e for e in evs if isinstance(e, EmotionEvent)]
    assert emos and emos[0].name == "reflexion"


def test_fallback_greeting():
    out = fallback_brain.respond("Bonjour")
    assert out.startswith("[emo:")
    assert "Salut" in out


def test_fallback_time():
    out = fallback_brain.respond("Quelle heure est-il ?")
    assert "[emo:reflexion]" in out
    assert "heures" in out
