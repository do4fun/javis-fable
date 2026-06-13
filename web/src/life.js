// life.js — LifeEngine : donne « vie » à l'avatar (F1.3).
//
// Principe (cf. prompt F1.3) : TalkingHead gère DÉJÀ nativement le clignement,
// la respiration, le balancement (sway) et un idle vivant. On NE les
// réimplémente PAS — on les configure et on complète uniquement les manques :
//   - contact visuel : la tête/les yeux suivent le pointeur (lookAt + lissage),
//     avec limites anatomiques et retour au regard caméra après inactivité ;
//   - saccades oculaires de faible amplitude ;
//   - gestes ambiants Mixamo joués aléatoirement (TalkingHead.playGesture) ;
//   - état « réflexion » : clignements plus fréquents (réglage TalkingHead).
//   - prefers-reduced-motion : amplitudes réduites.

import { config } from './config.js';

const DEG2RAD = Math.PI / 180;

export class LifeEngine {
  constructor(avatar) {
    this.avatar = avatar;
    this.cfg = config.life;
    this.reducedMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)'
    ).matches;

    // Cible de regard normalisée [-1,1] (x: gauche/droite, y: haut/bas).
    this._gazeTarget = { x: 0, y: 0 };
    this._gazeCurrent = { x: 0, y: 0 };
    this._lastPointerMs = 0;
    this._pointerActive = false;
    this._running = false;
    this._gestureTimer = null;
    this._saccadeTimer = null;

    this._onPointerMove = this._onPointerMove.bind(this);
    this._onPointerLeave = this._onPointerLeave.bind(this);
  }

  start() {
    if (this._running) return;
    this._running = true;

    // Délègue à TalkingHead l'idle natif (s'il expose un mode autonome).
    try {
      this.avatar.head?.start?.();
      this.avatar.head?.setAutoMotion?.(true);
    } catch {
      /* selon la version */
    }

    if (this.cfg.gaze.enabled) {
      window.addEventListener('pointermove', this._onPointerMove, { passive: true });
      window.addEventListener('pointerdown', this._onPointerMove, { passive: true });
      window.addEventListener('pointerleave', this._onPointerLeave);
    }

    this._scheduleAmbientGesture();
    this._scheduleSaccade();
  }

  stop() {
    this._running = false;
    window.removeEventListener('pointermove', this._onPointerMove);
    window.removeEventListener('pointerdown', this._onPointerMove);
    window.removeEventListener('pointerleave', this._onPointerLeave);
    clearTimeout(this._gestureTimer);
    clearTimeout(this._saccadeTimer);
  }

  // Appelée à chaque frame par la boucle principale (dt en secondes, réservé
  // pour un lissage indépendant du framerate ultérieur).
  update(_dt) {
    if (!this._running || !this.cfg.gaze.enabled) return;

    // Retour au regard caméra après inactivité du pointeur.
    if (
      this._pointerActive &&
      performance.now() - this._lastPointerMs > this.cfg.gaze.returnAfterMs
    ) {
      this._pointerActive = false;
      this._gazeTarget = { x: 0, y: 0 };
    }

    // Lissage (lerp) vers la cible.
    const k = this.reducedMotion ? this.cfg.gaze.smoothing * 0.5 : this.cfg.gaze.smoothing;
    this._gazeCurrent.x += (this._gazeTarget.x - this._gazeCurrent.x) * k;
    this._gazeCurrent.y += (this._gazeTarget.y - this._gazeCurrent.y) * k;

    this._applyGaze(this._gazeCurrent.x, this._gazeCurrent.y);
  }

  // --- État conversationnel : ajuste la « vie » selon l'état --------------
  setState(state) {
    // En « réflexion », on cligne plus souvent (réglage TalkingHead si dispo).
    try {
      if (state === 'thinking') {
        this.avatar.head?.setBlinkRate?.(1 / (4 * this.cfg.blink.thinkingFactor));
      } else {
        this.avatar.head?.setBlinkRate?.(1 / 4);
      }
    } catch {
      /* no-op */
    }
  }

  // --- Internes -----------------------------------------------------------

  _onPointerMove(ev) {
    this._lastPointerMs = performance.now();
    this._pointerActive = true;
    // Normalise la position écran en [-1, 1].
    const nx = (ev.clientX / window.innerWidth) * 2 - 1;
    const ny = (ev.clientY / window.innerHeight) * 2 - 1;
    const amp = this.reducedMotion ? 0.4 : 1;
    this._gazeTarget = { x: nx * amp, y: ny * amp };
  }

  _onPointerLeave() {
    this._pointerActive = false;
    this._gazeTarget = { x: 0, y: 0 };
  }

  // Convertit une cible normalisée en lookAt écran (px) borné anatomiquement.
  _applyGaze(nx, ny) {
    const yaw = Math.max(-1, Math.min(1, nx)) * this.cfg.gaze.maxYawDeg * DEG2RAD;
    const pitch = Math.max(-1, Math.min(1, ny)) * this.cfg.gaze.maxPitchDeg * DEG2RAD;

    // TalkingHead.lookAt attend des coordonnées écran (px). On reconvertit
    // la cible normalisée + saccade en pixels.
    const px = (yaw / (this.cfg.gaze.maxYawDeg * DEG2RAD) * 0.5 + 0.5) * window.innerWidth;
    const py = (pitch / (this.cfg.gaze.maxPitchDeg * DEG2RAD) * 0.5 + 0.5) * window.innerHeight;
    this.avatar.lookAt?.(px + this._saccadeX, py + this._saccadeY, 120);
  }

  // Saccades oculaires de faible amplitude (micro-mouvements aléatoires).
  _scheduleSaccade() {
    if (!this._running) return;
    const delay = 600 + Math.random() * 1400;
    this._saccadeTimer = setTimeout(() => {
      const amp = this.reducedMotion ? 4 : 12; // pixels
      this._saccadeX = (Math.random() - 0.5) * amp;
      this._saccadeY = (Math.random() - 0.5) * amp;
      this._scheduleSaccade();
    }, delay);
  }

  // Gestes ambiants Mixamo joués aléatoirement toutes les 20–60 s.
  _scheduleAmbientGesture() {
    if (!this._running || !this.cfg.ambientGestures.enabled) return;
    const { minIntervalMs, maxIntervalMs, pool } = this.cfg.ambientGestures;
    const delay = minIntervalMs + Math.random() * (maxIntervalMs - minIntervalMs);
    this._gestureTimer = setTimeout(() => {
      if (!this.reducedMotion && !this.avatar.lipsync?.speaking) {
        const name = pool[Math.floor(Math.random() * pool.length)];
        this.avatar.playGesture?.(name, 2.5);
      }
      this._scheduleAmbientGesture();
    }, delay);
  }
}

// Valeurs initiales pour les saccades.
LifeEngine.prototype._saccadeX = 0;
LifeEngine.prototype._saccadeY = 0;
