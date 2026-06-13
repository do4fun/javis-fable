// scene.js — Mise en place de la scène Three.js de base.
// Renderer WebGL plein écran, caméra cadrée buste, éclairage minimal,
// resize responsive (desktop + mobile). L'avatar (F1.1) et l'environnement
// (F1.2) viendront se greffer sur cette scène.

import * as THREE from 'three';
import { config } from './config.js';
import { Environment } from './environment.js';

export class Scene {
  constructor(canvas) {
    this.canvas = canvas;

    // --- Renderer -----------------------------------------------------------
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
      powerPreference: 'high-performance',
    });
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = config.render.exposure;
    this._applyPixelRatio();

    // --- Scène --------------------------------------------------------------
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(config.render.background);

    // --- Caméra « assistant » ----------------------------------------------
    const { fov, near, far, position, target } = config.camera;
    this.camera = new THREE.PerspectiveCamera(fov, this._aspect(), near, far);
    this.camera.position.set(position.x, position.y, position.z);
    this._target = new THREE.Vector3(target.x, target.y, target.z);
    this.camera.lookAt(this._target);

    // --- Environnement 3D (F1.2) : éclairage 3 points, sol, poussière, IBL --
    this.environment = new Environment(this.scene, this.renderer);
    // Repère central pour matérialiser la place de l'avatar (scène de repli).
    this._placeholder = this._buildPlaceholder();
    this.scene.add(this._placeholder);

    // --- Resize responsive --------------------------------------------------
    this._onResize = this._onResize.bind(this);
    window.addEventListener('resize', this._onResize);
    window.addEventListener('orientationchange', this._onResize);
    this._onResize();
  }

  // Plafonne le devicePixelRatio pour préserver les perfs mobiles.
  _applyPixelRatio() {
    const ratio = Math.min(window.devicePixelRatio || 1, config.render.maxPixelRatio);
    this.renderer.setPixelRatio(ratio);
  }

  _aspect() {
    return window.innerWidth / window.innerHeight;
  }

  // Témoin central : matérialise la place de l'avatar (le sol vient de
  // l'environnement). Retiré quand l'avatar TalkingHead est actif.
  _buildPlaceholder() {
    const marker = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.25, 1.0, 6, 16),
      new THREE.MeshStandardMaterial({ color: 0x2a3240, roughness: 0.6 })
    );
    marker.position.y = 1.0;
    marker.castShadow = true;
    return marker;
  }

  _onResize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    this.renderer.setSize(w, h, false);
    this._applyPixelRatio();
    this.camera.aspect = this._aspect();
    this.camera.updateProjectionMatrix();
  }

  // Appelée à chaque frame par la boucle de main.js.
  render(dt) {
    this.environment?.update(dt);
    this.renderer.render(this.scene, this.camera);
  }

  dispose() {
    window.removeEventListener('resize', this._onResize);
    window.removeEventListener('orientationchange', this._onResize);
    this.environment?.dispose();
    this.renderer.dispose();
  }
}
