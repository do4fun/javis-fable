# Avatar Ready Player Me + TalkingHead (F1.1)

Jarvis utilise la classe [TalkingHead](https://github.com/met4citizen/TalkingHead)
de met4citizen pour animer un avatar **Ready Player Me** (RPM) corps entier au
format **GLB**. Contrainte : **aucune URL `readyplayer.me` ni CDN à l'exécution**
— le GLB et le module TalkingHead sont déposés **en local**.

## 1. Créer et exporter l'avatar RPM

1. Crée ton avatar sur <https://readyplayer.me> (corps entier / *full body*).
2. Récupère l'URL du GLB (elle finit par `.glb`).
3. **Indispensable :** ajoute les morph targets ARKit + visèmes Oculus en
   suffixant l'URL d'export avec ces paramètres :

   ```
   https://models.readyplayer.me/<ID>.glb?morphTargets=ARKit,Oculus%20Visemes&textureAtlas=1024&pose=A&lod=0
   ```

   - `morphTargets=ARKit,Oculus Visemes` → blendshapes du visage + visèmes ;
   - `textureAtlas=1024` → atlas de textures (perf) ;
   - `pose=A` → pose en A (attendue par TalkingHead) ;
   - `lod=0` → pleine résolution (baisse à 1/2 pour le mobile bas de gamme).

4. Télécharge le fichier **une seule fois** et dépose-le ici :

   ```
   web/public/avatars/jarvis.glb
   ```

   Ce fichier n'est **pas** versionné (cf. `web/.gitignore`).

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
