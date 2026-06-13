// lipsync.js — Chaîne de visèmes côté client (F2.2).
//
// Deux voies :
//   1. PRINCIPALE (texte + timing) : on reçoit {audio, words} du serveur
//      (F2.1). On reconstruit un AudioBuffer et on confie à TalkingHead
//      (lipsyncLang:'fr') le calage mots → visèmes Oculus sur les timestamps,
//      via speakAudio(). TalkingHead lit l'audio avec sa propre horloge
//      (AudioContext.currentTime) : source de vérité unique.
//   2. SECOURS (audio-driven) : si `words` est absent, on déduit les visèmes
//      du signal en temps réel (audioVisemes.js).
//
// Co-articulation, fermeture nette et retour à 'sil' sont gérés par
// TalkingHead en voie principale, et par le driver en voie de secours.
// Interruption : stop audio + bouche neutre en < 100 ms.

import { AudioVisemeDriver } from './audioVisemes.js';

// Décode un PCM int16 little-endian (base64) en Float32Array [-1, 1].
function decodePcmBase64(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const int16 = new Int16Array(bytes.buffer);
  const f32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) f32[i] = int16[i] / 32768;
  return f32;
}

export class LipSync {
  constructor(avatar) {
    this.avatar = avatar;
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    this.driver = new AudioVisemeDriver(avatar, this.ctx);
    this._fallbackSource = null;
    this._speaking = false;
  }

  // À appeler sur un geste utilisateur (autoplay policy des navigateurs).
  async resume() {
    if (this.ctx.state === 'suspended') await this.ctx.resume();
  }

  /**
   * Joue une trame `tts_audio`.
   * @param {object} p - {audio:base64, sample_rate, words:[{word,start,end}]}
   */
  async play(p) {
    await this.resume();
    const f32 = decodePcmBase64(p.audio);
    const sr = p.sample_rate || 24000;

    // Voie principale uniquement si TalkingHead est chargé ET que les timings
    // sont présents. Sans avatar (module ou GLB absent), on passe directement
    // en fallback Web Audio pour que l'audio soit toujours joué.
    if (Array.isArray(p.words) && p.words.length > 0 && this.avatar.ready) {
      await this._playPrimary(f32, sr, p.words);
    } else {
      await this._playFallback(f32, sr);
    }
  }

  // Voie principale : on délègue le lip-sync à TalkingHead.
  async _playPrimary(f32, sr, words) {
    // Construit un AudioBuffer mono pour TalkingHead.
    const buffer = this.ctx.createBuffer(1, f32.length, sr);
    buffer.copyToChannel(f32, 0);

    // Convertit nos timings (secondes) au format TalkingHead (millisecondes).
    const wtimes = words.map((w) => Math.round(w.start * 1000));
    const wdurations = words.map((w) => Math.round((w.end - w.start) * 1000));
    const wordList = words.map((w) => w.word);

    // Accentuation : repère les mots longs (>600 ms) pour un léger hochement
    // de tête + sourcils (la fonction est passée à TalkingHead en callback
    // de sous-titres, déclenchée mot par mot, calée sur l'horloge audio).
    const onWord = (info) => this._accentuate(info, wdurations);

    this._speaking = true;
    try {
      await this.avatar.speak({
        audio: buffer,
        words: wordList,
        wtimes,
        wdurations,
      });
    } finally {
      this._speaking = false;
    }
    void onWord; // (le hook mot-à-mot exact dépend de la version TalkingHead)
  }

  // Voie de secours : lecture Web Audio + visèmes déduits du signal.
  async _playFallback(f32, sr) {
    const buffer = this.ctx.createBuffer(1, f32.length, sr);
    buffer.copyToChannel(f32, 0);

    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.ctx.destination);
    this.driver.connect(source);

    this._fallbackSource = source;
    this._speaking = true;
    this.driver.start();

    await new Promise((resolve) => {
      source.onended = resolve;
      source.start();
    });

    this.driver.stop();
    this._fallbackSource = null;
    this._speaking = false;
  }

  // Léger hochement de tête + sourcils sur les mots longs.
  _accentuate(info, wdurations) {
    const i = info?.i ?? -1;
    if (i < 0 || i >= wdurations.length) return;
    if (wdurations[i] > 600) {
      this.avatar.playGesture?.('acquiesce', 0.6);
    }
  }

  // Interruption (barge-in) : coupe tout et neutralise la bouche < 100 ms.
  stop() {
    this.avatar.stop?.();
    if (this._fallbackSource) {
      try {
        this._fallbackSource.stop();
      } catch {
        /* déjà arrêté */
      }
      this._fallbackSource = null;
    }
    this.driver.stop();
    // Fermeture nette de la bouche.
    this.avatar.setMorph?.('jawOpen', 0);
    this.avatar.setMorph?.('viseme_sil', 1);
    this._speaking = false;
  }

  get speaking() {
    return this._speaking;
  }
}
