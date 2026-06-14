import { defineConfig } from 'vite';
import { resolve } from 'node:path';
import fs from 'node:fs';

// Configuration Vite — projet 100 % local, aucun CDN à l'exécution.
// Le build doit produire un bundle autonome servable par un simple
// serveur de fichiers statiques (cf. /server qui sert /web/dist en F0.2).

// Les fichiers dans public/vendor/ sont des modules ES chargés dynamiquement
// à l'exécution (talkinghead.mjs, three, lipsync-*.mjs). Vite refuse de les
// servir via import() en dev car ils sont dans public/. Ce plugin les sert
// directement avec le bon Content-Type, bypass la restriction dev uniquement.
const serveVendorModules = {
  name: 'serve-vendor-modules',
  configureServer(server) {
    server.middlewares.use((req, res, next) => {
      if (!req.url?.startsWith('/vendor/')) return next();
      const localPath = resolve(import.meta.dirname, 'public', req.url.split('?')[0].slice(1));
      if (!fs.existsSync(localPath)) return next();
      const ext = localPath.split('.').pop();
      const mime = (ext === 'mjs' || ext === 'js')
        ? 'application/javascript; charset=utf-8'
        : 'application/octet-stream';
      res.setHeader('Content-Type', mime);
      res.end(fs.readFileSync(localPath));
    });
  },
};

export default defineConfig({
  plugins: [serveVendorModules],
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
    rollupOptions: {
      input: {
        // Page principale + page de validation des émotions (F1.4).
        main: resolve(import.meta.dirname, 'index.html'),
        emotions: resolve(import.meta.dirname, 'test/emotions.html'),
      },
    },
  },
  server: {
    host: true, // accessible depuis le mobile sur le réseau local
    port: 5173,
    open: false,
  },
  // Three.js est vendorisé dans public/vendor/three/ et résolu via importmap
  // au runtime — Vite ne doit pas le pré-bundler depuis node_modules.
  optimizeDeps: {
    exclude: ['three'],
  },
});
