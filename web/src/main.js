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
import { JarvisSocket } from './ws.js';
import { LipSync } from './lipsync.js';
import { LifeEngine } from './life.js';
import { EmotionEngine } from './emotions.js';
import { MicCapture } from './mic.js';
import { HUD } from './ui/hud.js';
import { config } from './config.js';
import './ui/ui.css';

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
  if (!running) return;

  let dt = (now - last) / 1000;
  last = now;
  if (dt > 0.1) dt = 0.1;

  // Vie autonome (regard) et émotions (couche additive) tournent toujours.
  life.update(dt);
  emotions.update(dt);

  // TalkingHead gère son propre rendu ; on ne rend la scène de repli que si
  // l'avatar n'est pas actif.
  if (avatarActive) return;

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
const lipsync = new LipSync(avatar);
const life = new LifeEngine(avatar);
const emotions = new EmotionEngine(avatar);
// Permet aux gestes ambiants de se mettre en retrait pendant la parole.
avatar.lipsync = lipsync;

// --- WebSocket : réception de l'audio TTS et lip-sync ---------------------
const socket = new JarvisSocket();

socket.on('tts_audio', (payload) => {
  // Voie principale (avec words) ou secours (sans) selon le payload.
  lipsync.play(payload).catch((err) => console.error('[lipsync]', err));
});

socket.on('state', (payload) => {
  // Relaie l'état à la vie autonome (ex. clignements accrus en « réflexion »).
  life.setState(payload.state);
  // Inhibe jawOpen des émotions pendant la parole (priorité visèmes).
  emotions.setSpeaking(payload.state === 'speaking');
  // Panneau ?debug : métriques de latence du pipeline (F5.1).
  if (config.debug && payload.metrics) showMetrics(payload.metrics);
});

// Bus émotion (F1.4 / F4.1) : {name, intensity} déclenche l'émotion.
socket.on('emotion', (payload) => {
  emotions.setEmotion(payload.name, {
    intensity: payload.intensity ?? 1,
    holdMs: payload.holdMs,
  });
});

// Geste ponctuel émis par le cerveau (F4.1).
socket.on('gesture', (payload) => {
  avatar.playGesture?.(payload.name, 2);
});

// Barge-in : couper la parole immédiatement.
function interrupt() {
  lipsync.stop();
  socket.send('interrupt', {});
}

// Overlay de métriques (?debug) — budget cible : fin de parole → 1er son < 2,5 s.
let debugEl = null;
function showMetrics(metrics) {
  if (!debugEl) {
    debugEl = document.createElement('div');
    debugEl.id = 'debug-metrics';
    document.getElementById('hud')?.appendChild(debugEl);
  }
  const fa = metrics.first_audio ?? '—';
  debugEl.textContent = `latence 1er son: ${fa} ms · ${JSON.stringify(metrics)}`;
}

// Premier geste utilisateur → débloque l'AudioContext (politique autoplay).
window.addEventListener(
  'pointerdown',
  () => lipsync.resume(),
  { once: true }
);

socket.connect();

// --- Micro + VAD (F3.1) ---------------------------------------------------
const mic = new MicCapture({
  socket,
  isAvatarSpeaking: () => lipsync.speaking,
  onStatus: (s) => {
    if (s.error) console.warn(s.error);
    if (typeof s.level === 'number') hud.setMicLevel(s.level);
  },
  onListen: () => {
    // À l'écoute : l'avatar prend l'air « réflexion » et incline la tête.
    emotions.setEmotion('reflexion', { intensity: 0.5, holdMs: 8000 });
  },
  onIdle: () => {},
});

// --- Interface utilisateur (F5.2) -----------------------------------------
const hud = new HUD({
  root: document.getElementById('hud'),
  socket,
  mic,
  lipsync,
  emotions,
  onConfig: ({ quality }) => {
    // La qualité graphique sera appliquée finement en F5.3.
    if (quality) console.info('[ui] qualité graphique:', quality);
  },
});

// Exposé pour les modules suivants (vie, émotions, UI) et le test manuel.
// Ex. en console : jarvis.say("Bonjour, je suis Jarvis.")
window.jarvis = {
  avatar,
  scene,
  socket,
  lipsync,
  life,
  emotions,
  mic,
  hud,
  interrupt,
  say: (text) => socket.send('user_text', { text }),
  emote: (name, intensity = 1) => emotions.setEmotion(name, { intensity }),
};

async function boot_() {
  rafId = requestAnimationFrame(frame); // démarre la scène de repli

  const result = await avatar.load(config.avatar.glbUrl);

  if (result.ok) {
    avatarActive = true;
    document.body.classList.add('avatar-active');
    life.start(); // vie autonome : regard, saccades, gestes ambiants
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
