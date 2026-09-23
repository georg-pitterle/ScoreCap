# Aufbau

| Modul | Aufgabe |
|---|---|
| `settings.py` | Seitenmaße, Ränder, Schrumpffaktor |
| `model.py` | Aufnahmen, Reihenfolge, Crop, Radierungen, Undo |
| `layout.py` | Paginierung, reine Rechnung in PDF-Punkten |
| `ink.py` | wo Tinte sitzt: Zeilen- und Spaltenprofile, Notenlinien |
| `pdf.py` | PDF-Bau samt Fußzeile |
| `preview.py` | rastert dasselbe PDF für die Vorschau |
| `capture.py` | Auswahl-Overlay und Bildschirmaufnahme |
| `hotkey.py` | systemweiter Hotkey über Win32 |
| `cropdialog.py`, `settingsdialog.py` | Dialoge |
| `projectui.py` | die Frage nach ungespeicherten Aufnahmen |
| `erase.py` | malt die Radierungen weiß, wenn eine Aufnahme gerendert wird |
| `shotlist.py` | Aufnahmeliste mit Vorschaubildern |
| `staff.py` | erkennt, wo die Notenlinien eines Systems enden |
| `tasks.py` | Update-Prüfung und Scan-Import abseits des Fensters |
| `scan.py` | Scans bereinigen, gerade stellen, in Systeme zerlegen |
| `theme.py`, `icons.py` | Farb- und Schrift-Tokens, Symbole |
| `i18n.py`, `translations/` | Sprache wählen, Übersetzungen laden |
| `optimize.py` | vorhandene PDFs verkleinern |
| `omr.py` | Noten erkennen lassen und als MusicXML schreiben |
| `project.py` | Projekte als `.scorecap` speichern und öffnen |
| `updater.py` | Selbst-Update über die GitHub-Releases |
| `app.py` | Hauptfenster, verdrahtet alles |
| `cli.py` | Start: Velopack-Übergabe, Symbol, Selbsttest |

Vorschau und Export teilen sich denselben Renderpfad: gebaut wird immer ein PDF,
die Vorschau zeigt genau dieses PDF. Was zu sehen ist, wird auch gedruckt.

`ink.py` und `staff.py` teilen sich eine Notenlinien-Erkennung: `scan.py`
braucht sie, um eine Seite in Systeme zu schneiden, `staff.py`, um die Enden
einer Aufnahme auf die Ränder zu legen.
