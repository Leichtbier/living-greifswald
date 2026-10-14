# Fischerbrunnen / Fischmarkt Greifswald – Szene für three.js

| Datei | Inhalt |
|---|---|
| `fischerbrunnen.glb` | Komplette Szene (Texturen eingebettet, ~114k Dreiecke, ~10 MB) |
| `fischerbrunnen_colliders.glb` | Einfache Kollisionsboxen (`COL_*`) für Gebäude, Brunnen, Skulpturen, Baum |
| `textures/`, `make_textures.py` | Kachelbare Texturen und ihr Generator (numpy + Pillow) |
| `build_fischerbrunnen.py` | Erzeugt alles reproduzierbar: `blender -b --factory-startup --python build_fischerbrunnen.py` |
| `render_preview.py` | Vorschau-Renderings (Blender-Freestyle-Outlines): `blender -b fischerbrunnen.blend --python render_preview.py -- <outdir>` |

`.blend`-Dateien und Vorschaubilder werden beim Bauen erzeugt und nicht versioniert (Blender speichert darin absolute lokale Pfade).

## Koordinaten
- 1 Einheit = 1 m, Ursprung = Mitte des Brunnenbeckens, Boden bei y = 0.
- three.js (glTF, Y-up): **Norden = −Z**, Osten = +X.
- Spielfläche ca. x −36…36, z −38…61 (Süden = +Z). Die Positionen stammen aus dem Satellitenbild (≈ 0,06 m/px).
- Empties: `POI_Fischerbrunnen`, `POI_Fischer`, `POI_Aaljunge`, `POI_FensterSkulptur`, `POI_Rathaus`, `POI_Linde`, `Spawn_Player`.

## Objekte (Auswahl)
`B_E2_Rathaus`, `B_S0_Keimblatt` (neugotischer Giebel), `B_W1_VeroModa`, `B_W2_Fellini`, `B_W3_Ernstings`, `B_W4/5/6_*Giebel`,
`Fountain_Basin`, `Fountain_Water` (Alpha-Blend), `Sculpture_*`, `Tree_Linde`, `Cafe_*`, `Props_*`, `Lights_Lichterketten`.

## Einbindung (Tipps)
```js
const gltf = await new GLTFLoader().loadAsync('fischerbrunnen.glb');
scene.add(gltf.scene);
renderer.outputColorSpace = THREE.SRGBColorSpace;
// Texturen wiederholen sich weltbasiert -> Wrap ist im glTF bereits auf REPEAT.
// Leuchtende Materialien (Glass_Warm, Lamp_Glow, Bulb_Glow) sind emissive -> mit UnrealBloomPass wirkt's besonders gemütlich.
// Für den Toon-Look: Materialien durch MeshToonMaterial ersetzen (map + color übernehmen) und einen Outline-Pass nutzen.
```
Hohe Gebäude (Rathaus-Giebel ~26 m, Keimblatt-Giebel ~29 m) können die Draufsicht-Kamera verdecken – Gebäude
zwischen Kamera und Spieler ggf. transparent schalten (Raycast gegen `fischerbrunnen_colliders.glb`).

## Spiel-Prototyp (`../app`)
`app/start.bat` doppelklicken (nutzt `python` aus dem PATH oder die Umgebungsvariable `PYTHON`) → lokaler Server auf `http://localhost:8080/app/` (Browser öffnet sich automatisch).
Steuerung: WASD/Pfeile laufen, Shift rennen, Q/E oder rechte Maus ziehen = Kamera drehen, Mausrad = Zoom, N = Tag/Abend.
Kollision: Kreis (r = 0,35 m) gegen die Rechtecke aus `fischerbrunnen_colliders.glb`. Gebäude zwischen Kamera und Figur werden ausgeblendet.
URL-Parameter: `?evening` (Abend), `?demo` (Figur läuft automatisch), `?selftest` (Kollisionstest, Ergebnis im DOM).

## Möwen (`seagull.glb`, `app/seagulls.js`)
Modell: `blender -b --factory-startup --python build_seagull.py` → `seagull.blend` + `seagull.glb` (Silbermöwe, ca. 1.800 Dreiecke,
Naturgröße, Blick nach +Z in three.js, Füße auf y = 0). Starre Teile in einer Gelenk-Hierarchie (`Body`, `Neck`, `Head`, `Jaw`, `Tail`,
`Leg_*`, `Foot_*`, `WingFold_*` = angelegte Flügel, `Wing_*`/`WingFore_*`/`WingHand_*` = ausgebreitete Flügel), animiert als Objekt-Animationen.
Jeder Clip keyt alle Gelenke, daher sind Crossfades sauber. Vorschau: `blender -b seagull.blend --python render_seagull.py -- <outdir> Clip:frame[:34|side|top|front] ...`

| Clip | Länge | Verwendung |
|---|---|---|
| Idle | 2,0 s | Stehen, Kopf dreht sich frech umher |
| Walk | 0,67 s | Watscheln (timeScale ~ Geschwindigkeit / 0,55 m/s) |
| Hop | 0,75 s | Sprung (Wurzelhöhe/Bogen macht der Code), Flügel kurz offen |
| Swim | 1,33 s | Paddeln; langsam abgespielt = Treiben |
| Fly | 0,5 s | Flügelschlag |
| Glide | 2,0 s | Gleiten |
| Land | 0,58 s | Bremsen und Aufsetzen |
| Peck | 0,83 s | Picken am Boden |
| Squawk | 1,5 s | Langruf mit offenem Schnabel |

KI (`seagulls.js`): Zustände Stehen/Picken/Kreischen/Laufen/Hüpfen/Schwimmen/Fliegen/Landen auf den Untergründen
Platz, Beckenrand, Wasser und Ansitz (per Raycast gefundene Flächen: Dächer, Laternen, Bänke, Tische, Skulpturen).
Möwen hüpfen zwischen Platz, Rand und Wasser, fliegen über Gebäude hinweg (Höhe aus den Kollidern + Dachzuschlag), legen sich
in Kurven in die Schräglage und laufen frech auf die stehende Spielfigur zu. Läuft oder rennt die Figur auf sie zu, hüpfen sie weg,
schwimmen davon oder fliegen auf.
URL-Parameter: `?gulls=<n>` (Anzahl, Standard 10), `?gallery` (alle Clips nebeneinander), `?follow=<i>` bzw. Taste **G** (Kamera folgt einer Möwe),
`?gullsim=<s>[&chase]` (Simulation mit festem Zeitschritt, Plausibilitätsprüfung im DOM).
