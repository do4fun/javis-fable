// main.js — Point d'entrée du frontend Jarvis.
//
// Stratégie de rendu :
//  - on tente de charger l'avatar TalkingHead dans #avatar (il gère son
//    propre rendu et sa boucle d'animation) ;
//  - s'il se charge, on masque la scène de repli (#scene) ;
//  - s'il échoue (module ou GLB absent), on garde la scène placeholder
//    animée et on affiche un message clair expliquant comment l'ajouter.

import { Scene } from './scene.js';
import { AvatarManager } from './avatar.js';
import { config } from './config.js';

const canvas = document.getElementById('scene');
const avatarEl = document.getElementById('avatar');
const boot = document.getElementById('boot');
const bootLabel = document.getElementById('boot-label');
const bootBar = document.getElementById('boot-bar-fill');

// --- Scène de repli (placeholder de F0.1) --------------------------------
const scene = new Scene(canvas);

let last = performance.now();
let running = true;
let rafId = null;
let avatarActive = false;

const minFrameMs = config.render.fpsCap > 0 ? 1000 / config.render.fpsCap : 0;
let acc = 0;

function frame(now) {
  rafId = requestAnimationFrame(frame);
  if (!running || avatarActive) return; // TalkingHead a sa propre boucle

  let dt = (now - last) / 1000;
  last = now;
  if (dt > 0.1) dt = 0.1;

  acc += dt * 1000;
  if (minFrameMs > 0 && acc < minFrameMs) return;
  acc = 0;

  scene.render(dt);
}

function handleVisibility() {
  running = document.visibilityState === 'visible';
  if (running) last = performance.now();
}
document.addEventListener('visibilitychange', handleVisibility);

// --- Écran de chargement --------------------------------------------------
function updateBoot({ progress, message }) {
  if (message && bootLabel) bootLabel.textContent = message;
  if (bootBar) bootBar.style.width = `${Math.round((progress || 0) * 100)}%`;
}

function hideBoot() {
  requestAnimationFrame(() => boot?.classList.add('hidden'));
}

function showBootError(message) {
  boot?.classList.add('error');
  if (bootLabel) bootLabel.textContent = message;
  if (bootBar) bootBar.style.width = '0%';
}

// --- Chargement de l'avatar ----------------------------------------------
const avatar = new AvatarManager(avatarEl, updateBoot);

// Exposé pour les modules suivants (vie, émotions, lip-sync, UI).
window.jarvis = { avatar, scene };

async function boot_() {
  rafId = requestAnimationFrame(frame); // démarre la scène de repli

  const result = await avatar.load(config.avatar.glbUrl);

  if (result.ok) {
    avatarActive = true;
    document.body.classList.add('avatar-active');
    hideBoot();
  } else {
    // Repli : on garde la scène placeholder visible et on explique l'erreur.
    showBootError(
      result.reason === 'glb_missing'
        ? 'Avatar non trouvé. Place jarvis.glb dans web/public/avatars/ ' +
            '(voir docs/avatar.md). Scène de démonstration affichée.'
        : result.reason === 'module_missing'
          ? 'Moteur TalkingHead non vendorisé. Voir docs/avatar.md. ' +
            'Scène de démonstration affichée.'
          : 'Avatar indisponible. Scène de démonstration affichée.'
    );
    // On laisse le message visible quelques secondes puis on dévoile la scène.
    setTimeout(hideBoot, 4000);
  }
}

boot_();

if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    cancelAnimationFrame(rafId);
    document.removeEventListener('visibilitychange', handleVisibility);
    scene.dispose();
  });
}
