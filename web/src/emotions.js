// emotions.js — Système d'émotions de l'avatar (F1.4).
//
// Machine à états à six émotions : neutre, joie, tristesse, surprise, colere,
// reflexion. Chaque état est un preset de blendshapes ARKit (sourcils,
// paupières, bouche) + un mood TalkingHead + un geste optionnel.
//
// Couche ADDITIVE : on n'écrit QUE des morphs d'expression (jamais les
// visèmes), de sorte que l'émotion se superpose au lip-sync (F2.2) et aux
// comportements de vie (F1.3) sans les écraser.
// Priorités assumées : visèmes > émotion > idle.
//
// Transitions interpolées (400–800 ms), retour automatique au neutre après
// holdMs (défaut 6000) avec décroissance douce.

// Presets : nom de morph ARKit → valeur cible à intensité 1.
// (Si un morph est absent du modèle, setMorph l'ignore silencieusement.)
const PRESETS = {
  neutre: {},
  joie: {
    mouthSmileLeft: 0.85,
    mouthSmileRight: 0.85,
    cheekSquintLeft: 0.4,
    cheekSquintRight: 0.4,
    browInnerUp: 0.2,
    eyeSquintLeft: 0.2,
    eyeSquintRight: 0.2,
  },
  tristesse: {
    mouthFrownLeft: 0.55,
    mouthFrownRight: 0.55,
    browInnerUp: 0.7,
    browDownLeft: 0.1,
    browDownRight: 0.1,
    eyeLookDownLeft: 0.2,
    eyeLookDownRight: 0.2,
  },
  surprise: {
    eyeWideLeft: 0.7,
    eyeWideRight: 0.7,
    browInnerUp: 0.8,
    browOuterUpLeft: 0.6,
    browOuterUpRight: 0.6,
    // jawOpen volontairement modéré et inhibé pendant la parole (cf. update).
    jawOpen: 0.25,
  },
  colere: {
    browDownLeft: 0.8,
    browDownRight: 0.8,
    noseSneerLeft: 0.4,
    noseSneerRight: 0.4,
    mouthPressLeft: 0.4,
    mouthPressRight: 0.4,
    eyeSquintLeft: 0.35,
    eyeSquintRight: 0.35,
  },
  reflexion: {
    browDownLeft: 0.35,
    browInnerUp: 0.25,
    mouthPucker: 0.25,
    eyeLookUpLeft: 0.2,
    eyeLookUpRight: 0.2,
  },
};

// Mood TalkingHead associé (baseline globale).
const MOOD = {
  neutre: 'neutral',
  joie: 'happy',
  tristesse: 'sad',
  surprise: 'fear',
  colere: 'angry',
  reflexion: 'neutral',
};

// Geste optionnel déclenché à l'entrée de l'émotion.
const GESTURE = {
  joie: 'celebre',
  surprise: null,
  colere: null,
  reflexion: 'reflechit',
};

const ALL_MORPHS = [
  ...new Set(Object.values(PRESETS).flatMap((p) => Object.keys(p))),
];

export const EMOTIONS = Object.keys(PRESETS);

export class EmotionEngine {
  constructor(avatar) {
    this.avatar = avatar;
    this.current = 'neutre';
    this.intensity = 0;
    this._target = { name: 'neutre', intensity: 0 };
    // Valeurs lissées par morph (couche additive).
    this._values = Object.fromEntries(ALL_MORPHS.map((m) => [m, 0]));
    this._transitionMs = 600;
    this._elapsed = 0;
    this._holdUntil = 0;
    this._speaking = false;
  }

  // Indique si l'avatar parle (pour inhiber jawOpen — priorité visèmes).
  setSpeaking(v) {
    this._speaking = !!v;
  }

  /**
   * Déclenche une émotion.
   * @param {string} name - une de EMOTIONS
   * @param {{intensity?:number, holdMs?:number, transitionMs?:number}} opts
   */
  setEmotion(name, opts = {}) {
    if (!PRESETS[name]) {
      console.warn('[emotions] inconnue :', name);
      return;
    }
    const intensity = Math.max(0, Math.min(1, opts.intensity ?? 1));
    this._transitionMs = Math.max(
      400,
      Math.min(800, opts.transitionMs ?? 600)
    );
    const holdMs = opts.holdMs ?? 6000;

    this._target = { name, intensity };
    this._elapsed = 0;
    this._holdUntil = performance.now() + holdMs;
    this.current = name;
    this.intensity = intensity;

    // Baseline globale via TalkingHead + geste d'entrée éventuel.
    this.avatar.setMood?.(MOOD[name] || 'neutral');
    const g = GESTURE[name];
    if (g && intensity > 0.4) this.avatar.playGesture?.(g, 2);
  }

  // Appelée chaque frame (dt en secondes).
  update(dt) {
    const now = performance.now();

    // Retour automatique au neutre après la tenue (décroissance douce).
    if (this._target.name !== 'neutre' && now > this._holdUntil) {
      this._target = { name: 'neutre', intensity: 0 };
      this._elapsed = 0;
    }

    // Progression de transition [0..1].
    this._elapsed += dt * 1000;
    const t = Math.min(1, this._elapsed / this._transitionMs);
    // Lissage cubique (easeInOut) pour des transitions sans cassure.
    const ease = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

    const targetPreset = PRESETS[this._target.name] || {};
    for (const morph of ALL_MORPHS) {
      const goal = (targetPreset[morph] || 0) * this._target.intensity;
      // Interpolation vers l'objectif.
      this._values[morph] += (goal - this._values[morph]) * ease * 0.5;

      let v = this._values[morph];
      // Priorité visèmes : on n'impose pas jawOpen pendant la parole.
      if (morph === 'jawOpen' && this._speaking) v = 0;
      this.avatar.setMorph?.(morph, v);
    }
  }

  reset() {
    this.setEmotion('neutre', { intensity: 0, holdMs: 0 });
  }
}
