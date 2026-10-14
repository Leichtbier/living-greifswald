# Living Greifswald – Hinweise für Claude

## Einbacken (Nutzer sagt „einbacken“)
1. **Zuerst `model/annotations.json` lesen.** Das sind Anmerkungen, die der Nutzer im Bearbeiten-Modus (Alt+Klick) an
   Claude gerichtet hat. Jede Anmerkung mit `"status": "offen"` umsetzen:
   - Fundstelle: `object` (Blender-Objekt), `part` (Bauteil-Pfad, bei Kopien `source` = Original), `material` und `side`
     der angeklickten Fläche, `scriptPos` = Punkt in Skript-Koordinaten (Blender: x = Ost, y = Nord, z = oben, Lage vor
     `edits.json`, also direkt mit den Zahlen in `build_fischerbrunnen.py` vergleichbar), `pos`/`normal` in three.js-Welt.
   - Screenshot mit rotem Ring um die Klickstelle: `model/annotations/<id>.jpg` (nur lokal, nicht im Repo) – ansehen.
   - Umsetzen meist im Build-Skript (Geometrie, Materialien, Positionen) oder in `edits.json`; Unklares beim Nutzer
     nachfragen statt raten.
   - Danach `"status": "erledigt"` und `"reply": "<kurz, was getan wurde>"` setzen (die Antwort sieht der Nutzer im Editor).
     Nicht Umsetzbares bleibt `offen` mit einer `reply`, die erklärt warum.
2. Bauen: `cd model` und `blender -b --factory-startup --python build_fischerbrunnen.py` (Blender 5.1 unter
   `C:/Program Files/Blender Foundation/Blender 5.1/blender.exe`). Die Ausgabe nennt unbekannte Pfade in `edits.json`
   und noch offene Anmerkungen.
3. Prüfen (Playwright, `app/tests/playwright_sim.py`) und committen; Modelle + `edits.json` + `annotations.json` getrennt vom Code.

## Sonstiges
- Python: `%USERPROFILE%\.conda\envs\claude-code-env\python.exe` (das `python` im PATH ist der Store-Platzhalter).
- Der Nutzer arbeitet oft parallel im Editor (`serve.py` auf 8080) und schreibt dabei `model/edits.json` und
  `model/annotations.json`. Diese Dateien vor Tests sichern und danach wiederherstellen; Testserver auf anderen Ports.
