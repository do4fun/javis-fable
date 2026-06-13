// pcm16k-worklet.js — AudioWorkletProcessor : ré-échantillonne le micro vers
// 16 kHz mono et émet des trames PCM Int16 de 30 ms (480 échantillons).
//
// Servi en statique depuis /public/worklets (pas de bundling : c'est un module
// AudioWorklet chargé par addModule). Aucune dépendance externe.

const TARGET_RATE = 16000;
const FRAME_MS = 30;
const FRAME_SAMPLES = (TARGET_RATE * FRAME_MS) / 1000; // 480

class PCM16kProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // Ratio de décimation entre la fréquence du contexte et 16 kHz.
    this._ratio = sampleRate / TARGET_RATE;
    this._buf = []; // accumulateur d'échantillons 16 kHz (float)
    this._pos = 0; // position fractionnaire dans le flux d'entrée
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0]; // mono (1re voie)
    if (!channel) return true;

    // Ré-échantillonnage linéaire simple vers 16 kHz.
    for (let i = 0; i < channel.length; i++) {
      this._pos += 1;
      if (this._pos >= this._ratio) {
        this._pos -= this._ratio;
        this._buf.push(channel[i]);

        if (this._buf.length >= FRAME_SAMPLES) {
          // Convertit en Int16 et envoie la trame.
          const frame = new Int16Array(FRAME_SAMPLES);
          for (let j = 0; j < FRAME_SAMPLES; j++) {
            const s = Math.max(-1, Math.min(1, this._buf[j]));
            frame[j] = s < 0 ? s * 32768 : s * 32767;
          }
          this.port.postMessage(frame, [frame.buffer]);
          this._buf = this._buf.slice(FRAME_SAMPLES);
        }
      }
    }
    return true; // garde le processor vivant
  }
}

registerProcessor('pcm16k-processor', PCM16kProcessor);
