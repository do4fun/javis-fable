# Avatar Ready Player Me + TalkingHead (F1.1)

Jarvis utilise la classe [TalkingHead](https://github.com/met4citizen/TalkingHead)
de met4citizen pour animer un avatar **Ready Player Me** (RPM) corps entier au
format **GLB**. Contrainte : **aucune URL `readyplayer.me` ni CDN à l'exécution**
— le GLB et le module TalkingHead sont déposés **en local**.

## 1. Obtenir le GLB de l'avatar

> ⚠️ **readyplayer.me est hors service** (racheté par Netflix, site inaccessible).
> Utilise le GLB open-source du dépôt officiel **readyplayerme/visage** à la place.

### Option A — GLB pré-construit (recommandé)

Le dépôt [readyplayerme/visage](https://github.com/readyplayerme/visage) contient
un fichier `half-body.glb` (demi-corps, 5,7 Mo) qui inclut déjà tous les morph
targets ARKit + visèmes Oculus nécessaires à TalkingHead.

**PowerShell :**

```powershell
# Depuis la racine du projet
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/readyplayerme/visage/main/public/half-body.glb" `
  -OutFile "web\public\avatars\jarvis.glb"
```

**Unix/macOS :**

```bash
mkdir -p web/public/avatars
curl -L \
  "https://raw.githubusercontent.com/readyplayerme/visage/main/public/half-body.glb" \
  -o web/public/avatars/jarvis.glb
```

### Option B — Cloner et builder visage (personnalisation)

Si tu veux personnaliser l'apparence (couleur de peau, cheveux…) :

```bash
git clone https://github.com/readyplayerme/visage.git
cd visage && npm install && npm run dev
# Exporte le GLB depuis l'interface, puis :
cp public/half-body.glb ../web/public/avatars/jarvis.glb
```

> Le GLB doit se trouver ici (chemin configuré dans `web/src/config.js`) :
> `web/public/avatars/jarvis.glb`
>
> Ce fichier n'est **pas** versionné (cf. `web/.gitignore`).

## 2. Vendoriser le module TalkingHead (hors-ligne)

TalkingHead est chargé en **import dynamique** depuis un chemin local
configurable (`config.avatar.modulePath`, défaut `/vendor/talkinghead/talkinghead.mjs`).

1. Récupère `talkinghead.mjs` depuis le dépôt met4citizen et place-le dans :

   ```
   web/vendor/talkinghead/talkinghead.mjs
   ```

2. TalkingHead importe `three` et ses addons via une **import map**. Ajoute-la
   dans `web/index.html`, avant les `<script type="module">` (chemins **locaux**,
   jamais de CDN) :

   ```html
   <script type="importmap">
     {
       "imports": {
         "three": "/vendor/three/three.module.js",
         "three/addons/": "/vendor/three/addons/"
       }
     }
   </script>
   ```

   (cf. `web/vendor/README.md` pour peupler `/vendor/three`.)

> ⚠️ La version de `three` doit rester compatible avec celle attendue par
> TalkingHead. En cas d'écran noir ou d'erreur d'import, aligne la version sur
> celle de l'import map officielle du dépôt TalkingHead.

## 3. Blendshapes requis

TalkingHead s'appuie sur ces familles de morph targets (présentes si l'export
RPM inclut bien `ARKit,Oculus Visemes`) :

- **Visèmes Oculus** : `viseme_sil`, `viseme_PP`, `viseme_FF`, `viseme_TH`,
  `viseme_DD`, `viseme_kk`, `viseme_CH`, `viseme_SS`, `viseme_nn`, `viseme_RR`,
  `viseme_aa`, `viseme_E`, `viseme_I`, `viseme_O`, `viseme_U`.
- **ARKit** (expressions) : `browInnerUp`, `browDown_L/R`, `eyeBlink_L/R`,
  `mouthSmile_L/R`, `jawOpen`, etc.

Au chargement, `AvatarManager` loggue un **rapport de compatibilité** listant
les blendshapes manquants (console + overlay si `?debug`). Un avatar sans
visèmes Oculus fonctionnera mais sans lip-sync correct (F2.2).

## 4. Vérification

`cd web && npm run dev`, puis ouvre la page :

- l'avatar s'affiche, l'idle natif de TalkingHead est actif ;
- l'onglet **Network** ne montre **aucune** requête externe ;
- si `jarvis.glb` est absent, un message clair explique comment l'ajouter.
