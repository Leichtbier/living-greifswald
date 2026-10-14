// Bearbeiten-Modus (Taste B oder ?edit): Bauteile anklicken, verschieben und drehen.
// Jede Aenderung wird ueber serve.py nach model/edits.json gespeichert; der naechste Blender-Build backt sie ein.
// Wird erst beim Einschalten geladen und kostet im normalen Spiel nichts.
import * as THREE from 'three';
import { TransformControls } from 'three/addons/controls/TransformControls.js';

const SAVE_URL = '../api/edits';

export function createEditor({ scene, camera, renderer, parts, panel }) {
  let active = false, sel = null;
  const handle = new THREE.Object3D();
  scene.add(handle);
  const controls = new TransformControls(camera, renderer.domElement);
  controls.setSpace('world');
  controls.setSize(0.9);
  const gizmo = controls.getHelper();
  scene.add(gizmo);
  controls.enabled = false;
  gizmo.visible = false;

  const box = new THREE.Box3();
  const boxHelper = new THREE.Box3Helper(box, 0xffb347);
  boxHelper.material.depthTest = false;
  boxHelper.renderOrder = 999;
  boxHelper.visible = false;
  scene.add(boxHelper);

  // ---------------------------------------------------------------- Anzeige
  let status = '', statusBad = false;
  const esc = s => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);
  function render() {
    const e = sel?.edit;
    const fmt = e ? `${(e.offset ?? [0, 0, 0]).map(v => v.toFixed(2)).join(' / ')} m · ${(e.rotY ?? 0).toFixed(1)}°` : 'unverändert';
    const n = Object.keys(parts.toJSON()).length;
    panel.innerHTML = `
      <h2>✏️ Bearbeiten <small>(B beendet)</small></h2>
      <div class="sel">${sel ? parts.chain(sel).map(p => esc(p.name)).join(' › ') : '<i>nichts ausgewählt</i>'}</div>
      ${sel ? `<div class="val">${fmt}</div>` : ''}
      <div class="row">Klick – auswählen, nochmal – eine Ebene tiefer, <kbd>Esc</kbd> – höher, <kbd>Tab</kbd> – nächstes daneben</div>
      <div class="row">Ausgewähltes ziehen – über den Boden schieben</div>
      <div class="row"><kbd>T</kbd> verschieben${controls.mode === 'translate' ? ' ✓' : ''} · <kbd>R</kbd> drehen${controls.mode === 'rotate' ? ' ✓' : ''} · <kbd>V</kbd> Höhe${height ? ' ✓' : ''}</div>
      <div class="row"><kbd>Shift</kbd> Raster (10 cm / 15°)</div>
      <div class="row"><kbd>Entf</kbd> zurücksetzen · <kbd>Strg</kbd>+<kbd>Z</kbd> rückgängig · <kbd>Strg</kbd>+<kbd>S</kbd> herunterladen</div>
      <div class="status${statusBad ? ' bad' : ''}">${esc(status || `${n} Teil${n === 1 ? '' : 'e'} geändert`)}${parts.pending() ? ' · noch nicht eingebacken' : ''}</div>`;
  }
  const setStatus = (s, bad = false) => { status = s; statusBad = bad; render(); };

  function syncHandle() {
    if (!sel) return;
    handle.position.copy(parts.worldPivot(sel));
    handle.quaternion.setFromAxisAngle(THREE.Object3D.DEFAULT_UP, parts.worldRotY(sel));
    parts.bounds(sel, box);
  }

  function select(p) {
    sel = p;
    if (p) { syncHandle(); controls.attach(handle); } else controls.detach();
    gizmo.visible = boxHelper.visible = active && !!p;
    render();
  }

  // Verschieben nur am Boden (Pfeile X/Z + Flaeche); V schaltet den Hoehenpfeil dazu. Drehen nur um die Hochachse.
  let height = false;
  function setMode(m) {
    controls.setMode(m);
    controls.showX = controls.showZ = m === 'translate';
    controls.showY = m === 'rotate' || height;
    render();
  }

  // ---------------------------------------------------------------- Speichern & Rueckgaengig
  const undo = [];
  let saveTimer = 0;
  function changed(p, before) {
    undo.push({ p, edit: before });
    if (undo.length > 200) undo.shift();
    scheduleSave();
  }
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 300);
    setStatus('speichere …');
  }
  async function save() {
    try {
      const r = await fetch(SAVE_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(parts.toJSON()) });
      if (!r.ok) throw new Error(r.status);
      setStatus('gespeichert in model/edits.json');
    } catch {
      setStatus('Speichern nicht möglich (läuft serve.py?) – Strg+S lädt edits.json herunter', true);
    }
  }
  function download() {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(parts.toJSON(), null, 2) + '\n'], { type: 'application/json' }));
    a.download = 'edits.json';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // ---------------------------------------------------------------- Ziehen
  let before = null;
  controls.addEventListener('mouseDown', () => { before = sel?.edit ?? null; });
  controls.addEventListener('objectChange', () => {
    if (!sel) return;
    const q = handle.quaternion;
    parts.setWorld(sel, handle.position, 2 * Math.atan2(q.y, q.w));
    parts.bounds(sel, box);
    render();
  });
  controls.addEventListener('mouseUp', () => {
    if (!sel) return;
    if (JSON.stringify(before) !== JSON.stringify(sel.edit)) changed(sel, before);
    syncHandle();
  });

  // ---------------------------------------------------------------- Auswahl per Klick, Ziehen am Objekt selbst
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  const canvas = renderer.domElement;
  function pickAt(e) {
    const r = canvas.getBoundingClientRect();
    ndc.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObjects(parts.meshes, false)[0];
    return hit ? { hit, part: parts.partAt(hit) } : null;
  }
  const groundAt = (e, y) => {
    pickAt(e); // setzt den Strahl
    const t = (y - ray.ray.origin.y) / ray.ray.direction.y;
    return t > 0 ? ray.ray.at(t, new THREE.Vector3()) : null;
  };
  let down = null, drag = null;
  canvas.addEventListener('pointerdown', e => {
    down = drag = null;
    if (!active || e.button !== 0 || controls.axis !== null) return; // Gizmo hat Vorrang
    down = { x: e.clientX, y: e.clientY };
    const h = sel && pickAt(e);
    if (h?.part && parts.chain(h.part).includes(sel)) { // ausgewaehltes Teil angefasst -> ueber den Boden ziehen
      drag = { y: h.hit.point.y, start: h.hit.point.clone(), pivot: parts.worldPivot(sel), rot: parts.worldRotY(sel), before: sel.edit, moved: false };
      canvas.setPointerCapture(e.pointerId);
    }
  });
  canvas.addEventListener('pointermove', e => {
    if (!drag || (!drag.moved && Math.hypot(e.clientX - down.x, e.clientY - down.y) < 5)) return;
    const pt = groundAt(e, drag.y);
    if (!pt) return;
    drag.moved = true;
    const d = pt.sub(drag.start).setY(0);
    if (e.shiftKey) d.set(Math.round(d.x * 10) / 10, 0, Math.round(d.z * 10) / 10);
    parts.setWorld(sel, drag.pivot.clone().add(d), drag.rot);
    syncHandle();
    render();
  });
  canvas.addEventListener('pointerup', e => {
    const d = down, g = drag;
    down = drag = null;
    if (g?.moved) {
      if (JSON.stringify(g.before) !== JSON.stringify(sel.edit)) changed(sel, g.before);
      return;
    }
    if (!d || !active || controls.dragging || Math.hypot(e.clientX - d.x, e.clientY - d.y) > 5) return;
    const p = pickAt(e)?.part;
    if (!p) return select(null);
    // erster Klick: oberste Ebene unter dem Objekt (z.B. Schirm-Gruppe), Klick in die Auswahl: eine Ebene tiefer
    const chain = parts.chain(p);
    const i = sel ? chain.indexOf(sel) : -1;
    select(chain[Math.min(i >= 0 ? i + 1 : 1, chain.length - 1)]);
  });

  // ---------------------------------------------------------------- Tasten
  addEventListener('keydown', e => {
    if (!active) return;
    if (e.key === 'Shift') {
      controls.setTranslationSnap(0.1);
      controls.setRotationSnap(15 * THREE.MathUtils.DEG2RAD);
    }
    const ctrl = e.ctrlKey || e.metaKey, key = e.key.toLowerCase(); // Buchstaben nach Belegung (QWERTZ: Strg+Z)
    if (ctrl && key === 's') { e.preventDefault(); download(); return; }
    if (ctrl && key === 'z') {
      e.preventDefault();
      const u = undo.pop();
      if (!u) return;
      parts.setEdit(u.p, u.edit);
      select(u.p);
      scheduleSave();
      return;
    }
    if (ctrl || e.altKey) return;
    if (key === 't') setMode('translate');
    if (key === 'r') setMode('rotate');
    if (key === 'v') { height = !height; setMode(controls.mode); }
    if (e.key === 'Escape' && sel) select(sel.parent);
    if (e.key === 'Tab' && sel?.parent) { // naechstes Teil derselben Ebene (z.B. Tisch unter dem Schirm)
      e.preventDefault();
      const sib = sel.parent.children, i = sib.indexOf(sel);
      select(sib[(i + (e.shiftKey ? sib.length - 1 : 1)) % sib.length]);
    }
    if ((e.key === 'Delete' || e.key === 'Backspace') && sel?.edit) {
      const b = sel.edit;
      parts.setEdit(sel, null);
      changed(sel, b);
      select(sel);
    }
  });
  addEventListener('keyup', e => {
    if (e.key === 'Shift') { controls.setTranslationSnap(null); controls.setRotationSnap(null); }
  });

  setMode('translate');

  return {
    get active() { return active; },
    get selected() { return sel; },
    toggle(on = !active) {
      active = on;
      controls.enabled = on;
      panel.hidden = !on;
      if (!on) controls.setTranslationSnap(null);
      select(on ? sel : null);
    },
    select,
  };
}
