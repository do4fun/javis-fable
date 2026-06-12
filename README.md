<h1 align="center">Jarvis</h1>
<p align="center"><em>Un assistant vocal incarné par un avatar 3D — qui parle, écoute, ressent, et tourne entièrement sur ta machine.</em></p>

<p align="center">
  <img alt="statut" src="https://img.shields.io/badge/statut-en%20développement-orange">
  <img alt="local" src="https://img.shields.io/badge/100%25-local-2ea44f">
  <img alt="licence" src="https://img.shields.io/badge/licence-à%20définir-lightgrey">
</p>

-----

## ✨ Le projet

**Jarvis** est un avatar virtuel conversationnel pour le web. Il s’affiche
dans un navigateur (desktop et mobile), respire, cligne des yeux, te suit
du regard, **parle à voix haute** avec une voix naturelle et des lèvres
synchronisées, et tient une **vraie conversation** : il t’écoute, te
comprend et te répond.

Sa particularité : **rien ne quitte ta machine**. Pas d’API cloud, pas de
clé, pas d’abonnement. La voix, la reconnaissance vocale et l’intelligence
tournent toutes en local.

> ⚠️ Le projet est en cours de construction. La feuille de route détaillée,
> découpée en fonctionnalités intégrables, se trouve dans [`TODO.md`](./TODO.md).

## 🧩 Capacités cibles

| |Capacité                                       |Comment                              |
|-|-----------------------------------------------|-------------------------------------|
|🧍|Avatar 3D réaliste corps entier                |TalkingHead.js + Ready Player Me     |
|🌬️|Vie autonome (respiration, clignements, regard)|Moteur « Life » maison               |
|😀|Six émotions expressives                       |Blendshapes ARKit, transitions douces|
|🗣️|Voix naturelle française                       |Kokoro TTS (local) avec timestamps   |
|👄|Synchronisation labiale précise                |Visèmes Oculus pilotés par le timing |
|👂|Écoute mains-libres                            |Micro + Silero VAD + faster-whisper  |
|🧠|Conversation intelligente                      |Ollama (LLM local) en streaming      |
|💾|Mémoire & outils                               |SQLite local, heure/minuteur/calcul  |

## 🏗️ Architecture

```
        ┌──────────────────────────── Navigateur (/web) ───────────────────────────┐
        │  Three.js · TalkingHead · Avatar RPM · Life · Émotions · Lip-sync · UI    │
        └───────────────▲───────────────────────────────────────────────┬──────────┘
                        │   WebSocket (audio, tokens, visèmes, état)     │
        ┌───────────────┴───────────────────────────────────────────────▼──────────┐
        │                        Serveur local (/server · FastAPI)                  │
        │   VAD ▸ Whisper (STT) ▸ Ollama (LLM) ▸ Kokoro (TTS) ▸ Pipeline temps réel │
        └───────────────────────────────────────────────────────────────────────────┘
                        tout en localhost — aucune sortie réseau
```

Le détail du protocole et des budgets de latence vivra dans
`/docs/architecture.md` (voir F5.3).

## 🛠️ Stack technique

- **Frontend** : Vite, Three.js, [TalkingHead](https://github.com/met4citizen/TalkingHead), avatar Ready Player Me (GLB, blendshapes ARKit + visèmes Oculus)
- **Voix** : [Kokoro TTS](https://github.com/hexgrad/kokoro) (repli piper-tts)
- **Lip-sync** : module français de TalkingHead, repli audio-driven (HeadAudio / wawa-lipsync)
- **Écoute** : Silero VAD (ONNX, navigateur) + [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- **Cerveau** : [Ollama](https://ollama.com) (LLM local)
- **Orchestration** : Python 3.11+, FastAPI, WebSocket, SQLite

## 🚀 Démarrage rapide

> Le scaffolding arrive avec les fonctionnalités **F0.1** et **F0.2**.
> Cette section sera complétée au fur et à mesure ; voici la cible.

### Prérequis

- Node.js 20+ et Python 3.11+
- [Ollama](https://ollama.com) installé et lancé
- ~6 Go d’espace disque pour les modèles (Whisper, Kokoro, VAD, LLM)
- GPU recommandé mais non obligatoire (le projet s’adapte au CPU)

### Installation (cible F5.3)

```bash
git clone -b dev https://github.com/<ton-org>/jarvis-fable.git
cd jarvis-fable

# 1. Récupère le modèle de langage local
ollama pull llama3.1:8b        # ou le modèle défini dans server/config.yaml

# 2. Lance tout (vérifie venv, modèles, Ollama, puis ouvre le navigateur)
make start
```

Le premier lancement télécharge **une seule fois** les poids des modèles ;
ensuite, tout fonctionne **hors-ligne**.

## 🔒 Vie privée

Jarvis est conçu pour ne dépendre d’aucun service externe à l’exécution.
La voix, la transcription et le raisonnement se font sur ta machine. Le
seul accès réseau possible (météo, etc.) est **désactivé par défaut** et
verrouillé derrière un drapeau explicite. La mémoire est stockée localement
et effaçable par la commande « oublie tout ».

## 🗺️ Feuille de route

Tout est dans [`TODO.md`](./TODO.md) : 15 fonctionnalités réparties en 6
phases, chacune avec un prompt de développement exhaustif et des critères
d’acceptation. Ordre conseillé :

```
F0.1 ▸ F0.2 ▸ F1.1 ▸ F2.1 ▸ F2.2   →  démo « il parle »
       ▸ F1.3 ▸ F1.4 ▸ F3.1 ▸ F3.2 ▸ F4.1   →  démo « il converse »
              ▸ F4.2 ▸ F5.1 ▸ F5.2 ▸ F5.3   →  produit fini
```

## 🤝 Contribution

Travaille sur des branches dérivées de `dev`, une par fonctionnalité
(ex. `dev/f1.1-avatar`). Préfixe tes commits par l’ID de la fonctionnalité,
ex. `[F1.1] charge l'avatar RPM`. Mets à jour `TODO.md` et la doc à chaque
fonctionnalité livrée.

## 🙏 Crédits

Bâti sur le travail open source de **met4citizen** (TalkingHead /
HeadAudio), **Ready Player Me**, **Kokoro**, **faster-whisper**, **Silero
VAD** et **Ollama**. Merci à eux.

## 📄 Licence

À définir avant la première publication. Vérifie les licences respectives
des modèles et avatars avant toute distribution.
