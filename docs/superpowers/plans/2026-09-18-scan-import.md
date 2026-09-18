# Plan: Scans importieren — Systeme automatisch erkennen, Seiten bereinigen

## Kontext
ScoreCap nimmt bisher nur Bildschirmbereiche auf. Neu: gescannte Noten (PDF/Bilder aus beliebiger Scanner-Software) importieren. ScoreCap bereinigt jede Seite (Schräglage, Bundschatten/Vergilbung, schwarze Scanränder), erkennt die Systeme und legt jedes als eigene Aufnahme an. Danach läuft alles wie gehabt: Liste, Zuschneiden, A4-Layout, PDF-Export, `.scorecap`.

Entschieden: Datei-Import (Dialog + Drag&Drop), kein direktes WIA. Bereinigung einstellbar (S/W oder Graustufen). Nur Drehung korrigieren, keine Wölbungs-Entzerrung.

## Ansatz
Jedes erkannte System wird eine eigene PNG-Datei: das **Band** zwischen den Lückenmitten zu den Nachbarsystemen, einzeln nachgedreht. `Shot.crop` = enger Inhaltsrahmen darin. Vorteile: die Drehung pro System geht, der Zuschneide-Dialog kann den Rahmen innerhalb des Bands noch erweitern, und am Datenmodell und Projektformat ändert sich nichts.

**Nur Pillow, kein numpy.** Alles Rechenintensive läuft über Pillow-Operationen in C (`resize(..., BOX)` für Zeilen-/Spaltenprofile, wie schon in `scorecap/staff.py`, `rotate`, `MaxFilter`, `GaussianBlur`, `ImageMath`). Die Deskew-Winkelsuche läuft auf einem verkleinerten Bild. Das Bundle wächst nicht. Nur falls die Performance-Messung (siehe Verifikation) durchfällt, kommt numpy nach.

## Neues Modul `scorecap/scan.py` (rein, ohne Qt, testbar)

1. **`load_pages(path) -> Iterator[Image]`**
   - PDF: PyMuPDF rendert jede Seite mit `SCAN_DPI = 300` in Graustufen (`pymupdf` ist schon Dependency, siehe `scorecap/optimize.py`).
   - PNG/JPG/TIFF/BMP: Pillow, mehrseitiges TIFF über `ImageSequence`, `ImageOps.exif_transpose` für Handyfotos.
   - Alles wird nach `"L"` konvertiert.
2. **`flatten_background(grey)`**: Hintergrund schätzen, dazu auf 1/16 verkleinern, `MaxFilter` (entfernt Tinte), `GaussianBlur` und zurück hochskalieren. Dann `grey / hintergrund * 255` per `ImageMath`. Das entfernt Bundschatten, Vergilbung und ungleichmäßige Belichtung.
3. **`clear_edges(grey)`**: Randspalten und -zeilen, die von der Kante her überwiegend dunkel sind (Scannerdeckel, Buchkante), werden weiß gesetzt.
4. **`skew_angle(grey, limit=5.0) -> float`**: Das Bild wird binarisiert und auf etwa 1/4 verkleinert. Dann wird es probeweise gedreht, grob in 0,2°-Schritten, danach fein in 0,02°-Schritten. Gewählt wird der Winkel mit maximaler Varianz des Zeilenprofils. Notenlinien geben einen scharfen Peak. Danach wird die volle Auflösung mit `rotate(..., BICUBIC, fillcolor=255)` gedreht.
5. **`find_systems(grey) -> list[System]`** mit `System(band: box, content: box)`:
   - Linienzeilen: Zeilen mit hohem Tintenanteil, bestätigt über den längsten Lauf (Logik aus `staff.py` wiederverwenden bzw. `_longest_run_end` dorthin teilen). Benachbarte Zeilen werden zu Linienmitten zusammengefasst.
   - Notensysteme: je 5 aufeinanderfolgende Linien mit annähernd gleichem Abstand. Daraus ergeben sich Linienabstand `s` und der x-Bereich der Linien.
   - Systeme: zwei benachbarte Notensysteme gehören zusammen, wenn nahe dem linken Linienanfang (`x0 - 2s … x0 + s`) eine Spalte Tinte von der unteren Linie des oberen bis zur oberen Linie des unteren Systems durchgehend verbindet (Systemklammer bzw. Taktstrich). Ohne Verbindung gelten sie als getrennte Systeme (z. B. einstimmige Melodie).
   - Bandgrenzen zwischen zwei Systemen: die tintenärmste Zeile in der Lücke. Liedtext und Dynamik landen dann beim richtigen System, wenn ein Weißraum dazwischen liegt. Bei Gleichstand wird die Mitte genommen.
   - Oben über dem ersten und unten unter dem letzten System wird höchstens `4 × Systemhöhe` weit gesucht, begrenzt durch eine Weißlücke ≥ `3s`. Titel, Kopf- und Fußzeilen (Seitenzahl, Copyright) fallen so meist heraus.
   - Horizontal wird auf `[x0 - 3·Systemhöhe, x1 + 2·Systemhöhe]` begrenzt, damit Instrumentennamen drin bleiben und Randflecken draußen.
   - Keine Notenlinien gefunden: die ganze Seite wird ein Band (Fallback).
6. **`straighten(band)`**: Feinkorrektur pro Band über `skew_angle(limit=0.5)`, nur ab einer Abweichung von 0,05°.
7. **`finish(image, mode)`**: `"bw"` = Otsu-Schwelle, Ergebnis im Modus `"1"`. `"grey"` = Levels, also alles oberhalb der Papierhelligkeit auf 255.
8. **`process_page(image, settings, target_dir) -> list[Shot]`**: verkettet die Schritte 2–7. Jedes Band wird als `scan-<uuid>.png` gespeichert. Der Crop kommt aus `trim_box()` von `scorecap/trim.py`.

## Weitere Änderungen
- **`scorecap/settings.py`**: `scan_mode: str = "bw"` (`"bw"`/`"grey"`). Persistenz über `load_settings`/`_coerce` funktioniert ohne Änderung, ungültige Werte werden in `scan.py` auf `"bw"` gesetzt.
- **`scorecap/settingsdialog.py`**: `QComboBox` „Scans bereinigen: Schwarz/Weiß | Graustufen", zusätzlich im `settings`-Property.
- **`scorecap/model.py`**: `Document.extend(shots)` mit *einem* Snapshot. Ein Import lässt sich damit mit einem `Strg+Z` rückgängig machen.
- **`scorecap/pdf.py`** `_png_bytes`: Bilder im Modus `"1"` bleiben 1-Bit, statt nach `"L"` konvertiert zu werden. Das gibt deutlich kleinere PDFs. Bestehende Screenshots sind nicht betroffen.
- **`scorecap/icons.py`**: Glyphe `IMPORT` (Segoe-Fluent-Glyphe „Scan", ``, bei der Umsetzung prüfen).
- **`scorecap/app.py`**:
  - Button „Scans importieren …" neben *Aufnahme vorbereiten* (`QFileDialog.getOpenFileNames`, Filter `*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp`).
  - `setAcceptDrops(True)` + `dragEnterEvent`/`dropEvent` für dieselben Endungen.
  - `import_files(paths)` startet ein `_ScanImport`-QRunnable im `QThreadPool` und nutzt das vorhandene Muster (Signale gehören dem Fenster, wie `_UpdateSignals`; `_track`). Es meldet `progress(seite, gesamt)` in die Statuszeile und `finished(shots, fehler)`.
  - Am Ende `document.extend(shots)`, `rebuild()`, Statusmeldung „12 Systeme aus 4 Seiten importiert". Bei Seiten ohne erkannte Systeme kommt der Hinweis „Seite 3: keine Notenlinien erkannt — als ganze Seite übernommen".
  - Während des Imports sind Import und Export gesperrt. Lesefehler landen gesammelt in einer `QMessageBox`.
- **`ScoreCap.spec`**: prüfen, dass nichts, was PyMuPDF/Pillow für den Import braucht, ausgeschlossen ist (voraussichtlich keine Änderung).
- **Doku**: README-Abschnitt „Scans importieren", Eintrag in `docs/manual-test.md`. Der Plan wird als `docs/superpowers/plans/2026-09-18-scan-import.md` abgelegt. CHANGELOG pflegt release-please.

## Tests (TDD, synthetische Bilder wie in `tests/test_staff.py`)
`tests/test_scan.py`:
- Seite mit gezeichneten Notensystemen um ±1,5° gedreht: `skew_angle` trifft auf ±0,1°, nach der Korrektur sind die Linien waagrecht.
- Grauverlauf (Bundschatten) + Gelbstich: nach `flatten_background` ist das Papier überall ≥ 240, die Linien bleiben dunkel.
- Schwarzer Balken am Rand wird entfernt.
- 3 einzelne Notensysteme → 3 Systeme. 2 Klaviersysteme (je 2 Notensysteme mit Klammer) → 2 Systeme. Chorsystem mit 4 Notensystemen und Textzeilen darunter → Text gehört zum oberen System.
- Titel oben und Seitenzahl unten: Seitenzahl fällt heraus.
- Leere Seite bzw. Seite ohne Linien → eine Aufnahme (Fallback).
- `load_pages` mit einem mit PyMuPDF erzeugten 2-seitigen PDF und einem mehrseitigen TIFF.
- `finish` im Modus bw liefert `"1"`, im Modus grey `"L"`.

Weitere Tests:
- `tests/test_model.py`: `extend` + ein Undo entfernt alle.
- `tests/test_pdf.py`: ein 1-Bit-Shot bleibt 1-Bit, und die PDF-Datei wird kleiner als mit `"L"`.
- `tests/test_app.py`: `import_files` mit synthetischem PNG fügt N Shots hinzu (Worker in Tests synchron oder über `qtbot.waitSignal`), Projekt speichern und laden hält den Stand.
- `tests/test_settingsdialog.py`: `scan_mode` wird übernommen.

## Verifikation
1. `.venv/Scripts/python.exe -m pytest` komplett grün.
2. App starten (`python -m scorecap`) und echte Scans importieren: je ein flach gescanntes Blatt, eine Buchseite mit Bundschatten, ein Handy-Scan-PDF und eine Chorpartitur. Sichtprüfung der Vorschau, beide Bereinigungsmodi, Zuschneiden, Undo, Speichern und Öffnen, Export.
3. Performance: eine A4-Seite mit 300 dpi sollte in < 2 s verarbeitet sein. Wenn nicht, erst die Winkelsuche weiter verkleinern, dann numpy erwägen.
4. PyInstaller-Build starten und den Import im gebauten Programm einmal testen.

## Abweichungen bei der Umsetzung
- `pdf.py` unverändert: PyMuPDF legt zweifarbige Bilder schon selbst mit 1 Bit ab. Ein Test sichert das ab.
- Hintergrund wird mit Max- und anschließendem Min-Filter geschätzt (Closing). Ein reiner Max-Filter überschätzt das Papier an steilen Bundschatten.
- Leere Seiten werden übersprungen statt als leere Aufnahme übernommen. Die Statuszeile nennt sie.
- Sehr große Scans (breiter als 3600 px) werden vorher verkleinert, damit ein 600-dpi-Scan nicht viermal so lange braucht.
- Die Vorschaubilder der Aufnahmeliste zeigen jetzt den Zuschnitt statt der ganzen Datei. Bei Scans sonst fast leer.
- Import- und Exportknopf: gesperrt wird nur der Importknopf während eines Imports.
