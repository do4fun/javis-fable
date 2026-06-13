// audioVisemes.js — Voie de secours « audio-driven » du lip-sync (F2.2).
//
// Quand les timings par mot (`words`) sont absents, on déduit les visèmes du
// signal audio en temps réel (à la manière de wawa-lipsync / HeadAudio) :
//   - énergie globale → ouverture de la mâchoire (jawOpen) ;
//   - centre de gravité spectral → voyelle dominante (aa / E / I / O / U).
// On lisse les valeurs (co-articulation) et on referme la bouche au silence.
//
// Volontairement léger : c'est un repli. La voie principale (TalkingHead +
// timings) reste préférée quand les `words` sont disponibles.

const VOWEL_VISEMES = ['viseme_U', 'viseme_O', 'viseme_aa', 'viseme_E', 'viseme_I'];

export class AudioVisemeDriver {
  /**
   * @param {object} avatar - AvatarManager (pour appliquer les morphs).
   * @param {AudioContext} ctx
   */
  constructor(avatar, ctx) {
    this.avatar = avatar;
    this.ctx = ctx;
    this.analyser = ctx.createAnalyser();
    this.analyser.fftSize = 1024;
    this.analyser.smoothingTimeConstant = 0.6; // lissage temporel intégré
    this._freq = new Uint8Array(this.analyser.frequencyBinCount);
    this._time = new Uint8Array(this.analyser.fftSize);
    this._raf = null;
    this._smoothJaw = 0;
    this._smoothVowel = new Array(VOWEL_VISEMES.length).fill(0);
  }

  // Branche une source audio dans l'analyseur (sans couper la sortie).
  connect(sourceNode) {
    sourceNode.connect(this.analyser);
  }

  start() {
    if (this._raf) return;
    const loop = () => {
      this._raf = requestAnimationFrame(loop);
      this._tick();
    };
    this._raf = requestAnimationFrame(loop);
  }

  stop() {
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = null;
    this._reset();
  }

  _tick() {
    this.analyser.getByteTimeDomainData(this._time);
    this.analyser.getByteFrequencyData(this._freq);

    // Énergie (RMS) du signal temporel → ouverture mâchoire.
    let sum = 0;
    for (let i = 0; i < this._time.length; i++) {
      const v = (this._time[i] - 128) / 128;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / this._time.length);
    const targetJaw = Math.min(1, rms * 3.2); // gain empirique

    // Centre de gravité spectral → choix de la voyelle.
    let num = 0;
    let den = 0;
    for (let i = 0; i < this._freq.length; i++) {
      num += i * this._freq[i];
      den += this._freq[i];
    }
    const centroid = den > 0 ? num / den / this._freq.length : 0; // 0..1
    const vowelIdx = Math.min(
      VOWEL_VISEMES.length - 1,
      Math.floor(centroid * VOWEL_VISEMES.length)
    );

    // Lissage (co-articulation) : approche douce vers la cible.
    this._smoothJaw += (targetJaw - this._smoothJaw) * 0.4;

    this.avatar.setMorph?.('jawOpen', this._smoothJaw * 0.7);
    for (let i = 0; i < VOWEL_VISEMES.length; i++) {
      const target = i === vowelIdx ? this._smoothJaw : 0;
      this._smoothVowel[i] += (target - this._smoothVowel[i]) * 0.35;
      this.avatar.setMorph?.(VOWEL_VISEMES[i], this._smoothVowel[i]);
    }
  }

  _reset() {
    this._smoothJaw = 0;
    this._smoothVowel.fill(0);
    this.avatar.setMorph?.('jawOpen', 0);
    for (const v of VOWEL_VISEMES) this.avatar.setMorph?.(v, 0);
  }
}
