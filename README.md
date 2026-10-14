# Living Greifswald

Gemütliche, stilisierte three.js-Szenen aus Greifswald zum Herumlaufen in der Draufsicht.
Erster Ort: der **Fischmarkt mit dem Fischerbrunnen**, mit frechen Silbermöwen.

## Starten
```
cd app
python serve.py 8080        # oder start.bat doppelklicken
```
Dann öffnet sich `http://localhost:8080/app/`. three.js wird vom CDN (jsdelivr) geladen.

Steuerung: WASD/Pfeile laufen, Shift rennen, Q/E oder rechte Maustaste ziehen = Kamera drehen, Mausrad = Zoom,
N = Tag/Abend, G = einer Möwe folgen, H = Hilfe.

## Aufbau
| Ordner | Inhalt |
|---|---|
| `app/` | Spiel: `index.html`, `main.js` (Szene, Figur, Kollision, Kamera), `seagulls.js` (Möwen-KI), `serve.py` |
| `app/tests/` | Playwright-Tests: `python app/tests/playwright_sim.py --out <ordner>` |
| `model/` | Exportierte Modelle (`*.glb`) und die Blender-Skripte, die sie erzeugen (siehe `model/README.md`) |

## Modelle neu bauen (Blender 5.1)
```
cd model
python make_textures.py
blender -b --factory-startup --python build_fischerbrunnen.py
blender -b --factory-startup --python build_seagull.py
```

## Tests
Benötigt `pip install playwright` und Microsoft Edge (wird über `channel="msedge"` genutzt, Rendering über die GPU).
Prüft Kollision, eine 300-s-Möwensimulation, Echtzeit-Spiel und Fluchtverhalten; Screenshots und `results.json` landen im `--out`-Ordner.
