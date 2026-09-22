# Einen falschen Systemschnitt nachträglich korrigieren

Stand 2026-09-22.

## Warum

Der Scan-Import schneidet eine Seite in Systeme, und manchmal schneidet er
falsch. Bei `assets/test_music_xml/Earth Song.pdf`, Seite 1, fällt das erste
System auseinander: Sopran und Alt werden zur einen Aufnahme, Tenor und Bass
zur nächsten. Die Prüfung in `scan._joined` sieht die Taktlinie zwischen Alt
und Tenor nicht, und der Schnitt liegt mitten im System.

Danach ist nichts mehr zu machen. Der Import speichert pro System ein eigenes
PNG — das Band — und verwirft die Seite. Der Bearbeiten-Dialog kennt nur dieses
Band, und im Band steht kein Tenor. Der Nutzer kann den Fehler sehen und nicht
beheben; der Ausweg ist, die vier Aufnahmen zu löschen und die Seite von Hand
zu fotografieren.

## Was gebaut wird

Der Bearbeiten-Dialog kann die ganze Seite zeigen, aus der eine Aufnahme kommt.
Der Crop läuft dann über die Seite statt über das Band — weit genug, um ein
zerschnittenes System wieder einzusammeln.

Kein neues Schneidewerkzeug, kein Verschmelzen, kein Prüfschritt nach dem
Import. Der Crop, den es gibt, bekommt nur mehr Bild unter sich.

## Ablauf

Aufnahme wählen, **Bearbeiten**. Im Dialog steht neben „Ganzes Bild" ein
zweiter stiller Knopf: **Ganze Seite**.

Ein Klick darauf, und dieselbe Leinwand zeigt die gereinigte, geradegestellte
Seite. Der Crop beginnt auf dem Rechteck, das dieses System schon hatte — die
Ansicht wechselt, das Bild darin bleibt zunächst dasselbe. Der Nutzer zieht die
Unterkante über das Nachbarsystem und bestätigt mit **Anwenden**: aus der
SA-Aufnahme ist eine seitenbasierte Aufnahme mit dem ganzen SATB-System
geworden. Die TB-Aufnahme löscht er.

Der Weg ist einbahnig. Zurück zum Band führt **Abbrechen**.

Der Knopf ist nur aktiv, solange die Seite vorliegt — also für Scans, die in
dieser Sitzung importiert wurden. Nach Speichern und Öffnen ist er still und
grau, mit einem Tooltip, der sagt warum.

## Datenfluss

`scan.process_page` legt die geradegestellte, geweißte Seite als eigenes PNG in
den Sitzungsordner und gibt neben den Aufnahmen eine Zuordnung zurück:
Band-Pfad → Seiten-PNG plus das Rechteck des Systems in Seitenkoordinaten.
`PageResult` und `ImportResult` tragen sie mit, `app.py` hält sie in einem Dict,
das nur in der Sitzung lebt.

Die Seite braucht kein zweites Bereinigen: `_whitened` rechnet Pixel für Pixel,
also sind die Pixel eines Bandes in der Seite dieselben wie im Band-PNG.

`Shot`, `project.py` und das Dateiformat bleiben unangetastet. Eine korrigierte
Aufnahme zeigt auf das Seiten-PNG und wird beim Speichern wie jede andere
Aufnahme mitsamt ihrem Bild ins Archiv geschrieben — die Korrektur überlebt das
Speichern, die Möglichkeit zu einer weiteren nicht.

`CropDialog` nimmt ein zweites, optionales `Shot`: die Seite. Nach dem
Umschalten liefert eine Eigenschaft `shot` die Seite statt des Bandes, und
`app.py` ersetzt damit die Aufnahme, statt nur Crop und Radierungen zu setzen.

## Was dabei verloren geht

Beim Umschalten fallen die Radierungen der Aufnahme weg. Sie sitzen in
Band-Pixeln, und ein Band wurde für sich noch einmal feinbegradigt — auf der
Seite treffen die Rechtecke daneben, um bis zu ein paar Dutzend Pixel.
Rückgängig holt sie zurück.

Ebenso entfällt für die korrigierte Aufnahme diese Feinbegradigung. Die Seite
ist als Ganze geradegestellt; was pro System noch übrig war, sind Bruchteile
eines Grades.

Beides steht im Dialog nicht als Warnung. Wer umschaltet, sieht die Seite ohne
seine weißen Rechtecke — das ist die Auskunft.

## Fehler

Fehlt das Seiten-PNG, weil der Sitzungsordner darunter weggeräumt wurde, bleibt
der Knopf grau. Ein Klick, dessen Bild sich nicht laden lässt, tut nichts und
schreibt eine Zeile ins Log; im Fenster erscheint nichts, denn der Nutzer kann
daran nichts ändern.

Ein Crop auf der Seite ist wie jeder Crop auf ihre Grenzen geklemmt
(`adjust_crop`), also kann er nie ungültig werden.

## Tests

`tests/test_scan.py`

- Ein Import legt für jede Seite mit Systemen ein Seitenbild ab, und die
  Aufnahme eines Systems ist der Ausschnitt daraus, den ihr Rechteck nennt.
- Eine Seite ohne Notenlinien meldet kein Seitenbild — sie ist schon ganz.

`tests/test_cropdialog.py`

- Ohne Seite fehlt die Möglichkeit, auf die Seite zu wechseln.
- Nach dem Wechsel liegt der Crop auf dem Rechteck des Systems, und die
  Radierungen sind fort.
- Abbrechen nach dem Wechsel lässt die Aufnahme, wie sie war.

`tests/test_scan_ui.py`

- Ein auf der Seite aufgezogener Crop nimmt das Nachbarsystem mit auf, und die
  Aufnahme zeigt danach auf das Seitenbild.
- Rückgängig stellt das Band samt seinen Radierungen wieder her.
- Nach dem Öffnen eines gespeicherten Projekts führt kein Weg auf die Seite.

`tools/update_translations.py` läuft nach den neuen Texten.
