# TODO — Avatar virtuel interactif « Jarvis »

**Repo :** `jarvis-fable` · **Branche de travail :** `dev` · **Contrainte globale : 100 % local, zéro API cloud**

**Stack cible :** TalkingHead.js (met4citizen) + avatar Ready Player Me (GLB) · Three.js · Kokoro TTS (voix FR, timestamps) · faster-whisper (STT) · Ollama (LLM) · FastAPI + WebSocket (orchestration)

Chaque fonctionnalité ci-dessous est autonome et intégrable séparément. Le bloc `PROMPT` de chaque fonctionnalité est conçu pour être donné tel quel à un agent de développement (ex. Claude Code) sur la branche `dev`.

**Préambule commun à injecter avant chaque prompt :**

> Tu travailles sur le repo `jarvis-fable`, branche `dev`. Lis d’abord le README et la structure existante avant de coder. Contrainte absolue : aucune dépendance à un service cloud à l’exécution (pas d’API externe, pas de clé). Tout doit tourner sur la machine locale. Code commenté en français, commits atomiques préfixés par l’ID de la fonctionnalité (ex. `[F1.1]`). Termine chaque tâche par : mise à jour du README, instructions de test manuel, et coche la case correspondante dans TODO.md.

-----

## PHASE 0 — Fondations

### ☑ F0.1 — Scaffolding frontend (Vite + Three.js + TalkingHead)

**But :** base web qui affiche une scène 3D vide, prête à recevoir l’avatar.
**Dépend de :** rien.
**Statut :** livré. Frontend Vite vanilla dans `/web` (scene.js, main.js, config.js),
ESLint + Prettier, `three` épinglé, dossier `/web/vendor` documenté (import map de
secours hors-ligne). `npm run build` produit un `dist/` autonome.
**Test manuel :** `cd web && npm install && npm run dev` → scène éclairée + écran de
chargement qui disparaît ; `npm run build && npm run preview` → bundle statique sans
réseau (vérifier l'onglet Network : aucune requête externe).

```
PROMPT F0.1
Initialise la partie frontend du projet dans /web :
1. Projet Vite vanilla JS (pas de framework lourd), ESLint + Prettier.
2. Installe three (version compatible TalkingHead, voir doc du repo
   met4citizen/TalkingHead) et le module talkinghead via npm, avec un
   import map de secours documenté. Vendorise les modules dans
   /web/vendor pour garantir un fonctionnement hors-ligne (aucun CDN
   à l'exécution).
3. Crée /web/src/scene.js : renderer WebGL plein écran, caméra
   PerspectiveCamera cadrée buste, pixelRatio plafonné à 2, resize
   responsive (desktop + mobile, viewport-fit=cover).
4. Crée /web/src/main.js : boucle requestAnimationFrame avec deltaTime,
   gestion visibilitychange (pause du rendu en arrière-plan).
5. Page index.html minimaliste : canvas + zone UI vide (#hud).
Critères d'acceptation : `npm run dev` affiche une scène éclairée à 60
fps sur desktop et mobile, `npm run build` produit un bundle 100 %
autonome servable par un simple serveur statique sans Internet.
```

### ☑ F0.2 — Serveur local d’orchestration (FastAPI + WebSocket)

**But :** colonne vertébrale qui reliera STT, LLM et TTS au navigateur.
**Dépend de :** rien.
**Statut :** livré. `/server` (FastAPI + uvicorn) : WebSocket `/ws` avec enveloppe
typée `{type,id,payload,ts}` (`core/protocol.py`), bus asyncio (`core/bus.py`),
service statique de `web/dist`, CORS limité à localhost, logs structurés,
déconnexions propres. `make run` / `run.ps1` pour lancer, `make test` pour pytest.
**Test manuel :** `cd server && make run` puis `python tests/ws_echo.py "Salut"`
→ état `idle` initial puis accusé `thinking`. `make test` → 5 tests verts, zéro réseau.

```
PROMPT F0.2
Crée la partie serveur dans /server (Python 3.11+, FastAPI, uvicorn) :
1. requirements.txt + venv documenté + script make/justfile `run`.
2. Endpoint WebSocket /ws : protocole JSON typé avec enveloppe
   {type, id, payload, ts}. Types prévus (stubs pour l'instant) :
   client→serveur : user_text, audio_chunk, interrupt, config ;
   serveur→client : state, llm_token, tts_audio, visemes, error.
3. Sert le build frontend (/web/dist) en statique sur http://localhost:8000.
4. Module /server/core/bus.py : petit bus d'événements asynchrone
   (asyncio) pour chaîner les futurs modules stt→llm→tts.
5. Gestion propre des déconnexions, logs structurés, CORS limité à
   localhost.
Critères d'acceptation : un client de test (script /server/tests/
ws_echo.py) envoie user_text et reçoit un state ack ; pytest passe ;
tout fonctionne sans connexion Internet.
```

-----

## PHASE 1 — Avatar & rendu

### ☑ F1.1 — Intégration TalkingHead + avatar Ready Player Me

**But :** un humain 3D corps entier, réaliste, visible dans le navigateur.
**Dépend de :** F0.1.
**Statut :** livré. `web/src/avatar.js` (`AvatarManager`) instancie TalkingHead via
import dynamique vendorisé (`@vite-ignore` → build autonome), charge `jarvis.glb`
local, expose `load/speak/setMood/lookAt/playGesture/stop/setView`, loggue un
rapport de compatibilité des morph targets, écran de chargement avec barre de
progression et repli lisible si le GLB/module manque. Procédure d'export RPM
(ARKit + visèmes Oculus) dans `docs/avatar.md`.
**Test manuel :** déposer `talkinghead.mjs` (vendor) + `jarvis.glb` (public/avatars),
ajouter l'import map (docs/avatar.md), puis `npm run dev` → avatar visible, idle
natif actif, aucune requête réseau externe. Sans assets : message d'aide + scène
de démonstration.

```
PROMPT F1.1
Intègre la classe TalkingHead (met4citizen) dans /web :
1. Crée /web/src/avatar.js : wrapper AvatarManager qui instancie
   TalkingHead dans le canvas existant et expose une API simple :
   load(url), speak(audio, visemes), setMood(name), lookAt(x,y),
   playGesture(name), stop().
2. Charge un avatar Ready Player Me corps entier au format GLB depuis
   /web/public/avatars/jarvis.glb (fichier local, PAS d'URL
   readyplayer.me à l'exécution). Documente dans /docs/avatar.md la
   procédure de création/export RPM avec morph targets ARKit + visèmes
   Oculus (paramètres d'URL d'export morphTargets=ARKit,Oculus%20Visemes)
   et le dépôt du fichier en local.
3. Pose caméra « assistant » : cadrage tête-épaules par défaut, plan
   américain en option (toggle), transitions douces.
4. Écran de chargement avec barre de progression et gestion d'erreur
   lisible si le GLB est absent (message expliquant comment l'ajouter).
5. Vérifie que les morph targets requis sont présents au chargement et
   loggue un rapport de compatibilité (liste des blendshapes manquants).
Critères d'acceptation : l'avatar s'affiche, idle par défaut de
TalkingHead actif, 60 fps desktop / ≥30 fps mobile milieu de gamme,
aucune requête réseau externe dans l'onglet Network.
```

### ☑ F1.2 — Environnement 3D de l’assistant

**But :** un décor cohérent, léger, qui situe l’avatar.
**Dépend de :** F1.1.
**Statut :** livré. `web/src/environment.js` (`Environment`) : éclairage 3 points
(key chaude, fill froide, rim) + ambiance, ombres douces desktop uniquement
(détection UA), sol à dégradé radial généré par canvas (≤ 512 px, zéro asset
réseau), particules de poussière animées, IBL optionnelle via HDRI locale
(ignorée si absente). 2 presets `jour`/`nuit` dans `config.js`, panneau debug
lil-gui (bundlé local) activé par `?debug`. Appliqué à la scène de repli et, en
best-effort, à la scène interne de TalkingHead.
**Test manuel :** rendu cohérent ; bascule jour/nuit via `?debug` ; aucun asset
chargé depuis Internet (onglet Network) ; FPS stable.

```
PROMPT F1.2
Construis l'environnement dans /web/src/environment.js :
1. Éclairage trois points (key chaude, fill froide, rim) + ambiance ;
   ombres douces uniquement sur desktop (détection GPU simple).
2. Décor minimaliste généré procéduralement ou via assets locaux
   libres (CC0, à placer dans /web/public/env) : sol avec dégradé
   radial, panneau/fond flouté, particules de poussière subtiles.
3. Mode « pièce » optionnel : skybox/HDRI locale basse résolution pour
   l'image-based lighting (fichier .hdr dans le repo).
4. Paramètres regroupés dans /web/src/config.js (couleurs, intensités)
   + un petit panneau de debug (lil-gui, vendorisé) activable par ?debug.
5. Budget perf : < 150k triangles décor compris, textures ≤ 1024px.
Critères d'acceptation : rendu cohérent jour/nuit (2 presets), aucun
asset chargé depuis Internet, FPS inchangé à ±10 % par rapport à F1.1.
```

### ☑ F1.3 — Comportements autonomes (vie)

**But :** respiration, clignements, contact visuel, micro-mouvements.
**Dépend de :** F1.1.
**Statut :** livré. `web/src/life.js` (`LifeEngine`) délègue clignement/respiration/
sway/idle à TalkingHead (configurés, non réimplémentés) et complète : suivi du
regard au pointeur/toucher via `lookAt` + lissage, limites anatomiques, retour
caméra après 2 s, saccades oculaires, gestes ambiants aléatoires (20–60 s, en
retrait pendant la parole), clignements accrus en état « réflexion ». Respecte
`prefers-reduced-motion` (amplitudes réduites). Réglages dans `config.js`.
**Test manuel :** avatar regardé 60 s sans interaction → aucune pose figée ; le
regard suit le pointeur/doigt puis revient à la caméra après 2 s.

```
PROMPT F1.3
Crée /web/src/life.js, un module LifeEngine branché sur AvatarManager :
1. Audite d'abord ce que TalkingHead gère nativement (clignement,
   respiration, sway) et ne réimplémente PAS ce qui existe : configure-le.
   Complète uniquement les manques.
2. Contact visuel : la tête et les yeux suivent le pointeur/le toucher
   via lookAt, avec lissage (lerp), limites anatomiques, et retour au
   regard caméra après 2 s d'inactivité du pointeur. Saccades oculaires
   aléatoires de faible amplitude.
3. Clignements : intervalle aléatoire 2–6 s, double-clignement
   occasionnel, fréquence accrue en état « réflexion ».
4. Respiration : cycle 3,5–4,5 s visible sur le torse, amplitude réduite
   pendant la parole.
5. Idle vivant : micro-rotations de tête (bruit de Perlin), transferts
   de poids occasionnels, gestes ambiants Mixamo locaux (/web/public/
   anims/*.fbx) joués aléatoirement toutes les 20–60 s.
6. Respecte prefers-reduced-motion (amplitudes réduites).
Critères d'acceptation : avatar regardé 60 s sans interaction = aucune
pose figée perceptible ; le regard suit le doigt sur mobile ; tout est
paramétrable dans config.js.
```

### ☑ F1.4 — Système d’émotions

**But :** six états émotionnels expressifs et des transitions naturelles.
**Dépend de :** F1.3.
**Statut :** livré. `web/src/emotions.js` (`EmotionEngine`) : machine à 6 états
(neutre, joie, tristesse, surprise, colere, reflexion), presets blendshapes ARKit
+ mood TalkingHead + geste d'entrée. `setEmotion(name,{intensity,holdMs,transitionMs})`,
transitions easeInOut 400–800 ms, retour auto au neutre après holdMs (défaut 6 s).
Couche additive : n'écrit que les morphs d'expression, jamais les visèmes
(priorité visèmes > émotion > idle), jawOpen inhibé pendant la parole. Écoute le
bus WebSocket `emotion` (préparé pour F4.1). Page `web/test/emotions.html`
(6 boutons + slider).
**Test manuel :** ouvrir `/test/emotions.html`, cliquer chaque émotion + régler
l'intensité ; chaque état identifiable, transitions sans cassure pendant la parole.

```
PROMPT F1.4
Crée /web/src/emotions.js :
1. Machine à états : neutre, joie, tristesse, surprise, colere,
   reflexion. Chaque état = preset de moods/blendshapes TalkingHead
   (sourcils, paupières, bouche, inclinaison de tête) + éventuel geste.
2. API : setEmotion(name, {intensity 0..1, holdMs}). Transitions
   interpolées 400–800 ms, retour automatique au neutre après holdMs
   (défaut 6000), avec décroissance douce.
3. Couche additive : les émotions se superposent au lip-sync et aux
   comportements de F1.3 sans les écraser (priorités définies :
   visèmes > émotion > idle).
4. Écoute le bus WebSocket : message {type:"emotion", payload:{name,
   intensity}} déclenche l'émotion (préparation pour F4.1).
5. Page de test /web/test/emotions.html avec 6 boutons + slider
   d'intensité pour validation visuelle.
Critères d'acceptation : chaque émotion est identifiable en aveugle
par un testeur ; aucune « cassure » visible pendant les transitions,
y compris pendant que l'avatar parle.
```

-----

## PHASE 2 — Voix & synchronisation labiale

### ☑ F2.1 — TTS local Kokoro (français, timestamps)

**But :** voix naturelle générée sur la machine, avec timing par mot.
**Dépend de :** F0.2.
**Statut :** livré. `server/modules/tts.py` : moteurs enfichables (Kokoro principal,
Piper repli, Dummy toujours dispo), `synthesize(text) → {audio 24kHz, words}`,
reconstruction des timestamps au prorata des mots, découpe en phrases, streaming
phrase par phrase avec annulation (barge-in via `interrupt`). Câblé au WebSocket :
`user_text` → `state:speaking` → `tts_audio` (PCM int16 base64 + words) → `idle`.
Téléchargement des poids documenté dans `docs/install.md`.
**Test manuel :** `python tests/tts_demo.py "Bonjour"` → WAV + timings ; `make test`
→ alignement vérifié (somme durées ≈ durée audio ±5 %), streaming et annulation.

```
PROMPT F2.1
Implémente /server/modules/tts.py autour de Kokoro TTS :
1. Installation locale du modèle (kokoro + voix française, ex. voix
   ff_siwis ou équivalente) ; documente le téléchargement unique des
   poids dans /docs/install.md (ensuite tout est hors-ligne).
2. API interne : synthesize(text) -> {audio: wav/pcm 24kHz, words:
   [{word, start, end}]}. Si Kokoro ne fournit pas nativement les
   timestamps au mot, utilise les durées par token/phonème exposées
   par le pipeline pour les reconstruire, et écris un test qui vérifie
   l'alignement (somme des durées ≈ durée audio ±5 %).
3. Streaming : découpe le texte en phrases, synthétise et envoie au
   client phrase par phrase (messages tts_audio en base64 ou binaire
   WebSocket) pour réduire la latence du premier son < 1,5 s.
4. File d'attente avec annulation (message interrupt) : toute synthèse
   en cours s'arrête proprement.
5. Fallback configurable : si Kokoro indisponible, basculer sur piper-tts
   (voix fr_FR locale) avec la même interface.
Critères d'acceptation : POST de test /server/tests/test_tts.py génère
un WAV français intelligible + timestamps cohérents, sans réseau.
```

### ☑ F2.2 — Lip-sync précis côté client

**But :** lèvres parfaitement synchronisées sur la voix locale.
**Dépend de :** F1.1, F2.1.
**Statut :** livré. `web/src/lipsync.js` : voie principale (texte+timing) qui
reconstruit un AudioBuffer depuis `tts_audio` (PCM base64) et délègue à
TalkingHead `speakAudio({audio, words, wtimes, wdurations})` (lipsyncLang fr,
horloge AudioContext unique) ; voie de secours audio-driven (`audioVisemes.js`,
AnalyserNode → jawOpen + voyelle, lissage/co-articulation) quand `words` absent ;
accentuation (hochement) sur mots longs ; `stop()` coupe l'audio et neutralise la
bouche (`viseme_sil`) en < 100 ms. Client WS frontend (`ws.js`) ajouté.
**Test manuel :** avatar chargé, console `jarvis.say("Bonjour, je suis Jarvis.")`
→ l'avatar parle, lèvres calées ; couper via `jarvis.interrupt()`. Repli testable
en envoyant un `tts_audio` sans `words`.

```
PROMPT F2.2
Implémente la chaîne de visèmes dans /web/src/lipsync.js :
1. Voie principale (pilotée par texte+timing) : à réception de
   {tts_audio, words}, utilise le module lip-sync FRANÇAIS de
   TalkingHead (lipsyncLang:"fr") via speakAudio({audio, words,
   wtimes, wdurations}) pour convertir mots→visèmes Oculus calés sur
   les timestamps. Lecture via Web Audio API avec horloge unique
   (AudioContext.currentTime) comme source de vérité.
2. Voie de secours (pilotée par l'audio) : module audio-driven type
   HeadAudio/wawa-lipsync (vendorisé) qui déduit les visèmes du signal
   en temps réel — utilisée si words est absent.
3. Co-articulation : lissage entre visèmes consécutifs, fermeture
   nette sur P/B/M, et retour à 'sil' en fin de phrase.
4. Synchronise aussi : amplitude de la voix → léger hochement de tête
   et accentuation des sourcils sur les mots longs (>600 ms).
5. Gestion de l'interruption : stop audio + retour bouche neutre < 100 ms.
Critères d'acceptation : sur une phrase test de 15 mots, le décalage
audio/lèvres perçu est imperceptible (< 80 ms mesuré par log
horodaté) ; la voie de secours fonctionne avec un simple fichier MP3.
```

-----

## PHASE 3 — Écoute

### ☑ F3.1 — Capture micro + détection de voix (VAD)

**But :** écouter l’utilisateur sans bouton à maintenir.
**Dépend de :** F0.2.
**Statut :** livré. AudioWorklet `web/public/worklets/pcm16k-worklet.js` (PCM 16 kHz
mono, trames 30 ms). `web/src/vad.js` : Silero VAD (ONNX via onnxruntime-web
vendorisé) avec repli énergétique automatique hors-ligne. `web/src/mic.js`
(`MicCapture`) : modes PTT/toggle/mains-libres, envoi binaire des trames pendant la
parole + marge 300 ms, marqueurs VAD start/end, barge-in (interrupt si l'avatar
parle), avatar « réflexion » à l'écoute. Serveur : la boucle `/ws` accepte
désormais texte ET binaire ; `audio_chunk` start/end bufferise et publie
`speech_segment` (consommé par le STT en F3.2).
**Test manuel :** clic sur le bouton micro → permission ; parler → indicateur de
parole, audio envoyé uniquement pendant la parole (binaire), refus micro → message
clair + repli clavier. Aucune donnée hors localhost.

```
PROMPT F3.1
Implémente la capture dans /web/src/mic.js :
1. getUserMedia + AudioWorklet : capture PCM 16 kHz mono, envoi en
   chunks binaires de 30 ms sur le WebSocket (type audio_chunk).
2. VAD local : intègre Silero VAD en ONNX via onnxruntime-web
   (modèle vendorisé dans /web/public/models) ; n'envoie l'audio au
   serveur que pendant la parole + 300 ms de marge.
3. Modes : push-to-talk (maintien du bouton micro), toggle, et
   mains-libres (VAD continu) — sélection dans les réglages.
4. UX d'état : indicateur visuel écoute/parole détectée ; l'avatar
   prend l'émotion « réflexion » et incline la tête quand il écoute.
5. Barge-in : si l'utilisateur parle pendant que l'avatar parle,
   émettre interrupt (l'avatar se tait et écoute).
Critères d'acceptation : aucune donnée micro envoyée hors de
localhost ; le VAD déclenche en < 200 ms ; permission micro refusée =
message clair + repli clavier.
```

### ☑ F3.2 — Transcription locale Whisper

**But :** comprendre la parole en français, sur la machine.
**Dépend de :** F3.1, F0.2.
**Statut :** livré. `server/modules/stt.py` : `WhisperEngine` (faster-whisper,
modèle `small` par défaut, langue `fr` forcée, int8 CPU) + `DummySTTEngine` de
repli. Normalisation (hésitations « euh », ponctuation, capitale), conversion
PCM int16→float32. `STTService.transcribe_segment` en thread. Abonné au bus
`speech_segment` (F3.1) → émet `transcript {text, final}` puis publie
`transcript_final` (pour F4.1) ; à défaut de cerveau, démo voix↔voix (synthèse du
texte transcrit). Bench RTF `tests/bench_stt.py` (suggère un modèle plus petit si
RTF > 0,8).
**Test manuel :** `python tests/bench_stt.py mon.wav` → RTF + texte ; `make test`
→ normalisation et conversion validées (moteur Dummy, sans modèle).

```
PROMPT F3.2
Implémente /server/modules/stt.py avec faster-whisper :
1. Modèle small (ou base selon CPU/GPU détecté), langue forcée fr,
   chargement au démarrage, poids stockés localement (documente le
   téléchargement unique).
2. Transcription par segments : à la fin d'un segment de parole (signal
   VAD du client), transcrit le buffer et émet {type:"transcript",
   payload:{text, final:true}}. Option transcription partielle toutes
   les 1,5 s pour affichage live (final:false).
3. Normalisation : ponctuation, nombres en chiffres, suppression des
   hésitations ("euh").
4. Bench : script /server/tests/bench_stt.py qui mesure le RTF (real
   time factor) et choisit automatiquement la taille de modèle si
   RTF > 0,8.
5. Le transcript final est poussé sur le bus vers le module LLM (F4.1).
Critères d'acceptation : phrase française de 10 s transcrite avec
< 10 % WER sur voix claire, latence fin-de-parole→texte < 1,5 s sur
CPU moderne, zéro appel réseau.
```

-----

## PHASE 4 — Intelligence

### ☑ F4.1 — Cerveau Ollama (streaming + balises d’expression)

**But :** réponses intelligentes, expressives, en flux.
**Dépend de :** F0.2.
**Statut :** livré. `server/modules/brain.py` : client Ollama streaming (`/api/chat`),
vérification de disponibilité au démarrage (message « ollama pull »), persona
`server/prompts/system.md`, annulation totale sur barge-in. `server/modules/tags.py` :
parseur de balises en flux (`[emo:]`/`[geste:]`/`[tool:]`) tolérant aux balises
coupées entre tokens. `server/modules/fallback_brain.py` : repli rule-based
(salutations, heure/date, capacités). Orchestration `_converse` dans `app.py` :
tokens propres → `llm_token`, balises → `emotion`/`gesture` (jamais prononcées),
phrases complètes → TTS au fil de l'eau. Frontend : handler `gesture`.
**Test manuel :** Ollama lancé (`ollama pull llama3.1:8b`), dire « Bonjour, raconte
une blague » → l'avatar sourit (`[emo:joie]`) et parle. Sans Ollama : repli
rule-based audible. `make test` → parseur (balises coupées) + repli validés.

```
PROMPT F4.1
Implémente /server/modules/brain.py :
1. Client Ollama (http://localhost:11434, modèle configurable dans
   /server/config.yaml, défaut llama3.x 8B instruct fr-capable).
   Vérification de disponibilité au démarrage avec message d'aide
   (« lancez : ollama pull <model> »).
2. Persona « Jarvis » dans /server/prompts/system.md : assistant
   français, réponses orales courtes (1–4 phrases), tutoiement
   configurable. Le modèle DOIT baliser ses réponses :
   [emo:joie|tristesse|surprise|colere|reflexion|neutre] en tête,
   et peut insérer [geste:nom] en cours de texte.
3. Streaming : tokens relayés au client (llm_token) ; un parseur
   extrait les balises au vol : émotions/gestes partent sur le bus
   (F1.4) et ne sont jamais lus à voix haute ; les phrases complètes
   partent vers le TTS (F2.1) au fil de l'eau.
4. Garde-fous : timeout, retry, et fallback rule-based minimal
   (/server/modules/fallback_brain.py : salutations, heure, capacités)
   si Ollama est injoignable.
5. Annulation totale sur interrupt (stoppe la génération Ollama).
Critères d'acceptation : « Bonjour, raconte-moi une blague » →
l'avatar sourit ([emo:joie] appliqué), parle la blague, premier mot
audible < 2,5 s après la fin de la question.
```

### ☑ F4.2 — Mémoire de conversation & petits outils

**But :** continuité du dialogue et utilité concrète.
**Dépend de :** F4.1.
**Statut :** livré. `server/modules/memory.py` : SQLite `server/data/memory.sqlite`
(gitignore), historique glissant (12 tours), profil (prénom, préférences), résumé
auto + élagage des tours anciens. `server/modules/tools.py` : `heure_date`,
`date`, `calcul` (eval sûr par AST, pas d'exécution de code), `minuteur` (planifié,
notification orale), `meteo` désactivée derrière `allow_network`. Intégration dans
`_converse` : commandes « oublie tout » / « je m'appelle… » / « souviens-toi que… »,
injection profil/historique dans le contexte LLM, exécution des balises `[tool:]`.
**Test manuel :** « Je m'appelle X » puis redémarrer le serveur puis « Comment je
m'appelle ? » → répond X ; « oublie tout » vide la base ; « calcule 12 fois 8 »
reste oral. Aucun accès réseau tant que `allow_network=false`.

```
PROMPT F4.2
Étends brain.py :
1. Historique glissant (12 derniers tours) + résumé automatique local
   quand l'historique dépasse le contexte ; persistance dans
   /server/data/memory.sqlite (créé au premier lancement, .gitignore).
2. Profil utilisateur léger : prénom, préférences déclarées («
   souviens-toi que… ») stockés en clair localement, avec commande
   vocale/texte « oublie tout » qui purge la base.
3. Outils locaux exposés au LLM (function calling si le modèle le
   supporte, sinon parsing de balises [tool:...]) : heure/date,
   minuteur, calcul, météo DÉSACTIVÉE par défaut (nécessiterait le
   réseau — la laisser derrière un flag explicite allow_network:false).
4. Chaque réponse outillée reste orale et brève.
Critères d'acceptation : « Comment je m'appelle ? » fonctionne après
redémarrage du serveur ; « oublie tout » vide la mémoire ; aucun accès
réseau tant que allow_network=false.
```

-----

## PHASE 5 — Orchestration, UX & qualité

### ☑ F5.1 — Pipeline temps réel complet & interruption

**But :** boucle voix↔voix fluide, comme une vraie conversation.
**Dépend de :** F2.2, F3.2, F4.1.
**Statut :** livré. `server/core/pipeline.py` (`Pipeline`) : machine à états
`idle→listening→thinking→speaking` diffusée au client, chaînage streaming intégral
(VAD→STT→LLM→découpe phrases→TTS→audio+timings), `Turn` avec `trace_id` et jalons
de latence (stt/first_token/first_audio) logués et renvoyés dans l'état final.
Barge-in robuste : `interrupt` annule génération LLM, file TTS et tâches suivies,
puis `gather` (pas de fuite asyncio). `app.py` slimé délègue au pipeline. Overlay
`?debug` côté frontend affiche les métriques.
**Test manuel :** 5 tours vocaux sans rechargement ; couper la parole 10× de suite.
`make test` → `test_pipeline.py` (machine à états, 5 tours, barge-in sans fuite de
tâches), 35 tests verts.

```
PROMPT F5.1
Crée /server/core/pipeline.py, chef d'orchestre de la conversation :
1. Machine à états serveur : idle → listening → thinking → speaking,
   diffusée au client (type state) pour piloter l'UI et les attitudes
   de l'avatar (F1.3/F1.4).
2. Chaînage streaming intégral : VAD fin de parole → STT → LLM tokens
   → découpe en phrases → TTS → audio+timestamps → client. Mesure et
   loggue la latence de chaque maillon (trace id par tour de parole).
3. Barge-in robuste : interrupt à n'importe quel stade annule STT en
   cours ignoré, génération LLM, file TTS et lecture client, sans
   fuite de tâches asyncio (test dédié).
4. Budget cible documenté : fin de parole utilisateur → premier son
   de l'avatar < 2,5 s (CPU) / < 1,5 s (GPU) ; affiche les métriques
   dans le panneau ?debug.
5. Tests d'intégration : conversation scriptée de 5 tours via un faux
   client WebSocket (pytest-asyncio).
Critères d'acceptation : 5 tours de conversation vocale sans
rechargement ; couper la parole à l'avatar fonctionne 10 fois de suite.
```

### ☑ F5.2 — Interface utilisateur de l’assistant

**But :** habillage sobre : états, sous-titres, réglages.
**Dépend de :** F5.1.
**Statut :** livré. `web/src/ui/hud.js` (`HUD`) + `ui/settings.js` + `ui/ui.css` :
bandeau d'état (prêt/écoute/réfléchit/parle) + niveau micro, sous-titres
synchronisés `aria-live` (transcript utilisateur en direct + texte avatar via
`llm_token`), activables. Panneau réglages persistés localStorage (sous-titres,
mode micro, qualité, thème clair/sombre, vitesse voix, modèle Ollama → message
`config`). Historique repliable (drawer) + export `.txt`. Saisie clavier (repli
si micro refusé). Accessibilité : focus visibles, Échap ferme les tiroirs,
`prefers-reduced-motion`, responsive ≤ 360 px.
**Test manuel :** utilisable au clavier seul ; thème bascule clair/sombre ;
sous-titres activables ; export conversation en .txt ; lisible sur 360 px.

```
PROMPT F5.2
Construis le HUD dans /web/src/ui/ :
1. Bandeau d'état discret (à l'écoute / réfléchit / parle) + indicateur
   de niveau micro.
2. Sous-titres synchronisés : transcript utilisateur en live (F3.2
   partiels) et texte de l'avatar mot à mot, calé sur les timestamps
   TTS ; activables/désactivables (accessibilité).
3. Panneau réglages : choix voix/vitesse, modèle Ollama, mode micro,
   sous-titres, qualité graphique (low/medium/high), thème. Persistance
   localStorage.
4. Historique de conversation repliable (drawer), avec export .txt local.
5. Accessibilité : navigation clavier complète, focus visibles,
   aria-live sur les sous-titres, contrastes AA, prefers-reduced-motion.
Critères d'acceptation : utilisable au clavier seul ; lisible sur un
écran 360 px de large ; aucun texte tronqué en français.
```

### ☐ F5.3 — Performance, packaging & démarrage en un clic

**But :** le projet se lance simplement et tient sur du matériel modeste.
**Dépend de :** toutes les phases.

```
PROMPT F5.3
Finalise l'industrialisation :
1. Profils de qualité auto : détection WebGL/GPU → ajuste ombres,
   pixelRatio, fréquence du LifeEngine ; cible 30 fps minimum mobile.
2. Script de démarrage unique : `make start` (ou start.sh / start.ps1)
   qui vérifie venv, modèles téléchargés (Kokoro, Whisper, VAD), Ollama
   actif, puis lance serveur + ouvre le navigateur. Messages d'erreur
   pédagogiques pour chaque prérequis manquant.
3. docker-compose.yml optionnel (serveur + ollama) avec volumes pour
   les poids des modèles ; documente les limites GPU.
4. Suite qualité : ESLint/ruff en pre-commit, pytest + vitest en CI
   locale (script `make check`), test de fumée headless (Playwright)
   qui charge la page et vérifie l'apparition de l'avatar.
5. /docs/architecture.md : schéma du pipeline, protocole WebSocket
   complet, budgets de latence, matrice navigateurs supportés.
Critères d'acceptation : installation depuis zéro en suivant le README
< 15 minutes ; `make start` aboutit à une conversation vocale
fonctionnelle ; `make check` passe au vert.
```

-----

## Suivi

|ID  |Fonctionnalité               |Statut|Branche suggérée     |
|----|-----------------------------|------|---------------------|
|F0.1|Scaffolding frontend         |☑     |dev/f0.1-scaffold-web|
|F0.2|Serveur FastAPI + WebSocket  |☑     |dev/f0.2-server-ws   |
|F1.1|TalkingHead + Ready Player Me|☑     |dev/f1.1-avatar      |
|F1.2|Environnement 3D             |☑     |dev/f1.2-environment |
|F1.3|Comportements autonomes      |☑     |dev/f1.3-life        |
|F1.4|Système d’émotions           |☑     |dev/f1.4-emotions    |
|F2.1|TTS local Kokoro             |☑     |dev/f2.1-tts         |
|F2.2|Lip-sync précis              |☑     |dev/f2.2-lipsync     |
|F3.1|Micro + VAD                  |☑     |dev/f3.1-mic-vad     |
|F3.2|STT Whisper local            |☑     |dev/f3.2-stt         |
|F4.1|Cerveau Ollama               |☑     |dev/f4.1-brain       |
|F4.2|Mémoire & outils             |☑     |dev/f4.2-memory      |
|F5.1|Pipeline temps réel          |☑     |dev/f5.1-pipeline    |
|F5.2|Interface utilisateur        |☑     |dev/f5.2-ui          |
|F5.3|Perf & packaging             |☐     |dev/f5.3-packaging   |

**Ordre recommandé :** F0.1 → F0.2 → F1.1 → F2.1 → F2.2 (démo « il parle ») → F1.3 → F1.4 → F3.1 → F3.2 → F4.1 (démo « il converse ») → F4.2 → F5.1 → F5.2 → F5.3.
