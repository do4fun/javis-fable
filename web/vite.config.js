import { defineConfig } from 'vite';

// Configuration Vite — projet 100 % local, aucun CDN à l'exécution.
// Le build doit produire un bundle autonome servable par un simple
// serveur de fichiers statiques (cf. /server qui sert /web/dist en F0.2).
export default defineConfig({
  // Racine = ce dossier /web. Les assets publics (avatars, modèles ONNX,
  // animations FBX, HDRI…) vivent dans /web/public et sont copiés tels quels.
  root: '.',
  base: './', // chemins relatifs → fonctionne derrière n'importe quel préfixe
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'es2020',
    sourcemap: true,
    // On évite tout split inutile : un bundle simple à servir hors-ligne.
    chunkSizeWarningLimit: 1500,
  },
  server: {
    host: true, // accessible depuis le mobile sur le réseau local
    port: 5173,
    open: false,
  },
  // Three.js est volumineux : on le pré-bundle pour un dev rapide.
  optimizeDeps: {
    include: ['three'],
  },
});
