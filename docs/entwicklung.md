# Entwickeln

## Aus dem Quellcode starten

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe -m scorecap
```

So gestartet ist die Update-Prüfung stillgelegt — sie greift nur in einer
installierten Fassung.

## Tests

```bash
.venv/Scripts/python.exe -m pytest
```

Die Suite läuft über alle Kerne verteilt (`-n auto` steht in `pyproject.toml`)
und braucht wenige Sekunden. Für einen Lauf in einem einzigen Prozess — etwa
unter dem Debugger — `-n0` anhängen.

Getestet wird, was die App tut: eine Aufnahme wird zugeschnitten, ein Projekt
überlebt Speichern und Öffnen, ein Klick in der Vorschau markiert die richtige
Zeile. Farbwerte, Typen, Aufrufzahlen und Objekt-Identitäten stehen nicht in
der Suite — sie halten die Tests an der Bauweise fest, statt an dem, was
herauskommt.

`tests/test_release_guards.py` ist die Ausnahme: dort stehen die Prüfungen auf
Dateien statt auf Verhalten — ob `pyproject.toml` und `scorecap/_version.py`
dieselbe Version nennen und ob die Übersetzungen vollständig und aktuell sind.
Beides ginge sonst still bis zum Nutzer durch.

Der manuelle Abnahmetest steht in [manual-test.md](manual-test.md), Spec und
Plan unter `superpowers/`.

## Übersetzen

Übersetzt wird mit den Werkzeugen von Qt: Texte stehen im Code auf Englisch in
`tr()` bzw. `QCoreApplication.translate()`, die Übersetzungen in
`scorecap/translations/scorecap_<sprache>.ts`. Nach dem Ändern eines Textes:

```bash
.venv/Scripts/python.exe tools/update_translations.py   # .ts abgleichen, .qm bauen
.venv/Scripts/pyside6-linguist.exe scorecap/translations/scorecap_de.ts
.venv/Scripts/python.exe tools/update_translations.py   # nach dem Übersetzen
```

Die Tests schlagen fehl, solange ein Text im Code fehlt, unübersetzt ist oder
die `.qm` veraltet ist. Für eine neue Sprache ihren Code in `LANGUAGES` in
`tools/update_translations.py` und `scorecap/i18n.py` ergänzen und das Skript
laufen lassen.

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
