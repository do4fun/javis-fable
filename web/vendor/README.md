# /web/vendor — modules vendorisés (fonctionnement hors-ligne)

Ce dossier garantit que Jarvis tourne **sans aucun CDN à l'exécution**.

## Stratégie

1. **Voie principale (npm + Vite).** Les dépendances (`three`, plus tard le
   module `talkinghead`) sont installées via `npm install` et bundlées par
   Vite. Le `npm run build` produit un `dist/` autonome : aucun appel réseau
   externe au runtime.

2. **Voie de secours (import map).** Si l'on sert `index.html` directement
   sans build (ouverture statique), on peut basculer sur une *import map*
   pointant vers ces fichiers vendorisés **locaux**. Exemple à coller dans
   `index.html`, avant les `<script type="module">` :

   ```html
   <script type="importmap">
     {
       "imports": {
         "three": "/vendor/three/three.module.js",
         "three/addons/": "/vendor/three/addons/",
         "talkinghead": "/vendor/talkinghead/talkinghead.mjs"
       }
     }
   </script>
   ```

   Les chemins sont **relatifs au site local** — jamais d'URL `https://cdn…`.

## Comment peupler ce dossier

Les binaires ne sont pas versionnés (cf. `.gitignore`). Pour les récupérer
une seule fois en local :

```bash
# Three.js (version épinglée dans web/package.json)
cp node_modules/three/build/three.module.js        vendor/three/
cp -r node_modules/three/examples/jsm              vendor/three/addons

# TalkingHead (ajouté en F1.1)
#   voir https://github.com/met4citizen/TalkingHead — déposer talkinghead.mjs
```

> ⚠️ La version de `three` doit rester **compatible avec TalkingHead**
> (voir la doc du dépôt met4citizen/TalkingHead). En cas de doute, aligne-toi
> sur la version utilisée dans leur import map officielle.
