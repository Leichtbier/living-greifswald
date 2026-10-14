// Bewegliche Bauteile der Szene (Props, Skulpturen), siehe model/build_fischerbrunnen.py ("Bauteile").
// Jedes Prop-Objekt traegt in den glTF-Extras eine Teil-Tabelle [id, elternId, pfad, drehpunkt, eingebackene Aenderung]
// und pro Eckpunkt das Attribut _part. Aenderungen (model/edits.json) verschieben/drehen ein Teil um seinen Drehpunkt;
// die Meshes bleiben zusammengefasst, es werden nur Eckpunkte umgeschrieben (keine zusaetzlichen Draw Calls).
import * as THREE from 'three';

const DEG = THREE.MathUtils.DEG2RAD;
const _r = new THREE.Matrix4(), _t = new THREE.Matrix4(), _v = new THREE.Vector3();

// Aenderung -> Matrix: T(drehpunkt + offset) * Ry(rotY) * T(-drehpunkt)
function editMatrix(e, pivot, out) {
  out.identity();
  if (!e) return out;
  const [x, y, z] = e.offset ?? [0, 0, 0];
  return out.makeTranslation(pivot.x + x, pivot.y + y, pivot.z + z)
    .multiply(_r.makeRotationY((e.rotY ?? 0) * DEG))
    .multiply(_t.makeTranslation(-pivot.x, -pivot.y, -pivot.z));
}

function cleanEdit(offset, rotY) {
  const o = offset.map(v => Math.round(v * 1000) / 1000 + 0);
  let r = Math.round((((rotY + 180) % 360 + 360) % 360 - 180) * 100) / 100 + 0;
  if (r === -180) r = 180;
  if (!o[0] && !o[1] && !o[2] && !r) return null;
  const e = {};
  if (o[0] || o[1] || o[2]) e.offset = o;
  if (r) e.rotY = r;
  return e;
}
const sameEdit = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

export function createParts(root, boxes) {
  const byId = new Map(), byPath = new Map();
  const meshes = []; // Meshes mit _part-Attribut (Auswahl per Raycast)
  root.updateMatrixWorld(true);
  root.traverse(o => {
    if (!o.userData.parts) return;
    for (const [id, parentId, path, pivot, e] of JSON.parse(o.userData.parts)) {
      const baked = e ? cleanEdit(e.offset ?? [0, 0, 0], e.rotY ?? 0) : null;
      const p = { id, parentId, path, name: path.split('/').pop(), pivot: new THREE.Vector3(...pivot), baked,
        edit: baked, parent: null, children: [], verts: [], cols: [] };
      byId.set(id, p); byPath.set(path, p);
    }
    o.traverse(m => { if (m.isMesh && m.geometry.attributes._part) meshes.push(m); });
  });
  for (const p of byId.values()) {
    p.parent = byId.get(p.parentId) ?? null;
    if (p.parent) p.parent.children.push(p);
  }
  for (const b of boxes) {
    const p = b.part && byPath.get(b.part);
    if (p && b.base) p.cols.push(b);
  }

  const local = (p, baked) => editMatrix(baked ? p.baked : p.edit, p.pivot, new THREE.Matrix4());
  // Gesamttransformation eines Teils (Originalgeometrie -> Welt): N = D(wurzel) * ... * D(teil)
  function net(p, baked = false) {
    const m = local(p, baked);
    return p.parent ? net(p.parent, baked).multiply(m) : m;
  }
  const subtree = p => [p, ...p.children.flatMap(subtree)];
  const rotY = p => ((p.edit?.rotY ?? 0) + (p.parent ? rotY(p.parent) : 0)); // Drehungen um Y addieren sich

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
      for (const [id, idx] of lists) byId.get(id)?.verts.push({ mesh: m, idx });
    }
  }

  // Geometrie und Kollider eines Teils (ohne Kinder) an den aktuellen Stand anpassen.
  // Im GLB steckt schon die eingebackene Aenderung, daher Korrektur C = N(aktuell) * N(eingebacken)^-1.
  const _c = new THREE.Matrix4(), _cl = new THREE.Matrix4(), _n3 = new THREE.Matrix3(), _box = new THREE.Box3();
  function applyOne(p) {
    const N = net(p);
    _c.copy(N).multiply(net(p, true).invert());
    for (const { mesh, idx } of p.verts) {
      const g = mesh.geometry, pos = g.attributes.position, nrm = g.attributes.normal;
      _cl.copy(mesh.matrixWorld).invert().multiply(_c).multiply(mesh.matrixWorld);
      _n3.getNormalMatrix(_cl);
      const bp = g.userData.basePos, bn = g.userData.baseNrm;
      for (const i of idx) {
        _v.fromArray(bp, i * 3).applyMatrix4(_cl).toArray(pos.array, i * 3);
        if (nrm) _v.fromArray(bn, i * 3).applyMatrix3(_n3).normalize().toArray(nrm.array, i * 3);
      }
      pos.needsUpdate = true;
      if (nrm) nrm.needsUpdate = true;
      g.boundingSphere = g.boundingBox = null; // werden fuer Raycast/Culling neu berechnet
    }
    for (const b of p.cols) {
      const [x0, y0, z0, x1, y1, z1] = b.base;
      _box.makeEmpty();
      for (const x of [x0, x1]) for (const y of [y0, y1]) for (const z of [z0, z1]) _box.expandByPoint(_v.set(x, y, z).applyMatrix4(N));
      Object.assign(b, { minX: _box.min.x, maxX: _box.max.x, minZ: _box.min.z, maxZ: _box.max.z, maxY: _box.max.y });
    }
  }

  const listeners = new Set();
  function setEdit(p, edit) {
    edit = edit ? cleanEdit(edit.offset ?? [0, 0, 0], edit.rotY ?? 0) : null;
    if (sameEdit(edit, p.edit)) return;
    p.edit = edit;
    prepare();
    for (const q of subtree(p)) applyOne(q);
    for (const f of listeners) f(p);
  }

  return {
    byId, byPath, meshes,
    get list() { return [...byId.values()]; },
    onChange: f => listeners.add(f),
    setEdit,
    chain(p) { const c = []; for (let q = p; q; q = q.parent) c.unshift(q); return c; },
    partAt(hit) { // Raycast-Treffer -> Teil
      const a = hit.object.geometry.attributes._part;
      return a && hit.face ? byId.get(Math.round(a.getX(hit.face.a))) ?? null : null;
    },
    worldPivot: p => p.pivot.clone().applyMatrix4(net(p)),
    toWorld: (p, v) => v.applyMatrix4(net(p)), // Punkt der Originalszene -> aktuelle Lage des Teils
    worldRotY: p => rotY(p) * DEG,
    // Teil so platzieren, dass sein Drehpunkt bei pos liegt und es insgesamt um rot (rad) um Y gedreht ist
    setWorld(p, pos, rot) {
      const parentN = p.parent ? net(p.parent) : new THREE.Matrix4();
      const W = new THREE.Matrix4().makeTranslation(pos.x, pos.y, pos.z).multiply(_r.makeRotationY(rot))
        .multiply(_t.makeTranslation(-p.pivot.x, -p.pivot.y, -p.pivot.z));
      const D = parentN.invert().multiply(W);
      const o = p.pivot.clone().applyMatrix4(D).sub(p.pivot);
      setEdit(p, { offset: o.toArray(), rotY: rot / DEG - (p.parent ? rotY(p.parent) : 0) });
    },
    // Weltbox der aktuellen Geometrie eines Teils samt Kindern (fuer die Auswahlanzeige)
    bounds(p, box = new THREE.Box3()) {
      prepare();
      box.makeEmpty();
      for (const q of subtree(p)) for (const { mesh, idx } of q.verts) {
        const pos = mesh.geometry.attributes.position;
        for (const i of idx) box.expandByPoint(_v.fromBufferAttribute(pos, i).applyMatrix4(mesh.matrixWorld));
      }
      return box;
    },
    // Stand aus edits.json uebernehmen (nur Abweichungen vom eingebackenen Stand kosten etwas)
    load(edits) {
      for (const path of Object.keys(edits)) if (!byPath.has(path)) console.warn('edits.json: unbekanntes Teil', path);
      for (const p of byId.values()) setEdit(p, edits[p.path] ?? null);
    },
    toJSON() {
      const out = {};
      for (const p of [...byId.values()].sort((a, b) => a.path.localeCompare(b.path))) if (p.edit) out[p.path] = p.edit;
      return out;
    },
    pending: () => [...byId.values()].some(p => !sameEdit(p.edit, p.baked)), // Aenderungen, die noch nicht im GLB stecken
  };
}
