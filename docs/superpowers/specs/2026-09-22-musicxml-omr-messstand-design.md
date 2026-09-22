# MusicXML-Export: Messstand für den Zuschnitt

Stand 2026-09-22. Entwurf für einen Vorversuch, nicht für die Funktion selbst.

## Warum

Aus einem Heft soll MusicXML fallen, damit sich eine Stimme zum Üben abspielen
lässt — in MuseScore oder auf dem Tablet, nicht in ScoreCap. Gehört wird
anderswo; ScoreCap schreibt nur die Datei.

Gemessen wird deshalb nur, was man hört: **Tonhöhe und Notenwert**. Liedtext,
Dynamik, Artikulation, Bögen bleiben außen vor. Liedtext darf sogar
verschwinden, bevor die Erkennung ihn sieht.

Die Erkennung selbst macht Audiveris. Mitgeliefert wird es nicht: es steht unter
AGPL-3.0 und brächte mit seiner Java-Laufzeit 300–400 MB neben die heutigen
152 MB. ScoreCap ruft auf, was installiert ist, und bleibt sonst still.

Offen ist nur eines, und genau das entscheidet über die ganze Funktion: **was
bekommt Audiveris vorgelegt?** Die Erfahrung sagt, eine einzelne Notenzeile
werde besser erkannt als ein ganzes System. Stimmt das, muss ScoreCap zerlegen
und die Ergebnisse wieder zusammensetzen — deutlich mehr Arbeit als eine Seite
durchzureichen. Das ist eine Messung wert, bevor irgendetwas gebaut wird.

## Was gebaut wird

Ein Wegwerf-Skript im Scratchpad. Kein Code in `scorecap/`, kein Test, kein
Menüpunkt. Ergebnis ist eine Tabelle.

## Material

Unter `assets/test_music_xml/`, nicht im Repo — die Noten gehören uns nicht.

| Datei | Rolle |
|---|---|
| `Earth Song.pdf` | gescannt, der Realfall, für den ScoreCap da ist |
| `Earth_Song.mxl` | Wahrheit dazu |
| `Dawn.pdf` | direkt aus MuseScore, sauberer Notensatz |
| `Dawn.mxl` | Wahrheit dazu |

Beide werden gemessen: der Scan sagt, was die Funktion im Alltag leistet, der
saubere Satz trennt Fehler der Vorlage von Fehlern der Erkennung.

## Varianten

| | Input je Audiveris-Lauf |
|---|---|
| A | ganze A4-Seite |
| B | ein System |
| C | eine Notenzeile, eng geschnitten |
| D | eine Notenzeile mit Rand nach oben und unten |
| E | ganze Seite, Liedtext weiß übermalt |

Geschnitten wird mit ScoreCaps eigenen Mitteln — `scan.find_systems` für B, die
Notenlinien aus `ink.py` für C und D. Kein neuer Erkennungscode für den Versuch.

## Ablauf

1. PDF-Seiten mit PyMuPDF rastern.
2. Je Variante die Streifen schneiden und als PNG ablegen.
3. Je Streifen `bin\Audiveris.bat -batch -export -output <ordner> -- <datei>`.
4. Aus jedem `.mxl` je Stimme die Folge `(Tonhöhe, Notenwert)` ziehen, Pausen
   zählen mit. Gelesen wird mit `zipfile` und `ElementTree` — für zwei Angaben
   je Note braucht es keine Notenbibliothek.
5. Dieselbe Folge aus der Wahrheit ziehen und abgleichen.

## Maßstab

Trefferquote je Stimme über einen Sequenzabgleich der beiden Folgen
(`difflib.SequenceMatcher`), dazu die Laufzeit. Ausgabe eine Tabelle
Variante × Stimme.

Ein Abgleich statt eines Vergleichs Position für Position, weil eine einzelne
zuviel erkannte Note sonst alles danach als falsch zählt.

Die Zuordnung Streifen → Stimme ist bei C und D durch die Schnittreihenfolge
bekannt, bei A, B und E durch die Reihenfolge der Parts im Ergebnis.

## Woran es scheitern kann

- **Audiveris nimmt schmale Streifen nicht an.** Der erste Punkt, der zu prüfen
  ist: fällt er aus, sind C und D erledigt und die Frage ist beantwortet.
- **Taktzählung je Lauf.** Bei C und D zählt jeder Streifen für sich. Für die
  Messung egal, für ein späteres Zusammensetzen der Knackpunkt — die Tabelle
  sagt, ob sich der Aufwand lohnt.
- **Laufzeit.** Die Java-Laufzeit startet je Aufruf neu; bei zwanzig Notenzeilen
  sind das Minuten statt Sekunden.
- **Gemischte Maßstäbe.** Bei A und E stehen unterschiedlich geschrumpfte
  Systeme auf einer Seite; Audiveris schätzt daraus die Notenzeilenhöhe.

## Was der Versuch entscheidet

Gewinnt A oder E, reicht es, die fertige Seite durchzureichen — die Funktion ist
klein. Gewinnen C oder D deutlich, braucht ScoreCap Zerlegen und
Zusammensetzen, und der nächste Entwurf dreht sich um die Taktzählung über
Streifengrenzen hinweg.

Voraussetzung: Audiveris in der Konsolen-Variante installiert. Auf dem Rechner
liegt bisher weder Audiveris noch Java.
