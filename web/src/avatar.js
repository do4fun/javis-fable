// avatar.js — Wrapper AvatarManager autour de la classe TalkingHead.
//
// TalkingHead (met4citizen) gère son propre rendu Three.js dans un conteneur
// DOM. AvatarManager l'instancie, charge un avatar Ready Player Me (GLB local)
// et expose une API simple, stable pour le reste de l'app :
//
//   load(url)                  → charge le GLB, renvoie un rapport de compat
//   speak(audio, visemes)      → fait parler l'avatar (lip-sync, F2.2)
//   setMood(name)              → humeur globale (neutral/happy/…)
//   lookAt(x, y)               → regarde un point écran (px)
//   playGesture(name)          → joue un geste ponctuel
//   stop()                     → coupe la parole en cours
//
// Contrainte : aucun réseau externe. Le module TalkingHead et le GLB sont
// vendorisés/locaux (cf. /docs/avatar.md). L'import est dynamique pour que le
// build reste autonome même si le module n'est pas encore déposé.

import { config, REQUIRED_MORPHS } from './config.js';

// Correspondance de nos humeurs internes → moods TalkingHead.
const MOOD_MAP = {
  neutral: 'neutral',
  neutre: 'neutral',
  happy: 'happy',
  joie: 'happy',
  sad: 'sad',
  tristesse: 'sad',
  angry: 'angry',
  colere: 'angry',
  surprise: 'fear', // TalkingHead n'a pas 'surprise' natif → approximation
  fear: 'fear',
  reflexion: 'neutral',
};

export class AvatarManager {
  /**
   * @param {HTMLElement} container - élément DOM hôte du rendu TalkingHead.
   * @param {(p:{loaded:boolean,progress:number,message:string}) => void} onStatus
   */
  constructor(container, onStatus = () => {}) {
    this.container = container;
    this.onStatus = onStatus;
    this.head = null; // instance TalkingHead
    this.ready = false;
    this.lastError = null;
  }

  // Charge le module TalkingHead (vendorisé) puis l'avatar GLB.
  async load(url = config.avatar.glbUrl) {
    this._status(0, 'Chargement du moteur d’avatar…');

    let TalkingHead;
    try {
      // @vite-ignore : on ne veut PAS que Vite résolve/bundle ce chemin au build.
      // Il est chargé à l'exécution depuis /vendor (asset local servi tel quel).
      const mod = await import(/* @vite-ignore */ config.avatar.modulePath);
      TalkingHead = mod.TalkingHead || mod.default;
    } catch (err) {
      this.lastError = err;
      this._fail(
        'Module TalkingHead introuvable. Dépose `talkinghead.mjs` dans ' +
          '/web/vendor/talkinghead/ (voir /docs/avatar.md).'
      );
      return { ok: false, reason: 'module_missing', error: err };
    }

    try {
      this.head = new TalkingHead(this.container, {
        ttsEndpoint: null, // on fournit l'audio nous-mêmes (Kokoro, F2.1)
        lipsyncModules: ['fi', 'en'], // base ; le module 'fr' est géré en F2.2
        lipsyncLang: config.avatar.lipsyncLang,
        cameraView: config.avatar.cameraView,
        avatarMood: config.avatar.mood,
        modelPixelRatio: Math.min(window.devicePixelRatio || 1, 2),
      });
    } catch (err) {
      this.lastError = err;
      this._fail('Impossible d’initialiser TalkingHead : ' + err.message);
      return { ok: false, reason: 'init_failed', error: err };
    }

    // Chargement du GLB avec barre de progression.
    try {
      await this.head.showAvatar(
        {
          url,
          body: 'F', // morphologie ; ajustable selon l'avatar RPM
          avatarMood: config.avatar.mood,
          lipsyncLang: config.avatar.lipsyncLang,
        },
        (ev) => {
          // ev.lengthComputable / ev.loaded / ev.total
          const p = ev && ev.lengthComputable ? ev.loaded / ev.total : 0;
          this._status(p, 'Chargement de l’avatar…');
        }
      );
    } catch (err) {
      this.lastError = err;
      this._fail(
        `Avatar introuvable ou invalide (${url}). Dépose jarvis.glb dans ` +
          '/web/public/avatars/ (voir /docs/avatar.md).'
      );
      return { ok: false, reason: 'glb_missing', error: err };
    }

    this.ready = true;
    this._meshesCache = null; // (re)construit le cache au premier accès
    const report = this._checkMorphs();
    this._status(1, 'Avatar prêt.', true);
    return { ok: true, report };
  }

  // Vérifie la présence des morph targets requis et loggue un rapport.
  _checkMorphs() {
    const present = this._availableMorphs();
    const missing = REQUIRED_MORPHS.filter(
      (m) => !present.some((p) => p.toLowerCase().includes(m.toLowerCase()))
    );
    const report = { total: REQUIRED_MORPHS.length, missing, presentCount: present.length };

    if (missing.length === 0) {
      console.info('[avatar] Tous les blendshapes requis sont présents.');
    } else {
      console.warn(
        `[avatar] ${missing.length} blendshape(s) manquant(s) — ` +
          'le lip-sync/les émotions seront dégradés :',
        missing
      );
    }
    return report;
  }

  // Récupère la liste des morph targets exposés par le modèle chargé.
  _availableMorphs() {
    const names = new Set();
    for (const mesh of this._morphMeshes()) {
      for (const k of Object.keys(mesh.morphTargetDictionary || {})) names.add(k);
    }
    return [...names];
  }

  // Localise (et met en cache) les meshes porteurs de morph targets.
  _morphMeshes() {
    if (this._meshesCache) return this._meshesCache;
    const root =
      this.head?.armature || this.head?.avatar?.scene || this.head?.scene || null;
    const meshes = [];
    if (root && typeof root.traverse === 'function') {
      root.traverse((o) => {
        if (o.morphTargetDictionary && o.morphTargetInfluences) meshes.push(o);
      });
    }
    this._meshesCache = meshes;
    return meshes;
  }

  // Applique directement une valeur de morph target (voie de secours F2.2).
  // La voie principale passe par TalkingHead.speakAudio() ; ceci sert au
  // driver audio-driven quand les timings de mots sont absents.
  setMorph(name, value) {
    const v = Math.max(0, Math.min(1, value));
    for (const mesh of this._morphMeshes()) {
      const idx = mesh.morphTargetDictionary[name];
      if (idx !== undefined) mesh.morphTargetInfluences[idx] = v;
    }
  }

  // --- API publique ---------------------------------------------------------

  /**
   * Fait parler l'avatar à partir d'un audio déjà synthétisé + timings.
   * @param {object} audio - { audio, words, wtimes, wdurations, visemes, vtimes, vdurations }
   */
  async speak(audio) {
    if (!this.ready || !this.head) return;
    try {
      await this.head.speakAudio(audio);
    } catch (err) {
      console.error('[avatar] speak a échoué :', err);
    }
  }

  setMood(name) {
    if (!this.ready || !this.head) return;
    const mood = MOOD_MAP[name] || 'neutral';
    try {
      this.head.setMood(mood);
    } catch (err) {
      console.warn('[avatar] setMood ignoré :', err.message);
    }
  }

  // x,y en pixels écran ; null = retour au regard caméra.
  lookAt(x, y, durationMs = 500) {
    if (!this.ready || !this.head) return;
    try {
      this.head.lookAt(x, y, durationMs);
    } catch {
      /* certaines versions n'exposent pas lookAt avec ces args */
    }
  }

  playGesture(name, durationS = 3) {
    if (!this.ready || !this.head) return;
    try {
      this.head.playGesture(name, durationS);
    } catch (err) {
      console.warn('[avatar] geste inconnu :', name, err.message);
    }
  }

  stop() {
    if (!this.head) return;
    try {
      this.head.stopSpeaking();
    } catch {
      /* no-op */
    }
  }

  // Bascule cadrage tête-épaules / plan américain.
  setView(view = 'upper') {
    if (!this.head) return;
    try {
      this.head.setView(view);
    } catch {
      /* no-op */
    }
  }

  // --- Internes ------------------------------------------------------------

  _status(progress, message, loaded = false) {
    this.onStatus({ loaded, progress, message });
  }

  _fail(message) {
    console.error('[avatar]', message);
    this._status(0, message, false);
  }
}
