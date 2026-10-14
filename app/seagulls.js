// Freche Silbermoewen fuer den Fischmarkt: laufen, picken, kreischen, huepfen, schwimmen im Brunnen und fliegen frei
// ueber den Platz (inkl. Landung auf Daechern, Laternen, Brunnenrand und Skulpturen).
import * as THREE from 'three';

const S = 1.5;                // Spielmassstab (Naturgroesse waere 1.0, etwas groesser liest sich in der Draufsicht besser)
const SWIM_SINK = 0.17 * S;     // Wasserlinie am Rumpf
const RIM = { a: 3.575, b: 3.375, y: 0.45 }; // Mittellinie des Beckenrands (halbe Masse), Oberkante
const WATER = { minX: -3.35, maxX: 3.35, minZ: -3.15, maxZ: 3.15, y: 0.34 };
const WALK_SPEED = 0.55, WALK_CLIP_SPEED = 0.55; // m/s, bei der die Walk-Animation timeScale 1 hat
const SWIM_SPEED = 0.45;
const FLY_SPEED = 6.5;
const GULL_R = 0.22;

const v3 = () => new THREE.Vector3();
const rand = (a, b) => a + Math.random() * (b - a);
const pick = arr => arr[Math.floor(Math.random() * arr.length)];
const angDiff = (a, b) => Math.atan2(Math.sin(b - a), Math.cos(b - a));
const smooth = t => t * t * (3 - 2 * t);

function weighted(options) {
  const tot = options.reduce((s, o) => s + Math.max(0, o[0]), 0);
  let r = Math.random() * tot;
  for (const [w, fn] of options) { if ((r -= Math.max(0, w)) <= 0) return fn(); }
  return options[options.length - 1][1]();
}

// Rechteckige Mittellinie des Beckenrands, parametrisiert ueber die Bogenlaenge s
const RIM_L = 4 * (RIM.a + RIM.b);
function ringPos(s, out = v3()) {
  const { a, b } = RIM;
  s = ((s % RIM_L) + RIM_L) % RIM_L;
  if (s < 2 * a) return out.set(-a + s, RIM.y, -b);
  s -= 2 * a;
  if (s < 2 * b) return out.set(a, RIM.y, -b + s);
  s -= 2 * b;
  if (s < 2 * a) return out.set(a - s, RIM.y, b);
  s -= 2 * a;
  return out.set(-a, RIM.y, b - s);
}
function ringParam(x, z) { // naechster Punkt auf dem Rand -> s
  const { a, b } = RIM;
  const cands = [
    [Math.abs(z + b), THREE.MathUtils.clamp(x, -a, a) + a],
    [Math.abs(x - a), 2 * a + THREE.MathUtils.clamp(z, -b, b) + b],
    [Math.abs(z - b), 2 * a + 2 * b + a - THREE.MathUtils.clamp(x, -a, a)],
    [Math.abs(x + a), 4 * a + 2 * b + b - THREE.MathUtils.clamp(z, -b, b)],
  ];
  return cands.sort((p, q) => p[0] - q[0])[0][1];
}

export async function createSeagulls({ scene, loader, world, boxes, bounds, player, lamps, count = 10 }) {
  const gltf = await loader.loadAsync('../model/seagull.glb');
  const clips = Object.fromEntries(gltf.animations.map(c => [c.name, c]));
  gltf.scene.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });

  const water = world.getObjectByName('Fountain_Water');
  if (water) { const bb = new THREE.Box3().setFromObject(water); WATER.y = bb.max.y; }

  // Hindernisse im Wasser: Skulpturen (Bounding-Boxen der Modelle)
  const sculptBoxes = [];
  world.traverse(o => {
    if (/^Sculpture_/.test(o.name) && o.parent && !/^Sculpture_/.test(o.parent.name)) {
      const bb = new THREE.Box3().setFromObject(o);
      sculptBoxes.push({ minX: bb.min.x, maxX: bb.max.x, minZ: bb.min.z, maxZ: bb.max.z, maxY: bb.max.y });
    }
  });
  const inBox = (b, x, z, m = 0) => x > b.minX - m && x < b.maxX + m && z > b.minZ - m && z < b.maxZ + m;
  const inWater = (x, z, m = 0) => x > WATER.minX + m && x < WATER.maxX - m && z > WATER.minZ + m && z < WATER.maxZ - m;
  const waterFree = (x, z, m = 0.3) => inWater(x, z, m) && !sculptBoxes.some(b => inBox(b, x, z, m));
  const rimFree = s => { const p = ringPos(s); return !sculptBoxes.some(b => inBox(b, p.x, p.z, 0.05)); };
  const groundFree = (x, z, m = GULL_R) =>
    x > bounds.minX && x < bounds.maxX && z > bounds.minZ && z < bounds.maxZ && !boxes.some(b => inBox(b, x, z, m));

  // Flughoehe ueber Hindernissen (Kollider-Hoehe + Dachzuschlag)
  function floorAt(x, z) {
    let h = 0;
    for (const b of boxes) if (inBox(b, x, z, 1.2)) h = Math.max(h, b.maxY + (/^COL_B_/.test(b.name) ? 8 : 1.2));
    return h;
  }
  function floorAlong(a, b) {
    let h = 0;
    for (let i = 0; i <= 12; i++) h = Math.max(h, floorAt(a.x + (b.x - a.x) * i / 12, a.z + (b.z - a.z) * i / 12));
    return h;
  }

  // Raycast-Ziele fuer Landeplaetze auf beliebigen Oberflaechen (Daecher, Laternen, Tische, Skulpturen ...)
  const rayMeshes = [];
  world.traverse(o => { if (o.isMesh && !/Lichterketten|Grass/.test(o.name) && !/Lichterketten|Grass/.test(o.parent?.name ?? '')) rayMeshes.push(o); });
  const ray = new THREE.Raycaster();
  const down = new THREE.Vector3(0, -1, 0);
  const nrm = new THREE.Vector3();
  function surfaceAt(x, z) {
    ray.set(new THREE.Vector3(x, 60, z), down);
    const hit = ray.intersectObjects(rayMeshes, false)[0];
    if (!hit) return null;
    nrm.copy(hit.face.normal).transformDirection(hit.object.matrixWorld);
    let o = hit.object, name = o.name;
    while (o.parent && o.parent !== world) { o = o.parent; name += '/' + o.name; }
    return { y: hit.point.y, flat: Math.abs(nrm.y), water: /Water/.test(name), name };
  }
  const perchCands = [
    ...lamps.map(([x, z]) => [x, z, 0.05]),
    ...sculptBoxes.map(b => [(b.minX + b.maxX) / 2, (b.minZ + b.maxZ) / 2, 0.35]),
    ...boxes.filter(b => /^COL_prop/.test(b.name) && b.maxY > 0.4).map(b => [(b.minX + b.maxX) / 2, (b.minZ + b.maxZ) / 2, 0.2]),
    ...boxes.filter(b => /^COL_B_/.test(b.name)).flatMap(b => [0, 1, 2].map(() => ['roof', b])),
  ];

  const gulls = [];
  const takenNear = (p, r = 0.8, self) => gulls.some(g => g !== self && ((g.dest && g.dest.pos.distanceTo(p) < r) || g.pos.distanceTo(p) < r));

  function spotWater(self) {
    for (let i = 0; i < 30; i++) {
      const x = rand(WATER.minX, WATER.maxX), z = rand(WATER.minZ, WATER.maxZ);
      const p = new THREE.Vector3(x, WATER.y - SWIM_SINK, z);
      if (waterFree(x, z, 0.45) && !takenNear(p, 0.8, self)) return { pos: p, kind: 'water' };
    }
    return null;
  }
  function spotRim(self) {
    for (let i = 0; i < 20; i++) {
      const s = rand(0, RIM_L);
      const p = ringPos(s);
      if (rimFree(s) && !takenNear(p, 0.8, self)) return { pos: p, kind: 'rim', s };
    }
    return null;
  }
  function spotGround(self, cx, cz, r0, r1) {
    for (let i = 0; i < 40; i++) {
      const a = rand(0, Math.PI * 2), r = rand(r0, r1);
      const x = cx + Math.cos(a) * r, z = cz + Math.sin(a) * r;
      const p = new THREE.Vector3(x, 0, z);
      if (groundFree(x, z, 0.35) && !takenNear(p, 0.9, self) && p.distanceTo(player.position) > 1.4) return { pos: p, kind: 'ground' };
    }
    return null;
  }
  function spotPerch(self) {
    for (let i = 0; i < 6; i++) {
      const c = pick(perchCands);
      let x, z;
      if (c[0] === 'roof') { const b = c[1]; x = rand(b.minX + 1, b.maxX - 1); z = rand(b.minZ + 1, b.maxZ - 1); }
      else { x = c[0] + rand(-c[2], c[2]); z = c[1] + rand(-c[2], c[2]); }
      const s = surfaceAt(x, z);
      if (!s || s.water || s.flat < 0.6 || s.y < 0.3) continue;
      const p = new THREE.Vector3(x, s.y, z);
      if (!takenNear(p, 0.7, self)) return { pos: p, kind: 'perch', what: s.name.split('/').pop() };
    }
    return null;
  }
  function pickSpot(self, flee = false) {
    const pp = player.position;
    const spot = weighted([
      [flee ? 0.5 : 2.5, () => spotWater(self)],
      [1.4, () => spotRim(self)],
      [flee ? 0 : 2.0, () => spotGround(self, pp.x, pp.z, 2.2, 7)],   // frech: in die Naehe der Figur
      [1.5, () => spotGround(self, 0, 0, 4.5, 16)],
      [flee ? 3 : 2.2, () => spotPerch(self)],
    ]);
    return spot || spotGround(self, 0, 0, 4.5, 18) || spotRim(self);
  }

  // ------------------------------------------------------------------ Moewe
  class Gull {
    constructor(i) {
      this.id = i;
      this.root = new THREE.Group();
      this.root.rotation.order = 'YXZ';
      this.model = gltf.scene.clone(true);
      this.model.scale.setScalar(S * rand(0.93, 1.07));
      this.root.add(this.model);
      scene.add(this.root);
      this.mixer = new THREE.AnimationMixer(this.model);
      this.actions = {};
      for (const [n, c] of Object.entries(clips)) this.actions[n] = this.mixer.clipAction(c);
      this.cur = null;
      this.pos = this.root.position;
      this.yaw = rand(0, Math.PI * 2); this.pitch = 0; this.bank = 0;
      this.state = 'idle'; this.timer = rand(0.5, 3);
      this.surface = 'ground'; this.s = 0;
      this.goal = v3(); this.dest = null;
      this.speed = 0; this.vy = 0; this.flap = 0; this.flightT = 0; this.wander = 0;
      this.cool = 0; this.yawRate = 0; this.yawT = this.yaw;
    }

    play(name, { fade = 0.25, ts = 1, once = false, restart = false } = {}) {
      const a = this.actions[name];
      if (this.cur === a && !restart) { a.setEffectiveTimeScale(ts); return; }
      a.reset();
      a.setLoop(once ? THREE.LoopOnce : THREE.LoopRepeat, Infinity);
      a.clampWhenFinished = once;
      a.setEffectiveTimeScale(ts).setEffectiveWeight(1).play();
      if (this.cur && this.cur !== a) a.crossFadeFrom(this.cur, fade, false);
      if (!this.cur) a.time = Math.random() * a.getClip().duration;
      this.cur = a;
    }

    // ---- Zustaende
    setIdle(t = rand(1.5, 5)) { this.state = 'idle'; this.timer = t; this.play(this.surface === 'water' ? 'Swim' : 'Idle', { ts: this.surface === 'water' ? 0.35 : rand(0.8, 1.2) }); }
    setPeck() { this.state = 'peck'; this.timer = clips.Peck.duration * Math.ceil(rand(1, 3)); this.play('Peck', { restart: true }); }
    setSquawk() { this.state = 'squawk'; this.timer = clips.Squawk.duration; this.play('Squawk', { once: true, fade: 0.15 }); }
    setWalk(goal, speed = WALK_SPEED) {
      this.state = 'walk'; this.goal.copy(goal); this.speed = speed; this.timer = 12;
      this.play('Walk', { ts: speed / WALK_CLIP_SPEED });
    }
    setRimWalk(s1) { this.state = 'rimwalk'; this.goalS = s1; this.speed = WALK_SPEED; this.timer = 15; this.play('Walk'); }
    setSwim(goal) { this.state = 'swim'; this.goal.copy(goal); this.timer = 20; this.play('Swim', { ts: 1 }); }
    setHop(to, kind, s = 0) {
      this.state = 'hop';
      this.hop = { from: this.pos.clone(), to: to.clone(), kind, s, t: 0, T: clips.Hop.duration };
      const dy = to.y - this.pos.y;
      this.hop.h = Math.max(0.22, dy + 0.3);
      const d = v3().subVectors(to, this.pos);
      if (d.x * d.x + d.z * d.z > 0.01) this.yawT = Math.atan2(d.x, d.z);
      this.play('Hop', { once: true, fade: 0.1 });
    }
    takeOff(flee = false) {
      this.state = 'fly'; this.surface = 'air';
      this.speed = flee ? 4.5 : 2.5; this.vy = 3.2; this.flap = 1.4; this.flightT = 0;
      if (flee) { const away = v3().subVectors(this.pos, player.position); this.yaw = Math.atan2(away.x, away.z) + rand(-0.4, 0.4); }
      this.dest = Math.random() < 0.4 && !flee ? null : pickSpot(this, flee);
      this.wander = rand(4, 12);
      this.cruise = rand(5, 13);
      this.waypoint = this.newWaypoint();
      this.play('Fly', { fade: 0.15, ts: 1.3 });
    }
    newWaypoint() { const a = rand(0, Math.PI * 2), r = rand(4, 24); return new THREE.Vector3(Math.cos(a) * r, rand(5, 14), Math.sin(a) * r + 6); }
    startLand() {
      this.state = 'land';
      this.land = { from: this.pos.clone(), t: 0, T: clips.Land.duration * 1.3 };
      this.play('Land', { once: true, fade: 0.2, ts: 1 / 1.3 });
    }
    arrive(kind, s) {
      this.surface = kind; this.s = s ?? this.s;
      this.pitch = 0; this.bank = 0; this.dest = null;
      if (kind === 'water') { this.setIdle(rand(2, 5)); return; }
      Math.random() < 0.35 ? this.setSquawk() : this.setIdle(rand(1, 3));
    }

    // ---- Entscheidungen
    decide() {
      const pp = player.position;
      const dPlayer = Math.hypot(pp.x - this.pos.x, pp.z - this.pos.z);
      if (this.surface === 'ground') {
        const nearBasin = Math.abs(this.pos.x) < RIM.a + 1.6 && Math.abs(this.pos.z) < RIM.b + 1.6;
        weighted([
          [2.5, () => { const g = spotGround(this, this.pos.x, this.pos.z, 1, 4.5); g ? this.setWalk(g.pos) : this.setIdle(); }],
          [1.2, () => this.setIdle()],
          [1.6, () => this.setPeck()],
          [0.6, () => this.setSquawk()],
          [0.6, () => this.takeOff()],
          [nearBasin ? 2.2 : 0, () => { const s = ringParam(this.pos.x, this.pos.z); rimFree(s) ? this.setHop(ringPos(s), 'rim', s) : this.setIdle(); }],
          [dPlayer < 9 && dPlayer > 1.8 && playerSpeed < 0.5 ? 3 : 0, () => { // frech zur Figur watscheln
            const dir = v3().subVectors(this.pos, pp).setY(0).normalize();
            const g = pp.clone().addScaledVector(dir, rand(1.15, 1.5)).setY(0);
            groundFree(g.x, g.z) ? this.setWalk(g, 0.8) : this.setIdle();
          }],
        ]);
      } else if (this.surface === 'rim') {
        weighted([
          [2, () => { const s1 = this.s + rand(-3, 3); this.setRimWalk(s1); }],
          [1.2, () => this.setIdle()],
          [0.8, () => this.setSquawk()],
          [0.6, () => this.setPeck()],
          [1.6, () => { // ins Wasser huepfen
            const p = ringPos(this.s); const q = p.clone().multiplyScalar(0.8);
            waterFree(q.x, q.z, 0.3) ? this.setHop(q.setY(WATER.y - SWIM_SINK), 'water') : this.setIdle();
          }],
          [0.8, () => { // auf den Platz huepfen
            const p = ringPos(this.s); const out = p.clone().setY(0).multiplyScalar(1.22);
            groundFree(out.x, out.z) ? this.setHop(out, 'ground') : this.setIdle();
          }],
          [0.6, () => this.takeOff()],
        ]);
      } else if (this.surface === 'perch') {
        weighted([[2, () => this.setIdle(rand(3, 8))], [1, () => this.setSquawk()], [1, () => this.takeOff()]]);
      } else if (this.surface === 'water') {
        weighted([
          [3, () => { const sp = spotWater(this); sp && sp.pos.distanceTo(this.pos) < 4 ? this.setSwim(sp.pos) : this.setIdle(); }],
          [1.5, () => this.setIdle(rand(2, 5))],
          [0.9, () => { const s = ringParam(this.pos.x, this.pos.z); rimFree(s) ? this.setHop(ringPos(s), 'rim', s) : this.setIdle(); }],
          [0.6, () => this.takeOff()],
        ]);
      }
    }

    // ---- Pro Frame
    update(dt, t) {
      if (this.frozen) { this.root.rotation.set(this.pitch, this.yaw, this.bank); this.mixer.update(dt); return; }
      this.cool -= dt;
      this.timer -= dt;
      const pp = player.position;
      const toPlayer = Math.hypot(pp.x - this.pos.x, pp.z - this.pos.z);

      // Flucht vor der Spielfigur
      if (this.surface !== 'air' && this.state !== 'hop' && this.cool < 0 && this.pos.y < 1.5) {
        const scared = toPlayer < 0.85 || (toPlayer < 2.6 && playerSpeed > 5) || (toPlayer < 1.6 && playerSpeed > 2);
        if (scared) {
          this.cool = 1.2;
          if (this.surface === 'water' && toPlayer > 1.0 && Math.random() < 0.6) {
            const away = v3().subVectors(this.pos, pp).setY(0).normalize().multiplyScalar(2.2).add(this.pos);
            if (waterFree(away.x, away.z, 0.3)) this.setSwim(away), this.speed = 2;
            else this.takeOff(true);
          } else if (this.surface === 'ground' && playerSpeed < 5 && Math.random() < 0.5) {
            const away = v3().subVectors(this.pos, pp).setY(0).normalize().multiplyScalar(0.9).add(this.pos);
            groundFree(away.x, away.z) ? this.setHop(away.setY(0), 'ground') : this.takeOff(true);
          } else this.takeOff(true);
        }
      }

      switch (this.state) {
        case 'idle': case 'peck': case 'squawk': {
          // frecher Blick: zur Figur drehen, wenn sie in der Naehe ist
          if (toPlayer < 6 && this.state === 'idle') this.yawT = Math.atan2(pp.x - this.pos.x, pp.z - this.pos.z);
          if (this.surface === 'water') { this.yawT = (this.yawT ?? this.yaw) + dt * 0.2 * Math.sin(t * 0.3 + this.id); }
          if (this.timer < 0) this.decide();
          break;
        }
        case 'walk': {
          const d = v3().subVectors(this.goal, this.pos).setY(0);
          const L = d.length();
          if (L < 0.08 || this.timer < 0) { this.decide(); break; }
          this.yawT = Math.atan2(d.x, d.z);
          const facing = Math.cos(angDiff(this.yaw, this.yawT));
          const stepLen = Math.min(L, this.speed * dt * Math.max(0, facing));
          const nx = this.pos.x + d.x / L * stepLen, nz = this.pos.z + d.z / L * stepLen;
          if (groundFree(nx, nz, GULL_R * 0.7)) { this.pos.x = nx; this.pos.z = nz; }
          else this.setIdle(1);
          break;
        }
        case 'rimwalk': {
          const ds = this.goalS - this.s;
          if (Math.abs(ds) < 0.05 || this.timer < 0) { this.decide(); break; }
          const ns = this.s + Math.sign(ds) * Math.min(Math.abs(ds), this.speed * dt);
          if (!rimFree(ns)) { this.setIdle(1); break; }
          const a = ringPos(this.s), b = ringPos(ns);
          if (b.distanceToSquared(a) > 1e-8) this.yawT = Math.atan2(b.x - a.x, b.z - a.z);
          this.s = ns; this.pos.copy(b);
          break;
        }
        case 'swim': {
          const d = v3().subVectors(this.goal, this.pos).setY(0);
          const L = d.length();
          if (L < 0.1 || this.timer < 0) { this.speed = SWIM_SPEED; this.decide(); break; }
          this.yawT = Math.atan2(d.x, d.z);
          const sp = Math.max(this.speed, SWIM_SPEED);
          this.speed += (SWIM_SPEED - this.speed) * (1 - Math.exp(-dt * 1.5));
          const nx = this.pos.x + d.x / L * Math.min(L, sp * dt), nz = this.pos.z + d.z / L * Math.min(L, sp * dt);
          if (waterFree(nx, nz, 0.2)) { this.pos.x = nx; this.pos.z = nz; } else this.setIdle(1);
          this.play('Swim', { ts: sp / SWIM_SPEED });
          break;
        }
        case 'hop': {
          const h = this.hop;
          h.t += dt;
          const k = THREE.MathUtils.clamp((h.t / h.T - 0.22) / 0.58, 0, 1);
          this.pos.lerpVectors(h.from, h.to, smooth(k));
          this.pos.y += h.h * 4 * k * (1 - k);
          if (h.t >= h.T) {
            this.pos.copy(h.to);
            this.arrive(h.kind, h.s);
          }
          break;
        }
        case 'fly': this.updateFlight(dt); break;
        case 'land': {
          const L = this.land;
          L.t += dt;
          const k = Math.min(1, L.t / L.T);
          const e = 1 - (1 - k) * (1 - k);
          this.pos.x = THREE.MathUtils.lerp(L.from.x, this.dest.pos.x, e);
          this.pos.z = THREE.MathUtils.lerp(L.from.z, this.dest.pos.z, e);
          this.pos.y = THREE.MathUtils.lerp(L.from.y, this.dest.pos.y, smooth(k));
          this.pitch *= 1 - Math.min(1, dt * 8); this.bank *= 1 - Math.min(1, dt * 8);
          if (k >= 1) { this.pos.copy(this.dest.pos); this.arrive(this.dest.kind, this.dest.s); }
          break;
        }
      }

      // Ausrichtung
      if (this.state !== 'fly' && this.state !== 'land' && this.yawT !== undefined) {
        this.yaw += angDiff(this.yaw, this.yawT) * (1 - Math.exp(-dt * (this.state === 'idle' ? 3 : 8)));
      }
      if (this.surface === 'water' && this.state !== 'hop') {
        this.pos.y = WATER.y - SWIM_SINK + (water ? water.position.y : 0) + 0.008 * Math.sin(t * 2.1 + this.id);
      }
      this.root.rotation.set(this.pitch, this.yaw, this.bank);
      this.mixer.update(dt);
    }

    updateFlight(dt) {
      this.flightT += dt;
      this.flap -= dt;
      const target = this.dest ? this.dest.pos : this.waypoint;
      const d = v3().subVectors(target, this.pos);
      const dh = Math.hypot(d.x, d.z);
      if (!this.dest) {
        this.wander -= dt;
        if (dh < 3) this.waypoint = this.newWaypoint();
        if (this.wander < 0) { this.dest = pickSpot(this); this.flightT = Math.min(this.flightT, 3); }
      }
      // Kurs: begrenzte Drehrate -> natuerliche Kurven mit Schraeglage
      const desiredYaw = Math.atan2(d.x, d.z);
      const turn = THREE.MathUtils.clamp(angDiff(this.yaw, desiredYaw) * 2.2, -1.9, 1.9);
      this.yawRate += (turn - this.yawRate) * (1 - Math.exp(-dt * 4));
      this.yaw += this.yawRate * dt;
      // Geschwindigkeit und Hoehe
      const approaching = this.dest && dh < 7;
      const vT = approaching ? THREE.MathUtils.clamp(dh * 0.9, 1.6, FLY_SPEED) : FLY_SPEED;
      this.speed += (vT - this.speed) * (1 - Math.exp(-dt * 1.5));
      const ahead = v3(Math.sin(this.yaw), 0, Math.cos(this.yaw)).multiplyScalar(3).add(this.pos);
      let yT;
      if (approaching) yT = target.y + Math.max(0, dh - 1.0) * 0.6;
      else yT = Math.max(this.dest ? this.cruise : target.y, floorAlong(this.pos, target) + 2);
      if (!(approaching && dh < 2.5)) yT = Math.max(yT, floorAt(ahead.x, ahead.z) + 1.0, floorAt(this.pos.x, this.pos.z) + 0.6);
      const vyT = THREE.MathUtils.clamp((yT - this.pos.y) * 1.4, -3.2, 3.5);
      this.vy += (vyT - this.vy) * (1 - Math.exp(-dt * 3));
      this.pos.x += Math.sin(this.yaw) * this.speed * dt;
      this.pos.z += Math.cos(this.yaw) * this.speed * dt;
      this.pos.y = Math.max(0.3, this.pos.y + this.vy * dt);
      // Lage
      this.bank += (THREE.MathUtils.clamp(-this.yawRate * 0.38, -0.65, 0.65) - this.bank) * (1 - Math.exp(-dt * 5));
      this.pitch += (THREE.MathUtils.clamp(-Math.atan2(this.vy, Math.max(this.speed, 1)) * 0.8, -0.5, 0.45) - this.pitch) * (1 - Math.exp(-dt * 4));
      // Fluegelschlag oder Gleiten
      if (this.vy > 0.6 || this.speed < vT - 0.8) this.flap = Math.max(this.flap, 0.6);
      if (this.flap <= 0 && Math.random() < dt * 0.12) this.flap = rand(0.8, 1.8);
      if (this.flap > 0) this.play('Fly', { fade: 0.35, ts: 1 + Math.max(0, this.vy) * 0.12 });
      else this.play('Glide', { fade: 0.5 });
      // Landeanflug
      if (this.dest) {
        if (this.flightT > 2.5 && dh < 0.9 + this.speed * 0.15 && Math.abs(this.pos.y - target.y) < 1.2) this.startLand();
        else if (this.flightT > 25 && dh < 6) { this.dest = pickSpot(this); this.flightT = 2.5; } // nicht ewig kreisen
      }
    }
  }

  // ------------------------------------------------------------------ Startverteilung
  let lastPP = player.position.clone(), playerSpeed = 0;
  for (let i = 0; i < count; i++) {
    const g = new Gull(i);
    gulls.push(g);
    const role = ['water', 'water', 'water', 'rim', 'rim', 'ground', 'ground', 'ground', 'air', 'air'][i % 10];
    let sp = role === 'water' ? spotWater(g) : role === 'rim' ? spotRim(g) : role === 'ground' ? spotGround(g, 0, 0, 4.5, 11) : null;
    if (role === 'air' || !sp) {
      g.pos.copy(g.newWaypoint()); g.surface = 'air'; g.state = 'fly'; g.speed = FLY_SPEED; g.flightT = 3;
      g.dest = null; g.wander = rand(3, 15); g.cruise = rand(6, 12); g.waypoint = g.newWaypoint();
      g.play('Glide');
      continue;
    }
    g.pos.copy(sp.pos); g.surface = sp.kind; g.s = sp.s ?? 0;
    g.setIdle(rand(0.5, 4));
  }

  return {
    gulls,
    update(dt, t) {
      playerSpeed = Math.hypot(player.position.x - lastPP.x, player.position.z - lastPP.z) / Math.max(dt, 1e-4);
      lastPP.copy(player.position);
      for (const g of gulls) g.update(dt, t);
    },
    // Vorschau: alle Animationen nebeneinander (?gallery)
    showcase(cx, cz) {
      Object.keys(clips).forEach((name, i) => {
        const g = gulls[i]; if (!g) return;
        g.frozen = true; g.pitch = g.bank = 0; g.yaw = Math.PI - 0.6;
        const air = /Fly|Glide|Land/.test(name);
        g.pos.set(cx + (i - 4) * 1.15, air ? 0.9 : 0, cz);
        g.play(name, { fade: 0 });
      });
      gulls.slice(Object.keys(clips).length).forEach(g => { g.root.visible = false; g.frozen = true; });
    },
    stats() {
      const c = {};
      for (const g of gulls) { const k = g.surface + ':' + g.state; c[k] = (c[k] || 0) + 1; }
      return c;
    },
    debug: { ringPos, spotPerch: () => spotPerch(null), surfaceAt, clips: Object.keys(clips) },
  };
}
