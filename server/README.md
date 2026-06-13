# /server — Orchestration Jarvis (FastAPI + WebSocket)

Colonne vertébrale qui reliera STT, LLM et TTS au navigateur. 100 % local.

## Installation

```bash
cd server
python -m venv .venv
# Windows :  .venv\Scripts\Activate.ps1
# Unix    :  source .venv/bin/activate
pip install -r requirements.txt
```

## Lancer

```bash
make run            # ou : make dev (rechargement à chaud)
# Windows sans make :
#   ./run.ps1        (ajoute -Reload pour le mode dev)
```

Le serveur écoute sur <http://localhost:8000> :

- `GET /health` → état du service ;
- `WS  /ws`     → protocole d'enveloppe typé ;
- `/`           → sert le build frontend `web/dist` (lance d'abord
  `cd web && npm run build`). En dev, on utilise plutôt Vite (port 5173).

## Protocole WebSocket

Toutes les trames : `{type, id, payload, ts}` (voir `core/protocol.py`).

| Sens            | Types                                              |
|-----------------|----------------------------------------------------|
| client→serveur  | `user_text`, `audio_chunk`, `interrupt`, `config`  |
| serveur→client  | `state`, `llm_token`, `tts_audio`, `visemes`, `transcript`, `emotion`, `error` |

À ce stade (F0.2), les types non encore implémentés sont des *stubs* qui
accusent réception via un message `state`. Le bus `core/bus.py` (asyncio
pub/sub) chaînera les vrais modules dans les fonctionnalités suivantes.

## Tester

```bash
make test                       # pytest (contrat du protocole)
python tests/ws_echo.py "Salut" # client manuel (serveur lancé à part)
```

Aucune connexion Internet n'est requise.
