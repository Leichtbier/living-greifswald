---
name: einbacken
description: Änderungen aus dem Bearbeiten-Modus in die Fischmarkt-Modelle einbacken – offene Anmerkungen (model/annotations.json) umsetzen, @-Verweise auf screenshots/ auflösen, mit Blender neu bauen, prüfen, committen. Verwenden, wenn der Nutzer „einbacken“ sagt.
---

# Einbacken

## 1. Eingaben einsammeln
- `git status` und `git diff model/edits.json`: Der Nutzer arbeitet oft parallel im Editor (`serve.py` auf 8080) und
  schreibt `model/edits.json` und `model/annotations.json` – immer den aktuellen Dateistand lesen, nichts überschreiben.
- **Offene Anmerkungen** (`"status": "offen"`) in `model/annotations.json`:
  - Fundstelle: `object` (Blender-Objekt), `part` (Bauteil-Pfad, bei Kopien `source` = Original), `material` und `side`
    der angeklickten Fläche, `scriptPos` = Punkt in Skript-Koordinaten (Blender: x = Ost, y = Nord, z = oben; Lage vor
    `edits.json`, direkt mit den Zahlen in `build_fischerbrunnen.py` vergleichbar), `pos`/`normal` in three.js-Welt,
    `view` = Kameraposition.
  - Screenshot mit rotem Ring um die Klickstelle: `model/annotations/<id>.jpg` – **immer ansehen**.
- **`@`-Verweise:** Steht im Text einer Anmerkung (oder in der Nachricht des Nutzers) ein Dateiname mit `@` davor,
  z. B. `@fassade.png` oder `@rathaus_alt`, ist eine Datei im Ordner `screenshots/` im Projektwurzelverzeichnis gemeint
  (vom Nutzer angelegt, per `.gitignore` nicht im Repo).
  - Auflösen: erst exakt `screenshots/<name>`, sonst Dateien, die mit `<name>` beginnen (Endung fehlt oft);
    Groß/Kleinschreibung ignorieren. Mehrdeutig oder nicht gefunden → beim Nutzer nachfragen.
  - Bilder mit dem Read-Werkzeug ansehen; sie sind Vorlagen/Referenzen (z. B. Fotos des echten Gebäudes) für die Anmerkung.
  - In der `reply` erwähnen, welche Datei verwendet wurde.

## 2. Umsetzen
- Meist im Build-Skript `model/build_fischerbrunnen.py` (Geometrie, Materialien, Fenster, Positionen), manchmal in
  `edits.json`. Unklares beim Nutzer nachfragen statt raten (AskUserQuestion).
- **Zufallsfolge stabil halten:** Das Skript nutzt `random.seed(42)`; Fenster, Türtöpfe, Blumen usw. verbrauchen
  Zufallszahlen. Fällt Geometrie weg, sie trotzdem in ein Wegwerf-`MB()` rechnen (siehe `door(pots=False)`,
  `house(face_rows=...)`), sonst ändern sich alle später gebauten Objekte – und damit Drehpunkte bereits bearbeiteter Teile.
- **Drehpunkte:** `edits.json`-Einträge tragen `"pivot"`; der Build verwendet ihn. Ältere Einträge ohne `pivot` vor
  einer Geometrieänderung mit dem Drehpunkt aus dem aktuellen GLB ergänzen (Teil-Tabelle in den Extras `parts`).
- Neue bewegliche Objekte als Bauteile anlegen (`with part("Name", root=True)`, `@as_part("Art")`, `small_col` für Kollider).
- Danach in der Anmerkung `"status": "erledigt"` und `"reply": "<kurz, was getan wurde>"` setzen (sieht der Nutzer im
  Editor). Nicht Umsetzbares bleibt `offen` mit einer `reply`, die erklärt warum.
- Erledigte Anmerkungen löscht der Build selbst beim jeweils nächsten Einbacken (`"baked": true`) – nicht von Hand.

## 3. Bauen
```
cd model
"C:/Program Files/Blender Foundation/Blender 5.1/blender.exe" -b --factory-startup --python build_fischerbrunnen.py
```
Ausgabe prüfen: `TRIS`, `PARTS`, Warnungen zu unbekannten Pfaden in `edits.json`, noch offene Anmerkungen, gelöschte
erledigte Anmerkungen. Vorher das alte GLB kopieren und danach vergleichen, welche Knoten sich geändert haben
(nur die erwarteten dürfen sich ändern; Abweichungen im Mikrometerbereich sind Rundung).

## 4. Prüfen
- Python: `%USERPROFILE%\.conda\envs\claude-code-env\python.exe` (das `python` im PATH ist der Store-Platzhalter).
- Eigener Testserver auf einem freien Port (`app/serve.py <port> --no-browser`), nie 8080; danach wieder beenden.
  Vorher `model/edits.json` und `model/annotations.json` sichern, wenn ein Test speichert.
- Sichtprüfung: die Stellen der Anmerkungen aus ihrer `view`-Kamera per Playwright fotografieren und ansehen.
- Regression: `app/tests/playwright_sim.py --out <scratchpad> --only selftest,gullsim,touch,play` (touch ist gelegentlich
  wackelig – bei Fehler einmal wiederholen).

## 5. Committen
- Code (Skript, app/) und Daten/Modelle (`edits.json`, `annotations.json`, `*.glb`) in getrennten Commits.
- Hat sich `serve.py` oder das Speicherformat geändert, den Nutzer bitten, seinen Server neu zu starten und die Seite
  neu zu laden.

## Fallstricke
- Python-Code per Bash-Heredoc einfügen: `"\\n"` wird dort zu einem echten Zeilenumbruch → Skript kaputt. Längere
  Ersetzungsskripte mit dem Write-Werkzeug als Datei anlegen; nach Änderungen `py_compile` laufen lassen.
