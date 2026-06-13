// Configuration centrale du frontend Jarvis.
// Regroupe ici tous les réglages visuels/perf pour éviter les « nombres
// magiques » dispersés. Les modules ultérieurs (environnement, vie,
// émotions…) viendront enrichir ce fichier.

export const config = {
  // Rendu / performance
  render: {
    // pixelRatio plafonné à 2 : au-delà, le coût GPU explose sans gain visible.
    maxPixelRatio: 2,
    fpsCap: 60,
    // Couleur de fond de la scène (avant l'environnement de F1.2).
    background: 0x0a0e14,
    exposure: 1.0,
  },

  // Caméra « assistant » : cadrage buste par défaut.
  camera: {
    fov: 32,
    near: 0.1,
    far: 100,
    // Position visant un cadrage tête-épaules d'un avatar debout (~1.7 m).
    position: { x: 0, y: 1.5, z: 1.4 },
    target: { x: 0, y: 1.5, z: 0 },
  },

  // Éclairage minimal de F0.1 (l'éclairage 3 points arrive en F1.2).
  lights: {
    ambientIntensity: 0.6,
    keyIntensity: 1.1,
  },

  // Avatar (F1.1) : TalkingHead + Ready Player Me, 100 % local.
  avatar: {
    // GLB déposé localement (cf. /docs/avatar.md). Jamais d'URL readyplayer.me.
    glbUrl: '/avatars/jarvis.glb',
    // Module TalkingHead vendorisé (import dynamique). Voir /web/vendor.
    modulePath: '/vendor/talkinghead/talkinghead.mjs',
    // Humeur initiale et langue de lip-sync (français).
    mood: 'neutral',
    lipsyncLang: 'fr',
    // Cadrage caméra TalkingHead : 'head' (tête-épaules) ou 'full' (plan américain).
    defaultView: 'head',
    cameraView: 'upper', // vue interne TalkingHead au chargement
  },

  // Vie autonome (F1.3). TalkingHead gère nativement clignement/respiration/
  // sway/idle : on les configure ici, et on complète (suivi du regard, gestes).
  life: {
    // Suivi du regard au pointeur/toucher.
    gaze: {
      enabled: true,
      smoothing: 0.12, // lerp vers la cible (0..1)
      returnAfterMs: 2000, // retour au regard caméra après inactivité
      maxYawDeg: 35, // limites anatomiques
      maxPitchDeg: 22,
    },
    // Gestes ambiants Mixamo joués aléatoirement (fichiers /public/anims).
    ambientGestures: {
      enabled: true,
      minIntervalMs: 20000,
      maxIntervalMs: 60000,
      pool: ['hausse_epaules', 'acquiesce', 'reflechit'],
    },
    // Clignements (délégués à TalkingHead ; valeurs indicatives).
    blink: { minMs: 2000, maxMs: 6000, thinkingFactor: 0.6 },
  },

  // Micro + VAD (F3.1).
  mic: {
    mode: 'handsfree', // 'ptt' | 'toggle' | 'handsfree'
    vad: {
      engine: 'silero', // 'silero' (ONNX) ou 'energy' (repli)
      modelUrl: '/models/silero_vad.onnx',
      ortPath: '/vendor/ort/',
    },
  },

  // Accès debug : ?debug dans l'URL active les panneaux de réglage (F1.2).
  debug: new URLSearchParams(window.location.search).has('debug'),
};

// Visèmes Oculus + quelques ARKit clés, attendus sur l'avatar RPM.
// Sert au rapport de compatibilité au chargement (F1.1).
export const REQUIRED_MORPHS = [
  'viseme_sil', 'viseme_PP', 'viseme_FF', 'viseme_TH', 'viseme_DD',
  'viseme_kk', 'viseme_CH', 'viseme_SS', 'viseme_nn', 'viseme_RR',
  'viseme_aa', 'viseme_E', 'viseme_I', 'viseme_O', 'viseme_U',
  'eyeBlinkLeft', 'eyeBlinkRight', 'jawOpen', 'mouthSmileLeft', 'mouthSmileRight',
];
