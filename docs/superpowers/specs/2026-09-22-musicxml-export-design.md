# MusicXML exportieren

Stand 2026-09-22. Baut auf der Messung in
[2026-09-22-omr-ergebnisse.md](../notes/2026-09-22-omr-ergebnisse.md) auf.

## Wofür

Wer eine Chorstimme lernen will, braucht sie zum Hören. ScoreCap gibt dafür
MusicXML aus; abgespielt wird in MuseScore oder auf dem Tablet. ScoreCap selbst
bleibt stumm — kein Player, kein Audio, keine Mischung.

Gemessen wurde, was dabei ankommt: 85 bis 100 % der Töne und Notenwerte je
Stimme. Das reicht zum Üben und nicht zum blinden Vertrauen; wer eine Stimme
danach einstudiert, sollte sie gegen die Noten hören.

## Wie

Erkannt wird mit **Audiveris**, das der Nutzer selbst installiert. Mitgeliefert
wird es nicht: AGPL-3.0, und mit seiner Java-Laufzeit brächte es 300–400 MB
neben die heutigen 152 MB.

Vorgelegt wird ihm **das Heft als PDF, wie ScoreCap es setzt** — ein System je
Zeile, gerade, weiß, in Lesereihenfolge. Die Messung hat gezeigt: zerlegen
bringt nichts, die Bereinigung schadet nicht, und Graustufen erkennt sich besser
als Schwarz/Weiß.

## Ablauf

1. Der Nutzer drückt *Als MusicXML exportieren …* und wählt einen Dateinamen.
2. ScoreCap baut dasselbe Layout wie für den Druck, aber in Graustufen und ohne
   Fußzeile, und legt es als PDF in den Sitzungsordner.
3. Audiveris läuft im Hintergrund darüber. Das Fenster bleibt bedienbar, die
   Statuszeile zählt mit, ein *Abbrechen* hält an.
4. Die geschriebenen Sätze werden zu einer Datei zusammengefügt, der übersehene
   Oktavschlüssel korrigiert, das Ergebnis unter dem gewählten Namen abgelegt.

Fehlt Audiveris, bleibt der Knopf sichtbar und erklärt beim Druck in einem
Dialog, was fehlt, mit Link auf die Installationsseite. Wer die Funktion nicht
kennt, soll von ihr erfahren.

## Entscheidungen

**Graustufen, immer.** Auch wenn *Scans drucken in* auf Schwarz/Weiß steht. In
der Messung lag Graustufen durchgehend vorn, beim Bass um neun Punkte. Die
Einstellung gilt dem Druck, nicht der Erkennung.

**Ohne Fußzeile.** „1 von 3" unter den Systemen ist für Audiveris nur Text an
einer Stelle, an der sonst Liedtext steht.

**Eine Datei.** Audiveris zerlegt ein Heft in Sätze und schreibt `.mvt1.mxl`,
`.mvt2.mxl` … Der Nutzer hat einen Namen gewählt und bekommt genau den: die
Sätze werden hintereinandergehängt. Zum Üben will man eine durchlaufende Datei
abspielen, keine Schnipsel sortieren.

**Oktavschlüssel still korrigieren.** Audiveris übersieht im Scan die kleine 8
unter dem Tenorschlüssel und legt die Stimme eine Oktave zu hoch — jede Note
richtig, die Lage falsch. Heißt eine Stimme nach Tenor, steht sie im
G-Schlüssel und fehlt die Oktavangabe, wird sie eine Oktave tiefer gelegt und
die Angabe nachgetragen. In der Messung: 4 % auf 100 %, und wo Audiveris den
Schlüssel selbst erkennt, ändert sich nichts. Ohne Stimmnamen bleibt alles wie
erkannt — geraten wird nicht.

**Kein Zugriff auf das Ergebnis in ScoreCap.** Die Datei wird geschrieben, mehr
nicht. Noten anzeigen, abspielen oder bearbeiten ist Sache des Programms, das
sie öffnet.

## Aufbau

| Modul | Aufgabe |
|---|---|
| `omr.py` (neu) | Audiveris finden und aufrufen, Sätze zusammenfügen, Oktave richten |
| `tasks.py` | `MusicXmlExport` als Hintergrundaufgabe, wie `ScanImport` |
| `app.py` | Knopf, Dateidialog, Statuszeile, der Hinweis ohne Audiveris |
| `pdf.py` | unverändert; der Graustufen-Render entsteht über eigene `Settings` |

`omr.py` kommt ohne Qt aus: Pfade hinein, Pfad hinaus, Fehler als Ausnahme. So
lässt es sich ohne Fenster prüfen, wie `layout.py` und `scan.py`.

Audiveris wird gesucht über `AUDIVERIS_HOME`, dann an den üblichen Stellen
(`%ProgramFiles%\Audiveris\Audiveris.exe`, daneben die alte Form
`bin\Audiveris.bat`). Gefunden wird einmal je Aufruf, nicht beim Start — eine
Installation soll ohne Neustart wirken.

## Fehler

| Fall | Was der Nutzer sieht |
|---|---|
| Audiveris fehlt | Dialog: was fehlt, wozu es dient, Link zur Installation |
| Audiveris bricht ab | Dialog mit der letzten Zeile aus seinem Log, Rest im ScoreCap-Log |
| Nichts erkannt | Meldung, dass keine Noten gefunden wurden — kein leeres MusicXML |
| Schreiben schlägt fehl | Wie beim PDF-Export: Dialog mit dem Fehler des Systems |
| Nutzer bricht ab | Statuszeile „Abgebrochen", keine halbe Datei |

Geschrieben wird wie beim Projekt: erst eine Hilfsdatei, die am Ende die alte
ersetzt. Bricht es ab, bleibt die vorige Fassung heil.

## Tests

Geprüft wird Verhalten, ohne Audiveris auf dem Rechner:

- Zwei Sätze werden zu einer Datei mit allen Takten beider.
- Eine Tenorstimme ohne Oktavangabe klingt nach dem Export eine Oktave tiefer.
- Eine Stimme, deren Schlüssel die Oktave schon nennt, bleibt unverändert.
- Eine Stimme ohne Namen bleibt unverändert.
- Fehlt Audiveris, erklärt ein Dialog warum, und es entsteht keine Datei.
- Ein Abbruch hinterlässt die vorige Datei unversehrt.

Der Aufruf selbst wird untergeschoben, nicht ausgeführt: ein Test läuft in
Millisekunden, kein Test startet eine JVM.

## Was nicht dazugehört

- **Mehrere Stücke in einem Heft** werden eine durchlaufende Partitur. Wer zwei
  Lieder in einem Projekt hat, bekommt sie in einer Datei hintereinander.
- **Liedtext, Dynamik, Artikulation** kommen mit, wie Audiveris sie liefert —
  gemessen wurde an ihnen nichts. *Überholt am 2026-09-23: sie kommen nicht
  mehr mit, siehe [nur Klingendes](2026-09-23-musicxml-nur-klingendes-design.md).*
- **Keine Korrektur in ScoreCap.** Wer Fehler sieht, bessert sie in MuseScore
  nach.
