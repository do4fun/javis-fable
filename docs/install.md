# Installation des modèles locaux

Jarvis fonctionne **hors-ligne à l'exécution**. Les poids des modèles se
téléchargent **une seule fois** lors de l'installation, puis plus aucun accès
réseau n'est nécessaire. Cette page regroupe ces téléchargements uniques.

## Vue d'ensemble

| Modèle            | Fonctionnalité | Taille indicative | Obligatoire ?              |
|-------------------|----------------|-------------------|----------------------------|
| Kokoro TTS (FR)   | F2.1 (voix)    | ~350 Mo           | recommandé (repli dispo)   |
| piper-tts (fr_FR) | F2.1 (repli)   | ~60 Mo            | optionnel                  |
| faster-whisper    | F3.2 (écoute)  | ~150–500 Mo       | requis pour la voix entrante |
| Silero VAD (ONNX) | F3.1 (VAD)     | ~2 Mo             | requis pour mains-libres   |
| LLM via Ollama    | F4.1 (cerveau) | ~4–5 Go           | requis pour converser      |

> Sans aucun modèle vocal, le TTS bascule automatiquement sur un moteur de
> repli (`dummy`, onde sinusoïdale) : utile pour développer, pas pour écouter.

## TTS — Kokoro (voix française)

```bash
cd server
.venv/Scripts/pip install kokoro soundfile   # Windows
# source .venv/bin/activate && pip install kokoro soundfile   # Unix
```

Au premier appel, Kokoro télécharge ses poids et la voix française
(`ff_siwis`). Renseigne le moteur dans `server/config.yaml` :

```yaml
tts:
  engine: kokoro
  voice: ff_siwis
  sample_rate: 24000
```

### Repli piper-tts (optionnel)

```bash
pip install piper-tts
# Télécharge une voix fr_FR (ex. fr_FR-siwis-medium) depuis les releases piper,
# place le .onnx en local, puis :
```

```yaml
tts:
  engine: piper
  piper_model: /chemin/local/fr_FR-siwis-medium.onnx
```

## STT — faster-whisper (F3.2)

```bash
pip install faster-whisper
```

Le modèle (`small` par défaut) est téléchargé au premier chargement et mis en
cache localement. Détaillé en F3.2.

## VAD — Silero (F3.1)

Le modèle ONNX (`silero_vad.onnx`) est vendorisé côté navigateur dans
`web/public/models/`. Récupère-le depuis le dépôt Silero VAD et dépose-le là
(non versionné).

## LLM — Ollama (F4.1)

```bash
# Installe Ollama depuis https://ollama.com puis :
ollama pull llama3.1:8b
```

Configuré dans `server/config.yaml` (section `llm`). Détaillé en F4.1.

## Vérifier le TTS sans navigateur

```bash
cd server
.venv/Scripts/python tests/tts_demo.py "Bonjour, je suis Jarvis."
# → écrit out.wav (avec le moteur configuré, ou le repli dummy)
```
