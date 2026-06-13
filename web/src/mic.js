// mic.js — Capture micro + VAD + envoi au serveur (F3.1).
//
// - getUserMedia + AudioWorklet (pcm16k-worklet.js) : PCM 16 kHz mono, trames
//   30 ms ;
// - VAD local (Silero ONNX, repli énergétique) : on n'envoie l'audio que
//   pendant la parole + 300 ms de marge ;
// - modes : push-to-talk, toggle, mains-libres (VAD continu) ;
// - barge-in : parler pendant que l'avatar parle émet `interrupt` ;
// - état visuel : callbacks d'UI + l'avatar prend l'air « réflexion » et
//   incline la tête à l'écoute.
//
// Confidentialité : aucune donnée micro ne quitte localhost (envoi sur le WS
// local uniquement).

import { makeVAD } from './vad.js';
import { config } from './config.js';

const SPEECH_ON = 0.6; // proba VAD d'entrée en parole
const SPEECH_OFF = 0.35; // proba VAD de sortie
const HANGOVER_MS = 300; // marge après la fin de parole

export class MicCapture {
  /**
   * @param {object} deps - { socket, onStatus, isAvatarSpeaking, onListen, onIdle }
   */
  constructor(deps = {}) {
    this.socket = deps.socket;
    this.onStatus = deps.onStatus || (() => {});
    this.isAvatarSpeaking = deps.isAvatarSpeaking || (() => false);
    this.onListen = deps.onListen || (() => {}); // entrée en écoute (UX avatar)
    this.onIdle = deps.onIdle || (() => {});

    this.mode = config.mic.mode; // 'ptt' | 'toggle' | 'handsfree'
    this.stream = null;
    this.ctx = null;
    this.node = null;
    this.vad = null;
    this.active = false; // capture en cours (micro ouvert)
    this._speaking = false; // segment de parole en cours
    this._lastSpeechMs = 0;
    this._ptt = false; // bouton PTT maintenu
  }

  async init() {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch (err) {
      this.onStatus({ error: 'Micro refusé. Utilise le clavier pour écrire à Jarvis.' });
      console.warn('[mic] permission refusée :', err.message);
      return false;
    }

    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    await this.ctx.audioWorklet.addModule('/worklets/pcm16k-worklet.js');
    const source = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, 'pcm16k-processor');
    source.connect(this.node);
    // On ne connecte PAS le worklet à la sortie (pas de larsen).

    this.vad = await makeVAD(config.mic.vad);
    this.node.port.onmessage = (ev) => this._onFrame(ev.data);
    return true;
  }

  setMode(mode) {
    this.mode = mode;
  }

  // Démarre la capture selon le mode.
  start() {
    this.active = true;
    if (this.ctx?.state === 'suspended') this.ctx.resume();
    this.onStatus({ listening: true, mode: this.mode });
  }

  stop() {
    this.active = false;
    this._endSpeech();
    this.onStatus({ listening: false });
  }

  // Push-to-talk : à brancher sur pointerdown/up d'un bouton micro.
  pttDown() {
    this._ptt = true;
    this.start();
  }
  pttUp() {
    this._ptt = false;
    this._endSpeech();
  }

  async _onFrame(frame) {
    if (!this.active) return;

    // En push-to-talk, on envoie tant que le bouton est maintenu (sans VAD).
    if (this.mode === 'ptt') {
      if (this._ptt) {
        if (!this._speaking) this._startSpeech();
        this.socket?.sendBinary(frame.buffer);
      }
      return;
    }

    // Toggle / mains-libres : le VAD décide.
    const prob = await this.vad.process(frame);
    const level = Math.round(prob * 100);

    const now = performance.now();
    if (prob > SPEECH_ON) {
      this._lastSpeechMs = now;
      if (!this._speaking) {
        this._startSpeech();
        // Barge-in : couper la parole de l'avatar si nécessaire.
        if (this.isAvatarSpeaking()) this.socket?.send('interrupt', {});
      }
    }

    if (this._speaking) {
      this.socket?.sendBinary(frame.buffer);
      // Fin de parole après marge de silence.
      if (prob < SPEECH_OFF && now - this._lastSpeechMs > HANGOVER_MS) {
        this._endSpeech();
      }
    }

    this.onStatus({ listening: true, speech: this._speaking, level });
  }

  _startSpeech() {
    this._speaking = true;
    this.socket?.send('audio_chunk', { event: 'start', sample_rate: 16000 });
    this.onListen(); // avatar : réflexion + inclinaison de tête
  }

  _endSpeech() {
    if (!this._speaking) return;
    this._speaking = false;
    this.socket?.send('audio_chunk', { event: 'end' });
    this.onIdle();
  }

  dispose() {
    this.stop();
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close();
  }
}
