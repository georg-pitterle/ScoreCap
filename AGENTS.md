# Programmierstil

Was in diesem Projekt als sauber gilt. Kein Wort über den Aufbau — der steht in
[docs/aufbau.md](docs/aufbau.md).

## Sprache

Code, Docstrings, Kommentare und Testnamen auf **Englisch**. README und alles
unter `docs/` auf **Deutsch**.

Jeder Text, den ein Nutzer sieht, steht englisch im Code und geht durch
`self.tr(...)` bzw. `QCoreApplication.translate("Kontext", ...)` — nie ein
nackter String in einem Widget. Nach jeder Textänderung
`tools/update_translations.py` laufen lassen, sonst schlagen die Tests fehl.

## Docstrings

Der Modul-Docstring ist eine Zeile und sagt, was hineingeht und was herauskommt:

```python
"""Pure pagination: image sizes in, page rectangles in PDF points out."""
```

Ein Funktions-Docstring sagt das Ergebnis, nicht den Weg dorthin — und bei einer
Entscheidung, die auch anders hätte ausfallen können, warum sie so fiel:

```python
def trim_box(image, threshold, padding):
    """Bounding box of everything darker than `threshold`, grown by `padding`.

    Returns None when the image holds no ink at all - a blank capture is
    better left alone than reduced to nothing.
    """
```

Selbsterklärende Funktionen brauchen keinen.

## Kommentare

Ein Kommentar begründet, er beschreibt nicht. Was der Code tut, steht im Code;
in den Kommentar gehört, was jemand sonst wieder kaputt machen würde:

```python
return shot.crop  # nothing left; better kept than reduced to nothing
```

```python
# debug_this_thread() without a client tries to connect: a 3 s stall and
# a traceback on every pool task.
```

Kein `# set the width` über `self.width = ...`.

## Tests

Ein Testname ist ein ganzer Satz über das, was der Nutzer erlebt:

```python
def test_erasing_a_page_number_pulls_the_crop_in(): ...
def test_a_failed_save_leaves_the_previous_file_intact(): ...
```

Nicht `test_crop_after_erase` oder `test_save_error`.

**Getestet wird Verhalten, nicht Bauweise.** Keine Farbwerte, keine Typprüfungen
(`isinstance(x, bool)`), keine Aufrufzähler, keine Objekt-Identitäten, kein
Quelltext, der sich selbst liest. Wenn ein Test nur deshalb bricht, weil eine
Funktion umbenannt wurde, prüft er das Falsche.

Die einzige Ausnahme steht als solche markiert in
`tests/test_release_guards.py`: Prüfungen auf Dateien, die sonst still bis zum
Nutzer durchgehen.

Ein Test läuft in Millisekunden. Kostet er eine Sekunde, gehört das Teure in ein
Fixture, das sich mehrere Tests teilen.

## Daten

Datenklassen sind unveränderlich:

```python
@dataclass(frozen=True)
class Shot: ...
```

Geändert wird mit `dataclasses.replace(shot, crop=box)`, nicht durch Zuweisung.
Ungültige Werte wirft der Konstruktor mit `ValueError` zurück, statt sie
stillschweigend zurechtzubiegen.

## Module

Jede Datei beginnt mit `from __future__ import annotations`. Innerhalb des
Pakets wird relativ importiert (`from .settings import Settings`).

Was rechnen kann, rechnet ohne Qt. `layout.py`, `trim.py` und `staff.py` nehmen
Zahlen und Bilder und geben Zahlen zurück — so lassen sie sich ohne Fenster
prüfen. Qt bleibt in den Dateien, die Fenster bauen.

Namen mit führendem Unterstrich sind privat (`_required_scale`). Öffentliche
Funktionen tragen Typ-Hinweise.

Zeilen bleiben unter 88 Zeichen.

## Fehler

Wo der Nutzer nichts ausrichten kann, bleibt es still — aber nie unsichtbar:

```python
except Exception as error:  # not installed, or velopack missing
    log.info("updates unavailable: %s", error)
    self._manager = None
```

Jedes Modul hält sich sein `log = logging.getLogger(__name__)`. Eine Meldung im
Fenster bekommt nur, was der Nutzer beheben kann — ein Schreibfehler beim
Export, eine unlesbare Datei.

## Commits

[Conventional Commits](https://www.conventionalcommits.org), englisch, Betreff
im Imperativ, und er nennt den Nutzen statt der Änderung:

```
feat: recompute the crop after erasing
fix: keep scanned systems together and crop them tightly
```

Nicht `feat: add crop_after_erasing()`. release-please leitet daraus die nächste
Version ab: `fix:` → Patch, `feat:` → Minor, `feat!:` → Major. Ein falsches
Präfix verschiebt die Version.
