// Steuerung für Tablet und Smartphone (nach dem Vorbild von core-business/src/touch.js):
// Steuerkreuz unten rechts zum Laufen, darüber Knöpfe für Tag/Abend, Möwe folgen und Hilfe.
// Ein Finger auf der Szene dreht die Kamera, zwei Finger zoomen (auseinander/zusammen ziehen).
// Sichtbar ist das alles nur im Touch-Modus (Klasse "touch" am <body>): an, sobald ein Finger den Bildschirm
// berührt (oder das Gerät nur Touch kennt), aus bei der ersten Taste auf einer Tastatur. ?touch erzwingt ihn.
//
// Steuerkreuz: analog. Der Ausschlag gibt Richtung (relativ zur Kamera, wie WASD) und Tempo vor; zieht der
// Finger über den Rand des Kreises hinaus, rennt die Figur (wie mit Shift). Der Finger darf den Kreis
// verlassen, die Richtung gilt weiter, bis er losgelassen wird.

const DEAD = 0.18; // Ruhezone, Anteil am Radius
const FULL = 0.8; // ab hier volles Lauftempo
const RUN = 1.12; // ab hier (Finger außerhalb des Kreises) rennen

const $ = (id) => document.getElementById(id);

// Tempo 0..1 aus dem Ausschlag (Anteil am Radius, darf über 1 liegen)
export function amount(len) {
  const t = (len - DEAD) / (FULL - DEAD);
  return t <= 0 ? 0 : t >= 1 ? 1 : t;
}

// canvas: Fläche für Kameragesten; rotate(dx, dy): Kamera drehen (Pixel wie Mausziehen); zoom(f): Abstand mal f;
// actions: { evening, follow, help } für die Knöpfe.
// Liefert stick: { x, y, amount, run } (x nach rechts, y nach vorn, Länge 1) – vor jedem Schritt auslesen
export function setupTouch({ canvas, rotate, zoom, actions, force = false }) {
  const body = document.body;
  const setTouch = (on) => body.classList.toggle('touch', on);
  setTouch(force || matchMedia('(hover: none) and (pointer: coarse)').matches);
  window.addEventListener('pointerdown', (e) => { if (e.pointerType === 'touch') setTouch(true); }, true);
  window.addEventListener('keydown', () => { if (!force) setTouch(false); }, true);

  const stick = { x: 0, y: 0, amount: 0, run: false };

  // ---------------------------------------------------------------- Steuerkreuz
  const pad = $('touchPad'), knob = $('touchKnob');
  const DIRS = ['up', 'down', 'left', 'right'];
  const arrows = Object.fromEntries(DIRS.map((k) => [k, pad.querySelector('.' + k)]));
  let finger = null;

  const show = () => {
    const on = { up: stick.y > 0.38, down: stick.y < -0.38, left: stick.x < -0.38, right: stick.x > 0.38 };
    for (const k of DIRS) {
      const lit = stick.amount > 0 && on[k];
      arrows[k].classList.toggle('on', lit);
      arrows[k].style.fillOpacity = lit ? 0.4 + 0.6 * stick.amount : '';
    }
    pad.classList.toggle('run', stick.run);
  };
  const release = () => {
    finger = null;
    knob.style.transform = '';
    pad.classList.remove('held');
    Object.assign(stick, { x: 0, y: 0, amount: 0, run: false });
    show();
  };
  const track = (e) => {
    const r = pad.getBoundingClientRect(), rad = r.width / 2;
    const x = (e.clientX - r.left - rad) / rad, y = (e.clientY - r.top - rad) / rad;
    const len = Math.hypot(x, y);
    // Knopf folgt dem Finger, bleibt aber im Kreis
    const k = len > 0.62 ? 0.62 / len : 1;
    knob.style.transform = `translate(${x * k * rad}px, ${y * k * rad}px)`;
    const a = amount(len);
    Object.assign(stick, a > 0 ? { x: x / len, y: -y / len, amount: a, run: len > RUN } : { x: 0, y: 0, amount: 0, run: false });
    show();
  };

  pad.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    if (finger !== null) return;
    finger = e.pointerId;
    try { pad.setPointerCapture(e.pointerId); } catch { /* künstliche Ereignisse (Tests) */ }
    pad.classList.add('held');
    track(e);
  });
  pad.addEventListener('pointermove', (e) => { if (e.pointerId === finger) track(e); });
  for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    pad.addEventListener(type, (e) => { if (e.pointerId === finger) release(); });
  }

  // ---------------------------------------------------------------- Kameragesten auf der Szene
  // Ein Finger: drehen; zwei Finger: Abstand der Finger steuert den Zoom (Mittelpunkt dreht weiter)
  const touches = new Map(); // pointerId -> { x, y }
  let pinch = 0;
  const spread = () => { const [a, b] = [...touches.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };
  const center = () => {
    let x = 0, y = 0;
    for (const p of touches.values()) { x += p.x; y += p.y; }
    return { x: x / touches.size, y: y / touches.size };
  };
  canvas.addEventListener('pointerdown', (e) => {
    if (e.pointerType !== 'touch') return;
    e.preventDefault();
    touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
    try { canvas.setPointerCapture(e.pointerId); } catch { /* künstliche Ereignisse (Tests) */ }
    if (touches.size === 2) pinch = spread();
  });
  canvas.addEventListener('pointermove', (e) => {
    const p = touches.get(e.pointerId);
    if (!p) return;
    const before = center();
    p.x = e.clientX; p.y = e.clientY;
    if (touches.size > 2) return;
    const after = center();
    rotate(after.x - before.x, after.y - before.y);
    if (touches.size === 2) {
      const d = spread();
      if (pinch > 10 && d > 10) zoom(pinch / d);
      pinch = d;
    }
  });
  const lift = (e) => {
    if (!touches.delete(e.pointerId)) return;
    if (touches.size === 2) pinch = spread();
  };
  for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) canvas.addEventListener(type, lift);

  // ---------------------------------------------------------------- Knöpfe
  for (const [id, fn] of [['touchEvening', actions.evening], ['touchFollow', actions.follow], ['touchHelp', actions.help]]) {
    $(id).addEventListener('click', (e) => { e.currentTarget.blur(); fn(); });
  }

  return stick;
}
