// ws.js — Client WebSocket typé du frontend Jarvis.
//
// Parle le même protocole d'enveloppe que le serveur : {type, id, payload, ts}.
// Reconnexion automatique avec backoff, routage par type via on(type, handler).

const DEFAULT_URL = (() => {
  // En dev (Vite, port 5173), on cible le serveur FastAPI sur 8000.
  // En prod (servi par FastAPI), on réutilise l'hôte courant.
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const host = location.port === '5173' ? `${location.hostname}:8000` : location.host;
  return `${proto}://${host}/ws`;
})();

export class JarvisSocket {
  constructor(url = DEFAULT_URL) {
    this.url = url;
    this.ws = null;
    this._handlers = new Map(); // type → Set<fn>
    this._connected = false;
    this._retry = 0;
    this._queue = []; // messages envoyés avant l'ouverture
  }

  connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this._connected = true;
      this._retry = 0;
      // Vide la file d'attente.
      for (const raw of this._queue.splice(0)) this.ws.send(raw);
      this._emit('open', {});
    };

    this.ws.onmessage = (ev) => {
      let env;
      try {
        env = JSON.parse(ev.data);
      } catch {
        return;
      }
      this._emit(env.type, env.payload, env);
    };

    this.ws.onclose = () => {
      this._connected = false;
      this._emit('close', {});
      this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      // onclose suivra et déclenchera la reconnexion.
      try {
        this.ws.close();
      } catch {
        /* no-op */
      }
    };
  }

  _scheduleReconnect() {
    this._retry = Math.min(this._retry + 1, 6);
    const delay = Math.min(500 * 2 ** this._retry, 8000); // backoff plafonné
    setTimeout(() => this.connect(), delay);
  }

  // Abonne un handler à un type d'événement (ou 'open'/'close').
  on(type, handler) {
    if (!this._handlers.has(type)) this._handlers.set(type, new Set());
    this._handlers.get(type).add(handler);
    return () => this._handlers.get(type)?.delete(handler);
  }

  _emit(type, payload, env) {
    const set = this._handlers.get(type);
    if (!set) return;
    for (const fn of set) {
      try {
        fn(payload, env);
      } catch (err) {
        console.error('[ws] handler', type, 'a échoué', err);
      }
    }
  }

  // Envoie une enveloppe. Si non connecté, on met en file.
  send(type, payload = {}) {
    const env = { type, id: crypto.randomUUID(), payload, ts: Date.now() };
    const raw = JSON.stringify(env);
    if (this._connected && this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(raw);
    } else {
      this._queue.push(raw);
    }
    return env.id;
  }

  // Envoi binaire (chunks audio du micro, F3.1).
  sendBinary(buffer) {
    if (this._connected && this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(buffer);
    }
  }

  get connected() {
    return this._connected;
  }
}
