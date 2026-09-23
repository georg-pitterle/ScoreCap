# ScoreCap

Bildschirmbereiche per Hotkey aufnehmen, bündig auf A4 stapeln, als PDF exportieren.

Gedacht für Noten: was im Browser oder auf dem Scanner liegt, wird zu einem
Heft, das sich ausdrucken und aufs Pult legen lässt.

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
- ***Jetzt neu starten*:** sofort umsteigen. Sind Aufnahmen noch nicht
  gespeichert, fragt ScoreCap vorher, ob sie gespeichert werden sollen.

Ohne Internet oder bei einem Fehler passiert nichts Sichtbares. Was geschehen
ist, steht in `%LocalAppData%\ScoreCap\logs\scorecap.log`.

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
- Links die Aufnahmen: per Drag&Drop sortieren, *Neu aufnehmen*, *Bearbeiten*,
  *Löschen*. Doppelklick auf einen Eintrag öffnet das Bearbeiten. `Strg+Z`
  macht rückgängig.
- *Bearbeiten* kennt zwei Werkzeuge und öffnet mit dem *Radierer*, weil der
  öfter gebraucht wird: ein gezogenes Rechteck wird weiß übermalt — für
  Seitenzahlen, Bleistiftspuren und anderes Störende. *Radierung zurück* nimmt
  das letzte wieder weg. Danach wird der Zuschnitt neu gerechnet: was weiß
  geworden ist, zählt als Rand und fällt weg. Enger wird er dabei, nie wieder
  weiter — was einmal weggeschnitten war, bleibt draußen.
- Auf *Zuschneiden* umgeschaltet lässt sich ein vorhandener Rahmen nachbessern,
  statt ihn neu aufzuziehen: an den Ecken oder Kanten ziehen ändert die Größe,
  im Rahmen ziehen verschiebt ihn, außerhalb ziehen zeichnet einen neuen. Ohne
  Rahmen lassen sich die Bildkanten selbst hereinziehen.
- Rechts die A4-Seiten, exakt so, wie sie exportiert werden. Ein Klick auf
  eine Aufnahme dort markiert sie links in der Liste.
- *Als PDF exportieren* schreibt die Datei.

## Projekte speichern

*Speichern* (`Strg+S`) legt alle Aufnahmen als Projekt ab: eine einzelne Datei
`Name.scorecap` mit den Original-Screenshots in voller Auflösung, ihrer
Reihenfolge und den Zuschnitten. *Öffnen …* (`Strg+O`) holt sie zurück, um
weiterzuarbeiten oder neu zu exportieren; *Speichern unter* liegt auf `F12`
(`Strg+Umschalt+S` ist der Aufnahme-Hotkey).

Die Dateidialoge öffnen im zuletzt benutzten Ordner, getrennt nach Projekten,
Scans und PDFs, auch nach einem Neustart.

Ungespeicherte Aufnahmen gehen nicht still verloren: Beim Schließen, beim
Öffnen eines anderen Projekts und beim Update-Neustart fragt ScoreCap
„Speichern / Nicht speichern / Abbrechen". Die Titelleiste zeigt Projektname
und ein `*` für ungespeicherte Änderungen.

Gespeichert wird zuerst in eine Hilfsdatei, die erst am Ende die alte ersetzt —
bricht das Speichern ab, bleibt die vorige Fassung heil. Die Einstellungen
(Ränder, Fußzeile, …) gehören nicht zum Projekt, sie gelten für alle.

## Scans importieren

Statt Bildschirmbereiche aufzunehmen, lassen sich auch gescannte Noten
verarbeiten: mit der üblichen Scanner-Software als PDF oder Bild (PNG, JPG,
TIFF, BMP) speichern, dann *Scans importieren …* oder die Dateien einfach ins
Fenster ziehen. Auch mehrseitige PDFs und TIFFs sowie Handy-Scans gehen.

ScoreCap bereinigt jede Seite und zerlegt sie in Systeme:

- **Papier wird weiß.** Vergilbung, ungleichmäßige Belichtung und der Schatten
  am Buchrücken werden herausgerechnet, dunkle Scanränder entfernt.
- **Schräglage wird gerade gestellt** — erst die ganze Seite, dann jedes System
  noch einmal für sich. Maßstab sind die Notenlinien.
- **Jedes System wird eine Aufnahme.** Notensysteme, die links ein gemeinsamer
  Taktstrich verbindet, bleiben zusammen (Klavier, Chor). Liedtext und Dynamik
  kommen zum richtigen System, Titel, Kopfzeilen und Seitenzahlen bleiben
  außen vor. Den Titel holt *Bearbeiten* zurück: jede Aufnahme enthält den
  ganzen Streifen der Seite bis zum Nachbarsystem, der obere Rand des Rahmens
  lässt sich einfach hochziehen.
- Eine Seite ohne Notenlinien — Titelblatt, Text — wird ganz übernommen, eine
  leere übersprungen. Die Statuszeile sagt, welche.

Ein Import lässt sich mit einem `Strg+Z` zurücknehmen. Scans werden in
Graustufen abgelegt; erst Vorschau und Export entscheiden nach der Einstellung
*Scans drucken in*: *Schwarz/Weiß* (Standard) ergibt die kleinsten PDFs — bei
fünf Seiten rund 1,3 statt 2 MB — und wird auf doppelter Auflösung gerechnet,
damit Notenköpfe rund statt treppig werden. *Graustufen* macht das Papier weiß
und die Tinte satt und behält nur an den Kanten einen weichen Übergang; das
glättet am meisten und rettet blasse Striche. Umstellen
wirkt sofort, auch auf schon importierte und gespeicherte Scans;
Bildschirmaufnahmen bleiben immer in Graustufen. Gebogene
Linien einer stark gewölbten Buchseite werden nicht entzerrt; flach auflegen
hilft.

## Als MusicXML exportieren

Wer eine Stimme zum Üben hören will, braucht sie als Datei: *Als MusicXML
exportieren …* liest die Noten aus dem Heft und schreibt sie als
`.musicxml`, das MuseScore und die üblichen Tablet-Apps öffnen und abspielen.

Die Erkennung übernimmt [Audiveris](https://github.com/Audiveris/audiveris/releases),
ein eigenes freies Programm; ScoreCap liefert es nicht mit. Fehlt es, sagt
ScoreCap beim Druck auf den Knopf, was zu tun ist.

Gemessen wurden 85 bis 100 % der Töne und Notenwerte je Stimme — genug zum
Üben, nicht genug zum blinden Vertrauen. Gerechnet wird eine Weile — rund
fünfzehn Sekunden je Seite —; die Statuszeile zählt die Seiten mit, und das
Fenster bleibt bedienbar. Mehrere Stücke in einem Heft werden eine
durchlaufende Partitur.

**In der Datei steht nur, was klingt.** Tonhöhen, Notenwerte, Pausen,
Haltebögen, Triolen, Wiederholungen und Tempo — und sonst nichts. Liedtext,
Akkordsymbole, Dynamik, Artikulation, Halsrichtungen und Seitenumbrüche bleiben
draußen: sie tragen zum Klang nichts bei, und die Erkennung hat sie am
häufigsten falsch. Bei `Earth Song` halbiert das die Datei von 472 auf 225 KB,
ohne einen einzigen Ton zu ändern. Wer die Noten lesen will, liest sie im
PDF-Export.

**Vorher die Systemschnitte prüfen.** Audiveris legt die Zahl der Stimmen am
ersten System fest. Ist dort ein vierstimmiges System in zwei Hälften
zerschnitten, bekommt die ganze Datei zwei Stimmen statt vier, und die Noten
landen in den falschen. Ein solcher Schnitt ist im Bearbeiten-Dialog mit
*Ganze Seite* zu richten; danach stimmt der Export. An `Earth Song` gemessen:
99, 100, 100 und 83 % mit geradem Schnitt, gegen zwei unbrauchbare Stimmen
ohne.

## Oberfläche

Die Palette kommt aus dem Notendruck: ein einziger Akzent im tiefen Ultramarin
der Urtext-Ausgaben, warme Neutraltöne für die Flächen, und das einzige kräftige
Schwarz auf dem Bildschirm sind die Noten selbst. Die Vorschau zeigt die Seiten
als Druckfahne — Papier mit Blattkante auf dunkler Fläche, Seitenzahl im
Bundsteg. Schrift ist Segoe UI Variable, Zahlen stehen in Cascadia Mono mit
Tabellenziffern untereinander, Symbole kommen aus Segoe Fluent Icons. Hell und
Dunkel folgen der Windows-Einstellung.

## Sprache

ScoreCap gibt es auf Deutsch und Englisch. Es nimmt die erste Sprache aus der
Windows-Spracheinstellung, für die es eine Übersetzung gibt, sonst Englisch. In
den Einstellungen lässt sich unter *Sprache* eine feste Sprache wählen; sie gilt
ab dem nächsten Start. Auch Zahlen, Tastenkürzel (`Strg+O` / `Ctrl+O`) und die
Fußzeile im PDF („1 von 3“ / „1 of 3“) folgen der Sprache.

## Weiterlesen

| | |
|---|---|
| [docs/verarbeitung.md](docs/verarbeitung.md) | Weiße Ränder, Layout, bündige Notenlinien, Dateigröße |
| [docs/aufbau.md](docs/aufbau.md) | welches Modul was tut |
| [docs/entwicklung.md](docs/entwicklung.md) | aus dem Quellcode starten, Tests, Übersetzen, Debuggen, Paket bauen |
| [docs/release.md](docs/release.md) | wie aus `main` ein Release wird |
| [docs/manual-test.md](docs/manual-test.md) | manueller Abnahmetest |
| [AGENTS.md](AGENTS.md) | Programmierstil im Projekt |
