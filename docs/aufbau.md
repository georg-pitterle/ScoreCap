# Aufbau

| Modul | Aufgabe |
|---|---|
| `settings.py` | Seitenmaße, Ränder, Schrumpffaktor |
| `model.py` | Aufnahmen, Reihenfolge, Crop, Radierungen, Undo |
| `layout.py` | Paginierung, reine Rechnung in PDF-Punkten |
| `ink.py` | wo Tinte sitzt: Zeilen- und Spaltenprofile, Notenlinien |
| `pdf.py` | PDF-Bau samt Fußzeile |
| `preview.py` | rastert dasselbe PDF für die Vorschau |
| `capture.py` | Auswahl-Overlay und Bildschirmaufnahme |
| `hotkey.py` | systemweiter Hotkey über Win32 |
| `cropdialog.py`, `settingsdialog.py` | Dialoge |
| `projectui.py` | die Frage nach ungespeicherten Aufnahmen |
| `erase.py` | malt die Radierungen weiß, wenn eine Aufnahme gerendert wird |
| `shotlist.py` | Aufnahmeliste mit Vorschaubildern |
| `staff.py` | erkennt, wo die Notenlinien eines Systems enden |
| `tasks.py` | Update-Prüfung, Scan-Import und MusicXML-Export abseits des Fensters |
| `scan.py` | Scans bereinigen, gerade stellen, in Systeme zerlegen |
| `theme.py`, `icons.py` | Farb- und Schrift-Tokens, Symbole |
| `i18n.py`, `translations/` | Sprache wählen, Übersetzungen laden |
| `optimize.py` | vorhandene PDFs verkleinern |
| `omr.py` | Noten von Audiveris erkennen lassen und als MusicXML schreiben |
| `noteheads.py` | Notenköpfe und Taktstriche eines Systems finden, als Tonhöhen-Hinweise |
| `transcript.py` | Kurznotation lesen, jeden Takt nachzählen, MusicXML schreiben |
| `voices.py` | Akkorde einer geteilten Stimme nach Stimmführung in Einzelzeilen legen |
| `reader.py` | Claude die Systeme lesen lassen, Fehler zur Korrektur zurückgeben |
| `project.py` | Projekte als `.scorecap` speichern und öffnen |
| `updater.py` | Selbst-Update über die GitHub-Releases |
| `app.py` | Hauptfenster, verdrahtet alles |
| `cli.py` | Start: Velopack-Übergabe, Symbol, Selbsttest |

Vorschau und Export teilen sich denselben Renderpfad: gebaut wird immer ein PDF,
die Vorschau zeigt genau dieses PDF. Was zu sehen ist, wird auch gedruckt.

`ink.py` und `staff.py` teilen sich eine Notenlinien-Erkennung: `scan.py`
braucht sie, um eine Seite in Systeme zu schneiden, `staff.py`, um die Enden
einer Aufnahme auf die Ränder zu legen.

`ink.py` kennt auch das Notensystem selbst — fünf Linien in gleichem Abstand —,
und `noteheads.py` liest darauf die Notenköpfe.

## MusicXML über Claude

Zwei Wege führen zu MusicXML. Audiveris (`omr.py`) erkennt alles selbst. Der
zweite teilt die Arbeit:

1. `noteheads.py` findet in jedem System Notenlinien, Taktstriche und
   Notenköpfe (gefüllt oder hohl) und rechnet ihre Höhe in Tonhöhen um — für
   Violin- und Bassschlüssel zugleich, denn den Schlüssel liest es nicht.
   Rhythmus, Vorzeichen, Bögen und Pausen sieht es nicht.
2. `reader.py` gibt die Systembilder und diese Hinweise an Claude, das daraus
   die Kurznotation schreibt (`F4:h C4:e D4:e`, `G3+Bb3:h~`, `R`). Ihre
   Grammatik steht als `NOTATION` in `transcript.py` und geht wörtlich in den
   Prompt.
3. `transcript.py` zählt jeden Takt jeder Stimme gegen die Taktart nach. Was
   nicht aufgeht, geht mit Takt und Stimme zurück an Claude, bis zu dreimal.
4. `voices.py` legt jeden Akkord einer Stimme auf Einzelzeilen (Bass 1, Bass 2
   …): jede Zeile nimmt den Ton, der ihrem letzten am nächsten liegt. Ein
   Haltebogen bleibt nur, wo die Zeile denselben Ton weitersingt.
5. `transcript.py` schreibt daraus MusicXML, eine Stimme pro Part — fertig für
   Übe-Dateien in MuseScore.

Claude läuft als `claude -p` mit dem eigenen Konto: ein Team-Plan ohne
API-Zugang reicht. Es darf nur Bilder lesen: `--tools Read` nimmt ihm jedes
andere Werkzeug, denn `--allowedTools Read` allein erspart Read nur die
Rückfrage und überlässt Bash den Einstellungen des Nutzers. Die Einstellungen,
Plugins und Hooks des Nutzers bleiben draußen
(`--setting-sources ""`) — sie liefen sonst bei jeder Lesung mit und kosteten
Kontingent. Korrekturen setzen die Sitzung mit `--resume` fort, statt alle
Bilder neu zu lesen.

Die Antwort kommt als `stream-json`, Zeile für Zeile: Jedes geöffnete
Systembild füllt den Fortschrittsbalken, und am Ende stehen Tokens, der Preis
zu API-Tarifen und — aus dem `rate_limit_event` — wie viel vom Fünf-Stunden-
und vom Wochenkontingent des Abos verbraucht ist. Das Log nennt jeden Aufruf
mit Arbeitsordner, jede Antwort mit Dauer und Verbrauch und am Ende die
gelesene Notation.

Jedes System liegt zusätzlich in vergrößerten, überlappenden Stücken im
Ordner (`system-07-zoom-2.png`, `reader.magnified`). Claude sieht ein Bild nur
bis 1568 Pixel Kantenlänge unverkleinert; ein breites System verliert darüber
Vorzeichen und Punkte. Die Stücke öffnet Claude nur, wo es unsicher ist, und
jedes geöffnete wird gezählt: Die Statuszeile nennt am Ende, wie viele Stücke
in wie vielen Systemen nötig waren, das Log nennt sie einzeln. Viele heißen:
Die Aufnahmen sind zu klein für eine sichere Lesung.

Gelesen wird in einem festen Ordner je Aufnahmen-Satz,
`%LOCALAPPDATA%\ScoreCap\claude\<Prüfsumme der Bilder>`, nicht im
Temp-Ordner der Sitzung. Stoppt das Nutzungslimit eine Lesung, merkt sich
`paused.json` dort Sitzung und Runde; `--resume` funktioniert nur aus dem
Ordner, in dem die Sitzung begann. Der nächste Export mit Claude derselben
Aufnahmen fragt, ob er dort weitermacht oder neu anfängt. Nach einer fertigen
Lesung wird der Ordner gelöscht.

Ein zweites Backend über einen API-Schlüssel braucht nur die Methode `ask` von
`reader.Backend`.
