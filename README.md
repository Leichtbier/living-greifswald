# Living Greifswald

Gemütliche, stilisierte three.js-Szenen aus Greifswald zum Herumlaufen in der Draufsicht.
Erster Ort: der **Fischmarkt mit dem Fischerbrunnen**, mit frechen Silbermöwen.

**Online spielen:** https://leichtbier.github.io/living-greifswald/
(GitHub Pages, Quelle: Branch `main`, Ordner `/`; `index.html` leitet nach `app/` weiter.)

## Starten
`app\start.bat` doppelklicken – öffnet `http://localhost:8080/app/` im Browser. Das Skript nimmt das erste Python, das wirklich läuft:
1. Umgebungsvariable `PYTHON` (z. B. `set PYTHON=%USERPROFILE%\.conda\envs\claude-code-env\python.exe`)
2. die conda-Umgebung `%USERPROFILE%\.conda\envs\claude-code-env`, falls vorhanden
3. `python` aus dem PATH (der Microsoft-Store-Platzhalter wird übersprungen)
4. der `py`-Launcher

Oder von Hand: `cd app` und `python serve.py 8080` (Python ≥ 3.7, nur Standardbibliothek; `--no-browser` unterdrückt den Browser).
three.js wird vom CDN (jsdelivr) geladen.

Steuerung: WASD/Pfeile laufen, Shift rennen, Q/E oder rechte Maustaste ziehen = Kamera drehen, Mausrad = Zoom,
N = Tag/Abend, G = einer Möwe folgen, H = Hilfe, B = Bearbeiten-Modus (siehe unten).

## Umgebung bearbeiten (B)
Im Bearbeiten-Modus (Taste `B` oder `?edit`) lassen sich Tische, Stühle, Schirme, Bänke, Laternen, Fahrräder, Autos,
Kübel, Mülleimer, Poller und die Skulpturen auswählen, verschieben, drehen, skalieren, kopieren und löschen:
- Klick wählt die oberste Ebene (z. B. Schirm mit seinen Tischen), ein weiterer Klick geht tiefer (Tisch → Stuhl),
  `Esc` eine Ebene höher, `Tab` zum nächsten Teil derselben Ebene (z. B. der Tisch unter dem Schirm).
- Ausgewähltes Teil mit der Maus über den Boden ziehen oder das Gizmo benutzen: `T` verschieben, `R` drehen, `V` Höhe;
  `Shift` rastet ein (10 cm / 15°). `+`/`-` (10 %) oder `Alt`+Mausrad (fein) ändern die Größe.
- `Strg+D` legt eine Kopie daneben, `Strg+C` und dann `Strg+V` fügt eine Kopie an der Mausposition ein.
- `Entf` löscht, `Pos1` setzt Lage, Drehung und Größe zurück, `Strg+Z` macht rückgängig.
- `Alt`+Klick auf eine beliebige Fläche setzt eine **Anmerkung für Claude** (Text, Stelle, Screenshot) → `model/annotations.json`.
  Beim nächsten Einbacken setzt Claude offene Anmerkungen um und markiert sie grün mit einer Antwort (Klick auf den Punkt).
- Jede Änderung speichert `serve.py` sofort in `model/edits.json`. Ohne lokalen Server (z. B. GitHub Pages) lädt `Strg+S` die Datei herunter.
- Die App wendet `edits.json` beim Laden an, auch wenn noch nicht neu gebaut wurde. Dauerhaft in die Modelle
  (inkl. Kollidern) kommt alles mit dem nächsten Blender-Build, siehe `model/README.md`.

## Aufbau
| Ordner | Inhalt |
|---|---|
| `app/` | Spiel: `index.html`, `main.js` (Szene, Figur, Kollision, Kamera), `seagulls.js` (Möwen-KI), `parts.js`/`editor.js` (Bearbeiten-Modus), `serve.py` |
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
