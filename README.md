# ScoreCap

Bildschirmbereiche per Hotkey aufnehmen, bündig auf A4 stapeln, als PDF exportieren.

## Installation

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

## Starten

```bash
.venv/Scripts/python.exe -m scorecap
```

## Bedienung

- `Ctrl+Shift+S` (systemweit) öffnet das Auswahl-Overlay: Rechteck ziehen,
  loslassen. `Esc` bricht ab.
- Links die Aufnahmen: per Drag&Drop sortieren, *Neu aufnehmen*, *Zuschneiden*,
  *Löschen*. `Strg+Z` macht rückgängig.
- Rechts die A4-Seiten, exakt so, wie sie exportiert werden.
- *Als PDF exportieren* schreibt die Datei.

## Layout

Jede Aufnahme wird auf die Inhaltsbreite skaliert und untereinander gesetzt.
Passt eine weitere Aufnahme knapp nicht mehr, wird die ganze Seite einheitlich
verkleinert, höchstens bis zum eingestellten Schrumpffaktor (Standard 0,85).
Das spart Seiten, ohne die Noten unlesbar zu machen. Aufnahmen unter 120 dpi
markiert die Liste als niedrige Druckqualität; dann im Browser hineinzoomen und
neu aufnehmen.

## Aufbau

| Modul | Aufgabe |
|---|---|
| `settings.py` | Seitenmaße, Ränder, Schrumpffaktor |
| `model.py` | Aufnahmen, Reihenfolge, Crop, Undo |
| `layout.py` | Paginierung, reine Rechnung in PDF-Punkten |
| `pdf.py` | PDF-Bau samt Fußzeile |
| `preview.py` | rastert dasselbe PDF für die Vorschau |
| `capture.py` | Auswahl-Overlay und Bildschirmaufnahme |
| `hotkey.py` | systemweiter Hotkey über Win32 |
| `cropdialog.py`, `settingsdialog.py` | Dialoge |
| `app.py` | Hauptfenster, verdrahtet alles |

Vorschau und Export teilen sich denselben Renderpfad: gebaut wird immer ein PDF,
die Vorschau zeigt genau dieses PDF. Was zu sehen ist, wird auch gedruckt.

## Tests

```bash
.venv/Scripts/python.exe -m pytest
```

Der manuelle Abnahmetest steht in [docs/manual-test.md](docs/manual-test.md),
Spec und Plan unter `docs/superpowers/`.
