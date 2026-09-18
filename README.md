# ScoreCap

Bildschirmbereiche per Hotkey aufnehmen, bündig auf A4 stapeln, als PDF exportieren.

## Installieren

Unter [Releases](https://github.com/georg-pitterle/ScoreCap/releases) die Datei
`ScoreCap-win-Setup.exe` laden und ausführen. Windows zeigt beim ersten Start
„Der Computer wurde geschützt" — die Anwendung ist nicht signiert. Über *Weitere
Informationen → Trotzdem ausführen* startet sie.

ScoreCap prüft beim Start im Hintergrund, ob eine neuere Version vorliegt, und
lädt sie still herunter. Ist sie da, steht unten rechts „Version X ist bereit —
wird beim Schließen installiert", daneben *Jetzt neu starten*.

- **Nichts tun:** beim nächsten Schließen installiert sich das Update, der
  folgende Start ist die neue Version.
- ***Jetzt neu starten*:** sofort umsteigen. Liegen Aufnahmen vor, fragt ScoreCap
  vorher nach — sie liegen nur in einem temporären Ordner und gehen bei einem
  Neustart verloren, wenn sie nicht als PDF exportiert sind.

Ohne Internet oder bei einem Fehler passiert nichts Sichtbares. Was geschehen
ist, steht in `%LocalAppData%\ScoreCap\logs\scorecap.log`.

## Aus dem Quellcode starten

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe -m scorecap
```

So gestartet ist die Update-Prüfung stillgelegt — sie greift nur in einer
installierten Fassung.

## Bedienung

- `Ctrl+Shift+S` (systemweit) öffnet das Auswahl-Overlay: Rechteck ziehen,
  loslassen. `Esc` bricht ab.
- *Aufnahme vorbereiten* und *Neu aufnehmen* nehmen selbst noch kein Bild auf.
  Sie stellen nur scharf: das Fenster geht aus dem Weg, du scrollst oder
  wechselst in Ruhe zum richtigen Fenster, und erst der Hotkey dunkelt den
  Bildschirm ab. Ein Hinweis am Cursor erinnert an den Hotkey.
- **Serienaufnahme:** nach einer Aufnahme bleibt ScoreCap minimiert, der Browser
  behält den Fokus. Also: scrollen, Hotkey, ziehen, scrollen, Hotkey, … Ein
  kurzer Hinweis am Cursor zeigt, dass die Aufnahme saß. Zurück ins Fenster:
  Hotkey drücken und `Esc`, oder das Fenster aus der Taskleiste holen — dann
  wird die Vorschau nachgezogen.
- Links die Aufnahmen: per Drag&Drop sortieren, *Neu aufnehmen*, *Zuschneiden*,
  *Löschen*. `Strg+Z` macht rückgängig.
- Rechts die A4-Seiten, exakt so, wie sie exportiert werden.
- *Als PDF exportieren* schreibt die Datei.

## Oberfläche

Die Palette kommt aus dem Notendruck: ein einziger Akzent im tiefen Ultramarin
der Urtext-Ausgaben, warme Neutraltöne für die Flächen, und das einzige kräftige
Schwarz auf dem Bildschirm sind die Noten selbst. Die Vorschau zeigt die Seiten
als Druckfahne — Papier mit Blattkante auf dunkler Fläche, Seitenzahl im
Bundsteg. Schrift ist Segoe UI Variable, Zahlen stehen in Cascadia Mono mit
Tabellenziffern untereinander, Symbole kommen aus Segoe Fluent Icons. Hell und
Dunkel folgen der Windows-Einstellung.

## Weiße Ränder

Jede Aufnahme wird beim Anlegen automatisch auf ihren Inhalt beschnitten: alles
heller als 245 gilt als Hintergrund, um den Rest bleiben 2 px Luft. Beschnitten
wird nur als Rechteck, die PNG-Datei bleibt unangetastet — *Zuschneiden →
Ganzes Bild* holt den vollen Screenshot zurück, und ein selbst gezogener
Zuschnitt wird nie überschrieben. Eine leere, ganz weiße Aufnahme bleibt wie sie
ist. Abschaltbar in den Einstellungen.

Das spart Seiten: zwölf Notenzeilen mit großzügigem Weißraum brauchen ohne Trim
zwei Seiten, mit Trim eine.

## Layout

Jede Aufnahme wird auf die Inhaltsbreite skaliert und untereinander gesetzt.
Passt eine weitere Aufnahme knapp nicht mehr, wird die ganze Seite einheitlich
verkleinert, höchstens bis zum eingestellten Schrumpffaktor (Standard 0,85).
Das spart Seiten, ohne die Noten unlesbar zu machen. Aufnahmen unter 120 dpi
markiert die Liste als niedrige Druckqualität; dann im Browser hineinzoomen und
neu aufnehmen.

## Systemenden

Zeichen hinter dem Ende eines Systems — etwa die Pfeile, die eine Teilung im
nächsten System ankündigen — gehören mit auf den Screenshot. Würde die ganze
Aufnahme auf Satzbreite gebracht, endeten die Notenlinien dieses Systems vor
denen aller anderen, und das System wäre kleiner. ScoreCap erkennt deshalb, wo
die Notenlinien enden, legt dieses Ende auf den rechten Satzrand und lässt
alles dahinter in den Seitenrand ragen, wie im Notensatz üblich.

Erkannt wird ein System an mindestens fünf Linien, die über mehr als die Hälfte
der Aufnahme laufen. Ohne erkanntes System, oder wenn der Überstand näher als
3 mm an die Blattkante käme, bleibt es beim Einpassen der ganzen Aufnahme.
Abschaltbar in den Einstellungen.

## Dateigröße

Aufnahmen landen in Graustufen und verlustfrei komprimiert im PDF: neun Seiten
Partitur ergeben rund 2 MB. Reines Schwarz-Weiß wäre noch kleiner, macht bei
Bildschirmauflösung aber die Notenlinien ungleich dick und die Notenköpfe
treppig — deshalb Graustufen, die die geglätteten Kanten behalten.

*PDF verkleinern …* wendet dasselbe auf ein vorhandenes PDF an, etwa auf
Exporte älterer Versionen, die ihre Bilder unkomprimiert enthielten. Das
Ergebnis landet als neue Datei neben dem Original (`Name-klein.pdf`), das
Original bleibt unverändert. Farbige Bilder bleiben farbig, JPEG-Fotos werden
nicht angefasst, und größer als vorher wird eine Datei nie.

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
| `shotlist.py` | Aufnahmeliste mit Vorschaubildern |
| `staff.py` | erkennt, wo die Notenlinien eines Systems enden |
| `theme.py`, `icons.py` | Farb- und Schrift-Tokens, Symbole |
| `optimize.py` | vorhandene PDFs verkleinern |
| `updater.py` | Selbst-Update über die GitHub-Releases |
| `app.py` | Hauptfenster, verdrahtet alles |
| `cli.py` | Start: Velopack-Übergabe, Symbol, Selbsttest |

Vorschau und Export teilen sich denselben Renderpfad: gebaut wird immer ein PDF,
die Vorschau zeigt genau dieses PDF. Was zu sehen ist, wird auch gedruckt.

## Debuggen in VS Code

`.vscode/launch.json` bringt fünf Konfigurationen mit (F5 bzw. *Ausführen und
Debuggen*):

| Konfiguration | Zweck |
|---|---|
| **ScoreCap** | App starten, Breakpoints im eigenen Code, Log bis DEBUG im Terminal |
| **ScoreCap (auch in Bibliotheken anhalten)** | wie oben, aber auch durch PySide6, PyMuPDF, Pillow, Velopack steppen |
| **ScoreCap: Selbsttest** | den Selbsttest debuggen; Bericht in `selftest.txt` |
| **Tests: aktuelle Datei** / **Tests: alle** | pytest unter dem Debugger |

Breakpoints im Update-Check und im Download greifen ebenfalls: diese laufen in
Threads von Qt, die der Debugger von sich aus nicht kennt, und melden sich
deshalb selbst bei ihm an. Aus dem Quellcode gestartet bleibt die Update-Prüfung
stillgelegt; um sie zu debuggen, braucht es eine installierte Fassung.

## Tests

```bash
.venv/Scripts/python.exe -m pytest
```

Der manuelle Abnahmetest steht in [docs/manual-test.md](docs/manual-test.md),
Spec und Plan unter `docs/superpowers/`.

## Paket bauen

```bash
.venv/Scripts/python.exe -m PyInstaller ScoreCap.spec --noconfirm
dist/ScoreCap/ScoreCap.exe --selftest selftest.txt   # prüft das fertige Paket
```

Der Selbsttest baut im gepackten Zustand ein PDF und konstruiert das Fenster.
Er findet genau die Fehler, die erst beim Paketieren entstehen — fehlende
PyMuPDF-Daten, fehlende Qt-Plugins — und schreibt sein Ergebnis in die
angegebene Datei, weil eine fensterbasierte Anwendung nichts ausgeben kann.

Das Symbol entsteht aus der Palette: `.venv/Scripts/python.exe tools/make_icon.py`.

## Wie ein Release entsteht

`main` ist immer auslieferbar; es gibt keinen Entwicklungszweig. Bei jedem Push
nach `main` aktualisiert [release-please](https://github.com/googleapis/release-please)
einen offenen Release-PR: es sammelt die Commits seit dem letzten Release, leitet
daraus die nächste Version ab (`fix:` → Patch, `feat:` → Minor, `feat!:` → Major)
und schreibt den Changelog.

Solange dieser PR offen liegt, ist nichts veröffentlicht. **Der Merge ist die
Veröffentlichung**: er erzeugt Tag und Release, und erst dann baut der Workflow
das Paket, prüft es mit dem Selbsttest und hängt Setup, portables ZIP und
Delta-Paket an das Release. Ein Tag wie `v1.4.0` bezeichnet damit unveränderlich
den Stand, aus dem ein Paket entstanden ist.

Vorabversionen laufen über Tags der Form `v1.4.0-beta.1`.

**Einmalig einzustellen:** unter *Settings → Actions → General → Workflow
permissions* muss „Allow GitHub Actions to create and approve pull requests"
angehakt sein. GitHub verbietet das standardmäßig, und der Workflow scheitert
sonst mit „GitHub Actions is not permitted to create or approve pull requests" —
unabhängig davon, dass er `pull-requests: write` anfordert.

Auf dem Release-PR selbst laufen bewusst keine Tests: er enthält nur
Versionssprung und Changelog, und der Release-Workflow testet ohnehin erneut,
bevor er packt. GitHub zeigt dort trotzdem „workflow awaiting approval", weil es
Läufe aus Bot-PRs vor jeder Job-Bedingung zurückhält. Das blockiert nichts — der
PR lässt sich ohne Freigabe mergen.

Das Release entsteht zunächst als **Entwurf** und wird erst veröffentlicht,
wenn Setup, Pakete und Update-Feed angehängt sind. Sonst wäre es für die Minuten
des Builds öffentlich die neueste Version, ohne dass installierte Kopien sich
darauf aktualisieren könnten — und ein gescheiterter Build hinterließe ein leeres
Release.
