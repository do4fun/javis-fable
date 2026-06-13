// settings.js — Réglages persistés (localStorage) de l'interface (F5.2).

const KEY = 'jarvis.settings';

export const DEFAULTS = {
  subtitles: true,
  micMode: 'handsfree', // 'ptt' | 'toggle' | 'handsfree'
  quality: 'high', // 'low' | 'medium' | 'high'
  theme: 'dark', // 'dark' | 'light'
  voice: 'ff_siwis',
  speed: 1.0,
  model: 'llama3.1:8b',
};

export class Settings {
  constructor() {
    this.values = { ...DEFAULTS, ...this._load() };
  }

  _load() {
    try {
      return JSON.parse(localStorage.getItem(KEY) || '{}');
    } catch {
      return {};
    }
  }

  get(key) {
    return this.values[key];
  }

  set(key, value) {
    this.values[key] = value;
    try {
      localStorage.setItem(KEY, JSON.stringify(this.values));
    } catch {
      /* mode privé : on ignore */
    }
  }

  // Applique le thème et la qualité graphique au document.
  applyTheme() {
    document.body.dataset.theme = this.values.theme;
  }
}
