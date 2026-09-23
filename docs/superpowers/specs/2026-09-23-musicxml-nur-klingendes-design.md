# MusicXML auf das Klingende eindampfen

Stand 2026-09-23. Ergänzt [den MusicXML-Export](2026-09-22-musicxml-export-design.md)
und widerruft dessen Satz, Liedtext und Dynamik kämen mit, wie Audiveris sie
liefert.

## Warum

Die Datei ist zum Hören da. Was Audiveris liefert, ist aber eine vollständige
Partitur: Halsrichtungen, Balken, Seitenumbrüche, Liedtext, Akkordsymbole —
Dinge, die beim Abspielen nichts beitragen und die die Erkennung obendrein am
häufigsten falsch hat. An `Earth Song` gemessen sind das die Hälfte der Datei:
472 KB und 12245 Elemente, von denen 923 Noten sind.

Was wegfällt, kann auch nicht falsch sein. Ein Liedtext, den die Erkennung
verrutscht hat, steht sonst im MuseScore-Fenster unter den falschen Noten.

## Was fliegt

| | |
|---|---|
| `stem`, `beam` | Halsrichtung und Balken — reine Schreibweise |
| `accidental` | die gezeichnete Versetzung; die klingende steht in `alter` |
| `notations` | samt `tied`, `slur`, `articulations`, `staccato` |
| `lyric` | 675 Silben, die nicht klingen |
| `harmony` | Akkordsymbole; MuseScore spielt sie standardmäßig nicht |
| `print`, `system-layout`, `staff-layout`, `staff-details` | Umbrüche und Abstände |
| `defaults`, `credit` | Seitenmaße und Titelblock |
| `bar-style` | wie ein Taktstrich aussieht |
| `direction` ohne Tempo | auch Dynamik und Pedal: siehe unten |
| Inhalt von `rest` | `display-step`, `display-octave`: wo die Pause sitzt |

## Was bleibt, obwohl es nach Beiwerk aussieht

`tie` — nicht zu verwechseln mit `tied`: das eine bindet den Ton, das andere
zeichnet den Bogen. `time-modification` trägt die Dauer einer Triole.
`chord` macht aus zwei Noten einen Zusammenklang statt einer Folge.
`backup` und `forward` halten mehrstimmige Takte zusammen. Ein `barline` bleibt,
wenn `repeat` oder `ending` darin steht — eine Wiederholung ändert, was gespielt
wird.

Ein `direction` bleibt nur für **Tempo** (`metronome`) oder einen **Sprung**
(`sound` mit `tempo`, `dacapo`, `segno`, `coda`, `tocoda`, `fine`). Nicht „wenn
ein `sound` darin steht": eine Dynamikangabe trägt `<sound dynamics="96"/>` und
rutschte durch eine so gefasste Regel hindurch, obwohl sie gehen soll. Dasselbe
gilt fürs Pedal mit seinem `damper-pedal`.

`attributes` bleibt ganz. Divisions, Taktart, Tonart und Schlüssel sind
zusammen 60 Elemente; ohne Schlüssel wäre die Datei in MuseScore nicht mehr
lesbar, und gewonnen wäre nichts.

## Wirkung

Gemessen an `Earth Song`, fünf Seiten, vier Stimmen:

| | vorher | nachher |
|---|---|---|
| Größe | 472 KB | 225 KB |
| Elemente | 12245 | 6947 |
| Stimmen | 4 | 4 |
| Treffer S/A/T/B | 99 / 100 / 100 / 83 % | 99 / 100 / 100 / 83 % |

Die Trefferquote ist dieselbe, und das ist der Beweis: entfernt wurde nichts,
was Tonhöhe oder Notenwert trägt.

Ein Tempo steht in dieser Datei nicht — Audiveris hat das „♩ = ca. 68" der
Vorlage nicht als solches gelesen, sondern als Text. Die Regel für `direction`
greift hier also ins Leere; die Datei spielt in MuseScores Voreinstellung. Das
ist eine Grenze der Erkennung und kein Verlust dieses Schritts.

## Aufbau

Eine Funktion in `omr.py`:

```python
def playable_only(score: ElementTree.Element) -> ElementTree.Element
```

Aufgerufen in `transcribe`, nach `fix_octave_clefs` und vor dem Schreiben. Qt-frei,
Baum hinein, Baum heraus — wie der Rest des Moduls.

Kein Schalter, keine Einstellung. Die Funktion heißt „zum Üben hören"; wer die
volle Partitur will, hat sie als Noten vor sich.

## Tests

- Tonhöhen und Notenwerte einer Stimme überstehen die Bearbeitung unverändert.
- Ein Taktstrich mit Wiederholung bleibt, einer mit bloßem Stil verschwindet.
- `tie` bleibt, `tied` geht.
- Eine Triole behält ihre Dauer.
- Liedtext, Halsrichtungen und Seitenumbrüche sind danach nicht mehr da.
- Eine Anweisung mit Tempo bleibt, eine ohne verschwindet.

## Was nicht dazugehört

- **Keine Reparatur.** Was Audiveris falsch gelesen hat, bleibt falsch; hier
  wird nur weggelassen, nie geraten.
- **Keine zweite Ausgabe.** Es gibt nicht zusätzlich eine vollständige Datei.
