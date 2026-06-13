// environment.js — Décor et éclairage de la scène (F1.2).
//
// Éclairage trois points (key chaude, fill froide, rim) + ambiance ; sol à
// dégradé radial, particules de poussière subtiles, IBL optionnelle (HDRI
// locale). Ombres douces sur desktop uniquement (détection simple).
//
// S'applique à une scène Three.js fournie (celle de scene.js en repli, ou la
// scène interne de TalkingHead quand l'avatar est actif). Budget : décor léger
// (< 150k triangles), textures ≤ 1024 px.

import * as THREE from 'three';
import { config } from './config.js';

// Détection grossière « desktop » pour activer les ombres.
function isDesktop() {
  return !/Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);
}

export class Environment {
  constructor(scene, renderer) {
    this.scene = scene;
    this.renderer = renderer;
    this.group = new THREE.Group();
    this.group.name = 'jarvis-env';
    scene.add(this.group);

    this._dust = null;
    this._lights = {};
    this.preset = config.env.preset;

    const shadows = config.env.shadows;
    this.shadows = shadows === 'auto' ? isDesktop() : !!shadows;
    if (renderer) {
      renderer.shadowMap.enabled = this.shadows;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    }

    this._build();
    this.applyPreset(this.preset);
  }

  _build() {
    // --- Éclairage trois points -------------------------------------------
    this._lights.ambient = new THREE.AmbientLight(0xffffff, 0.5);
    this._lights.key = new THREE.DirectionalLight(0xffffff, 1);
    this._lights.key.position.set(2.5, 3.5, 2.5);
    this._lights.fill = new THREE.DirectionalLight(0xffffff, 0.5);
    this._lights.fill.position.set(-3, 2, 1.5);
    this._lights.rim = new THREE.DirectionalLight(0xffffff, 0.8);
    this._lights.rim.position.set(0, 3, -3.5);

    if (this.shadows) {
      this._lights.key.castShadow = true;
      this._lights.key.shadow.mapSize.set(1024, 1024);
      this._lights.key.shadow.bias = -0.0005;
    }

    for (const l of Object.values(this._lights)) this.group.add(l);

    // --- Sol à dégradé radial ---------------------------------------------
    this._floor = new THREE.Mesh(
      new THREE.CircleGeometry(6, 64),
      new THREE.MeshStandardMaterial({ roughness: 0.95, metalness: 0 })
    );
    this._floor.rotation.x = -Math.PI / 2;
    this._floor.receiveShadow = this.shadows;
    this.group.add(this._floor);

    // --- Particules de poussière ------------------------------------------
    if (config.env.dust.enabled) this._buildDust(config.env.dust.count);

    // --- IBL optionnelle (HDRI locale) ------------------------------------
    this._loadHDRI();
  }

  // Texture de dégradé radial générée par canvas (≤ 1024 px, pas d'asset réseau).
  _gradientTexture(inner, outer) {
    const size = 512;
    const c = document.createElement('canvas');
    c.width = c.height = size;
    const ctx = c.getContext('2d');
    const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    g.addColorStop(0, `#${inner.toString(16).padStart(6, '0')}`);
    g.addColorStop(1, `#${outer.toString(16).padStart(6, '0')}`);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }

  _buildDust(count) {
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 6;
      positions[i * 3 + 1] = Math.random() * 3;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 6;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const mat = new THREE.PointsMaterial({
      color: 0xffffff,
      size: 0.012,
      transparent: true,
      opacity: 0.35,
      depthWrite: false,
    });
    this._dust = new THREE.Points(geo, mat);
    this.group.add(this._dust);
  }

  async _loadHDRI() {
    if (!config.env.hdri) return;
    try {
      const { RGBELoader } = await import('three/addons/loaders/RGBELoader.js');
      const tex = await new RGBELoader().loadAsync(config.env.hdri);
      tex.mapping = THREE.EquirectangularReflectionMapping;
      this.scene.environment = tex; // image-based lighting
    } catch {
      // HDRI absente : on reste sur l'éclairage analytique (cas normal).
    }
  }

  // Applique un preset jour/nuit.
  applyPreset(name) {
    const p = config.env.presets[name];
    if (!p) return;
    this.preset = name;

    if (this.scene.background instanceof THREE.Color) {
      this.scene.background.setHex(p.background);
    } else {
      this.scene.background = new THREE.Color(p.background);
    }

    this._lights.ambient.intensity = p.ambient;
    this._lights.key.color.setHex(p.key.color);
    this._lights.key.intensity = p.key.intensity;
    this._lights.fill.color.setHex(p.fill.color);
    this._lights.fill.intensity = p.fill.intensity;
    this._lights.rim.color.setHex(p.rim.color);
    this._lights.rim.intensity = p.rim.intensity;

    const tex = this._gradientTexture(p.floor.inner, p.floor.outer);
    this._floor.material.map?.dispose();
    this._floor.material.map = tex;
    this._floor.material.needsUpdate = true;
  }

  // Animation légère des poussières (appelée par la boucle de rendu).
  update(dt) {
    if (!this._dust) return;
    const pos = this._dust.geometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      let y = pos.getY(i) + dt * 0.04; // dérive lente vers le haut
      if (y > 3) y = 0;
      pos.setY(i, y);
    }
    pos.needsUpdate = true;
  }

  // Panneau de debug (lil-gui), activé par ?debug.
  async mountDebug() {
    if (!config.debug) return;
    const { GUI } = await import('lil-gui');
    const gui = new GUI({ title: 'Environnement' });
    gui
      .add({ preset: this.preset }, 'preset', ['jour', 'nuit'])
      .name('Preset')
      .onChange((v) => this.applyPreset(v));
    gui.add(this._lights.key, 'intensity', 0, 3).name('Key');
    gui.add(this._lights.fill, 'intensity', 0, 3).name('Fill');
    gui.add(this._lights.rim, 'intensity', 0, 3).name('Rim');
    gui.add(this._lights.ambient, 'intensity', 0, 2).name('Ambiance');
    this._gui = gui;
  }

  dispose() {
    this._gui?.destroy?.();
    this.scene.remove(this.group);
  }
}
