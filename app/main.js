import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { createSeagulls } from './seagulls.js';

const MODEL = '../model/fischerbrunnen.glb';
const COLLIDERS = '../model/fischerbrunnen_colliders.glb';
const params = new URLSearchParams(location.search);
const DEMO = params.has('demo');

// Spielfeldgrenzen (Welt: x = Ost, z = Sued)
const BOUNDS = { minX: -36.5, maxX: 36.5, minZ: -40, maxZ: 63 };
const PLAYER_R = 0.35;
const STEP_HEIGHT = 0.25; // niedrigere Kollider (z.B. Kanaldeckel) werden ignoriert

// ------------------------------------------------------------------ Renderer & Szene
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.NeutralToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, innerWidth / innerHeight, 0.3, 400);

// Himmel: weicher Verlauf (Style-Vorlage: lavendel/violett oben, warm am Horizont)
const skyUniforms = { top: { value: new THREE.Color('#7f78b8') }, bottom: { value: new THREE.Color('#f3c99a') } };
const sky = new THREE.Mesh(new THREE.SphereGeometry(300, 24, 12), new THREE.ShaderMaterial({
  side: THREE.BackSide, depthWrite: false, fog: false, uniforms: skyUniforms,
  vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }',
  fragmentShader: 'uniform vec3 top; uniform vec3 bottom; varying vec3 vP; void main(){ float t = smoothstep(-0.05, 0.6, vP.y); gl_FragColor = vec4(mix(bottom, top, t), 1.); }',
}));
scene.add(sky);
scene.fog = new THREE.Fog('#c9a9b0', 70, 170);

const hemi = new THREE.HemisphereLight('#d9d2ff', '#8a6a52', 1.3);
scene.add(hemi);
const sun = new THREE.DirectionalLight('#ffd9a8', 2.6);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -35, right: 35, top: 35, bottom: -35, near: 1, far: 160 });
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 0.04;
scene.add(sun, sun.target);
const SUN_OFFSET = new THREE.Vector3(-30, 45, 22); // Sonne aus Suedost (morgens wie im Satellitenbild)

// Postprocessing: Bloom fuer Laternen, Lichterketten und warme Fenster
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.45, 0.6, 0.9);
composer.addPass(bloom);
composer.addPass(new OutputPass());

// ------------------------------------------------------------------ Laden
const loader = new GLTFLoader();
const pct = document.getElementById('pct');
const [world, colGltf] = await Promise.all([
  loader.loadAsync(MODEL, e => { if (e.total) pct.textContent = Math.round(100 * e.loaded / e.total) + ' %'; }),
  loader.loadAsync(COLLIDERS),
]);
scene.add(world.scene);

const glowMats = new Set();
const fadeables = []; // Gebaeude/Baum, die bei Verdeckung transparent werden
const pois = [];
// Gebaeude-Wurzeln (B_*) und Baum: eigene Materialkopien, damit sie einzeln ausgeblendet werden koennen
world.scene.traverse(o => {
  if (!/^(B_|Tree_)/.test(o.name) || !o.parent || /^(B_|Tree_)/.test(o.parent.name)) return;
  const meshes = [];
  o.traverse(c => { if (c.isMesh) meshes.push(c); });
  for (const c of meshes) {
    c.material = Array.isArray(c.material) ? c.material.map(m => m.clone()) : c.material.clone();
  }
  fadeables.push({ root: o, meshes, opacity: 1, target: 1 });
});

world.scene.traverse(o => {
  if (o.isMesh) {
    const isWater = /Water/.test(o.name);
    o.castShadow = !isWater && !/Lichterketten|Grass/.test(o.name);
    o.receiveShadow = true;
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    for (const m of mats) {
      if (m.map) m.map.anisotropy = renderer.capabilities.getMaxAnisotropy();
      if (m.emissiveIntensity > 0 && m.emissive && m.emissive.getHex() !== 0) { m.userData.baseEmissive = m.emissiveIntensity; glowMats.add(m); }
    }
  }
  if (/^POI_/.test(o.name)) pois.push(o);
});
// Kollider -> 2D-Rechtecke (XZ) mit Hoehe
const boxes = [];
colGltf.scene.updateMatrixWorld(true);
colGltf.scene.traverse(o => {
  if (!o.isMesh) return;
  const b = new THREE.Box3().setFromObject(o);
  if (b.max.y < STEP_HEIGHT) return;
  boxes.push({ minX: b.min.x, maxX: b.max.x, minZ: b.min.z, maxZ: b.max.z, maxY: b.max.y, name: o.name });
});

// ------------------------------------------------------------------ Spielfigur (in Anlehnung an die Style-Vorlage)
function makeCharacter() {
  const g = new THREE.Group();
  const fur = new THREE.MeshStandardMaterial({ color: '#3d3f6b', roughness: 0.9 });
  const furLight = new THREE.MeshStandardMaterial({ color: '#5a5d8f', roughness: 0.9 });
  const pack = new THREE.MeshStandardMaterial({ color: '#b8e05a', roughness: 0.8 });
  const white = new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 0.4 });
  const black = new THREE.MeshStandardMaterial({ color: '#1a1414', roughness: 0.3 });

  const body = new THREE.Group(); g.add(body);
  const torso = new THREE.Mesh(new THREE.SphereGeometry(0.42, 16, 12), fur);
  torso.scale.set(1, 1.15, 0.95); torso.position.y = 0.62; body.add(torso);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.34, 16, 12), fur);
  head.position.set(0, 1.18, 0.08); body.add(head);
  const snout = new THREE.Mesh(new THREE.SphereGeometry(0.17, 12, 8), furLight);
  snout.scale.set(1.3, 0.8, 1.2); snout.position.set(0, 1.1, 0.38); body.add(snout);
  const nose = new THREE.Mesh(new THREE.SphereGeometry(0.06, 8, 6), black);
  nose.position.set(0, 1.15, 0.56); body.add(nose);
  for (const s of [-1, 1]) {
    const eye = new THREE.Mesh(new THREE.SphereGeometry(0.075, 10, 8), white);
    eye.position.set(s * 0.15, 1.27, 0.3); body.add(eye);
    const pupil = new THREE.Mesh(new THREE.SphereGeometry(0.045, 8, 6), black);
    pupil.position.set(s * 0.16, 1.28, 0.36); body.add(pupil);
    const ear = new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.3, 6), fur);
    ear.position.set(s * 0.2, 1.48, -0.02); ear.rotation.z = -s * 0.35; body.add(ear);
  }
  const bag = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.55, 0.3), pack);
  bag.position.set(0, 0.78, -0.42); bag.rotation.x = 0.12; body.add(bag);
  const flap = new THREE.Mesh(new THREE.BoxGeometry(0.58, 0.18, 0.34), new THREE.MeshStandardMaterial({ color: '#8fbf3a', roughness: 0.8 }));
  flap.position.set(0, 1.04, -0.42); body.add(flap);
  const tail = new THREE.Mesh(new THREE.SphereGeometry(0.12, 8, 6), fur);
  tail.position.set(0, 0.35, -0.42); body.add(tail);

  const legs = [];
  for (const s of [-1, 1]) {
    const pivot = new THREE.Group(); pivot.position.set(s * 0.18, 0.32, 0); g.add(pivot);
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.11, 0.3, 8), fur);
    leg.position.y = -0.15; pivot.add(leg);
    const foot = new THREE.Mesh(new THREE.SphereGeometry(0.12, 8, 6), furLight);
    foot.scale.set(1, 0.6, 1.4); foot.position.set(0, -0.3, 0.05); pivot.add(foot);
    legs.push(pivot);
  }
  g.traverse(c => { if (c.isMesh) { c.castShadow = true; c.receiveShadow = true; } });
  g.userData = { body, legs };
  return g;
}
const player = makeCharacter();
const spawn = world.scene.getObjectByName('Spawn_Player');
player.position.set(spawn ? spawn.position.x : 0, 0, spawn ? spawn.position.z : 10);
player.rotation.y = Math.PI; // Blick nach Norden zum Brunnen
scene.add(player);
const blob = new THREE.Mesh(new THREE.CircleGeometry(0.45, 20), new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.18, depthWrite: false }));
blob.rotation.x = -Math.PI / 2; blob.position.y = 0.04; scene.add(blob);

// ------------------------------------------------------------------ Kollision (Kreis gegen Rechtecke)
function resolveCollisions(p) {
  for (let iter = 0; iter < 3; iter++) {
    let moved = false;
    for (const b of boxes) {
      if (p.x < b.minX - PLAYER_R || p.x > b.maxX + PLAYER_R || p.z < b.minZ - PLAYER_R || p.z > b.maxZ + PLAYER_R) continue;
      const cx = Math.min(Math.max(p.x, b.minX), b.maxX);
      const cz = Math.min(Math.max(p.z, b.minZ), b.maxZ);
      let dx = p.x - cx, dz = p.z - cz;
      const d2 = dx * dx + dz * dz;
      if (d2 > 1e-8) {
        if (d2 >= PLAYER_R * PLAYER_R) continue;
        const d = Math.sqrt(d2);
        p.x = cx + dx / d * PLAYER_R; p.z = cz + dz / d * PLAYER_R;
      } else { // Mittelpunkt im Rechteck -> auf kuerzestem Weg hinaus
        const pen = [[p.x - b.minX, -1, 0], [b.maxX - p.x, 1, 0], [p.z - b.minZ, 0, -1], [b.maxZ - p.z, 0, 1]].sort((a, c) => a[0] - c[0])[0];
        p.x += pen[1] * (pen[0] + PLAYER_R); p.z += pen[2] * (pen[0] + PLAYER_R);
      }
      moved = true;
    }
    p.x = Math.min(Math.max(p.x, BOUNDS.minX), BOUNDS.maxX);
    p.z = Math.min(Math.max(p.z, BOUNDS.minZ), BOUNDS.maxZ);
    if (!moved) break;
  }
}

// ------------------------------------------------------------------ Eingabe & Kamera
const keys = new Set();
addEventListener('keydown', e => {
  keys.add(e.code);
  if (e.code === 'KeyN') toggleEvening();
  if (e.code === 'KeyH') document.getElementById('hud').classList.toggle('hidden');
  if (e.code === 'KeyG') cycleFollow();
});
addEventListener('keyup', e => keys.delete(e.code));
addEventListener('blur', () => keys.clear());

const cam = { yaw: 0, pitch: 0.95, dist: 22, yawT: 0, pitchT: 0.95, distT: 22, target: new THREE.Vector3() };
let dragging = false, lastX = 0, lastY = 0;
renderer.domElement.addEventListener('contextmenu', e => e.preventDefault());
renderer.domElement.addEventListener('pointerdown', e => { if (e.button === 2 || e.button === 1) { dragging = true; lastX = e.clientX; lastY = e.clientY; } });
addEventListener('pointerup', () => dragging = false);
addEventListener('pointermove', e => {
  if (!dragging) return;
  cam.yawT -= (e.clientX - lastX) * 0.006;
  cam.pitchT = THREE.MathUtils.clamp(cam.pitchT + (e.clientY - lastY) * 0.004, 0.45, 1.45);
  lastX = e.clientX; lastY = e.clientY;
});
renderer.domElement.addEventListener('wheel', e => { e.preventDefault(); cam.distT = THREE.MathUtils.clamp(cam.distT * (1 + Math.sign(e.deltaY) * 0.1), 7, 60); }, { passive: false });

function updateCamera(dt) {
  const k = 1 - Math.exp(-dt * 8);
  cam.yaw += (cam.yawT - cam.yaw) * k;
  cam.pitch += (cam.pitchT - cam.pitch) * k;
  cam.dist += (cam.distT - cam.dist) * k;
  const g = follow >= 0 ? seagulls.gulls[follow] : null;
  cam.target.lerp(g ? g.pos.clone().setY(g.pos.y + 0.4) : new THREE.Vector3(player.position.x, 1.0, player.position.z), 1 - Math.exp(-dt * (g ? 4 : 6)));
  const h = Math.cos(cam.pitch) * cam.dist;
  camera.position.set(cam.target.x + Math.sin(cam.yaw) * h, cam.target.y + Math.sin(cam.pitch) * cam.dist, cam.target.z + Math.cos(cam.yaw) * h);
  camera.lookAt(cam.target);
}

// Gebaeude zwischen Kamera und Figur ausblenden
const ray = new THREE.Raycaster();
const fadeMeshes = () => fadeables.flatMap(f => f.meshes);
let allFadeMeshes = null;
function updateOcclusion(dt) {
  allFadeMeshes ??= fadeMeshes();
  const head = player.position.clone().add(new THREE.Vector3(0, 1.0, 0));
  const dir = head.clone().sub(camera.position);
  const len = dir.length();
  ray.set(camera.position, dir.normalize());
  ray.far = len - 0.5;
  const hit = new Set(ray.intersectObjects(allFadeMeshes, false).map(i => i.object));
  for (const f of fadeables) {
    f.target = f.meshes.some(m => hit.has(m)) ? 0.22 : 1;
    if (Math.abs(f.opacity - f.target) < 0.001) continue;
    f.opacity += (f.target - f.opacity) * (1 - Math.exp(-dt * 10));
    if (Math.abs(f.opacity - f.target) < 0.01) f.opacity = f.target;
    for (const m of f.meshes) for (const mat of (Array.isArray(m.material) ? m.material : [m.material])) {
      const t = f.opacity < 0.999;
      if (mat.transparent !== t) { mat.transparent = t; mat.needsUpdate = true; }
      mat.opacity = f.opacity;
      mat.depthWrite = !t;
    }
    for (const m of f.meshes) m.castShadow = true;
  }
}

// ------------------------------------------------------------------ Tag / Abend
// Warme Lichtpools an den Laternen (Positionen wie im Blender-Skript, Blender (x, y) -> three (x, -y))
const LAMPS = [[-15.5, 1.0], [-15.8, -13.0], [-15.8, -30.0], [-15.8, -46.0], [11.8, -8.5], [11.8, -20.5], [-7.0, 15.5], [9.5, 15.0], [-7.0, -24.0], [25.0, -29.0]];
const lampLights = LAMPS.map(([x, y]) => {
  const l = new THREE.PointLight('#ffb36b', 0, 16, 1.6);
  l.position.set(x, 3.8, -y);
  scene.add(l);
  return l;
});
let evening = params.has('evening');
function applyMood() {
  if (evening) {
    sun.color.set('#ff9f6b'); sun.intensity = 1.2; hemi.intensity = 1.0; hemi.color.set('#9d97e0'); hemi.groundColor.set('#5a4450');
    skyUniforms.top.value.set('#3b3470'); skyUniforms.bottom.value.set('#e88f6a'); scene.fog.color.set('#6d5470');
    bloom.strength = 0.55; bloom.threshold = 0.85; bloom.radius = 0.4;
    for (const m of glowMats) m.emissiveIntensity = m.userData.baseEmissive * (m.name === 'Bulb_Glow' ? 1 : 1.6);
    for (const l of lampLights) l.intensity = 30;
    SUN_OFFSET.set(-45, 18, 10);
  } else {
    sun.color.set('#ffd9a8'); sun.intensity = 2.6; hemi.intensity = 1.3; hemi.color.set('#d9d2ff'); hemi.groundColor.set('#8a6a52');
    skyUniforms.top.value.set('#7f78b8'); skyUniforms.bottom.value.set('#f3c99a'); scene.fog.color.set('#c9a9b0');
    bloom.strength = 0.45; bloom.threshold = 0.9; bloom.radius = 0.6;
    for (const m of glowMats) m.emissiveIntensity = m.userData.baseEmissive;
    for (const l of lampLights) l.intensity = 0;
    SUN_OFFSET.set(-30, 45, 22);
  }
}
function toggleEvening() { evening = !evening; applyMood(); }
applyMood();

// ------------------------------------------------------------------ Orte (Hinweise beim Naehern)
const POI_TEXT = {
  POI_Fischerbrunnen: 'Fischerbrunnen – Bronzefiguren von Jo Jastram auf dem Fischmarkt',
  POI_Fischer: 'Der Fischer mit Südwester und sein Netzzieher',
  POI_Aaljunge: 'Ein Junge greift nach dem glitschigen Aal',
  POI_FensterSkulptur: 'Frau und Kind schauen aus dem Bronzefenster',
  POI_Rathaus: 'Das rote Rathaus mit seinem geschwungenen Westgiebel',
  POI_Linde: 'Schattiges Plätzchen unter der Linde',
};
const poiEl = document.getElementById('poi');
let currentPoi = null;
function updatePoi() {
  let best = null, bestD = 4.5;
  for (const p of pois) {
    if (!POI_TEXT[p.name]) continue;
    const d = Math.hypot(p.position.x - player.position.x, p.position.z - player.position.z);
    if (d < bestD) { best = p; bestD = d; }
  }
  if (best !== currentPoi) {
    currentPoi = best;
    if (best) poiEl.textContent = POI_TEXT[best.name];
    poiEl.classList.toggle('show', !!best);
  }
}

// ------------------------------------------------------------------ Moewen
const seagulls = await createSeagulls({
  scene, loader, world: world.scene, boxes, bounds: BOUNDS, player,
  lamps: LAMPS.map(([x, y]) => [x, -y]), count: +(params.get('gulls') ?? 10),
});
let follow = -1; // G: Kamera folgt einer Moewe
function cycleFollow() { follow = follow + 1 >= seagulls.gulls.length ? -1 : follow + 1; }

// ------------------------------------------------------------------ Hauptschleife
const water = world.scene.getObjectByName('Fountain_Water');
const clock = new THREE.Clock();
const vel = new THREE.Vector3();
let walkPhase = 0, demoT = 0;
const fwd = new THREE.Vector3(), right = new THREE.Vector3(), wish = new THREE.Vector3();

function step() {
  const dt = Math.min(clock.getDelta(), 0.05);
  const t = clock.elapsedTime;

  // Eingabe -> Wunschrichtung relativ zur Kamera
  if (keys.has('KeyQ')) cam.yawT += dt * 1.8;
  if (keys.has('KeyE')) cam.yawT -= dt * 1.8;
  fwd.set(-Math.sin(cam.yaw), 0, -Math.cos(cam.yaw));
  right.set(-fwd.z, 0, fwd.x);
  wish.set(0, 0, 0);
  if (keys.has('KeyW') || keys.has('ArrowUp')) wish.add(fwd);
  if (keys.has('KeyS') || keys.has('ArrowDown')) wish.sub(fwd);
  if (keys.has('KeyD') || keys.has('ArrowRight')) wish.add(right);
  if (keys.has('KeyA') || keys.has('ArrowLeft')) wish.sub(right);
  if (DEMO) { demoT += dt; wish.set(Math.sin(demoT * 0.4), 0, -1); cam.yawT = 0.4 * Math.sin(demoT * 0.2); }
  const running = keys.has('ShiftLeft') || keys.has('ShiftRight');
  const speed = running ? 7.5 : 4.2;
  if (wish.lengthSq() > 0) wish.normalize().multiplyScalar(speed);
  vel.lerp(wish, 1 - Math.exp(-dt * 12));

  const p = player.position;
  p.x += vel.x * dt; p.z += vel.z * dt;
  resolveCollisions(p);

  // Ausrichtung & Laufanimation
  const sp = Math.hypot(vel.x, vel.z);
  if (sp > 0.2) {
    const targetRot = Math.atan2(vel.x, vel.z);
    let dr = targetRot - player.rotation.y;
    dr = Math.atan2(Math.sin(dr), Math.cos(dr));
    player.rotation.y += dr * (1 - Math.exp(-dt * 14));
  }
  walkPhase += dt * sp * 2.4;
  const amp = Math.min(sp / 4.2, 1);
  const { body, legs } = player.userData;
  body.position.y = Math.abs(Math.sin(walkPhase)) * 0.09 * amp + Math.sin(t * 2) * 0.01;
  body.rotation.z = Math.sin(walkPhase) * 0.06 * amp;
  body.rotation.x = 0.12 * amp * (running ? 1.6 : 1);
  legs[0].rotation.x = Math.sin(walkPhase) * 0.8 * amp;
  legs[1].rotation.x = -Math.sin(walkPhase) * 0.8 * amp;
  blob.position.x = p.x; blob.position.z = p.z;

  seagulls.update(dt, t);
  updateCamera(dt);
  updateOcclusion(dt);
  updatePoi();

  // Sonne folgt der Figur (Schattenkamera bleibt scharf)
  sun.position.copy(p).add(SUN_OFFSET);
  sun.target.position.copy(p);
  sky.position.copy(camera.position);
  if (water) water.position.y = Math.sin(t * 1.3) * 0.015;
  for (const m of glowMats) if (m.name === 'Bulb_Glow') m.emissiveIntensity = m.userData.baseEmissive * (0.92 + 0.08 * Math.sin(t * 3));

  composer.render();
  requestAnimationFrame(step);
}

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight); composer.setSize(innerWidth, innerHeight);
});

cam.target.set(player.position.x, 1, player.position.z);
document.getElementById('loading').classList.add('done');
window.__game = { player, boxes, cam, resolveCollisions, seagulls, setFollow: i => { follow = i; } };

// Selbsttest (?selftest): laeuft gegen Brunnen, Fassaden und Laternen und schreibt das Ergebnis ins DOM
if (params.has('selftest')) {
  const walk = (x, z, dx, dz, dist) => {
    const q = new THREE.Vector3(x, 0, z);
    for (let i = 0; i < dist / 0.05; i++) { q.x += dx * 0.05; q.z += dz * 0.05; resolveCollisions(q); }
    return [+q.x.toFixed(2), +q.z.toFixed(2)];
  };
  const res = {
    boxes: boxes.length,
    northToFountain: walk(0, 10, 0, -1, 10),        // erwartet z ~ 3.95
    westToVeroModa: walk(-10, 0, -1, 0, 15),        // erwartet x ~ -17.25
    eastToRathaus: walk(8, 15, 1, 0, 15),           // erwartet x ~ 13.85
    southToKeimblatt: walk(2, 20, 0, 1, 30),        // erwartet z ~ 33.65 (Strasse davor frei)
    streetEastAlongRathaus: walk(0, 30.5, 1, 0, 25),// Strasse suedlich vom Rathaus, erwartet x weit im Osten
    intoLamp: walk(-15.5, 4, 0, -1, 6),             // Laterne bei z=-1 -> stoppt bei ~ -0.55
  };
  const pre = document.createElement('pre'); pre.id = 'selftest'; pre.textContent = JSON.stringify(res); document.body.appendChild(pre);
}
// Moewen-Vorschau und -Statistik (?gallery, ?gullstats, ?follow=<n>)
if (params.has('gallery')) {
  player.position.set(5, 0, 21);
  seagulls.showcase(5, 20);
  player.visible = blob.visible = false;
  Object.assign(cam, { yaw: Math.PI, yawT: Math.PI, pitch: 0.32, pitchT: 0.32, dist: 7.5, distT: 7.5 });
  cam.target.set(5, 1, 21);
}
if (params.has('follow')) follow = +params.get('follow');
// ?gullsim=<s>: simuliert die Moewen-KI mit festem Zeitschritt und prueft Plausibilitaet (Headless-Test)
if (params.has('gullsim')) {
  const secs = +params.get('gullsim') || 120, dt = 1 / 30;
  const seen = {}, trans = {}, bad = [], last = seagulls.gulls.map(g => g.surface + ':' + g.state);
  let maxY = 0;
  const inBox = (p, m) => boxes.some(b => p.x > b.minX + m && p.x < b.maxX - m && p.z > b.minZ + m && p.z < b.maxZ - m && p.y < b.maxY - 0.05);
  const t0 = performance.now();
  for (let i = 0; i < secs / dt; i++) {
    const t = i * dt;
    if (params.has('chase')) { // Figur laeuft im Kreis um den Brunnen
      player.position.set(Math.cos(t * 0.35) * 7, 0, Math.sin(t * 0.35) * 7);
    }
    seagulls.update(dt, t);
    seagulls.gulls.forEach((g, k) => {
      const key = g.surface + ':' + g.state;
      seen[key] = (seen[key] || 0) + 1;
      if (key !== last[k]) { const tk = last[k] + '>' + key; trans[tk] = (trans[tk] || 0) + 1; last[k] = key; }
      maxY = Math.max(maxY, g.pos.y);
      if (!Number.isFinite(g.pos.x + g.pos.y + g.pos.z)) bad.push(['nan', k, t]);
      else if (g.surface === 'ground' && inBox(g.pos, 0.05)) bad.push(['inBox', k, +t.toFixed(1), g.pos.toArray().map(v => +v.toFixed(2))]);
    });
  }
  const pre = document.createElement('pre'); pre.id = 'gullsim';
  pre.style.cssText = 'position:fixed;right:8px;top:8px;max-width:50vw;white-space:pre-wrap;background:#fffc;font:11px monospace;padding:6px';
  pre.textContent = JSON.stringify({ secs, msPerStep: +((performance.now() - t0) / (secs / dt)).toFixed(3), maxY: +maxY.toFixed(1), seen, trans, bad: bad.slice(0, 8), nBad: bad.length,
    perches: seagulls.gulls.filter(g => g.surface === 'perch').map(g => g.pos.toArray().map(v => +v.toFixed(1))) });
  document.body.appendChild(pre);
}
if (params.has('gullstats')) {
  const pre = document.createElement('pre'); pre.id = 'gullstats'; document.body.appendChild(pre);
  pre.style.cssText = 'position:fixed;right:8px;top:8px;max-width:45vw;white-space:pre-wrap;background:#fffc;font:12px monospace;padding:6px';
  const seen = {};
  setInterval(() => {
    for (const g of seagulls.gulls) { const k = g.surface + ':' + g.state; seen[k] = (seen[k] || 0) + 1; }
    pre.textContent = JSON.stringify({ t: +clock.elapsedTime.toFixed(1), now: seagulls.stats(), seen, pos: seagulls.gulls.map(g => g.pos.toArray().map(v => +v.toFixed(1))) });
  }, 500);
}
requestAnimationFrame(step);
