"""Démo TTS hors navigateur (F2.1) : écrit un WAV + affiche les timings.

Usage :
    python tests/tts_demo.py "Bonjour, je suis Jarvis." [out.wav]

Utilise le moteur configuré dans config.yaml (Kokoro si installé), sinon le
repli `dummy`. Aucune connexion réseau.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import soundfile as sf  # noqa: E402

from app import load_config  # noqa: E402
from modules.tts import make_engine  # noqa: E402


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else "Bonjour, je suis Jarvis."
    out = sys.argv[2] if len(sys.argv) > 2 else "out.wav"

    engine = make_engine(load_config().get("tts"))
    print(f"Moteur : {engine.name}")
    res = engine.synthesize(text)

    sf.write(out, res.audio, res.sample_rate)
    print(f"Écrit {out} — {res.duration:.2f}s @ {res.sample_rate} Hz")
    for w in res.words:
        print(f"  [{w.start:6.2f} → {w.end:6.2f}] {w.word}")


if __name__ == "__main__":
    main()
