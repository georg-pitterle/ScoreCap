# MusicXML: welcher Zuschnitt wird am besten erkannt

Messung vom 2026-09-22, Aufbau siehe
[Spec](../specs/2026-09-22-musicxml-omr-messstand-design.md). Audiveris 5.x,
Trefferquote je Stimme über die Folge aus Tonhöhe und Notenwert.

Die Oktavkorrektur unten ist eingerechnet. `*` heißt: sie konnte nicht greifen,
weil im Streifen kein Stimmname steht — die Stimme ist richtig erkannt, liegt
aber eine Oktave zu hoch.

## Ergebnis

| Variante | Zuschnitt | Dawn (Notensatz) | Earth Song (Scan) | Läufe |
|---|---|---|---|---|
| A | ganze Seite | 91 93 86 85 | **98 99 100 83** | 5 / 5 |
| B | ein System | **94 94 93 91** | 97 97 3* 84 | 11 / 16 |
| C | Notenzeile, eng | 0 0 0 0 | 0 0 0 0 | 43 / 60 |
| D | Notenzeile mit Rand | 59 49 93 90 | 98 97 3* 83 | 43 / 60 |
| E | Seite ohne Liedtext, grob | 26 29 28 24 | 13 22 32 16 | 5 / 5 |
| F | Seite ohne Liedtext, sauber | 8 23 5 17 | 15 18 5 11 | 5 / 5 |

Laufzeit: A und E rund eine Minute je Stück, B knapp zwei, D vier.

## Was das heißt

**Die Ausgangsthese hält nicht.** Eine einzelne Notenzeile wird nicht besser
erkannt als ein ganzes System. D liegt bei `Earth Song` gleichauf mit A und B
und bei `Dawn` deutlich darunter — bei vier- bis fünffacher Laufzeit, weil je
Zeile eine eigene JVM startet.

**Eng geschnitten geht gar nichts.** Variante C wurde in allen 103 Läufen
abgelehnt: Audiveris stirbt mit `ArrayIndexOutOfBoundsException` in
`DistancesBuilder`, er malt über den Bildrand hinaus. Ein Streifen braucht Luft
über und unter der Zeile, sonst stürzt die Erkennung ab.

**Der Einbruch bei D/`Dawn` ist das Zusammensetzen, nicht die Erkennung.**
Seite 5 hat 11 Notenzeilen statt der 8 der anderen Seiten — ein unvollständiges
letztes System. Damit verrutscht die Zuordnung Streifen → Stimme, Sopran und
Alt fallen auf 59 und 49 %, Tenor und Bass bleiben bei 93 und 90 %. Und das
unter besten Bedingungen: Stimmenzahl bekannt, Reihenfolge fest. In der App
wäre beides unbekannt. Wer Notenzeilen einzeln erkennt, handelt sich genau
dieses Problem ein — und gewinnt dafür nichts.

**Variante E maß erst den Radierer, F dann die Sache selbst.** E fiel auf 13 bis
32 %, aber die Zahl gehört nicht dem Liedtext, sondern dem Radierer: er rechnet starr mit `0,8 ×
Zeilenhöhe` statt den Text zu suchen und **schneidet die Buchstaben quer durch**
— obere Hälfte weiß, untere stehengeblieben. Übrig bleiben Fragmente in
Notenhöhe. Audiveris fand daraufhin 4, 3, 3, 1 und 3 Stimmen auf den fünf Seiten
statt überall vier; die Stimmzuordnung zerfiel.

Nachgemessen mit **Variante F**: ein Radierer, der die Textzeilen an ihrer
Dichte erkennt — eine Textzeile deckt einen guten Teil der Breite, ein Hals oder
ein Bogen fast nichts — und die gefundene Zeile samt Ober- und Unterlängen ganz
herausnimmt. Keine halben Buchstaben mehr. Das Ergebnis ist trotzdem schlechter:
5 bis 25 %, und Audiveris findet auf jeder Seite nur noch **eine** Stimme statt
vier.

Damit ist die Frage beantwortet, nur anders als vermutet: nicht der Text trägt
die Erkennung, sondern alles, was ein weißer Balken über die volle Breite sonst
noch mitnimmt — Systemklammer, Notenhälse nach unten, Hilfslinien-Noten, die 8
unter dem Tenorschlüssel. Wer Text wegnehmen will, muss ihn spaltenweise
nehmen, nicht zeilenweise. Für die Funktion ist das ohne Belang: die Seite
unangetastet zu lassen ist ohnehin das Beste.

**Der Tenor kommt eine Oktave zu hoch — reparierbar.** Audiveris *sieht* die 8
unter dem Violinschlüssel durchaus: beim sauberen Notensatz (`Dawn`) schreibt er
`clef-octave-change -1` und rechnet richtig. Im Scan (`Earth Song`) übersieht er
die kleine Ziffer, meldet einen blanken G-Schlüssel und legt die Stimme eine
Oktave zu hoch — 4 % statt 100 %, bei ansonsten fehlerfreien Noten.

Die Lücke lässt sich ohne Raten schließen: Audiveris liest die Stimmnamen
(`S`, `A`, `T`, `B` bzw. `Soprano` … `Bass`) korrekt mit. Heißt eine Stimme nach
Tenor, steht sie im G-Schlüssel und fehlt die Oktavangabe, war die 8 da und
wurde übersehen. Damit steigt `Earth Song` Tenor von 4 % auf **100 %**, und
`Dawn` bleibt unverändert, weil dort nichts zu reparieren ist.

Zwei Einschränkungen: der Name steht nur am ersten System eines Stücks, die
Entscheidung gehört deshalb auf die Stimme über die ganze Partitur, nicht auf
die einzelne Seite. Und bei den Streifen-Varianten B und D greift sie gar nicht,
weil im Streifen kein Stimmname mehr steht — ein weiteres Argument, die Seite
im Ganzen durchzureichen.

**Der Bass bleibt überall bei 83 bis 91 %.** Bei `Earth Song` steht dort
reichlich Rhythmusnotation mit Kreuzköpfen („ts doo"); die haben keine Tonhöhe
und können nicht getroffen werden.

## Nachtrag: Original gegen ScoreCap-Export

Zweite Messung, nachgereicht: dieselben Stücke einmal als Original-PDF und
einmal durch ScoreCap hindurch — importiert, in Systeme zerlegt, auf A4 gesetzt,
exportiert. Jeweils das ganze PDF als ein Buch an Audiveris.

| Vorlage | Dawn | Earth Song |
|---|---|---|
| Original-PDF | 90 95 85 85 | 98 100 100 83 |
| ScoreCap, Schwarz/Weiß | 86 92 84 77 | 96 97 99 83 |
| ScoreCap, Graustufen | 87 92 88 86 | 98 99 99 83 |

**Der Umweg über ScoreCap kostet nichts.** Beim Scan (`Earth Song`) liegt der
Graustufen-Export gleichauf mit dem Original, bei `Dawn` zwei bis drei Punkte
darunter — dort gibt es aber auch nichts zu bereinigen, das PDF kommt direkt aus
MuseScore. Die Bereinigung hilft Audiveris also nicht; er binarisiert selbst gut
genug. Sie schadet aber auch nicht, und das ist die Antwort, auf die es ankommt:
der Export darf die Vorlage sein.

**Graustufen schlägt Schwarz/Weiß.** Durchgehend, beim Bass von `Dawn` um neun
Punkte (86 gegen 77). Wer aus einem Projekt MusicXML zieht, sollte dafür in
Graustufen rendern, gleich welche Einstellung für den Druck gilt.

**Fallstrick beim Auslesen:** Audiveris zerlegt ein Buch in Sätze und schreibt
`.mvt1.mxl`, `.mvt2.mxl` … Wer nur die erste Datei liest, bekommt ein Bruchstück
— beim ersten Durchlauf ergab das 5 bis 8 % statt 96 bis 99 %. Alle Dateien
lesen.

## Folge für die Funktion

Die Seite durchreichen, nichts zerlegen. A und B liegen innerhalb weniger
Prozentpunkte, und B — das System — entspricht genau dem, was ScoreCap ohnehin
exportiert. Der einfachste Weg ist damit auch der beste: das fertige PDF an
Audiveris geben, das Ergebnis als `.mxl` daneben schreiben.

Zu lösen bleibt für den nächsten Entwurf:

- **Oktavierende Schlüssel**: die Regel steht (Stimmname + G-Schlüssel ohne
  Oktavangabe), sie braucht nur noch einen Platz in der Funktion. Offen bleibt,
  wie eine Stimme ohne Namen behandelt wird.
- **Mehrere Stücke in einem Heft** werden zu einer durchlaufenden Partitur.
- **Gemischte Maßstäbe** waren im Nachtrag mit drin — der ScoreCap-Export
  schrumpft Systeme unterschiedlich, und Audiveris kam damit zurecht. Die
  Sorge aus der Spec hat sich nicht bestätigt.
- **Für MusicXML in Graustufen rendern**, auch wenn der Druck auf Schwarz/Weiß
  steht.
- **Alle `.mvt*.mxl` einsammeln**, nicht nur die erste Datei.
