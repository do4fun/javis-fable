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

  // Accès debug : ?debug dans l'URL active les panneaux de réglage (F1.2).
  debug: new URLSearchParams(window.location.search).has('debug'),
};
