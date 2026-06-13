// quality.js — Profils de qualité automatiques (F5.3).
//
// Détecte grossièrement les capacités GPU/WebGL et choisit un profil
// low/medium/high, qui ajuste pixelRatio, ombres et fréquence du LifeEngine.
// Cible : ≥ 30 fps sur mobile milieu de gamme. Le réglage explicite de
// l'utilisateur (Settings) a priorité sur la détection auto.

const PROFILES = {
  low: { pixelRatio: 1, shadows: false, lifeHz: 20, dust: 0 },
  medium: { pixelRatio: 1.5, shadows: false, lifeHz: 45, dust: 200 },
  high: { pixelRatio: 2, shadows: true, lifeHz: 60, dust: 400 },
};

// Heuristique : mobile → medium au mieux ; desktop avec WebGL2 → high.
export function detectProfile() {
  const isMobile = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);
  const cores = navigator.hardwareConcurrency || 4;
  const mem = navigator.deviceMemory || 4;

  let gl = null;
  try {
    const c = document.createElement('canvas');
    gl = c.getContext('webgl2') || c.getContext('webgl');
  } catch {
    /* pas de WebGL */
  }

  if (!gl) return 'low';
  if (isMobile) return mem >= 4 && cores >= 6 ? 'medium' : 'low';
  // Desktop : renderer haut de gamme ?
  const dbg = gl.getExtension('WEBGL_debug_renderer_info');
  const renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : '';
  const weak = /Intel.*(HD|UHD) Graphics (6|5|4)/i.test(renderer);
  return weak || cores < 4 ? 'medium' : 'high';
}

export function profileSettings(name) {
  return PROFILES[name] || PROFILES.high;
}

// Renvoie le profil effectif : réglage utilisateur s'il diffère de 'auto'.
export function resolveProfile(userChoice) {
  if (userChoice && userChoice !== 'auto' && PROFILES[userChoice]) {
    return { name: userChoice, ...PROFILES[userChoice] };
  }
  const name = detectProfile();
  return { name, ...PROFILES[name] };
}
