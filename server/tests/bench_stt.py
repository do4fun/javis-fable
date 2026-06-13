"""Bench STT (F3.2) : mesure le RTF (real time factor) et conseille la taille
de modèle. Si RTF > 0,8, on suggère de descendre d'un cran (small → base →
tiny) pour tenir le temps réel sur la machine.

Usage :
    python tests/bench_stt.py [chemin.wav]
    # sans argument : génère un bip synthétique de 5 s (RTF indicatif seulement)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from app import load_config  # noqa: E402
from modules.stt import make_stt_engine  # noqa: E402

SMALLER = {"large-v3": "medium", "medium": "small", "small": "base", "base": "tiny"}


def load_audio(path: str | None) -> tuple[np.ndarray, float]:
    if path:
        import soundfile as sf

        audio, sr = sf.read(path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != 16000:
            # rééchantillonnage grossier (suffisant pour un bench)
            idx = (np.arange(int(len(audio) * 16000 / sr)) * sr / 16000).astype(int)
            audio = audio[idx]
        return audio.astype(np.float32), len(audio) / 16000
    # Signal synthétique de 5 s (pas de vraie parole : RTF approximatif).
    dur = 5.0
    t = np.arange(int(dur * 16000)) / 16000
    return (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), dur


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = load_config().get("stt", {})
    engine = make_stt_engine(cfg)
    audio, dur = load_audio(path)

    t0 = time.perf_counter()
    text = engine.transcribe(audio, 16000)
    elapsed = time.perf_counter() - t0

    rtf = elapsed / dur if dur else 0
    print(f"Moteur     : {engine.name} ({getattr(engine, 'model_size', '-')})")
    print(f"Durée audio: {dur:.2f}s")
    print(f"Temps STT  : {elapsed:.2f}s")
    print(f"RTF        : {rtf:.2f} {'(OK)' if rtf <= 0.8 else '(LENT)'}")
    print(f"Texte      : {text!r}")

    if rtf > 0.8:
        size = getattr(engine, "model_size", "small")
        suggestion = SMALLER.get(size)
        if suggestion:
            print(f"⚠️  RTF > 0.8 : envisage le modèle '{suggestion}' (stt.model).")


if __name__ == "__main__":
    main()
