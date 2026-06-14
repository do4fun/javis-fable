// avatarVRM.js — VRMAvatarManager : équivalent VRM de AvatarManager.
//
// Expose EXACTEMENT la même API publique que web/src/avatar.js (load, speak,
// setMood, lookAt, playGesture, stop, setMorph, setView + propriétés ready/head)
// pour que lipsync.js, emotions.js, life.js et main.js fonctionnent à
// l'identique, sans connaître le moteur sous-jacent.
//
// Différences internes vs TalkingHead :
//  - le rendu/idle/spring bones sont gérés par VRMEngine ;
//  - les émotions (ARKit) et visèmes (Oculus) écrits via setMorph sont
//    TRADUITS en expressions VRM natives (aa/ih/ou/ee/oh, happy/angry/sad…) ;
//  - le lip-sync passe par la voie audio-driven de lipsync.js (flag
//    `audioLipsync`), car VRM n'a pas l'équivalent de speakAudio().

import { config } from '../config.js';
import { VRMEngine } from './vrmEngine.js';

// Mood interne (valeurs émises par emotions.js) → expression émotion VRM.
const MOOD_TO_VRM = {
  neutral: 'neutral',
  happy: 'happy',
  sad: 'sad',
  angry: 'angry',
  fear: 'surprised', // VRM n'a pas 'fear' → 'surprised'
  surprised: 'surprised',
  relaxed: 'relaxed',
};

// Signature de morphs ARKit (écrits par emotions.js) servant à dériver
// l'INTENSITÉ de l'émotion VRM courante (montée/décroissance lissées).
// clé = expression VRM, valeur = { morph: valeurMaxPreset }.
const EMOTION_SIGNATURE = {
  happy: { mouthSmileLeft: 0.85, mouthSmileRight: 0.85 },
  sad: { mouthFrownLeft: 0.55, mouthFrownRight: 0.55 },
  angry: { browDownLeft: 0.8, browDownRight: 0.8 },
  surprised: { eyeWideLeft: 0.7, eyeWideRight: 0.7 },
  relaxed: { mouthPucker: 0.25 },
};

// Visèmes Oculus (écrits par audioVisemes.js / lipsync) → visèmes VRM.
const VISEME_TO_VRM = {
  viseme_aa: 'aa',
  viseme_E: 'ee',
  viseme_I: 'ih',
  viseme_O: 'oh',
  viseme_U: 'ou',
};

// Expressions VRM attendues pour un avatar pleinement fonctionnel.
const REQUIRED_VRM_EXPR = [
  'aa', 'ih', 'ou', 'ee', 'oh', // visèmes
  'happy', 'angry', 'sad', 'surprised', 'neutral', // émotions
  'blink', // clignement
];

export class VRMAvatarManager {
  /**
   * @param {HTMLElement} container
   * @param {(p:{loaded:boolean,progress:number,message:string}) => void} onStatus
   */
  constructor(container, onStatus = () => {}) {
    this.container = container;
    this.onStatus = onStatus;
    this.head = null; // instance VRMEngine (expose scene/renderer pour le décor)
    this.ready = false;
    this.lastError = null;

    // Indique à lipsync.js d'utiliser la voie audio-driven (pas speakAudio).
    this.audioLipsync = true;

    // État des morphs écrits par emotions.js / le driver audio (absolu,
    // dernière écriture conservée). Traduit en expressions VRM chaque frame.
    this._morphState = Object.create(null);
    this._mood = 'neutral';
  }

  async load(url = config.avatar.vrmUrl) {
    this._status(0, 'Chargement du moteur VRM…');

    try {
      this.head = new VRMEngine(this.container, {
        pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
      });
    } catch (err) {
      this.lastError = err;
      this._fail('Impossible d’initialiser le moteur VRM : ' + err.message);
      return { ok: false, reason: 'init_failed', error: err };
    }

    try {
      await this.head.load(url, (ev) => {
        const p = ev && ev.lengthComputable ? ev.loaded / ev.total : 0;
        this._status(p, 'Chargement de l’avatar VRM…');
      });
    } catch (err) {
      this.lastError = err;
      this._fail(
        `Avatar VRM introuvable ou invalide (${url}). Dépose jarvis.vrm dans ` +
          '/web/public/avatars/ (voir /docs/vrm.md).'
      );
      return { ok: false, reason: 'vrm_missing', error: err };
    }

    // Le manager pousse les expressions chaque frame via ce callback.
    this.head.onUpdate = () => this._applyMorphState();
    this.head.start();

    this.ready = true;
    const report = this._checkExpressions();
    this._status(1, 'Avatar prêt.', true);
    return { ok: true, report };
  }

  // Vérifie la présence des expressions VRM attendues (rapport de compat).
  _checkExpressions() {
    const em = this.head.vrm?.expressionManager;
    const present = new Set(
      (em?.expressions || []).map((e) => e.expressionName)
    );
    const missing = REQUIRED_VRM_EXPR.filter((n) => !present.has(n));
    const report = { total: REQUIRED_VRM_EXPR.length, missing, presentCount: present.size };

    if (missing.length === 0) {
      console.info('[avatar] VRM : toutes les expressions requises sont présentes.');
    } else {
      console.warn(
        `[avatar] VRM : ${missing.length} expression(s) manquante(s) — ` +
          'lip-sync/émotions dégradés :',
        missing
      );
    }
    return report;
  }

  // Traduit l'état des morphs (ARKit/Oculus) en expressions VRM, chaque frame.
  _applyMorphState() {
    const s = this._morphState;
    const set = (name, v) => this.head.setExpressionTarget(name, v);

    // Visèmes : aa intègre aussi l'ouverture mâchoire (jawOpen).
    const jaw = s.jawOpen || 0;
    set('aa', Math.max(s.viseme_aa || 0, jaw * 0.85));
    set('ee', s.viseme_E || 0);
    set('ih', s.viseme_I || 0);
    set('oh', s.viseme_O || 0);
    set('ou', s.viseme_U || 0);

    // Émotion : seule l'émotion choisie par setMood est appliquée, avec une
    // intensité dérivée des morphs ARKit (montée/décroissance de emotions.js).
    const vrmMood = MOOD_TO_VRM[this._mood] || 'neutral';
    const sig = EMOTION_SIGNATURE[vrmMood];
    if (sig) {
      let intensity = 0;
      for (const [morph, max] of Object.entries(sig)) {
        intensity = Math.max(intensity, (s[morph] || 0) / max);
      }
      set(vrmMood, Math.min(1, intensity));
    }
  }

  // --- API publique (identique à AvatarManager) -----------------------------

  // Écriture directe d'un « morph » (nom ARKit/Oculus). Stocké puis traduit.
  setMorph(name, value) {
    this._morphState[name] = Math.max(0, Math.min(1, value));
  }

  // Non utilisé en VRM (lip-sync via voie audio-driven), gardé pour parité.
  async speak() {
    /* no-op : lipsync.js route VRM vers _playFallback (audioLipsync=true) */
  }

  setMood(name) {
    this._mood = name in MOOD_TO_VRM ? name : 'neutral';
  }

  lookAt(x, y) {
    if (!this.ready || !this.head) return;
    this.head.lookAtScreen(x, y);
  }

  playGesture(name, durationS = 2) {
    if (!this.ready || !this.head) return;
    this.head.playGesture(name, durationS);
  }

  stop() {
    // Ferme la bouche immédiatement (barge-in).
    for (const v of ['viseme_aa', 'viseme_E', 'viseme_I', 'viseme_O', 'viseme_U', 'jawOpen']) {
      this._morphState[v] = 0;
    }
  }

  setView() {
    /* no-op : le cadrage VRM est géré par VRMEngine._frameCamera() */
  }

  // --- Internes -------------------------------------------------------------

  _status(progress, message, loaded = false) {
    this.onStatus({ loaded, progress, message });
  }

  _fail(message) {
    console.error('[avatar]', message);
    this._status(0, message, false);
  }
}

void VISEME_TO_VRM; // table de référence (mapping appliqué inline ci-dessus)
