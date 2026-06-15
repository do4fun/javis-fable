#!/usr/bin/env python3
"""Démarrage en un clic de Jarvis (F5.3).

Vérifie les prérequis avec des messages pédagogiques, build le frontend si
besoin, contrôle Ollama et les modèles, puis lance le serveur et ouvre le
navigateur. Tout est local ; les vérifications « manquantes » n'empêchent pas
le lancement (Jarvis bascule sur ses replis), elles informent.

Usage : python scripts/start.py [--no-browser] [--port 8000]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
SERVER = ROOT / "server"
LOGS = ROOT / "logs"
LOG_FRONTEND = LOGS / "frontend.log"

GREEN, YELLOW, RED, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[0m"


def ok(msg: str) -> None:
    print(f"{GREEN}✓{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}!{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"{RED}✗{RESET} {msg}")


def venv_python() -> Path:
    p = SERVER / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
    return p / ("python.exe" if sys.platform == "win32" else "python")


def check_node() -> bool:
    if shutil.which("node"):
        ok("Node.js détecté.")
        return True
    fail("Node.js absent. Installe Node 20+ depuis https://nodejs.org puis relance.")
    return False


def ensure_venv() -> Path:
    py = venv_python()
    if py.exists():
        ok("Environnement Python prêt.")
        return py
    warn("Environnement Python absent — création…")
    subprocess.run([sys.executable, "-m", "venv", str(SERVER / ".venv")], check=True)
    subprocess.run(
        [str(py), "-m", "pip", "install", "-q", "-r", str(SERVER / "requirements.txt")],
        check=True,
    )
    ok("Dépendances serveur installées.")
    return py


def ensure_build() -> None:
    if (WEB / "dist" / "index.html").exists():
        ok("Frontend déjà buildé.")
        return
    warn("Frontend non buildé — build en cours (npm)…")
    LOGS.mkdir(parents=True, exist_ok=True)
    with LOG_FRONTEND.open("w", encoding="utf-8") as flog:
        if not (WEB / "node_modules").exists():
            subprocess.run(
                ["npm", "install"], cwd=WEB, shell=(sys.platform == "win32"),
                check=True, stdout=flog, stderr=flog,
            )
        subprocess.run(
            ["npm", "run", "build"], cwd=WEB, shell=(sys.platform == "win32"),
            check=True, stdout=flog, stderr=flog,
        )
    ok(f"Frontend buildé. (logs → {LOG_FRONTEND})")


def check_llm() -> None:
    """Vérifie le provider LLM configuré et la présence de ses prérequis."""
    import yaml  # disponible dans le venv (pyyaml)
    cfg_path = SERVER / "config.yaml"
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        warn("config.yaml illisible — vérification LLM ignorée.")
        return

    provider = (cfg.get("llm") or {}).get("provider", "ollama")

    if provider == "claude":
        key = os.environ.get("ANTHROPIC_API_KEY") or (cfg.get("llm") or {}).get("api_key", "")
        if key:
            ok(f"LLM : Claude ({(cfg.get('llm') or {}).get('model', '?')}) — clé API présente.")
        else:
            fail(
                "LLM : clé API Anthropic manquante !\n"
                "  → Définis la variable d'environnement ANTHROPIC_API_KEY avant de lancer :\n"
                "       $env:ANTHROPIC_API_KEY = 'sk-ant-...'\n"
                "  → Ou ajoute  api_key: 'sk-ant-...'  dans server/config.yaml (section llm).\n"
                "  → Jarvis tournera en MODE DÉGRADÉ (réponses statiques) jusqu'à ce que la clé soit fournie."
            )
    else:  # ollama
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2):
                ok("LLM : Ollama actif.")
        except Exception:
            warn(
                "LLM : Ollama injoignable. Installe-le (https://ollama.com), lance le service "
                "et `ollama pull llama3.1:8b`. En attendant, Jarvis utilise un cerveau de repli."
            )


def check_models() -> None:
    checks = {
        "VAD Silero (web/public/models/silero_vad.onnx)": WEB / "public" / "models" / "silero_vad.onnx",
        "Avatar GLB (web/public/avatars/jarvis.glb)": WEB / "public" / "avatars" / "jarvis.glb",
        "Avatar VRM (web/public/avatars/jarvis.vrm)": WEB / "public" / "avatars" / "jarvis.vrm",
    }
    for label, path in checks.items():
        (ok if path.exists() else warn)(
            f"{label} : {'présent' if path.exists() else 'absent (repli actif, voir docs/install.md)'}"
        )


def launch(py: Path, port: int, open_browser: bool) -> None:
    if open_browser:
        def _open():
            time.sleep(2.0)
            webbrowser.open(f"http://localhost:{port}")

        threading.Thread(target=_open, daemon=True).start()

    print(f"\n{GREEN}Jarvis démarre sur http://localhost:{port}{RESET}  (Ctrl+C pour arrêter)\n")
    subprocess.run(
        [str(py), "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=SERVER,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    print("— Vérification des prérequis de Jarvis —\n")
    if not check_node():
        sys.exit(1)
    py = ensure_venv()
    ensure_build()
    check_llm()
    check_models()
    launch(py, args.port, not args.no_browser)


if __name__ == "__main__":
    main()
