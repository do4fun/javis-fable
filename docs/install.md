# Installation des modèles locaux

Jarvis fonctionne **hors-ligne à l'exécution**. Les poids des modèles se
téléchargent **une seule fois** lors de l'installation, puis plus aucun accès
réseau n'est nécessaire. Cette page regroupe ces téléchargements uniques.

## Vue d'ensemble

| Modèle                 | Fonctionnalité | Taille indicative | Obligatoire ?                |
|------------------------|----------------|-------------------|------------------------------|
| Avatar RPM (GLB)       | F1.1 (avatar)  | ~5–15 Mo          | requis pour l'avatar 3D      |
| TalkingHead + Three.js | F1.1 (avatar)  | ~2 Mo (vendorisé) | requis pour l'avatar 3D      |
| Kokoro TTS (FR)        | F2.1 (voix)    | ~350 Mo           | recommandé (repli dispo)     |
| piper-tts (fr_FR)      | F2.1 (repli)   | ~60 Mo            | optionnel                    |
| faster-whisper         | F3.2 (écoute)  | ~150–500 Mo       | requis pour la voix entrante |
| Silero VAD (ONNX)      | F3.1 (VAD)     | ~2 Mo             | requis pour mains-libres     |
| LLM via Ollama         | F4.1 (cerveau) | ~4–5 Go           | requis pour converser        |

> Sans aucun modèle vocal, le TTS bascule automatiquement sur un moteur de
> repli (`dummy`, onde sinusoïdale) : utile pour développer, pas pour écouter.

## Activation du venv Python (rappel)

Toutes les commandes `pip install` ci-dessous s'exécutent dans le venv du
serveur. Active-le une seule fois par terminal :

```bash
# Windows (PowerShell)
cd server
.venv\Scripts\activate

# Unix / Git Bash
cd server
source .venv/bin/activate
```

> Si le venv n'existe pas encore : `python -m venv .venv` puis `pip install -r requirements.txt`.

---

## TTS — Kokoro (voix française)

**Pourquoi :** Kokoro génère une voix française naturelle (~24 kHz) avec des
timestamps mot à mot utilisés pour synchroniser les lèvres. C'est le moteur
TTS principal. Les poids sont téléchargés automatiquement au **premier appel**.

### Installation de Kokoro

Kokoro requiert **Python 3.10 ou supérieur**. Vérifie avant d'installer :

```bash
# Windows
.venv\Scripts\python --version

# Unix
python --version
```

Si la version est correcte, installe Kokoro dans le venv activé :

```bash
# Windows
cd server
.venv\Scripts\activate
pip install kokoro soundfile

# Unix
cd server
source .venv/bin/activate
pip install kokoro soundfile
```

> **Erreur `No module named 'kokoro'` lors du test ?** Cela signifie que Kokoro
> n'est pas installé dans le venv courant. Assure-toi d'avoir activé le venv
> (`activate`) avant de lancer `pip install`, puis relance le script.

### Dépendance système : espeak-ng (obligatoire pour le français)

Kokoro utilise **espeak-ng** comme backend de phonémisation pour le français.
Ce n'est **pas** un package pip — c'est un outil système à installer
séparément. Sans lui, Kokoro accepte le texte mais synthétise du **silence**
(durée 0.00s dans le script de test).

**Diagnostic :** si `tts_demo.py` affiche `Écrit out.wav — 0.00s`, espeak-ng
est absent ou introuvable.

#### Installation de espeak-ng

**Windows :**

1. Télécharge l'installateur depuis
   <https://github.com/espeak-ng/espeak-ng/releases> (prends le `.msi` ou
   `.exe` de la dernière release).
2. Lance l'installateur et laisse-le cocher **"Add to PATH"**.
3. Ferme et réouvre le terminal (PowerShell), puis vérifie :

```powershell
espeak-ng --version
# → eSpeak NG text-to-speech: 1.x.x  ...
```

**Unix / macOS :**

```bash
# Debian / Ubuntu
sudo apt install espeak-ng

# macOS
brew install espeak-ng
```

**Vérification après installation :**

```bash
# Depuis server/, venv activé
python tests/tts_demo.py "Bonjour, je suis Jarvis."
# → Écrit out.wav — 2.35s @ 24000 Hz  (durée > 0)
#   [ 0.00 →  0.45] Bonjour,
#   [ 0.45 →  0.72] je
#   ...
```

Si la durée est maintenant positive mais qu'on n'entend toujours rien, ouvre
directement `server/out.wav` dans un lecteur audio (VLC, Windows Media Player)
pour confirmer que le fichier contient bien de l'audio.

### Configuration de Kokoro

Ouvre `server/config.yaml` et vérifie :

```yaml
tts:
  engine: kokoro
  voice: ff_siwis     # voix française Kokoro
  sample_rate: 24000
```

### Vérification de Kokoro

```bash
# Windows
.venv\Scripts\python tests/tts_demo.py "Bonjour, je suis Jarvis."

# Unix
python tests/tts_demo.py "Bonjour, je suis Jarvis."
# → génère server/out.wav ; écoute-le pour confirmer la voix
```

Au premier lancement, Kokoro télécharge ses poids (~350 Mo). Les appels
suivants sont hors-ligne.

> **Tester sans Kokoro :** mets `engine: dummy` dans `server/config.yaml` pour
> utiliser le moteur de repli (onde sinusoïdale, aucune dépendance). Le WAV
> généré confirme que le reste du pipeline fonctionne correctement.

---

### Repli — piper-tts (optionnel)

**Pourquoi :** Si Kokoro n'est pas installé ou plante, le serveur peut utiliser
piper-tts comme deuxième repli avant de basculer sur le moteur `dummy`.

#### Installation de piper-tts

```bash
pip install piper-tts
```

#### Télécharger une voix française

Récupère le fichier `.onnx` + `.onnx.json` depuis les releases officielles de
piper :

```bash
# Exemple : voix fr_FR-siwis-medium
curl -L -o fr_FR-siwis-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx

curl -L -o fr_FR-siwis-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json
```

Place les deux fichiers dans `server/models/` (crée le dossier si besoin).

#### Configuration de piper-tts

```yaml
tts:
  engine: piper
  piper_model: models/fr_FR-siwis-medium.onnx
  sample_rate: 22050
```

---

## STT — faster-whisper (F3.2)

**Pourquoi :** faster-whisper transcrit la parole capturée par le micro en
texte, entièrement en local. Il utilise CTranslate2, une implémentation
optimisée de Whisper (OpenAI). Le modèle est mis en cache localement au premier
chargement.

### Installation de faster-whisper

```bash
# Avec le venv activé
pip install faster-whisper
```

### Choix du modèle

Le modèle se configure dans `server/config.yaml` (section `stt`) :

```yaml
stt:
  model: small     # tiny | base | small | medium | large-v3
  language: fr
```

| Modèle     | Taille   | VRAM (GPU) | Qualité FR  | Latence (CPU) |
|------------|----------|------------|-------------|---------------|
| `tiny`     | ~75 Mo   | ~1 Go      | correcte    | très rapide   |
| `base`     | ~145 Mo  | ~1 Go      | bonne       | rapide        |
| `small`    | ~465 Mo  | ~2 Go      | très bonne  | moyenne       |
| `medium`   | ~1,5 Go  | ~5 Go      | excellente  | lente         |
| `large-v3` | ~3 Go    | ~10 Go     | référence   | très lente    |

**Recommandation :** `small` est le meilleur compromis pour une machine sans GPU
dédié. Sur GPU, `medium` ou `large-v3` sont nettement meilleurs.

### Vérification de faster-whisper

```bash
# Windows
.venv\Scripts\python tests/bench_stt.py

# Unix
python tests/bench_stt.py
# → transcrit un fichier audio de test et affiche la latence
```

Au premier démarrage du serveur, faster-whisper télécharge les poids (~150 Mo
pour `small`) et les met en cache dans `~/.cache/huggingface/`. Les démarrages
suivants sont hors-ligne.

---

## VAD — Silero (F3.1)

Le VAD (détecteur d'activité vocale) tourne **dans le navigateur** via
onnxruntime-web, 100 % local. Il faut deux choses : le modèle Silero et le
moteur WebAssembly qui l'exécute.

### Pourquoi « vendoriser » ONNX Runtime Web ?

ONNX Runtime Web est une bibliothèque JavaScript + WebAssembly publiée par
Microsoft. Elle permet au navigateur d'exécuter des modèles `.onnx` (dont
Silero). Normalement elle se chargerait depuis un CDN ; comme Jarvis est
100 % local, on copie ces fichiers **une seule fois** dans le dépôt pour
qu'ils soient servis par le serveur local. C'est ce qu'on appelle « vendoriser ».

### Étape 1 — Modèle Silero VAD

Télécharge `silero_vad.onnx` depuis le dépôt officiel et dépose-le dans
`web/public/models/` :

```bash
# Unix / Git Bash (depuis la racine du projet)
curl -L -o web/public/models/silero_vad.onnx \
  https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx
```

```powershell
# Windows PowerShell (depuis la racine du projet)
Invoke-WebRequest `
  -Uri "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx" `
  -OutFile "web\public\models\silero_vad.onnx"
```

Ou télécharge-le manuellement depuis <https://github.com/snakers4/silero-vad>
et place-le dans `web/public/models/`.

### Étape 2 — Runtime ONNX Web (vendorisé)

```bash
# Unix / Git Bash
cd web
npm install onnxruntime-web
mkdir -p public/vendor/ort
cp node_modules/onnxruntime-web/dist/esm/ort.min.mjs  public/vendor/ort/
cp node_modules/onnxruntime-web/dist/esm/*.wasm        public/vendor/ort/
npm uninstall onnxruntime-web
```

```powershell
# Windows PowerShell
cd web
npm install onnxruntime-web
New-Item -ItemType Directory -Force public\vendor\ort
Copy-Item node_modules\onnxruntime-web\dist\esm\ort.min.mjs public\vendor\ort\
Copy-Item node_modules\onnxruntime-web\dist\esm\*.wasm      public\vendor\ort\
npm uninstall onnxruntime-web
```

Les fichiers `.wasm` copiés sont typiquement :

| Fichier                       | Utilité                         |
|-------------------------------|---------------------------------|
| `ort-wasm-simd-threaded.wasm` | chemin optimal (SIMD + threads) |
| `ort-wasm-simd.wasm`          | SIMD sans threads               |
| `ort-wasm-threaded.wasm`      | threads sans SIMD               |
| `ort-wasm.wasm`               | repli universel                 |

ONNX Runtime choisit automatiquement le meilleur `.wasm` selon le navigateur.

### Résultat attendu

```text
web/public/
  models/
    silero_vad.onnx
  vendor/ort/
    ort.min.mjs
    ort-wasm-simd-threaded.wasm
    ort-wasm-simd.wasm
    ort-wasm-threaded.wasm
    ort-wasm.wasm
```

Le chemin du runtime est configurable dans `web/src/config.js` :

```js
mic: {
  vad: {
    ortPath: '/vendor/ort/ort.min.mjs',
  }
}
```

> **Sans ces fichiers**, le VAD bascule automatiquement sur un repli
> **énergétique** (RMS + plancher de bruit adaptatif) — aucune erreur, aucun
> téléchargement, mais la détection de parole est moins précise qu'avec Silero.

---

## LLM — Ollama (F4.1)

**Pourquoi :** Ollama fait tourner un grand modèle de langage (LLM) en local.
C'est le « cerveau » de Jarvis : il reçoit l'historique de conversation et
génère des réponses en streaming, token par token.

### Installation d'Ollama

Télécharge et installe Ollama depuis <https://ollama.com> :

```bash
# Unix (installe le service + CLI)
curl -fsSL https://ollama.com/install.sh | sh

# Windows : télécharge l'installateur .exe depuis https://ollama.com/download
# puis lance-le ; Ollama démarre automatiquement en tâche de fond.

# macOS
brew install ollama
```

Vérifie que le service tourne :

```bash
ollama list   # doit afficher la liste des modèles (vide au début)
```

### Télécharger un modèle

```bash
ollama pull llama3.1:8b      # recommandé — bon équilibre qualité/vitesse (~4,7 Go)
# ollama pull mistral:7b     # alternative légère (~4,1 Go)
# ollama pull llama3.1:70b   # qualité maximale, nécessite ~40 Go de RAM
```

Le modèle est stocké dans `~/.ollama/models/` et utilisable hors-ligne ensuite.

### Configuration d'Ollama

Ouvre `server/config.yaml` et ajuste la section `llm` :

```yaml
llm:
  host: "http://localhost:11434"   # URL d'Ollama (défaut)
  model: "llama3.1:8b"            # doit correspondre au modèle téléchargé
  timeout: 30                     # secondes avant abandon de la génération
  tutoiement: true                # Jarvis tutoie l'utilisateur
```

Si Ollama tourne sur une autre machine du réseau local, change `host` en
conséquence ou exporte la variable d'environnement :

```bash
export JARVIS_OLLAMA_HOST=http://192.168.1.42:11434
```

### Vérification d'Ollama

```bash
# Test rapide en ligne de commande
ollama run llama3.1:8b "Dis bonjour en une phrase."
```

```bash
# Test via le serveur Jarvis (avec venv activé)
# Windows
.venv\Scripts\python tests/bench_stt.py

# Unix
python -c "
import asyncio
from modules.brain import Brain
async def t():
    b = Brain({'host':'http://localhost:11434','model':'llama3.1:8b','timeout':30,'tutoiement':True})
    async for tok in b.stream('Bonjour !', []):
        print(tok, end='', flush=True)
asyncio.run(t())
"
```

> **Sans Ollama**, le serveur bascule sur le cerveau **rule-based** intégré
> (réponses prédéfinies pour les salutations, l'heure, les capacités). Utile
> pour développer sans avoir besoin du LLM.

---

## Vérifier le TTS sans navigateur

```bash
# Windows
.venv\Scripts\python tests/tts_demo.py "Bonjour, je suis Jarvis."

# Unix
python tests/tts_demo.py "Bonjour, je suis Jarvis."
# → génère server/out.wav avec le moteur configuré (ou le repli dummy)
```

## Suite de tests complète

```bash
# Depuis la racine du projet
make check
# → ESLint + vitest + build (web) ; ruff + pytest (serveur)
```

---

## Avatar 3D — Ready Player Me + TalkingHead (F1.1)

L'avatar est un fichier GLB exporté depuis Ready Player Me avec les blendshapes
ARKit (expressions) et les visèmes Oculus (lip-sync). TalkingHead et Three.js
sont déjà **vendorisés dans le dépôt** (`web/vendor/`) — aucune action requise
de ce côté.

### Étape 1 — Créer l'avatar sur Ready Player Me

1. Va sur <https://readyplayer.me> et crée un compte (gratuit) ou continue en
   invité.
2. Choisis **"Full Body"** (corps entier) — pas *Half Body* : TalkingHead
   requiert le squelette complet pour les animations.
3. Personnalise l'apparence à ton goût, puis clique **"Done"**.
4. Sur la page finale, copie l'**ID** de l'avatar (24 caractères dans l'URL,
   entre le dernier `/` et `.glb`).

### Étape 2 — Télécharger le GLB avec les bons paramètres

L'URL d'export doit inclure les morph targets ARKit + visèmes Oculus.
Remplace `<TON_ID>` par l'ID copié à l'étape précédente :

```text
https://models.readyplayer.me/<TON_ID>.glb?morphTargets=ARKit,Oculus%20Visemes&textureAtlas=1024&pose=A&lod=0
```

| Paramètre                          | Rôle                                                  |
|------------------------------------|-------------------------------------------------------|
| `morphTargets=ARKit,Oculus Visemes`| 52 blendshapes ARKit + 15 visèmes Oculus (lip-sync)   |
| `textureAtlas=1024`                | Atlas de textures fusionné (performance)              |
| `pose=A`                           | Pose en A requise par TalkingHead pour les animations |
| `lod=0`                            | Pleine résolution (`lod=1` si fichier trop lourd)     |

**Téléchargement via PowerShell (Windows) :**

```powershell
Invoke-WebRequest `
  -Uri "https://models.readyplayer.me/<TON_ID>.glb?morphTargets=ARKit,Oculus%20Visemes&textureAtlas=1024&pose=A&lod=0" `
  -OutFile "web\public\avatars\jarvis.glb"
```

**Téléchargement via curl (Unix) :**

```bash
curl -L -o web/public/avatars/jarvis.glb \
  "https://models.readyplayer.me/<TON_ID>.glb?morphTargets=ARKit,Oculus%20Visemes&textureAtlas=1024&pose=A&lod=0"
```

Ou ouvre l'URL dans un navigateur et enregistre le fichier dans
`web/public/avatars/jarvis.glb`.

> Le fichier `jarvis.glb` n'est **pas versionné** (cf. `web/.gitignore`) — il
> reste sur ta machine uniquement.

### Étape 3 — Vérification

Lance le serveur (`make start` ou `.\start.ps1`), ouvre la console du navigateur
et vérifie :

```text
[avatar] Tous les blendshapes requis sont présents.
```

Si tu vois des blendshapes manquants, le GLB a été exporté sans les paramètres
`ARKit,Oculus Visemes` — renouvelle le téléchargement avec l'URL complète
ci-dessus.

> **Sans `jarvis.glb`**, Jarvis démarre quand même et affiche un message
> explicatif avec la scène 3D de démonstration. La voix et la conversation
> fonctionnent normalement.

---

## Démarrage de Jarvis

Une fois les modèles installés, deux façons de lancer l'application.

### Méthode 1 — démarrage en un clic (recommandée)

Le script `scripts/start.py` vérifie les prérequis, build le frontend si
nécessaire, contrôle Ollama, puis lance le serveur et ouvre le navigateur.

```powershell
# Windows PowerShell (depuis la racine du projet)
.\start.ps1
```

```bash
# Unix / Git Bash (depuis la racine du projet)
make start
# ou directement :
python scripts/start.py
```

Options disponibles :

```bash
python scripts/start.py --no-browser   # ne pas ouvrir le navigateur automatiquement
python scripts/start.py --port 9000    # changer le port (défaut : 8000)
```

Le script affiche l'état de chaque prérequis (✓ ok / ! avertissement) et
indique clairement ce qui manque. Un prérequis manquant n'empêche pas le
lancement : Jarvis bascule sur ses replis et reste utilisable.

Une fois lancé, ouvre <http://localhost:8000> dans le navigateur.

---

### Méthode 2 — démarrage manuel (mode développement)

Utile pour travailler sur le code avec le rechargement automatique (HMR côté
frontend, `--reload` côté serveur).

**Terminal 1 — serveur FastAPI :**

```powershell
# Windows
cd server
.venv\Scripts\activate
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

```bash
# Unix
cd server
source .venv/bin/activate
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — frontend Vite (HMR) :**

```bash
cd web
npm install        # seulement au premier lancement
npm run dev        # démarre sur http://localhost:5173
```

Ouvre <http://localhost:5173> (dev avec HMR) ou <http://localhost:8000>
(version buildée servie par FastAPI après `npm run build`).

> Le frontend en mode `npm run dev` pointe sur le serveur FastAPI via
> `http://localhost:8000` pour la WebSocket. Les deux terminaux doivent
> donc tourner simultanément.

---

### Arrêt

`Ctrl+C` dans le terminal du serveur suffit à tout arrêter proprement.
