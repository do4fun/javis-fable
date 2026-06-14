# Avatar VRM + three-vrm (alternative à TalkingHead/GLB)

Jarvis peut animer un avatar au format **VRM 1.0** via
[@pixiv/three-vrm](https://github.com/pixiv/three-vrm) au lieu d'un GLB Ready
Player Me + TalkingHead. Le VRM apporte des **expressions faciales natives**
(émotions + visèmes), un **squelette humanoïde standard**, des **spring bones**
(cheveux/vêtements qui réagissent au mouvement) et un système de **regard**
(lookAt) intégré.

Contrainte inchangée : **100 % local**. `three` et `three-vrm` sont bundlés par
Vite depuis `node_modules` (aucun CDN). Le fichier `.vrm` est déposé localement.

## Pourquoi VRM plutôt que GLB ?

| Aspect            | GLB + TalkingHead                  | VRM + three-vrm                     |
|-------------------|------------------------------------|-------------------------------------|
| Expressions       | morphs ARKit (52) + visèmes Oculus | expressions VRM normalisées         |
| Squelette         | Mixamo (doit être complet)         | humanoïde VRM standard              |
| Lip-sync          | calage mots→visèmes (TalkingHead)  | audio-driven (analyse du signal)    |
| Physique          | dynamic bones (TalkingHead)        | spring bones (natif VRM)            |
| Création d'avatar | readyplayer.me (hors service)      | **VRoid Studio** (gratuit, offline) |

## 1. Choisir le moteur

Dans [web/src/config.js](../web/src/config.js) :

```js
avatar: {
  format: 'vrm', // 'vrm' (three-vrm) | 'glb' (TalkingHead)
  vrmUrl: '/avatars/jarvis.vrm',
  ...
}
```

## 2. Obtenir un fichier VRM

### Option A — Modèle d'exemple (démarrage immédiat)

Le dépôt officiel three-vrm fournit un avatar VRM 1.0 complet (toutes les
expressions standard), pratique pour tester.

**PowerShell :**

```powershell
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/pixiv/three-vrm/dev/packages/three-vrm/examples/models/VRM1_Constraint_Twist_Sample.vrm" `
  -OutFile "web\public\avatars\jarvis.vrm"
```

**Unix/macOS :**

```bash
curl -L \
  "https://raw.githubusercontent.com/pixiv/three-vrm/dev/packages/three-vrm/examples/models/VRM1_Constraint_Twist_Sample.vrm" \
  -o web/public/avatars/jarvis.vrm
```

> Modèle « VRM1_Constraint_Twist_Sample » par pixiv Inc., licence
> [VRM 1.0](https://vrm.dev/licenses/1.0/), `avatarPermission: everyone`.
> Pratique pour le développement ; remplace-le par ton propre avatar pour la
> production.

### Option B — Créer son avatar avec VRoid Studio (recommandé)

[VRoid Studio](https://vroid.com/en/studio) est une application **gratuite et
hors-ligne** (Windows/macOS) pour créer et personnaliser un avatar (visage,
cheveux, vêtements, couleurs) puis l'exporter en **VRM**.

1. Crée/personnalise ton personnage dans VRoid Studio.
2. **Export → VRM**, en choisissant **VRM 1.0**.
3. Place le fichier exporté ici :

   ```text
   web/public/avatars/jarvis.vrm
   ```

> Le fichier `.vrm` n'est **pas versionné** (cf. `web/.gitignore`).

## 3. Expressions requises

Le moteur attend les expressions VRM standard (présentes sur tout export VRoid /
sur le modèle d'exemple) :

- **Visèmes** : `aa`, `ih`, `ou`, `ee`, `oh` (lip-sync) ;
- **Émotions** : `happy`, `angry`, `sad`, `surprised`, `relaxed`, `neutral` ;
- **Clignement** : `blink` (+ `blinkLeft`/`blinkRight` optionnels) ;
- **Regard** : `lookUp`, `lookDown`, `lookLeft`, `lookRight` (ou applier osseux).

Au chargement, un **rapport de compatibilité** liste les expressions manquantes
(console ; `[avatar] VRM : toutes les expressions requises sont présentes.`).

## 4. Comment les fonctionnalités sont mappées

Le `VRMAvatarManager` expose la même API interne que la voie GLB, donc
`emotions.js`, `life.js` et `lipsync.js` fonctionnent sans modification :

- **Émotions** (F1.4) : `setMood()` choisit l'expression VRM ; l'intensité
  (montée/décroissance) est dérivée des morphs ARKit écrits par `emotions.js`.
- **Lip-sync** (F2.2) : la voie audio-driven (`audioVisemes.js`) analyse le
  signal et pilote `jawOpen`/voyelles → traduits en visèmes VRM `aa/ih/ou/ee/oh`.
- **Regard** (F1.3) : `lookAt(x,y)` déplace la cible VRM lookAt + oriente
  légèrement la tête/le cou.
- **Gestes** : gestes procéduraux (`acquiesce`, `reflechit`, `hausse_epaules`,
  `celebre`) animant les os humanoïdes normalisés.
- **Vie** : clignement, respiration et balancement (sway) sont générés par le
  moteur ; les spring bones réagissent au mouvement.

## 5. Vérification

```powershell
cd web ; npm run build
```

Lance le serveur, puis dans la console du navigateur :

- `[avatar] VRM : toutes les expressions requises sont présentes.`
- l'avatar s'affiche cadré tête-épaules, cligne et respire ;
- demande-lui de parler : la bouche bouge en cadence avec l'audio.

> **Sans `jarvis.vrm`**, Jarvis démarre quand même et affiche un message
> explicatif avec la scène de démonstration ; la voix et la conversation
> fonctionnent.
