// Anmerkungen fuer Claude im Bearbeiten-Modus: Alt+Klick setzt einen Punkt auf die angeklickte Flaeche und fragt nach
// einem Text. Gespeichert wird ueber serve.py in model/annotations.json (+ Screenshot in model/annotations/<id>.jpg);
// beim naechsten Einbacken arbeitet Claude die offenen Anmerkungen ab und markiert sie als erledigt (mit Antwort);
// erledigte bleiben bis zum darauffolgenden Einbacken sichtbar und werden dann geloescht (Build-Skript).
// Klick auf einen Punkt zeigt/aendert/loescht ihn.
// Damit die Stelle eindeutig im Build-Skript zu finden ist, steht im Eintrag: Objekt, Bauteil (bei Kopien auch das
// Original), Material und Seite der Flaeche, Punkt in Welt- und in Skript-Koordinaten (Blender: x = Ost, y = Nord,
// z = oben; Lage vor allen Aenderungen aus edits.json, also wie im Skript), Kameraposition und Screenshot.
import * as THREE from 'three';

const URL_FILE = '../model/annotations.json';
const URL_SAVE = '../api/annotations';
const COLORS = { offen: 0xff7a2f, erledigt: 0x3fbf6a };
const r3 = v => v.toArray().map(x => Math.round(x * 1000) / 1000 + 0);

export async function createAnnotations({ scene, camera, renderer, world, parts, isActive, setStatus, snapshot }) {
  let list = await fetch(URL_FILE).then(r => r.ok ? r.json() : []).catch(() => []);
  if (!Array.isArray(list)) list = [];

  // ---------------------------------------------------------------- Punkte in der Szene (nur im Bearbeiten-Modus)
  const group = new THREE.Group();
  group.visible = false;
  scene.add(group);
  const ball = new THREE.SphereGeometry(0.13, 12, 8);
  const mats = Object.fromEntries(Object.entries(COLORS).map(([k, c]) => [k, new THREE.MeshBasicMaterial({ color: c, depthTest: false })]));
  const lineMat = new THREE.LineBasicMaterial({ color: 0x3a2c2a, depthTest: false });
  function rebuild() {
    group.clear();
    for (const a of list) {
      const p = new THREE.Vector3(...a.pos), n = new THREE.Vector3(...(a.normal ?? [0, 1, 0]));
      const top = p.clone().addScaledVector(n, 0.45);
      const m = new THREE.Mesh(ball, mats[a.status] ?? mats.offen);
      m.position.copy(top);
      m.renderOrder = 998;
      m.userData.note = a;
      const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints([p, top]), lineMat);
      l.renderOrder = 997;
      group.add(m, l);
    }
  }
  rebuild();

  async function save() {
    try {
      const r = await fetch(URL_SAVE, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(list) });
      if (!r.ok) throw new Error(r.status);
      setStatus('Anmerkung gespeichert in model/annotations.json');
    } catch {
      setStatus('Anmerkung nicht gespeichert (läuft serve.py?)', true);
    }
  }

  // ---------------------------------------------------------------- Eingabefenster
  const pop = document.createElement('div');
  pop.id = 'notePopup';
  pop.hidden = true;
  document.body.appendChild(pop);
  let current = null, isNew = false;
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  function open(a, x, y, fresh) {
    current = a;
    isNew = fresh;
    pop.innerHTML = `
      <div class="head">💬 Anmerkung für Claude <small>${esc(a.target)}</small></div>
      <textarea rows="4" placeholder="Was soll hier passieren? (Strg+Enter speichert, Esc schließt)">${esc(a.text)}</textarea>
      ${a.reply ? `<div class="reply"><b>Claude:</b> ${esc(a.reply)}</div>` : ''}
      <div class="btns">
        ${fresh ? '' : `<label><input type="checkbox" ${a.status === 'erledigt' ? 'checked' : ''}> erledigt</label><button data-act="del">Löschen</button>`}
        <button data-act="cancel">Abbrechen</button><button data-act="ok" class="ok">Speichern</button>
      </div>`;
    pop.hidden = false;
    const w = pop.offsetWidth, h = pop.offsetHeight;
    pop.style.left = Math.max(8, Math.min(x + 12, innerWidth - w - 8)) + 'px';
    pop.style.top = Math.max(8, Math.min(y + 12, innerHeight - h - 8)) + 'px';
    pop.querySelector('textarea').focus();
  }
  function close() { pop.hidden = true; current = null; }
  function commit() {
    const text = pop.querySelector('textarea').value.trim();
    const done = pop.querySelector('input[type=checkbox]')?.checked;
    if (!text) return isNew ? close() : remove();
    current.text = text;
    if (done !== undefined) current.status = done ? 'erledigt' : 'offen';
    if (!done) delete current.baked; // wieder offen: erst nach dem naechsten Erledigen loeschen
    if (isNew) {
      const img = current._img;
      delete current._img;
      list.push(current);
      if (img) uploadShot(current.id, img);
    }
    close(); rebuild(); save();
  }
  function remove() {
    list = list.filter(a => a !== current);
    close(); rebuild(); save();
  }
  pop.addEventListener('click', e => {
    const act = e.target.dataset?.act;
    if (act === 'ok') commit();
    if (act === 'cancel') close();
    if (act === 'del') remove();
  });
  pop.addEventListener('keydown', e => {
    e.stopPropagation(); // Tippen steuert weder Figur noch Editor
    if (e.key === 'Escape') close();
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) commit();
  });
  pop.addEventListener('pointerdown', e => e.stopPropagation());

  // ---------------------------------------------------------------- Klicks (vor Editor und Gizmo abfangen)
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2(), canvas = renderer.domElement;
  function aim(e) {
    const r = canvas.getBoundingClientRect();
    ndc.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
    ray.setFromCamera(ndc, camera);
  }
  const side = n => n.y > 0.7 ? 'oben' : n.y < -0.7 ? 'unten'
    : Math.abs(n.x) > Math.abs(n.z) ? (n.x > 0 ? 'Ost' : 'West') : (n.z < 0 ? 'Nord' : 'Süd');
  const solid = h => [h.object.material].flat().every(m => !(m.transparent && m.opacity < 0.5)); // ausgeblendete Gebaeude durchklicken
  function objectName(hit) {
    let o = hit.object;
    while (o.parent && o.parent !== world) o = o.parent;
    return o.name || hit.object.name || 'Szene';
  }
  async function uploadShot(id, dataUrl) {
    try {
      const r = await fetch(`${URL_SAVE}/shot?id=${id}`, { method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body: await (await fetch(dataUrl)).blob() });
      if (!r.ok) throw new Error(r.status);
    } catch { setStatus('Screenshot nicht gespeichert (läuft serve.py?)', true); }
  }
  addEventListener('pointerdown', e => {
    if (!isActive() || e.button !== 0 || e.target !== canvas) return;
    aim(e);
    const mark = ray.intersectObjects(group.children.filter(o => o.isMesh), false)[0];
    if (!mark && !e.altKey) return;
    e.stopPropagation();
    e.preventDefault();
    if (mark) return open(mark.object.userData.note, e.clientX, e.clientY, false);
    const hit = ray.intersectObject(world, true).find(h => h.object.isMesh && h.face && solid(h));
    if (!hit) return;
    const n = hit.face.normal.clone().transformDirection(hit.object.matrixWorld);
    if (n.dot(ray.ray.direction) > 0) n.negate();
    const p = parts.partAt(hit);
    const orig = p ? parts.toOriginal(p, hit.point.clone()) : hit.point.clone(); // Lage wie im Skript (vor edits.json)
    const object = objectName(hit);
    const a = {
      id: 'a' + Date.now().toString(36), status: 'offen', created: new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16).replace('T', ' '),
      target: p ? p.path : object, object, part: p?.path ?? null, source: p && parts.originalPath(p) !== p.path ? parts.originalPath(p) : null,
      material: [hit.object.material].flat()[0]?.name ?? null, side: side(n),
      pos: r3(hit.point), normal: r3(n), scriptPos: r3(new THREE.Vector3(orig.x, -orig.z, orig.y)),
      view: r3(camera.position), shot: null, text: '',
    };
    if (snapshot) { // Bild der Ansicht mit Klickstelle (relativ 0..1)
      const r = canvas.getBoundingClientRect();
      a.shot = { file: `annotations/${a.id}.jpg`, x: +((e.clientX - r.left) / r.width).toFixed(3), y: +((e.clientY - r.top) / r.height).toFixed(3) };
      a._img = snapshot(a.shot.x, a.shot.y);
    }
    open(a, e.clientX, e.clientY, true);
  }, true);

  return {
    setVisible(on) { group.visible = on; if (!on) close(); },
    get openCount() { return list.filter(a => a.status !== 'erledigt').length; },
    get list() { return list; },
  };
}
