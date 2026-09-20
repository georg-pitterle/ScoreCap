# Wie ScoreCap die Seiten baut

Was zwischen einer Aufnahme und der fertigen PDF-Seite passiert, und welche
Stellschrauben es dafür gibt.

## Weiße Ränder

Jede Aufnahme wird beim Anlegen automatisch auf ihren Inhalt beschnitten: alles
heller als 245 gilt als Hintergrund, um den Rest bleiben 2 px Luft. Beschnitten
wird nur als Rechteck, die PNG-Datei bleibt unangetastet — *Bearbeiten →
Ganzes Bild* holt den vollen Screenshot zurück, und ein selbst gezogener
Zuschnitt wird beim Anlegen nie überschrieben. Eine leere, ganz weiße Aufnahme
bleibt wie sie ist.

Dieselbe Rechnung läuft noch einmal, sobald etwas wegradiert wurde — diesmal
innerhalb des bestehenden Zuschnitts, der dadurch nur enger werden kann.
Beides ist in den Einstellungen abschaltbar; dann bleibt der Zuschnitt auch
nach dem Radieren stehen.

Das spart Seiten: zwölf Notenzeilen mit großzügigem Weißraum brauchen ohne Trim
zwei Seiten, mit Trim eine.

## Layout

Jede Aufnahme wird auf die Inhaltsbreite skaliert und untereinander gesetzt.
Passt eine weitere Aufnahme knapp nicht mehr, wird die ganze Seite einheitlich
verkleinert, höchstens bis zum eingestellten Schrumpffaktor (Standard 0,85).
Das spart Seiten, ohne die Noten unlesbar zu machen. Aufnahmen unter 120 dpi
markiert die Liste als niedrige Druckqualität; dann im Browser hineinzoomen und
neu aufnehmen.

## Bündige Notenlinien

Zeichen hinter dem Ende eines Systems — etwa die Pfeile, die eine Teilung im
nächsten System ankündigen — und vor seinem Anfang — eine geschweifte Klammer,
die Stimmen zusammenfasst — gehören mit auf die Aufnahme. Würde die ganze
Aufnahme auf Satzbreite gebracht, begännen oder endeten die Notenlinien dieses
Systems anders als die aller anderen, und das System wäre kleiner. ScoreCap
erkennt deshalb, wo die Notenlinien beginnen und enden, legt beides auf die
Satzränder und lässt alles davor und dahinter in den Seitenrand ragen, wie im
Notensatz üblich.

Erkannt wird ein System an mindestens fünf Linien, die über mehr als die Hälfte
der Aufnahme laufen. Ohne erkanntes System bleibt es beim Einpassen der ganzen
Aufnahme; käme ein Überstand näher als 3 mm an die Blattkante, gilt das für
diese Seite. Stimmnamen vor dem ersten System sind dafür meist zu breit — es
bleibt dann eingerückt, wie im Notensatz. Abschaltbar in den Einstellungen.

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
