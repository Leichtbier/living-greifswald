"""
Browser-Simulationen / Tests der Fischmarkt-App mit Playwright.

Aufruf (Python mit `pip install playwright`, nutzt das installierte Microsoft Edge):
  python app/tests/playwright_sim.py [--out <ordner>] [--only selftest,gullsim,gallery,play,chase]

Startet selbst einen lokalen Server, oeffnet die App headless (WebGL ueber SwiftShader) und
  selftest  - Kollisionstest der Spielfigur (?selftest)
  gullsim   - Moewen-KI mit festem Zeitschritt, 300 s (?gullsim=300&chase)
  gallery   - Screenshot aller Moewen-Animationen (?gallery)
  play      - Echtzeit: Spiel laeuft 20 s, Figur steht -> Moewen kommen frech naeher; Screenshots
  chase     - Echtzeit: Figur rennt per Tastatur auf eine Bodenmoewe zu -> sie muss fliehen
Konsolenfehler der Seite lassen den Lauf fehlschlagen. Exit-Code 0 = alles ok.
"""
import argparse, functools, http.server, json, os, sys, threading, time
from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GPU_ARGS = ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"]          # echte Grafikkarte (~60 fps)
SOFT_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]  # Notfall: Software


def serve():
    class H(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".glb": "model/gltf-binary"}

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=ROOT))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/app/"


def launch(pw, soft=False):
    """Installiertes Edge (kein Browser-Download noetig), sonst Playwright-Chromium."""
    args = SOFT_ARGS if soft else GPU_ARGS
    try:
        return pw.chromium.launch(channel="msedge", args=args)
    except Exception:
        return pw.chromium.launch(args=args)


def renderer_name(browser):
    pg = browser.new_page()
    r = pg.evaluate("(() => { const c = document.createElement('canvas').getContext('webgl2'); const e = c && c.getExtension('WEBGL_debug_renderer_info'); return e ? c.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'unbekannt'; })()")
    pg.close()
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "app", "tests", "out"))
    ap.add_argument("--only", default="selftest,gullsim,gallery,play,chase")
    ap.add_argument("--soft", action="store_true", help="SwiftShader statt GPU (sehr langsam)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    only = set(a.only.split(","))
    srv, base = serve()
    results, ok = {}, True

    with sync_playwright() as pw:
        browser = launch(pw, a.soft)
        print('WebGL:', renderer_name(browser))

        def page_for(query, wait_sel=None):
            page = browser.new_page(viewport={"width": 1400, "height": 850})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: m.type == "error" and "favicon" not in (m.location or {}).get("url", "") and errors.append(m.text))
            page.goto(base + query)
            page.wait_for_function("document.getElementById('loading')?.classList.contains('done')", timeout=120_000)
            if wait_sel:
                page.wait_for_selector(wait_sel, state="attached", timeout=120_000)
            return page, errors

        def finish(name, page, errors, data, passed):
            nonlocal ok
            passed = passed and not errors
            ok &= passed
            results[name] = {"ok": passed, "errors": errors, **data}
            print(f"[{'OK' if passed else 'FEHLER'}] {name}: {json.dumps(data, ensure_ascii=False)[:600]}")
            for e in errors:
                print("   Konsole:", e)
            page.close()

        if "selftest" in only:
            page, err = page_for("?selftest", "#selftest")
            r = json.loads(page.text_content("#selftest"))
            exp = {"northToFountain": (1, 3.95), "westToVeroModa": (0, -17.25), "eastToRathaus": (0, 13.85),
                   "southToKeimblatt": (1, 33.65), "intoLamp": (1, -0.45)}
            good = all(abs(r[k][i] - v) < 0.1 for k, (i, v) in exp.items()) and r["streetEastAlongRathaus"][0] > 24
            finish("selftest", page, err, r, good)

        if "gullsim" in only:
            page, err = page_for("?gullsim=300&chase", "#gullsim")
            r = json.loads(page.text_content("#gullsim"))
            states = set(r["seen"])
            need = {"water:swim", "ground:walk", "rim:rimwalk", "ground:hop", "water:hop", "rim:hop", "air:fly", "air:land",
                    "ground:peck", "ground:squawk", "perch:idle"}
            finish("gullsim", page, err, {"nBad": r["nBad"], "maxY": r["maxY"], "fehlend": sorted(need - states)},
                   r["nBad"] == 0 and need <= states)

        if "gallery" in only:
            page, err = page_for("?gallery")
            page.wait_for_timeout(2500)
            page.screenshot(path=os.path.join(a.out, "gallery.png"))
            finish("gallery", page, err, {"screenshot": "gallery.png"}, True)

        if "play" in only:
            page, err = page_for("")
            snap = "window.__game.seagulls.gulls.map(g => ({s: g.surface, st: g.state, p: g.pos.toArray()}))"
            page.wait_for_timeout(1000)
            t0 = page.evaluate(snap)
            page.screenshot(path=os.path.join(a.out, "play_0s.png"))
            page.wait_for_timeout(20000)
            t1 = page.evaluate(snap)
            page.screenshot(path=os.path.join(a.out, "play_20s.png"))
            pp = page.evaluate("window.__game.player.position.toArray()")
            moved = sum(1 for x, y in zip(t0, t1) if sum((p - q) ** 2 for p, q in zip(x["p"], y["p"])) > 0.25)
            near = sum(1 for g in t1 if g["s"] != "air" and ((g["p"][0] - pp[0]) ** 2 + (g["p"][2] - pp[2]) ** 2) ** 0.5 < 4)
            page.evaluate("window.__game.setFollow(8)")
            page.wait_for_timeout(2500)
            page.screenshot(path=os.path.join(a.out, "play_follow.png"))
            fps = page.evaluate("new Promise(r => { let n = 0; const t = performance.now(); (function f(){ n++; performance.now() - t < 2000 ? requestAnimationFrame(f) : r(n / 2); })(); })")
            finish("play", page, err, {"bewegt": moved, "nahBeiFigur": near, "fps": fps,
                                       "zustaende": sorted({g['s'] + ':' + g['st'] for g in t1})}, moved >= 3)

        if "chase" in only:
            page, err = page_for("")
            page.wait_for_timeout(1500)
            # naechste Bodenmoewe suchen, Figur daneben setzen und mit Shift+Pfeil auf sie zurennen
            info = page.evaluate("""() => {
              const G = window.__game, gs = G.seagulls.gulls.filter(g => g.surface === 'ground');
              if (!gs.length) return null;
              const g = gs[0];
              G.player.position.set(g.pos.x, 0, g.pos.z + 5);
              G.cam.yaw = G.cam.yawT = 0;           // Kamera schaut nach Norden: Pfeil hoch = -Z
              return { id: g.id, before: g.surface + ':' + g.state };
            }""")
            if info is None:
                finish("chase", page, err, {"hinweis": "keine Bodenmoewe"}, True)
            else:
                page.keyboard.down("ShiftLeft")
                page.keyboard.down("ArrowUp")
                page.wait_for_timeout(1200)
                page.keyboard.up("ArrowUp")
                page.keyboard.up("ShiftLeft")
                page.screenshot(path=os.path.join(a.out, "chase.png"))
                after = page.evaluate(f"(() => {{ const g = window.__game.seagulls.gulls[{info['id']}]; return g.surface + ':' + g.state; }})()")
                fled = after.startswith("air") or after.endswith("hop")
                finish("chase", page, err, {**info, "after": after}, fled)

        browser.close()
    srv.shutdown()
    with open(os.path.join(a.out, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("ALLES OK" if ok else "FEHLER GEFUNDEN", "->", a.out)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
