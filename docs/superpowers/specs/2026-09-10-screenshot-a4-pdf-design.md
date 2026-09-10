# ScoreCap — Screenshot-Bereiche zu A4-PDF

Datum: 2026-09-10
Status: Design freigegeben

## Zweck

Notenzeilen (oder beliebige Bildschirmbereiche) aus einem Browser abgreifen, bündig
untereinander auf A4-Seiten anordnen, in der Vorschau korrigieren und als PDF
exportieren. Zielplattform: Windows 11.

## Kern-Entscheidung: PDF ist die Wahrheit

Das Layout wird nach PDF gerendert, und die Vorschau zeigt genau dieses PDF als
gerenderte Pixmap. Ein einziger Renderpfad, deshalb kann die Vorschau nicht vom
Druckergebnis abweichen. PyMuPDF baut das PDF im Speicher und rendert dieselben
Seiten für die Anzeige; Export schreibt die bereits erzeugten Bytes auf Platte.

## Technik

- Python 3.11+, PySide6 (Qt)
- Qt `QScreen.grabWindow()` für Screen Capture, Pillow für Crop und PNG-Kodierung
- PyMuPDF (`fitz`) für PDF-Bau und Vorschau-Rendering
- Start: `python -m scorecap`. Optional später PyInstaller-EXE.

## Module

Jedes Modul hat eine Aufgabe und ist einzeln testbar.

| Modul | Aufgabe | Kennt nicht |
|---|---|---|
| `model.py` | `Shot` (Pfad, Originalgröße, Crop-Rect), `Document` (Shot-Liste, Settings, Undo-Stack) | UI, Dateisystem, PDF |
| `capture.py` | Auswahl-Overlay, Aufnahme, liefert PNG-Pfad + Pixelgröße | Document, Layout |
| `hotkey.py` | Globaler Hotkey über Win32 `RegisterHotKey` | alles andere |
| `layout.py` | `paginate(sizes, settings) -> list[Page]`, reine Funktion, Ergebnis in PDF-Punkten | Bilder, PDF, UI |
| `pdf.py` | `build(pages, settings) -> bytes` — Bilder platzieren, Fußzeile zeichnen | UI |
| `preview.py` | PDF-Bytes seitenweise zu QPixmap, scrollbare Seitenansicht | Layout-Regeln |
| `app.py` | MainWindow, Shot-Liste, Verdrahtung, Settings-Panel | — |

## Datenfluss

Hotkey → `capture` → `Shot` ins `Document` → `layout.paginate` → `pdf.build` →
`preview` rendert. Jede Änderung (löschen, sortieren, croppen, neu aufnehmen)
durchläuft denselben Pfad. Rebuild ist um ~150 ms entprellt, damit Drag&Drop
flüssig bleibt.

## Capture

- Hotkey über Win32 `RegisterHotKey` (ctypes) plus Qt `nativeEventFilter` auf
  `WM_HOTKEY`. Keine Extra-Abhängigkeit, kein Admin nötig. Standard: `Ctrl+Shift+S`.
- Overlay: randloses Vollbildfenster über den gesamten virtuellen Desktop (alle
  Monitore), abgedunkelt, Fadenkreuz, Rechteck ziehen. `Esc` bricht ab.
- Aufnahme über `QScreen.grabWindow()`. Qt rechnet logische Overlay-Koordinaten
  selbst in physische Pixel um und liefert das Bild in voller Geräteauflösung, auch
  bei Windows-Skalierung 125/150 %. Damit entfällt eigene `devicePixelRatio`-Mathematik
  und eine Abhängigkeit.
- Ergebnis als PNG in einem Session-Tempordner, beim Beenden gelöscht.

## Layout

Ziel: gut druckbar und möglichst wenig Seiten.

**Seitenmaß.** A4 = 595,3 × 841,9 pt. Ränder: 12 mm seitlich und oben, 15 mm unten
(Platz für die Fußzeile). Inhaltsbereich ≈ 527 × 765 pt. Ränder in den Settings
änderbar.

**Skalierung.** Jeder Shot wird auf volle Inhaltsbreite skaliert, Seitenverhältnis
erhalten: `h = 527 * ih / iw`. Nie verzerren, nie beschneiden.

**Paginierung.**

1. Mindestabstand zwischen Bildern: 4 mm.
2. Greedy füllen, solange `Σh + Σgaps ≤ 765`.
3. Passt der nächste Shot knapp nicht, wird ein einheitlicher Schrumpffaktor `s`
   für diese Seite geprüft. Reicht `s ≥ s_min`, kommt der Shot mit auf die Seite
   und alle Bilder dieser Seite werden mit `s` skaliert. Sonst neue Seite.
   `s_min` Standard 0,85, einstellbar 0,70–1,00.
4. Restplatz: volle Seiten werden justiert, der Restraum also gleichmäßig auf die
   Lücken verteilt, gedeckelt bei 3× Mindestabstand. Die letzte Seite ist oben
   bündig mit Mindestabstand.
5. Horizontal immer zentriert.
6. Ausnahme Einzelbild: ist ein Shot allein schon höher als die Seite, wird er
   trotzdem auf seiner eigenen Seite platziert und dafür so weit skaliert, wie
   nötig — auch unter `s_min`. Sonst käme die Paginierung nicht voran.

**Druck-Guard.** Pro Shot wird die effektive Auflösung berechnet
(`dpi = iw / Zielbreite_in_Zoll`). Unter 120 dpi erscheint eine gelbe Warnung am
Thumbnail mit dem Hinweis, im Browser hineinzuzoomen und neu aufzunehmen. Der
Export wird nicht blockiert.

## Vorschau und Bearbeiten

Zweispaltiges Fenster.

**Links** die Shot-Liste als Thumbnails mit Nummer, Pixelgröße und dpi-Warnung.
Drag&Drop sortiert. Pro Eintrag: *Neu aufnehmen*, *Zuschneiden*, *Löschen*.

**Rechts** die gerenderten A4-Seiten untereinander, scrollbar, mit Zoom.

- *Neu aufnehmen*: Fenster tritt kurz in den Hintergrund, Overlay öffnet, das neue
  Bild ersetzt das alte an derselben Listenposition. Ein vorhandener Crop wird
  dabei zurückgesetzt.
- *Zuschneiden*: Dialog mit dem Bild und einem ziehbaren Rechteck mit anfassbaren
  Kanten, plus *Zurücksetzen*. Gespeichert wird nur das Rect im Model; die
  Originaldatei bleibt unangetastet, der Crop ist jederzeit revidierbar.
- `Strg+Z` macht Löschen, Sortieren und Crop rückgängig (Undo-Stack auf dem
  `Document`).

## Fußzeile und Export

- Checkbox „Seitenzahl". Format `x von y`, zentriert, 9 pt Helvetica in Grau,
  8 mm über der Unterkante. `y` ist die Gesamtseitenzahl.
- „Als PDF exportieren" öffnet einen Dateidialog und schreibt die bereits gebauten
  PyMuPDF-Bytes.
- Bilder werden als PNG eingebettet. Noten sind Strichgrafik, JPEG-Artefakte wären
  deutlich sichtbar.
- Settings (Ränder, `s_min`, Fußzeile an/aus, Hotkey) in einem kleinen Panel,
  persistiert über `QSettings`.

## Fehlerfälle

| Fall | Verhalten |
|---|---|
| Auswahl kleiner als 20 px, oder `Esc` | verworfen, keine Meldung |
| Hotkey bereits belegt | Hinweis beim Start, Hotkey in den Settings änderbar |
| Export-Ziel schreibgeschützt oder Datei im Reader geöffnet | Fehlerdialog, Dokument bleibt erhalten |
| Kein Shot vorhanden | Export-Button deaktiviert |
| Screenshot-Datei zwischenzeitlich verschwunden | Shot im Layout übersprungen, Thumbnail rot markiert |

## Tests

- `layout.py` trägt die Hauptlast: Eingabe sind nur `(iw, ih)`-Tupel plus Settings.
  Geprüft wird, dass sich nichts überlappt, nichts aus dem Inhaltsbereich ragt,
  `s ≥ s_min` gilt und bekannte Fälle die minimale Seitenzahl ergeben.
- `pdf.py` baut aus synthetischen Bildern und liest Seitenzahl und Bildrechtecke
  mit PyMuPDF zurück.
- `model.py`: Undo, Sortieren, Crop-Anwendung.
- Capture und Overlay bleiben manuell. Screen Capture lässt sich nicht sinnvoll
  automatisiert prüfen.

## Nicht im Umfang (YAGNI)

Projekt speichern/laden, Titel-Kopfzeile, automatisches Trimmen weißer Ränder,
erzwungene Seitenumbrüche, andere Seitenformate als A4 hochkant.
