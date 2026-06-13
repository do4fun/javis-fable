// hud.js — Interface utilisateur de Jarvis (F5.2).
//
// Construit et pilote le HUD : bandeau d'état, niveau micro, sous-titres
// synchronisés (aria-live), panneau de réglages persistés, historique repliable
// avec export .txt, et saisie clavier (repli si micro indisponible).
//
// Accessibilité : navigation clavier complète, focus visibles (CSS), aria-live
// sur les sous-titres, prefers-reduced-motion respecté par les transitions CSS.

import { Settings } from './settings.js';

const STATE_LABELS = {
  idle: 'Prêt',
  listening: 'À l’écoute…',
  thinking: 'Réfléchit…',
  speaking: 'Parle…',
};

export class HUD {
  /**
   * @param {object} deps - { root, socket, mic, lipsync, emotions, onConfig }
   */
  constructor(deps) {
    this.socket = deps.socket;
    this.mic = deps.mic;
    this.lipsync = deps.lipsync;
    this.settings = new Settings();
    this.onConfig = deps.onConfig || (() => {});
    this.root = deps.root;
    this.history = []; // {role, text}
    this._avatarLine = '';

    this.settings.applyTheme();
    this._build();
    this._wireSocket();
  }

  // --- Construction du DOM ------------------------------------------------

  _build() {
    this.el = document.createElement('div');
    this.el.id = 'hud-root';
    this.el.innerHTML = `
      <div id="status-banner" role="status" aria-live="polite">
        <span class="dot"></span><span class="label">Prêt</span>
        <span class="mic-meter" aria-hidden="true"><i></i></span>
      </div>

      <div id="subtitles" aria-live="polite" aria-atomic="false">
        <p class="sub-user"></p>
        <p class="sub-avatar"></p>
      </div>

      <div id="hud-controls">
        <button id="btn-mic" title="Parler (micro)" aria-label="Activer le micro">🎤</button>
        <button id="btn-stop" title="Couper la parole" aria-label="Interrompre">⏹</button>
        <button id="btn-history" title="Historique" aria-label="Afficher l’historique">🗂</button>
        <button id="btn-settings" title="Réglages" aria-label="Ouvrir les réglages">⚙</button>
      </div>

      <form id="text-input">
        <input type="text" placeholder="Écris à Jarvis…" aria-label="Message à Jarvis" />
        <button type="submit" aria-label="Envoyer">Envoyer</button>
      </form>

      <aside id="drawer-history" class="drawer" aria-hidden="true">
        <header><h2>Conversation</h2>
          <button id="btn-export" title="Exporter en .txt">Exporter</button>
          <button id="btn-history-close" aria-label="Fermer">✕</button>
        </header>
        <div class="history-list"></div>
      </aside>

      <aside id="drawer-settings" class="drawer" aria-hidden="true">
        <header><h2>Réglages</h2>
          <button id="btn-settings-close" aria-label="Fermer">✕</button>
        </header>
        <div class="settings-list"></div>
      </aside>
    `;
    this.root.appendChild(this.el);

    this._cacheRefs();
    this._buildSettings();
    this._wireControls();
    this._applySubtitlesVisibility();
  }

  _cacheRefs() {
    const $ = (s) => this.el.querySelector(s);
    this.banner = $('#status-banner');
    this.bannerLabel = $('#status-banner .label');
    this.micMeter = $('#status-banner .mic-meter i');
    this.subUser = $('.sub-user');
    this.subAvatar = $('.sub-avatar');
    this.subtitles = $('#subtitles');
    this.historyDrawer = $('#drawer-history');
    this.settingsDrawer = $('#drawer-settings');
    this.historyList = $('.history-list');
    this.input = $('#text-input input');
  }

  // --- Réglages -----------------------------------------------------------

  _buildSettings() {
    const list = this.el.querySelector('.settings-list');
    const s = this.settings;
    const rows = [
      this._select('Sous-titres', 'subtitles', [
        ['true', 'Activés'],
        ['false', 'Désactivés'],
      ], String(s.get('subtitles'))),
      this._select('Mode micro', 'micMode', [
        ['handsfree', 'Mains-libres'],
        ['toggle', 'Bascule'],
        ['ptt', 'Maintenir'],
      ], s.get('micMode')),
      this._select('Qualité', 'quality', [
        ['low', 'Basse'],
        ['medium', 'Moyenne'],
        ['high', 'Haute'],
      ], s.get('quality')),
      this._select('Thème', 'theme', [
        ['dark', 'Sombre'],
        ['light', 'Clair'],
      ], s.get('theme')),
      this._range('Vitesse de voix', 'speed', 0.7, 1.4, 0.05, s.get('speed')),
      this._text('Modèle Ollama', 'model', s.get('model')),
    ];
    rows.forEach((r) => list.appendChild(r));
  }

  _row(labelText, control, id) {
    const row = document.createElement('label');
    row.className = 'setting-row';
    row.htmlFor = id;
    row.innerHTML = `<span>${labelText}</span>`;
    row.appendChild(control);
    return row;
  }

  _select(label, key, options, current) {
    const sel = document.createElement('select');
    sel.id = `set-${key}`;
    for (const [value, text] of options) {
      const o = document.createElement('option');
      o.value = value;
      o.textContent = text;
      if (value === current) o.selected = true;
      sel.appendChild(o);
    }
    sel.addEventListener('change', () => this._onSetting(key, sel.value));
    return this._row(label, sel, sel.id);
  }

  _range(label, key, min, max, step, current) {
    const r = document.createElement('input');
    r.type = 'range';
    r.id = `set-${key}`;
    Object.assign(r, { min, max, step, value: current });
    r.addEventListener('input', () => this._onSetting(key, parseFloat(r.value)));
    return this._row(label, r, r.id);
  }

  _text(label, key, current) {
    const t = document.createElement('input');
    t.type = 'text';
    t.id = `set-${key}`;
    t.value = current;
    t.addEventListener('change', () => this._onSetting(key, t.value));
    return this._row(label, t, t.id);
  }

  _onSetting(key, raw) {
    let value = raw;
    if (key === 'subtitles') value = raw === 'true';
    this.settings.set(key, value);

    if (key === 'theme') this.settings.applyTheme();
    if (key === 'subtitles') this._applySubtitlesVisibility();
    if (key === 'micMode') this.mic?.setMode(value);
    if (key === 'quality') this.onConfig({ quality: value });
    if (['voice', 'speed', 'model'].includes(key)) {
      // Transmis au serveur (le TTS/LLM s'y adaptera).
      this.socket?.send('config', {
        voice: this.settings.get('voice'),
        speed: this.settings.get('speed'),
        model: this.settings.get('model'),
      });
    }
  }

  _applySubtitlesVisibility() {
    this.subtitles.style.display = this.settings.get('subtitles') ? '' : 'none';
  }

  // --- Contrôles ----------------------------------------------------------

  _wireControls() {
    const $ = (s) => this.el.querySelector(s);
    $('#btn-mic').addEventListener('click', () => this._toggleMic());
    $('#btn-stop').addEventListener('click', () => this._stop());
    $('#btn-history').addEventListener('click', () => this._toggleDrawer(this.historyDrawer));
    $('#btn-history-close').addEventListener('click', () => this._closeDrawer(this.historyDrawer));
    $('#btn-settings').addEventListener('click', () => this._toggleDrawer(this.settingsDrawer));
    $('#btn-settings-close').addEventListener('click', () => this._closeDrawer(this.settingsDrawer));
    $('#btn-export').addEventListener('click', () => this._exportHistory());

    $('#text-input').addEventListener('submit', (e) => {
      e.preventDefault();
      const text = this.input.value.trim();
      if (!text) return;
      this.socket?.send('user_text', { text });
      this._pushHistory('user', text);
      this.subUser.textContent = text;
      this.input.value = '';
    });

    // Échap ferme les tiroirs ouverts (accessibilité clavier).
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this._closeDrawer(this.historyDrawer);
        this._closeDrawer(this.settingsDrawer);
      }
    });
  }

  async _toggleMic() {
    this.lipsync?.resume();
    if (!this._micReady) {
      this._micReady = await this.mic?.init();
      this.mic?.setMode(this.settings.get('micMode'));
      if (!this._micReady) {
        this.banner.classList.add('error');
        this.bannerLabel.textContent = 'Micro indisponible — utilise le clavier';
        return;
      }
    }
    if (this.mic.active) this.mic.stop();
    else this.mic.start();
  }

  _stop() {
    this.lipsync?.stop();
    this.socket?.send('interrupt', {});
  }

  _toggleDrawer(d) {
    const open = d.getAttribute('aria-hidden') === 'false';
    if (open) this._closeDrawer(d);
    else {
      d.setAttribute('aria-hidden', 'false');
      d.querySelector('button')?.focus();
    }
  }

  _closeDrawer(d) {
    d.setAttribute('aria-hidden', 'true');
  }

  // --- Branchement WebSocket ---------------------------------------------

  _wireSocket() {
    const s = this.socket;
    if (!s) return;

    s.on('state', (p) => {
      this.bannerLabel.textContent = STATE_LABELS[p.state] || p.state;
      this.banner.dataset.state = p.state;
      if (p.state === 'thinking') {
        // Nouveau tour : on prépare la ligne avatar.
        this._avatarLine = '';
        this.subAvatar.textContent = '';
      }
    });

    s.on('transcript', (p) => {
      this.subUser.textContent = p.text;
      if (p.final && p.text) this._pushHistory('user', p.text);
    });

    s.on('llm_token', (p) => {
      this._avatarLine += p.token;
      this.subAvatar.textContent = this._avatarLine;
    });

    s.on('state', (p) => {
      if (p.state === 'idle' && this._avatarLine.trim()) {
        this._pushHistory('avatar', this._avatarLine.trim());
        this._avatarLine = '';
      }
    });
  }

  // Niveau micro (appelé depuis le callback de MicCapture).
  setMicLevel(level) {
    if (this.micMeter) this.micMeter.style.width = `${Math.min(100, level)}%`;
  }

  // --- Historique ---------------------------------------------------------

  _pushHistory(role, text) {
    this.history.push({ role, text });
    const line = document.createElement('p');
    line.className = `hist-${role}`;
    line.textContent = `${role === 'user' ? 'Toi' : 'Jarvis'} : ${text}`;
    this.historyList.appendChild(line);
    this.historyList.scrollTop = this.historyList.scrollHeight;
  }

  _exportHistory() {
    const text = this.history
      .map((h) => `${h.role === 'user' ? 'Toi' : 'Jarvis'}: ${h.text}`)
      .join('\n');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'conversation-jarvis.txt';
    a.click();
    URL.revokeObjectURL(url);
  }
}
