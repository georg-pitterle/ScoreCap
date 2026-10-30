# ScoreCap

Macht aus Noten auf dem Bildschirm ein Heft fürs Pult.

ScoreCap ist ein Windows-Programm für Musikerinnen, Musiker und Chöre, deren
Noten im Browser, als PDF oder als Scan vorliegen. Es nimmt Notensysteme per
Hotkey vom Bildschirm auf, stapelt sie bündig auf A4-Seiten und exportiert ein
druckfertiges PDF. Auf Wunsch wird aus denselben Aufnahmen eine MusicXML-Datei
zum Üben.

## Was es kann

- **Aufnehmen, ohne den Lesefluss zu unterbrechen.** Der Browser behält den
  Fokus, eine Serie läuft mit Hotkey und Maus durch die ganze Partitur, und eine
  misslungene Aufnahme lässt sich sofort wiederholen.
- **Seiten, die so gedruckt werden, wie sie aussehen.** Vorschau und Export
  kommen aus demselben PDF. Weiße Ränder fallen weg, Notenlinien stehen bündig.
- **Scans aufräumen.** Papier wird weiß, Schräglagen werden gerade gestellt, und
  jede Seite zerfällt in ihre Systeme.
- **Nachbessern, ohne etwas zu zerstören.** Zuschnitte und Radierungen bleiben
  Angaben neben dem Original und lassen sich jederzeit ändern.
- **Als Projekt weiterarbeiten.** Eine `.scorecap`-Datei hält alle Aufnahmen in
  voller Auflösung zusammen.
- **Noten hörbar machen.** Audiveris oder Claude lesen die Partitur als MusicXML.
  Mit Claude wird jede geteilte Stimme eine eigene Zeile, die Klavierbegleitung
  kommt mit, und jeder Takt wird nachgezählt. Das reicht zum Üben, ersetzt aber
  nicht das Gegenlesen.

Die Oberfläche gibt es auf Deutsch und Englisch, hell und dunkel, und sie lässt
sich auch ohne Maus bedienen.

## Installieren

`ScoreCap-win-Setup.exe` von den
[Releases](https://github.com/georg-pitterle/ScoreCap/releases) laden und
ausführen. Die Anwendung ist nicht signiert, Windows warnt deshalb beim ersten
Start; über *Weitere Informationen → Trotzdem ausführen* startet sie. Updates
kommen danach von selbst.

Für den MusicXML-Export braucht es zusätzlich
[Audiveris](https://github.com/Audiveris/audiveris/releases) oder
[Claude Code](https://claude.com/claude-code).

## Weiterlesen

| | |
|---|---|
| [docs/bedienung.md](docs/bedienung.md) | die Anleitung: Aufnehmen, Scans, Projekte, MusicXML |
| [docs/verarbeitung.md](docs/verarbeitung.md) | Weiße Ränder, Layout, bündige Notenlinien, Dateigröße |
| [docs/aufbau.md](docs/aufbau.md) | welches Modul was tut |
| [docs/entwicklung.md](docs/entwicklung.md) | aus dem Quellcode starten, Tests, Übersetzen, Debuggen, Paket bauen |
| [docs/release.md](docs/release.md) | wie aus `main` ein Release wird |
| [AGENTS.md](AGENTS.md) | Programmierstil im Projekt |
