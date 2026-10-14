# Living Greifswald – Hinweise für Claude

## Einbacken (Nutzer sagt „einbacken“)
Ablauf steht im Projekt-Skill `.claude/skills/einbacken/SKILL.md` (`/einbacken`) – vorher laden und befolgen:
offene Anmerkungen aus `model/annotations.json` umsetzen, `@datei`-Verweise auf `screenshots/` auflösen, bauen, prüfen,
committen.

## Sonstiges
- Python: `%USERPROFILE%\.conda\envs\claude-code-env\python.exe` (das `python` im PATH ist der Store-Platzhalter).
- Der Nutzer arbeitet oft parallel im Editor (`serve.py` auf 8080) und schreibt dabei `model/edits.json` und
  `model/annotations.json`. Diese Dateien vor Tests sichern und danach wiederherstellen; Testserver auf anderen Ports.
- `screenshots/` (Projektwurzel) enthält Referenzbilder des Nutzers; `@name` in Anmerkungen oder Nachrichten meint
  eine Datei dort.
