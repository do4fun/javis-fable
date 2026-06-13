// vad.js — Détection d'activité vocale (VAD) côté navigateur (F3.1).
//
// Deux implémentations derrière une interface commune `process(frame) -> prob`:
//   - SileroVAD : modèle Silero (ONNX) via onnxruntime-web, vendorisé localement
//     dans /web/public/models (silero_vad.onnx) + runtime /vendor/ort. Précis.
//   - EnergyVAD : repli sans dépendance, basé sur l'énergie (RMS) avec plancher
//     de bruit adaptatif. Toujours disponible, hors-ligne, robuste.
//
// Les trames sont des Int16Array de 30 ms à 16 kHz (cf. pcm16k-worklet.js).

// Convertit une trame Int16 en Float32 [-1,1].
function toFloat(frame) {
  const f = new Float32Array(frame.length);
  for (let i = 0; i < frame.length; i++) f[i] = frame[i] / 32768;
  return f;
}

export class EnergyVAD {
  constructor({ threshold = 2.2 } = {}) {
    // Seuil exprimé en multiple du plancher de bruit (rapport signal/bruit).
    this.threshold = threshold;
    this._noise = 0.0015; // plancher initial
  }

  // Renvoie une probabilité de parole approximative [0,1].
  process(frame) {
    const f = toFloat(frame);
    let sum = 0;
    for (let i = 0; i < f.length; i++) sum += f[i] * f[i];
    const rms = Math.sqrt(sum / f.length);

    // Mise à jour lente du plancher de bruit quand c'est calme.
    if (rms < this._noise * 1.5) {
      this._noise = this._noise * 0.95 + rms * 0.05;
    }
    const ratio = rms / Math.max(this._noise, 1e-5);
    // Mappe le ratio sur [0,1] autour du seuil.
    return Math.max(0, Math.min(1, (ratio - this.threshold) / this.threshold + 0.5));
  }

  reset() {
    this._noise = 0.0015;
  }
}

export class SileroVAD {
  constructor({ modelUrl = '/models/silero_vad.onnx', ortPath = '/vendor/ort/' } = {}) {
    this.modelUrl = modelUrl;
    this.ortPath = ortPath;
    this.session = null;
    this._state = null;
    this._sr = null;
  }

  // Charge onnxruntime-web (vendorisé) + le modèle. Lève si indisponible.
  async load() {
    // @vite-ignore : runtime ESM vendorisé en local, pas de CDN.
    const ort = await import(/* @vite-ignore */ `${this.ortPath}ort.min.mjs`);
    ort.env.wasm.wasmPaths = this.ortPath; // wasm servis localement
    this.session = await ort.InferenceSession.create(this.modelUrl);
    this._ort = ort;
    // État LSTM Silero v5 : tenseur [2,1,128] initialisé à zéro.
    this._state = new ort.Tensor('float32', new Float32Array(2 * 1 * 128), [2, 1, 128]);
    this._sr = new ort.Tensor('int64', BigInt64Array.from([16000n]), []);
    return true;
  }

  async process(frame) {
    if (!this.session) return 0;
    const ort = this._ort;
    const input = new ort.Tensor('float32', toFloat(frame), [1, frame.length]);
    const out = await this.session.run({
      input,
      state: this._state,
      sr: this._sr,
    });
    // Récupère la proba + le nouvel état.
    this._state = out.stateN || out.state || this._state;
    const prob = out.output?.data?.[0] ?? 0;
    return prob;
  }

  reset() {
    if (this._ort) {
      this._state = new this._ort.Tensor(
        'float32',
        new Float32Array(2 * 1 * 128),
        [2, 1, 128]
      );
    }
  }
}

// Fabrique : tente Silero, repli automatique sur EnergyVAD.
export async function makeVAD(opts = {}) {
  if (opts.engine !== 'energy') {
    try {
      const v = new SileroVAD(opts);
      await v.load();
      console.info('[vad] Silero chargé.');
      return v;
    } catch (err) {
      console.warn('[vad] Silero indisponible → repli énergétique :', err.message);
    }
  }
  return new EnergyVAD(opts);
}
