// vrmEngine.js — Moteur de rendu VRM autonome (équivalent VRM de TalkingHead).
//
// @pixiv/three-vrm anime un avatar VRM 1.0 (expressions natives, spring bones,
// lookAt). Contrairement à TalkingHead, three-vrm ne fournit PAS de scène, de
// caméra, de boucle ni d'idle : ce moteur les implémente.
//
// Responsabilités :
//  - créer renderer/scène/caméra/lumières dans le conteneur DOM ;
//  - charger le VRM (GLTFLoader + VRMLoaderPlugin) ;
//  - boucle d'animation propre (RAF) : idle, clignement, regard, gestes,
//    expressions lissées, spring bones (vrm.update), rendu ;
//  - exposer scene/renderer/camera pour le décor (F1.2) et une API simple
//    (setExpressionTarget, lookAtScreen, playGesture…) consommée par le
//    VRMAvatarManager.
//
// 100 % local : three et three-vrm sont bundlés par Vite depuis node_modules.

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

const DEG2RAD = Math.PI / 180;

// Expressions appliquées SANS lissage additionnel : les visèmes (déjà lissés
// par le driver audio, co-articulation) et le clignement (enveloppe déjà
// formée — un lissage l'empêcherait de se fermer complètement). Les émotions,
// elles, sont lissées dans _applyExpressions pour des transitions douces.
const DIRECT_EXPR = new Set(['aa', 'ih', 'ou', 'ee', 'oh', 'blink']);

export class VRMEngine {
  /**
   * @param {HTMLElement} container - hôte du canvas WebGL.
   * @param {object} [opts]
   * @param {number} [opts.pixelRatio]
   */
  constructor(container, opts = {}) {
    this.container = container;
    this.opt = {
      pixelRatio: Math.min(window.devicePixelRatio || 1, opts.pixelRatio || 2),
      background: 0x0a0e14,
    };

    this.vrm = null;
    this.scene = null;
    this.renderer = null;
    this.camera = null;
    this.clock = new THREE.Clock();
    this._raf = null;
    this._running = false;
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // Callback fourni par le manager, appelé chaque frame AVANT le rendu :
    // c'est là que le manager pousse les cibles d'expression (visèmes/émotions).
    this.onUpdate = null;

    // État expressions : cible (écrite par le manager) → courant (lissé).
    this._exprTarget = Object.create(null);
    this._exprCurrent = Object.create(null);

    // Regard : cible normalisée [-1,1] (x droite, y bas) + objet monde suivi.
    this._gaze = { x: 0, y: 0 };
    this._lookTarget = new THREE.Object3D();

    // Clignement automatique (enveloppe ouverte→fermée→ouverte).
    this._blink = { value: 0, nextAt: 0, closing: false, rate: 1 / 4 };

    // Geste procédural en cours : { eval(t)->{bone:euler}, dur, elapsed }.
    this._gesture = null;

    // Cache des nœuds d'os normalisés (humanoid) souvent animés.
    this._bones = {};

    this._onResize = this._onResize.bind(this);
  }

  // --- Chargement -----------------------------------------------------------

  async load(url, onProgress = null) {
    this._initThree();

    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));

    const gltf = await loader.loadAsync(url, (ev) => {
      if (onProgress) onProgress(ev);
    });

    const vrm = gltf.userData.vrm;
    if (!vrm) throw new Error('Fichier sans extension VRM (userData.vrm absent).');

    // Optimisations recommandées (selon la version de three-vrm).
    try { VRMUtils.removeUnnecessaryVertices?.(gltf.scene); } catch { /* opt. */ }
    // combineSkeletons omis : peut rompre le mapping humanoid→raw bones dans
    // certains exports VRoid, causant des poses T-pose permanentes.
    try { VRMUtils.removeUnnecessaryJoints?.(gltf.scene); } catch { /* opt. */ }

    // VRM 0.x regarde +Z (dos à la caméra) : on le retourne. VRM 1.0 : rien.
    const isVRM0 = vrm.meta?.metaVersion === '0' || vrm.meta?.specVersion === '0.0';
    if (isVRM0) {
      try { VRMUtils.rotateVRM0?.(vrm); } catch { /* opt. */ }
    }

    // Désactive le frustum culling (les spring bones débordent des bounds).
    vrm.scene.traverse((o) => { o.frustumCulled = false; });

    this.vrm = vrm;
    this.scene.add(vrm.scene);
    this.scene.add(this._lookTarget);

    // Une passe update(0) synchronise le rig humanoïde normalisé pour que les
    // positions monde (tête) soient valides avant de cadrer la caméra.
    vrm.update(0);
    this.scene.updateMatrixWorld(true);

    console.info(`[vrm] version détectée : VRM ${isVRM0 ? '0.x' : '1.0'}`);

    this._cacheBones();
    this._frameCamera();
    this._setupLookAt();

    return vrm;
  }

  _initThree() {
    const w = this.container.clientWidth || window.innerWidth;
    const h = this.container.clientHeight || window.innerHeight;

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setPixelRatio(this.opt.pixelRatio);
    this.renderer.setSize(w, h);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(this.opt.background);

    this.camera = new THREE.PerspectiveCamera(30, w / h, 0.1, 100);
    this.camera.position.set(0, 1.35, 1.4);

    // Éclairage 3 points minimal (le décor F1.2 peut le compléter/remplacer).
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(1, 2, 2);
    this.scene.add(key);
    const fill = new THREE.DirectionalLight(0xbcd4ff, 0.8);
    fill.position.set(-2, 1, 1);
    this.scene.add(fill);
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.6));

    window.addEventListener('resize', this._onResize);
  }

  // Cadre l'avatar au chargement.
  //
  // Contraintes :
  //  - avatar occupe au plus ~45% de la hauteur d'écran (fillFactor) ;
  //  - la caméra orbite autour de la TÊTE avec une élévation de ELEV_DEG degrés
  //    → elle surplombe légèrement l'avatar, regard dirigé vers la tête ;
  //  - adaptatif : fonctionne quelle que soit la taille/proportion du modèle.
  _frameCamera() {
    const FILL_FACTOR = 0.45; // avatar ≤ 45% de la hauteur d'écran
    const ELEV_DEG   = 18;    // degrés d'élévation (surplomb)

    // Bounding box de la scène complète (mesh + spring bones).
    const box  = new THREE.Box3().setFromObject(this.vrm.scene);
    const size = box.getSize(new THREE.Vector3());

    // Pivot de la caméra = position monde de la tête.
    const headBone = this.vrm.humanoid?.getNormalizedBoneNode('head');
    const pivot = new THREE.Vector3();
    if (headBone) headBone.getWorldPosition(pivot);
    else pivot.set(0, box.max.y - size.y * 0.08, 0);
    this._headY = pivot.y;

    // Recul calculé depuis la bounding box de l'avatar entier,
    // mis à l'échelle pour que l'avatar tienne dans FILL_FACTOR de l'écran.
    // distV : contrainte verticale (FOV déclaré).
    // distH : contrainte horizontale (FOV déduit de l'aspect ratio).
    const halfFovV = (this.camera.fov / 2) * DEG2RAD;
    const halfFovH = Math.atan(Math.tan(halfFovV) * this.camera.aspect);
    const distV = (size.y / 2) / Math.tan(halfFovV) / FILL_FACTOR;
    const distH = (size.x / 2) / Math.tan(halfFovH) / FILL_FACTOR;
    const dist  = Math.max(distV, distH);

    // Position de la caméra : orbite autour du pivot (tête) avec élévation.
    // L'axe de recul reste Z+ ; l'élévation monte sur Y tout en reculant sur Z.
    const elev = ELEV_DEG * DEG2RAD;
    this.camera.position.set(
      pivot.x,
      pivot.y + dist * Math.sin(elev),   // monte sur Y
      pivot.z + dist * Math.cos(elev)    // recule sur Z
    );
    // Regard pointé vers la tête (pivot de l'orbite).
    this.camera.lookAt(pivot);
    this._camTarget = pivot.clone();

    console.info(
      `[vrm] caméra : avatar ${size.x.toFixed(2)}×${size.y.toFixed(2)} m` +
      ` → recul ${dist.toFixed(2)} m, élévation ${ELEV_DEG}°, pivot tête Y=${pivot.y.toFixed(2)}`
    );
  }

  _cacheBones() {
    const h = this.vrm.humanoid;
    if (!h) return;
    const get = (n) => h.getNormalizedBoneNode(n);
    this._bones = {
      head: get('head'),
      neck: get('neck'),
      chest: get('chest') || get('upperChest'),
      spine: get('spine'),
      hips: get('hips'),
      leftUpperArm: get('leftUpperArm'),
      rightUpperArm: get('rightUpperArm'),
      leftLowerArm: get('leftLowerArm'),
      rightLowerArm: get('rightLowerArm'),
      leftShoulder: get('leftShoulder'),
      rightShoulder: get('rightShoulder'),
    };
    // Rotations de repos (pour composer idle/geste/regard en additif).
    this._rest = {};
    for (const [k, b] of Object.entries(this._bones)) {
      if (b) this._rest[k] = b.rotation.clone();
    }
    // Bras le long du corps : VRM T-pose → on abaisse les bras au repos.
    this._restArmFix();
  }

  // VRM est en T-pose ; on descend les bras pour une pose « bras le long du
  // corps » plus naturelle au repos.
  //
  // Le signe de la rotation Z dépend de la version VRM ET de si rotateVRM0 a
  // été appliqué (pivot 180° autour de Y qui inverse l'axe Z local).
  // Plutôt que de deviner, on teste empiriquement : on applique +Z, on mesure
  // si l'avant-bras gauche monte ou descend, puis on corrige le signe.
  _restArmFix() {
    const L  = this._bones.leftUpperArm;
    const R  = this._bones.rightUpperArm;
    const Ll = this._bones.leftLowerArm;
    const Rl = this._bones.rightLowerArm;

    if (!L || !R) {
      const missing = ['leftUpperArm', 'rightUpperArm'].filter(k => !this._bones[k]);
      console.warn('[vrm] bras non trouvés dans le squelette :', missing, '→ T-pose conservée.');
      return;
    }

    // ── Auto-détection du signe Z ─────────────────────────────────────────────
    // Bone de référence : avant-bras gauche (raw), car il bouge beaucoup
    // quand le haut du bras tourne.
    const testBone = this.vrm.humanoid?.getRawBoneNode('leftLowerArm')
                  || this.vrm.humanoid?.getRawBoneNode('leftHand');
    let s = 1; // signe par défaut

    if (testBone) {
      const v = new THREE.Vector3();
      const preY = testBone.getWorldPosition(v).y;

      // Tente +70° Z sur le bras normalisé gauche.
      L.rotation.set(0, 0, 70 * DEG2RAD);
      this.vrm.humanoid.update();           // normalized → raw bones
      this.vrm.scene.updateMatrixWorld(true); // propage les matrices monde

      const postY = testBone.getWorldPosition(v).y;

      // Si l'avant-bras est monté (Δy > 0), +Z lève le bras → on inverse.
      s = (postY > preY + 0.001) ? -1 : 1;
      console.info(
        `[vrm] auto-signe bras : Δy=${(postY - preY).toFixed(3)} m` +
        ` → rotation Z = ${s > 0 ? '+' : '−'}70°`
      );
    } else {
      // Repli heuristique si aucun raw bone trouvé.
      const isVRM0 = this.vrm.meta?.metaVersion === '0' || this.vrm.meta?.specVersion === '0.0';
      s = isVRM0 ? -1 : 1;
      console.warn(`[vrm] leftLowerArm introuvable — repli heuristique VRM ${isVRM0 ? '0.x' : '1.0'}, signe=${s}`);
    }

    // ── Application de la pose finale ─────────────────────────────────────────
    L.rotation.set(0, 0,  s * 70 * DEG2RAD);
    R.rotation.set(0, 0, -s * 70 * DEG2RAD);
    if (Ll) Ll.rotation.set(0, -0.2, 0);
    if (Rl) Rl.rotation.set(0,  0.2, 0);

    this._rest.leftUpperArm  = L.rotation.clone();
    this._rest.rightUpperArm = R.rotation.clone();
    if (Ll) this._rest.leftLowerArm  = Ll.rotation.clone();
    if (Rl) this._rest.rightLowerArm = Rl.rotation.clone();

    // Resync raw bones avec la pose finale (pour _frameCamera qui suit).
    this.vrm.humanoid.update();
    this.vrm.scene.updateMatrixWorld(true);

    console.info('[vrm] pose repos des bras appliquée.');
  }

  _setupLookAt() {
    if (this.vrm.lookAt) {
      this.vrm.lookAt.target = this._lookTarget;
      // Position initiale du regard : droit devant, hauteur des yeux.
      this._lookTarget.position.set(0, this._headY || 1.35, 5);
    }
  }

  // --- Boucle ---------------------------------------------------------------

  start() {
    if (this._running) return;
    this._running = true;
    this.clock.start();
    const loop = () => {
      this._raf = requestAnimationFrame(loop);
      this._tick();
    };
    this._raf = requestAnimationFrame(loop);
  }

  stop() {
    this._running = false;
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = null;
  }

  _tick() {
    const dt = Math.min(this.clock.getDelta(), 0.1);
    if (!this.vrm) return;

    // 1) Le manager pousse les cibles d'expression (visèmes + émotions).
    this._resetManagedExpr();
    try { this.onUpdate?.(dt); } catch (e) { console.warn('[vrm] onUpdate', e); }

    // 2) Clignement automatique.
    this._updateBlink(dt);

    // 3) Os normalisés : repos + idle + regard + geste.
    this._updateBones(dt);

    // 4) Expressions (visèmes directs, émotions lissées).
    this._applyExpressions(dt);

    // 5) Convertit les normalized bones → raw bones (sans spring ni contraintes).
    //    On capture les quaternions bruts des bras AVANT que vrm.update()
    //    puisse les écraser via nodeConstraintManager.
    //    Note : le renderer utilise les RAW bones pour le skinning, pas les
    //    normalized bones — c'est pourquoi on snapshote/restore les raw bones.
    this.vrm.humanoid.update();
    const armSnap = this._snapshotArms();

    // 6) Spring bones, lookAt, contraintes VRM (+ second humanoid.update interne).
    this.vrm.update(dt);

    // 7) Rétablit les bras (override de toute contrainte sur les raw bones).
    this._restoreArms(armSnap);

    // 8) Rendu.
    this.renderer.render(this.scene, this.camera);
  }

  // Capture les quaternions des RAW bones des bras (ceux lus par SkinnedMesh).
  _snapshotArms() {
    const snap = {};
    for (const k of ['leftUpperArm', 'rightUpperArm', 'leftLowerArm', 'rightLowerArm']) {
      const b = this.vrm.humanoid.getRawBoneNode(k);
      if (b) snap[k] = b.quaternion.clone();
    }
    return snap;
  }

  // Restaure les quaternions des RAW bones après vrm.update().
  _restoreArms(snap) {
    for (const [k, q] of Object.entries(snap)) {
      const b = this.vrm.humanoid.getRawBoneNode(k);
      if (b) b.quaternion.copy(q);
    }
  }

  // --- Expressions ----------------------------------------------------------

  // Le manager appelle ceci (dans onUpdate) pour fixer la cible d'une
  // expression VRM ('aa','happy',…) sur la frame courante.
  setExpressionTarget(name, value) {
    this._exprTarget[name] = Math.max(0, Math.min(1, value));
  }

  // Avant onUpdate : remet à 0 les expressions « gérées » (celles que le
  // manager repousse chaque frame), pour qu'une absence d'écriture = 0.
  _resetManagedExpr() {
    for (const k in this._exprTarget) {
      if (k !== 'blink') this._exprTarget[k] = 0;
    }
  }

  _applyExpressions(dt) {
    const em = this.vrm.expressionManager;
    if (!em) return;
    const k = 1 - Math.pow(0.001, dt); // lissage indépendant du framerate
    // On itère sur les expressions effectivement pilotées (clés de _exprTarget,
    // peuplées par le manager + blink). setValue ignore les noms inconnus.
    for (const name of Object.keys(this._exprTarget)) {
      const target = this._exprTarget[name] || 0;
      let cur = this._exprCurrent[name] || 0;
      // Visèmes + clignement : application directe (latence minimale).
      cur = DIRECT_EXPR.has(name) ? target : cur + (target - cur) * k;
      this._exprCurrent[name] = cur;
      em.setValue(name, cur < 0.001 ? 0 : cur);
    }
  }

  // --- Regard ---------------------------------------------------------------

  // x,y en pixels écran ; déplace la cible de regard et oriente la tête.
  lookAtScreen(x, y) {
    const nx = (x / window.innerWidth) * 2 - 1;
    const ny = (y / window.innerHeight) * 2 - 1;
    this._gaze.x = Math.max(-1, Math.min(1, nx));
    this._gaze.y = Math.max(-1, Math.min(1, ny));
  }

  // --- Clignement -----------------------------------------------------------

  setBlinkRate(perSec) {
    if (perSec > 0) this._blink.rate = perSec;
  }

  _updateBlink(dt) {
    const b = this._blink;
    const now = performance.now();
    if (b.nextAt === 0) b.nextAt = now + 1500 + Math.random() * 4000;

    if (b.closing) {
      b.value += dt * 14; // fermeture rapide
      if (b.value >= 1) { b.value = 1; b.closing = false; }
    } else if (b.value > 0) {
      b.value -= dt * 10; // réouverture
      if (b.value < 0) b.value = 0;
    } else if (now >= b.nextAt) {
      b.closing = true;
      const interval = 1000 / Math.max(0.05, b.rate);
      b.nextAt = now + interval * (0.6 + Math.random() * 0.8);
    }
    // Le clignement ne doit pas être effacé par _resetManagedExpr.
    this._exprTarget.blink = b.value;
  }

  // --- Os : idle + regard + geste ------------------------------------------

  _updateBones(dt) {
    this._t = (this._t || 0) + dt;
    const t = this._t;

    // Réinitialise les os animés à leur repos avant composition additive.
    for (const k of ['head', 'neck', 'chest', 'spine', 'hips',
      'leftUpperArm', 'rightUpperArm', 'leftLowerArm', 'rightLowerArm',
      'leftShoulder', 'rightShoulder']) {
      const b = this._bones[k];
      const r = this._rest[k];
      if (b && r) b.rotation.copy(r);
    }

    // Respiration : légère oscillation du buste (chest) + balancement (sway).
    const breathe = Math.sin(t * 1.6) * 0.025;
    const sway = Math.sin(t * 0.5) * 0.02;
    if (this._bones.chest) this._bones.chest.rotation.x += breathe;
    if (this._bones.spine) this._bones.spine.rotation.z += sway * 0.5;
    if (this._bones.hips) this._bones.hips.rotation.z += sway * 0.3;

    // Regard : la tête suit partiellement la cible (contact visuel).
    const k = this.reducedMotion ? 0.04 : 0.08;
    this._gazeCur = this._gazeCur || { x: 0, y: 0 };
    this._gazeCur.x += (this._gaze.x - this._gazeCur.x) * k;
    this._gazeCur.y += (this._gaze.y - this._gazeCur.y) * k;
    const yaw = -this._gazeCur.x * 22 * DEG2RAD;
    const pitch = this._gazeCur.y * 14 * DEG2RAD;
    if (this._bones.head) {
      this._bones.head.rotation.y += yaw * 0.6;
      this._bones.head.rotation.x += pitch * 0.6;
    }
    if (this._bones.neck) {
      this._bones.neck.rotation.y += yaw * 0.4;
      this._bones.neck.rotation.x += pitch * 0.4;
    }
    // Cible de regard des yeux (VRM lookAt) en coordonnées monde.
    this._lookTarget.position.set(
      this._gazeCur.x * 1.2,
      (this._headY || 1.35) - this._gazeCur.y * 0.8,
      2.5
    );

    // Geste procédural additif.
    if (this._gesture) {
      this._gesture.elapsed += dt;
      const tt = Math.min(1, this._gesture.elapsed / this._gesture.dur);
      const pose = this._gesture.eval(tt);
      for (const [bone, euler] of Object.entries(pose)) {
        const b = this._bones[bone];
        if (!b) continue;
        if (euler.x) b.rotation.x += euler.x;
        if (euler.y) b.rotation.y += euler.y;
        if (euler.z) b.rotation.z += euler.z;
      }
      if (tt >= 1) this._gesture = null;
    }
  }

  // --- Gestes procéduraux ---------------------------------------------------

  playGesture(name, durationS = 2) {
    const clip = GESTURES[name];
    if (!clip) return;
    this._gesture = { eval: clip, dur: durationS, elapsed: 0 };
  }

  // --- Divers ---------------------------------------------------------------

  _onResize() {
    if (!this.renderer || !this.camera) return;
    const w = this.container.clientWidth || window.innerWidth;
    const h = this.container.clientHeight || window.innerHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
  }

  dispose() {
    this.stop();
    window.removeEventListener('resize', this._onResize);
    try {
      if (this.vrm) VRMUtils.deepDispose?.(this.vrm.scene);
    } catch { /* opt. */ }
    this.renderer?.dispose();
    if (this.renderer?.domElement?.parentNode) {
      this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
    }
  }
}

// Enveloppe « cloche » : 0 → 1 → 0 sur t∈[0,1] (sin²).
const bell = (t) => Math.sin(t * Math.PI);
// Enveloppe « maintien » : monte vite, tient, redescend.
const hold = (t) => Math.min(1, Math.sin(Math.min(t, 1 - t) * Math.PI * 2));

// Gestes procéduraux : t∈[0,1] → rotations additives (radians) par os.
// Noms alignés sur ceux utilisés par life.js / emotions.js.
const GESTURES = {
  // Hochement de tête (oui).
  acquiesce: (t) => ({ head: { x: bell(t) * 0.18 }, neck: { x: bell(t) * 0.08 } }),
  // Réflexion : tête inclinée + légère rotation.
  reflechit: (t) => ({ head: { z: hold(t) * 0.18, y: hold(t) * 0.12 } }),
  // Haussement d'épaules.
  hausse_epaules: (t) => ({
    leftShoulder: { z: bell(t) * 0.25 },
    rightShoulder: { z: -bell(t) * 0.25 },
    leftUpperArm: { z: -bell(t) * 0.12 },
    rightUpperArm: { z: bell(t) * 0.12 },
  }),
  // Célébration : bras qui s'ouvrent vers le haut.
  celebre: (t) => ({
    leftUpperArm: { z: -bell(t) * 0.6, x: -bell(t) * 0.3 },
    rightUpperArm: { z: bell(t) * 0.6, x: -bell(t) * 0.3 },
    head: { x: -bell(t) * 0.1 },
  }),
};
