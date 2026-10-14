// Bewegliche Bauteile der Szene (Props, Skulpturen), siehe model/build_fischerbrunnen.py ("Bauteile").
// Jedes Prop-Objekt traegt in den glTF-Extras eine Teil-Tabelle [id, elternId, pfad, drehpunkt, eingebackene Aenderung]
// und pro Eckpunkt das Attribut _part. Aenderungen (model/edits.json) verschieben/drehen/skalieren ein Teil um seinen
// Drehpunkt, loeschen es oder legen Kopien an. Die Meshes bleiben zusammengefasst, es werden nur Eckpunkte umgeschrieben;
// nur Kopien, die noch nicht eingebacken sind, bekommen bis zum naechsten Build ein eigenes Mesh.
import * as THREE from 'three';

const DEG = THREE.MathUtils.DEG2RAD;
const _r = new THREE.Matrix4(), _s = new THREE.Matrix4(), _t = new THREE.Matrix4(), _v = new THREE.Vector3();

// Aenderung -> Matrix: T(drehpunkt + offset) * Ry(rotY) * S(scale) * T(-drehpunkt)
function editMatrix(e, pivot, out) {
  out.identity();
  if (!e) return out;
  const [x, y, z] = e.offset ?? [0, 0, 0];
  const s = e.scale ?? 1;
  return out.makeTranslation(pivot.x + x, pivot.y + y, pivot.z + z)
    .multiply(_r.makeRotationY((e.rotY ?? 0) * DEG))
    .multiply(_s.makeScale(s, s, s))
    .multiply(_t.makeTranslation(-pivot.x, -pivot.y, -pivot.z));
}

// Einheitliche, gerundete Form (mm, 0,01°, 0,001); null = unveraendert. copyOf steht am Teil, nicht in der Aenderung.
function cleanEdit(e) {
  if (!e) return null;
  const o = (e.offset ?? [0, 0, 0]).map(v => Math.round(v * 1000) / 1000 + 0);
  let r = Math.round(((((e.rotY ?? 0) % 360) + 540) % 360 - 180) * 100) / 100 + 0;
  if (r === -180) r = 180;
  const s = Math.round((e.scale ?? 1) * 1000) / 1000;
  const out = {};
  if (o[0] || o[1] || o[2]) out.offset = o;
  if (r) out.rotY = r;
  if (s !== 1 && s > 0) out.scale = s;
  if (e.deleted) out.deleted = true;
  return Object.keys(out).length ? out : null;
}
const sameEdit = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const depth = path => path.split('/').length;
const FAR = 1e6; // Kollider geloeschter Teile liegen weit ausserhalb

export function createParts(root, boxes) {
  const byId = new Map(), byPath = new Map();
  const meshes = []; // Meshes mit _part-Attribut (Auswahl per Raycast)
  let nextId = -1;   // Laufzeit-Kopien bekommen negative IDs

  function add(p) {
    byId.set(p.id, p);
    byPath.set(p.path, p);
    p.parent = byId.get(p.parentId) ?? null;
    p.parent?.children.push(p);
    return p;
  }
  const newPart = (id, parentId, path, pivot, extra) => ({ id, parentId, path, name: path.split('/').pop(), pivot, copyOf: null,
    derived: false, runtime: false, baked: null, edit: null, parent: null, children: [], verts: [], cols: [], ...extra });

  root.updateMatrixWorld(true);
  root.traverse(o => {
    if (!o.userData.parts) return;
    for (const [id, parentId, path, pivot, e] of JSON.parse(o.userData.parts)) {
      const baked = cleanEdit(e);
      add(newPart(id, parentId, path, new THREE.Vector3(...pivot), { baked, edit: baked, copyOf: e?.copyOf ?? null }));
    }
    o.traverse(m => { if (m.isMesh && m.geometry.attributes._part) meshes.push(m); });
  });
  for (const p of byId.values()) p.derived = chain(p).some(q => q.copyOf); // Kopie oder Teil einer Kopie
  for (const b of boxes) {
    const p = b.part && byPath.get(b.part);
    if (p && b.base) p.cols.push(b);
  }

  function chain(p) { const c = []; for (let q = p; q; q = q.parent) c.unshift(q); return c; }
  const subtree = p => [p, ...p.children.flatMap(subtree)];
  const isDeleted = p => chain(p).some(q => q.edit?.deleted);
  const rotY = p => chain(p).reduce((a, q) => a + (q.edit?.rotY ?? 0), 0);         // Drehungen um Y addieren sich
  const scaleOf = p => chain(p).reduce((a, q) => a * (q.edit?.scale ?? 1), 1);
  // Gesamttransformation eines Teils (Originalgeometrie -> Welt): N = D(wurzel) * ... * D(teil)
  function net(p, baked = false) {
    const m = editMatrix(baked ? p.baked : p.edit, p.pivot, new THREE.Matrix4());
    return p.parent ? net(p.parent, baked).multiply(m) : m;
  }
  // Pfad des Originalteils, aus dessen Geometrie ein (Kopie-)Teil entsteht
  function originalPath(p) {
    for (let q = p; q; q = q.parent) if (q.copyOf) return q.copyOf + p.path.slice(q.path.length);
    return p.path;
  }

  // Eckpunkt-Listen erst bei Bedarf anlegen (im normalen Spiel ohne Aenderungen nie)
  let prepared = false;
  function prepare() {
    if (prepared) return;
    prepared = true;
    for (const m of meshes) {
      const g = m.geometry, ids = g.attributes._part.array;
      g.userData.basePos = g.attributes.position.array.slice();
      if (g.attributes.normal) g.userData.baseNrm = g.attributes.normal.array.slice();
      const lists = new Map();
      for (let i = 0; i < ids.length; i++) {
        const id = Math.round(ids[i]);
        if (!id) continue;
        if (!lists.has(id)) lists.set(id, []);
        lists.get(id).push(i);
      }
      for (const [id, idx] of lists) byId.get(id)?.verts.push({ mesh: m, idx, original: false });
    }
  }

  // Geometrie und Kollider eines Teils (ohne Kinder) an den aktuellen Stand anpassen.
  // Im GLB steckt schon die eingebackene Aenderung: Korrektur C = N(aktuell) * N(eingebacken)^-1;
  // Laufzeit-Kopien halten die Originalgeometrie: C = N(aktuell).
  const _c = new THREE.Matrix4(), _cl = new THREE.Matrix4(), _inv = new THREE.Matrix4(), _n3 = new THREE.Matrix3(), _box = new THREE.Box3();
  function applyOne(p) {
    const N = net(p), del = isDeleted(p);
    if (p.verts.some(e => !e.original)) _inv.copy(net(p, true)).invert();
    for (const { mesh, idx, original } of p.verts) {
      const g = mesh.geometry, pos = g.attributes.position, nrm = g.attributes.normal;
      _c.copy(N);
      if (!original) _c.multiply(_inv);
      _cl.copy(mesh.matrixWorld).invert().multiply(_c).multiply(mesh.matrixWorld);
      _n3.getNormalMatrix(_cl);
      const bp = g.userData.basePos, bn = g.userData.baseNrm;
      if (del) _v.fromArray(bp, idx[0] * 3).applyMatrix4(_cl); // geloescht: alle Eckpunkte auf einen Punkt (unsichtbar)
      for (const i of idx) {
        if (del) { _v.toArray(pos.array, i * 3); continue; }
        _v.fromArray(bp, i * 3).applyMatrix4(_cl).toArray(pos.array, i * 3);
        if (nrm) _v.fromArray(bn, i * 3).applyMatrix3(_n3).normalize().toArray(nrm.array, i * 3);
      }
      pos.needsUpdate = true;
      if (nrm) nrm.needsUpdate = true;
      g.boundingSphere = g.boundingBox = null; // werden fuer Raycast/Culling neu berechnet
    }
    for (const b of p.cols) {
      if (del) { Object.assign(b, { minX: FAR, maxX: FAR, minZ: FAR, maxZ: FAR }); continue; }
      const [x0, y0, z0, x1, y1, z1] = b.base;
      _box.makeEmpty();
      for (const x of [x0, x1]) for (const y of [y0, y1]) for (const z of [z0, z1]) _box.expandByPoint(_v.set(x, y, z).applyMatrix4(N));
      Object.assign(b, { minX: _box.min.x, maxX: _box.max.x, minZ: _box.min.z, maxZ: _box.max.z, maxY: _box.max.y });
    }
  }

  const listeners = new Set();
  function setEdit(p, edit) {
    const { copyOf, ...rest } = edit ?? {};
    edit = cleanEdit(rest);
    if (sameEdit(edit, p.edit)) return;
    p.edit = edit;
    prepare();
    for (const q of subtree(p)) applyOne(q);
    for (const f of listeners) f(p);
  }

  // Kopie anlegen, die noch nicht im GLB steckt: Originalgeometrie der Quelle (samt Kindern) in ein eigenes Mesh
  function createCopy(path, srcPath) {
    const src = byPath.get(srcPath);
    const parentPath = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : null;
    const parent = parentPath ? byPath.get(parentPath) : null;
    if (!src || src.derived || byPath.has(path) || (parentPath && !parent)) return null;
    prepare();
    const orig = subtree(src).filter(q => !q.derived);
    const map = new Map();
    for (const q of orig) {
      const c = add(newPart(nextId--, q === src ? parent?.id : map.get(q.parent).id, path + q.path.slice(src.path.length), q.pivot.clone(),
        { copyOf: q === src ? src.path : null, derived: true, runtime: true, baked: { deleted: true } }));
      map.set(q, c);
    }
    const byMesh = new Map();
    for (const q of orig) for (const { mesh, idx } of q.verts) {
      if (!byMesh.has(mesh)) byMesh.set(mesh, []);
      byMesh.get(mesh).push([q, idx]);
    }
    for (const [mesh, list] of byMesh) {
      const g = mesh.geometry, remap = new Map(), from = [], partOf = [];
      for (const [q, idx] of list) {
        const toOrig = new THREE.Matrix4().copy(mesh.matrixWorld).invert().multiply(net(q, true).invert()).multiply(mesh.matrixWorld);
        for (const i of idx) { remap.set(i, from.length); from.push(i); partOf.push([q, toOrig]); }
      }
      const ng = new THREE.BufferGeometry();
      for (const [name, a] of Object.entries(g.attributes)) {
        const arr = new a.array.constructor(from.length * a.itemSize);
        const data = name === 'position' ? g.userData.basePos : name === 'normal' ? g.userData.baseNrm : a.array;
        from.forEach((i, j) => {
          for (let k = 0; k < a.itemSize; k++) arr[j * a.itemSize + k] = data[i * a.itemSize + k];
          if (name === 'position') _v.fromArray(arr, j * 3).applyMatrix4(partOf[j][1]).toArray(arr, j * 3);
          if (name === 'normal') _v.fromArray(arr, j * 3).applyMatrix3(_n3.getNormalMatrix(partOf[j][1])).normalize().toArray(arr, j * 3);
          if (name === '_part') arr[j] = map.get(partOf[j][0]).id;
        });
        ng.setAttribute(name, new THREE.BufferAttribute(arr, a.itemSize, a.normalized));
      }
      const tri = [], index = g.index?.array;
      if (index) for (let t = 0; t < index.length; t += 3) if (remap.has(index[t])) tri.push(remap.get(index[t]), remap.get(index[t + 1]), remap.get(index[t + 2]));
      ng.setIndex(tri);
      ng.userData.basePos = ng.attributes.position.array.slice();
      if (ng.attributes.normal) ng.userData.baseNrm = ng.attributes.normal.array.slice();
      const cm = new THREE.Mesh(ng, mesh.material);
      cm.name = mesh.name + '+';
      cm.castShadow = mesh.castShadow;
      cm.receiveShadow = mesh.receiveShadow;
      cm.position.copy(mesh.position); cm.quaternion.copy(mesh.quaternion); cm.scale.copy(mesh.scale);
      mesh.parent.add(cm);
      cm.updateMatrixWorld(true);
      meshes.push(cm);
      const own = new Map();
      from.forEach((_, j) => {
        const c = map.get(partOf[j][0]);
        if (!own.has(c)) own.set(c, []);
        own.get(c).push(j);
      });
      for (const [c, idx] of own) c.verts.push({ mesh: cm, idx, original: true });
    }
    for (const q of orig) for (const b of q.cols) {
      const nb = { name: b.name + '+', part: map.get(q).path, base: b.base, minX: FAR, maxX: FAR, minZ: FAR, maxZ: FAR, maxY: b.maxY };
      boxes.push(nb);
      map.get(q).cols.push(nb);
    }
    for (const c of map.values()) applyOne(c);
    return map.get(src);
  }

  // edits.json-Form: Kopien stehen mit copyOf; geloeschte Kopien fallen samt ihrem Inhalt heraus
  function serialize(get) {
    const out = {};
    for (const p of [...byId.values()].sort((a, b) => a.path.localeCompare(b.path))) {
      if (chain(p).some(q => q.copyOf && get(q)?.deleted)) continue;
      const e = get(p);
      if (p.copyOf) out[p.path] = { copyOf: p.copyOf, ...(e ?? {}) };
      else if (e) out[p.path] = e;
    }
    return out;
  }

  return {
    byId, byPath, meshes,
    get list() { return [...byId.values()]; },
    onChange: f => listeners.add(f),
    setEdit, chain, isDeleted, originalPath,
    partAt(hit) { // Raycast-Treffer -> Teil
      const a = hit.object.geometry.attributes._part;
      return a && hit.face ? byId.get(Math.round(a.getX(hit.face.a))) ?? null : null;
    },
    worldPivot: p => p.pivot.clone().applyMatrix4(net(p)),
    toWorld: (p, v) => v.applyMatrix4(net(p)), // Punkt der Originalszene -> aktuelle Lage des Teils
    toOriginal: (p, v) => v.applyMatrix4(net(p).invert()), // aktuelle Lage -> Originalszene (Skript)
    worldRotY: p => rotY(p) * DEG,
    worldScale: scaleOf,
    // Teil so platzieren, dass sein Drehpunkt bei pos liegt, insgesamt um rot (rad) gedreht und um scale skaliert
    setWorld(p, pos, rot, scale = scaleOf(p)) {
      const parentN = p.parent ? net(p.parent) : new THREE.Matrix4();
      const W = new THREE.Matrix4().makeTranslation(pos.x, pos.y, pos.z).multiply(_r.makeRotationY(rot))
        .multiply(_s.makeScale(scale, scale, scale)).multiply(_t.makeTranslation(-p.pivot.x, -p.pivot.y, -p.pivot.z));
      const D = parentN.invert().multiply(W);
      const o = p.pivot.clone().applyMatrix4(D).sub(p.pivot);
      setEdit(p, { offset: o.toArray(), rotY: rot / DEG - (p.parent ? rotY(p.parent) : 0),
        scale: scale / (p.parent ? scaleOf(p.parent) : 1), deleted: p.edit?.deleted });
    },
    // Kopie eines Teils als Geschwister (Name+1, +2, ...); uebernimmt den Zustand der Kinder (verschobene/geloeschte Stuehle,
    // Kopien in der Kopie) und die Lage der Quelle
    duplicate(p) {
      const orig = originalPath(p);
      const base = (p.parent ? p.parent.path + '/' : '') + orig.split('/').pop();
      let k = 1;
      while (byPath.has(`${base}+${k}`)) k++;
      const top = createCopy(`${base}+${k}`, orig);
      if (!top) return null;
      for (const q of subtree(p).slice(1)) {
        const qp = top.path + q.path.slice(p.path.length);
        if (q.copyOf && !byPath.has(qp)) createCopy(qp, q.copyOf);
        const c = byPath.get(qp);
        if (c) setEdit(c, q.edit);
      }
      setEdit(top, { ...p.edit, deleted: false });
      return top;
    },
    // Weltbox der aktuellen Geometrie eines Teils samt Kindern (fuer die Auswahlanzeige)
    bounds(p, box = new THREE.Box3()) {
      prepare();
      box.makeEmpty();
      for (const q of subtree(p)) if (!isDeleted(q)) for (const { mesh, idx } of q.verts) {
        const pos = mesh.geometry.attributes.position;
        for (const i of idx) box.expandByPoint(_v.fromBufferAttribute(pos, i).applyMatrix4(mesh.matrixWorld));
      }
      return box;
    },
    // Stand aus edits.json uebernehmen (nur Abweichungen vom eingebackenen Stand kosten etwas)
    load(edits) {
      for (const [path, e] of Object.entries(edits).sort((a, b) => depth(a[0]) - depth(b[0])))
        if (e.copyOf && !e.deleted && !byPath.has(path) && !createCopy(path, e.copyOf)) console.warn('edits.json: Kopie nicht moeglich', path);
      for (const path of Object.keys(edits)) if (!byPath.has(path) && !edits[path].deleted) console.warn('edits.json: unbekanntes Teil', path);
      for (const p of [...byId.values()]) setEdit(p, edits[p.path] ?? (p.copyOf ? { deleted: true } : null));
    },
    toJSON: () => serialize(p => p.edit),
    pending: () => JSON.stringify(serialize(p => p.edit)) !== JSON.stringify(serialize(p => p.baked)), // noch nicht eingebacken
  };
}
