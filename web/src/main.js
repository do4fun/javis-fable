// main.js — Point d'entrée du frontend Jarvis.
// Met en place la scène et la boucle de rendu requestAnimationFrame avec
// deltaTime, plus la gestion de visibilitychange (pause en arrière-plan
// pour économiser CPU/GPU/batterie).

import { Scene } from './scene.js';
import { config } from './config.js';

const canvas = document.getElementById('scene');
const boot = document.getElementById('boot');

const scene = new Scene(canvas);

// --- Boucle de rendu ------------------------------------------------------
let last = performance.now();
let running = true;
let rafId = null;

// Intervalle minimal entre frames (cap FPS). 0 = pas de cap au-delà du vsync.
const minFrameMs = config.render.fpsCap > 0 ? 1000 / config.render.fpsCap : 0;
let acc = 0;

function frame(now) {
  rafId = requestAnimationFrame(frame);
  if (!running) return;

  let dt = (now - last) / 1000; // deltaTime en secondes
  last = now;
  // Garde-fou : après un retour d'arrière-plan, dt peut être énorme.
  if (dt > 0.1) dt = 0.1;

  // Cap FPS optionnel : on saute le rendu si on est en avance.
  acc += dt * 1000;
  if (minFrameMs > 0 && acc < minFrameMs) return;
  acc = 0;

  scene.render(dt);
}

// --- Pause en arrière-plan ------------------------------------------------
function handleVisibility() {
  running = document.visibilityState === 'visible';
  if (running) {
    // On resynchronise l'horloge pour éviter un saut de deltaTime au retour.
    last = performance.now();
  }
}
document.addEventListener('visibilitychange', handleVisibility);

// --- Démarrage ------------------------------------------------------------
function start() {
  rafId = requestAnimationFrame(frame);
  // Masque l'écran de chargement : la scène est prête.
  // (En F1.1 cette transition attendra le chargement réel de l'avatar.)
  requestAnimationFrame(() => boot?.classList.add('hidden'));
}

start();

// Nettoyage propre (utile pour le HMR de Vite en dev).
if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    cancelAnimationFrame(rafId);
    document.removeEventListener('visibilitychange', handleVisibility);
    scene.dispose();
  });
}
