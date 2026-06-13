# Architecture de Jarvis

Vue d'ensemble technique : pipeline temps réel, protocole WebSocket, budgets de
latence et matrice de compatibilité. Contrainte transverse : **100 % local,
aucune sortie réseau à l'exécution**.

## Schéma du pipeline

```
   Navigateur (/web)                         Serveur local (/server, FastAPI)
 ┌───────────────────────┐    WebSocket    ┌──────────────────────────────────┐
 │ Micro → AudioWorklet  │  audio_chunk    │  /ws  ──► buffer PCM 16 kHz        │
 │  (PCM 16 kHz, 30 ms)  │ ───(binaire)──► │         │ (marqueurs VAD start/end)│
 │ VAD Silero/énergie    │                 │         ▼                          │
 │                       │                 │   STT faster-whisper (fr)          │
 │                       │  transcript     │         │  → transcript            │
 │  Sous-titres (HUD)    │ ◄────────────── │         ▼                          │
 │                       │                 │   Pipeline (machine à états)       │
 │                       │  state          │   idle→listening→thinking→speaking │
 │                       │ ◄────────────── │         ▼                          │
 │  Émotions / gestes    │ emotion/gesture │   Cerveau Ollama (streaming)       │
 │  (TalkingHead)        │ ◄────────────── │   parseur balises [emo]/[geste]    │
 │                       │  llm_token      │         │  (texte propre)          │
 │  Lip-sync (visèmes)   │ ◄────────────── │         ▼ découpe en phrases        │
 │  Web Audio (horloge)  │  tts_audio      │   TTS Kokoro/Piper/Dummy           │
 │                       │ ◄────────────── │   (PCM + timestamps par mot)       │
 └───────────────────────┘                 │   Mémoire SQLite (profil/historique)│
                                           └──────────────────────────────────┘
              Barge-in : interrupt  ──►  annule STT/LLM/TTS à n'importe quel stade
```

## Protocole WebSocket

Toutes les trames : enveloppe `{type, id, payload, ts}` (`server/core/protocol.py`,
`web/src/ws.js`). `id` corrèle requête/réponse ; `ts` est l'horodatage epoch ms.

### Client → serveur

| type          | payload                                  | rôle                              |
|---------------|------------------------------------------|-----------------------------------|
| `user_text`   | `{text}`                                 | message clavier                   |
| `audio_chunk` | `{event:"start"\|"end", sample_rate}`    | bornes VAD (+ trames binaires PCM)|
| `interrupt`   | `{}`                                     | barge-in : couper la parole       |
| `config`      | `{voice, speed, model, …}`               | réglages                          |

Les **trames binaires** (entre `start` et `end`) sont du PCM int16 mono 16 kHz.

### Serveur → client

| type         | payload                                            | rôle                          |
|--------------|----------------------------------------------------|-------------------------------|
| `state`      | `{state, trace?, metrics?}`                         | machine à états + métriques   |
| `transcript` | `{text, final}`                                     | transcription STT             |
| `llm_token`  | `{token}`                                           | texte propre en flux          |
| `emotion`    | `{name, intensity}`                                 | émotion d'avatar              |
| `gesture`    | `{name}`                                            | geste ponctuel                |
| `tts_audio`  | `{index, text, sample_rate, audio(b64), words[]}`   | audio synthétisé + timings    |
| `error`      | `{reason}`                                          | erreur lisible                |

## Machine à états (serveur)

`idle → listening → thinking → speaking → idle` (`server/core/pipeline.py`).
Chaque transition est diffusée au client (`state`) pour piloter l'UI et les
attitudes de l'avatar. Un `Turn` porte un `trace_id` et des jalons de latence.

## Budgets de latence

Mesurés par maillon (`trace_id` par tour), affichés dans le panneau `?debug`.

| Maillon                         | Cible CPU | Cible GPU |
|---------------------------------|-----------|-----------|
| Fin de parole → texte (STT)     | < 1,5 s   | < 0,6 s   |
| Texte → 1er token LLM           | < 1,0 s   | < 0,4 s   |
| **Fin de parole → 1er son**     | **< 2,5 s** | **< 1,5 s** |

Leviers : streaming phrase par phrase (1er son dès la 1re phrase), modèles plus
petits si RTF > 0,8 (`bench_stt.py`), profils de qualité graphique auto.

## Replis (jamais d'échec dur)

| Composant | Principal        | Repli automatique                |
|-----------|------------------|----------------------------------|
| TTS       | Kokoro (fr)      | Piper → Dummy (onde, hors-modèle)|
| STT       | faster-whisper   | Dummy (texte vide)               |
| VAD       | Silero (ONNX)    | énergétique (RMS adaptatif)      |
| Cerveau   | Ollama (LLM)     | rule-based (`fallback_brain`)    |

## Matrice de compatibilité navigateurs

| Navigateur        | WebGL2 | AudioWorklet | WebSocket | Statut          |
|-------------------|--------|--------------|-----------|-----------------|
| Chrome/Edge ≥ 110 | ✅     | ✅           | ✅        | recommandé      |
| Firefox ≥ 110     | ✅     | ✅           | ✅        | supporté        |
| Safari ≥ 16       | ✅     | ✅           | ✅        | supporté (iOS : geste requis pour l'audio) |

## Performance & packaging

- Profils qualité auto (`web/src/quality.js`) : pixelRatio, ombres, fréquence du
  LifeEngine, densité de poussière ajustés selon GPU/CPU ; cible ≥ 30 fps mobile.
- Démarrage en un clic : `make start` (ou `start.ps1`) → vérifie venv, build,
  Ollama, modèles, lance le serveur et ouvre le navigateur.
- `docker-compose.yml` : serveur + Ollama, volumes pour les poids (GPU optionnel).
- Suite qualité : `make check` (ESLint + vitest + build côté web ; ruff + pytest
  côté serveur). Test de fumée headless Playwright optionnel (`web/test/e2e`).
