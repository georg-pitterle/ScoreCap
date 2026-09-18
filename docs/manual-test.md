# Manueller Abnahmetest

Voraussetzung: `python -m scorecap` läuft, ein Browser mit einer mehrzeiligen
Partitur ist geöffnet.

1. **Button friert nichts ein.** Im Fenster auf *Aufnahme vorbereiten* klicken.
   Erwartet: ScoreCap geht aus dem Weg, ein Hinweis nennt den Hotkey, der
   Bildschirm bleibt normal bedienbar — Browser scrollen und Fenster wechseln
   geht weiterhin. Erst der Hotkey dunkelt ab.
2. **Vorbereitetes Neu aufnehmen.** Eintrag wählen, *Neu aufnehmen*, dann zum
   Browser wechseln, scrollen, Hotkey, Rechteck ziehen.
   Erwartet: Bild wird an derselben Listenposition ersetzt, Fenster kommt zurück.
3. **Hotkey über fremdem Fenster.** Browser fokussieren, `Ctrl+Shift+S` drücken.
   Erwartet: Bildschirm dunkelt ab, Fadenkreuz erscheint.
4. **Auswahl.** Rechteck über eine Notenzeile ziehen und loslassen.
   Erwartet: ScoreCap kommt nach vorn, die Aufnahme steht in der Liste und auf
   der Vorschauseite.
5. **Serienaufnahme.** Ohne das Fenster anzufassen: Hotkey, ziehen, im Browser
   weiterscrollen, Hotkey, ziehen — zehnmal hintereinander.
   Erwartet: ScoreCap bleibt minimiert, der Browser behält Fokus und
   Scrollposition, nach jeder Aufnahme erscheint kurz „Aufnahme N", jeder
   Hotkey greift sofort.
6. **Rückkehr über Taskleiste.** Nach der Serie ScoreCap aus der Taskleiste
   holen.
   Erwartet: Vorschau enthält alle Aufnahmen der Serie in der richtigen
   Reihenfolge.
7. **Abbruch.** Hotkey drücken, `Esc` drücken.
   Erwartet: keine neue Aufnahme, keine Fehlermeldung, Fenster kommt zurück.
8. **Zu kleine Auswahl.** Hotkey drücken, nur wenige Pixel ziehen.
   Erwartet: keine neue Aufnahme, keine Fehlermeldung.
9. **Weißer Rand.** Bewusst großzügig um eine Notenzeile herum auswählen, mit
   viel Weiß über und unter den Noten.
   Erwartet: in der Vorschau sitzt die Zeile ohne den weißen Rand auf der Seite;
   *Zuschneiden → Ganzes Bild* zeigt wieder den vollen Screenshot. Mit
   abgeschaltetem Auto-Trim in den Einstellungen bleibt der Rand erhalten.
10. **Seitenfüllung.** So viele Zeilen aufnehmen, bis eine zweite Seite beginnt.
   Erwartet: Seite eins ist gleichmäßig gefüllt, nichts überlappt, alle Bilder
   haben dieselbe Breite.
10a. **Systemende mit Teilungspfeil.** Ein System aufnehmen, hinter dessen
    Ende Teilungspfeile stehen, dazu ein System ohne.
    Erwartet: die Notenlinien beider Systeme enden auf derselben Höhe am
    rechten Satzrand, die Pfeile stehen außerhalb im Seitenrand. Mit
    abgeschaltetem „Systemenden bündig ausrichten" enden die Linien des
    Pfeil-Systems wieder früher.
11. **Umsortieren.** Einen Eintrag in der Liste an eine andere Position ziehen.
   Erwartet: Vorschau folgt der neuen Reihenfolge.
12. **Neu aufnehmen.** Eintrag wählen, *Neu aufnehmen*, neues Rechteck ziehen.
   Erwartet: Bild wird an derselben Listenposition ersetzt.
13. **Zuschneiden.** Eintrag wählen, *Zuschneiden*, Rechteck ziehen, OK.
    Erwartet: außerhalb der Auswahl dunkelt das Bild ab, die Vorschau zeigt den
    beschnittenen Ausschnitt. *Ganzes Bild* stellt den vollen Screenshot wieder her.
14. **Löschen und Undo.** Eintrag löschen, dann `Strg+Z`.
    Erwartet: Eintrag ist wieder da, an derselben Position.
15. **Fußzeile.** In den Einstellungen die Fußzeile aus- und wieder einschalten.
    Erwartet: `1 von N` verschwindet und erscheint wieder, zentriert unten.
16. **Export.** *Als PDF exportieren*, speichern, im PDF-Reader öffnen.
    Erwartet: Seiten sehen exakt aus wie die Vorschau, A4, sauber druckbar.
16a. **Dateigröße.** Eine Partitur mit rund zehn Seiten exportieren.
    Erwartet: die Datei hat wenige MB, nicht Dutzende; die Noten sehen im
    Reader genauso scharf aus wie in der Vorschau.
16b. **Vorhandenes PDF verkleinern.** *PDF verkleinern …*, ein älteres, großes
    Export-PDF wählen, vorgeschlagenen Namen `…-klein.pdf` übernehmen.
    Erwartet: neue Datei neben dem Original, deutlich kleiner, Seiten sehen
    gleich aus; das Original ist unverändert. Ein zweites Mal auf die kleine
    Datei angewandt meldet „bereits kompakt".
16c. **Projekt speichern und öffnen.** Einige Aufnahmen machen, eine
    zuschneiden, `Strg+S`, Namen vergeben, ScoreCap schließen, neu starten,
    `Strg+O`, Projekt öffnen.
    Erwartet: dieselben Aufnahmen in derselben Reihenfolge, der Zuschnitt ist
    erhalten, die Vorschau gleich. Titelleiste zeigt den Projektnamen.
16d. **Ungespeichertes nicht verlieren.** Aufnahme hinzufügen, Fenster
    schließen.
    Erwartet: Frage „Speichern / Nicht speichern / Abbrechen", alle drei
    Knöpfe vollständig lesbar; *Abbrechen* lässt das Fenster offen. Nach dem
    Speichern schließt das Fenster ohne Frage.
17. **Export-Fehler.** Die exportierte Datei im Reader geöffnet lassen und
    erneut auf denselben Namen exportieren.
    Erwartet: Fehlerdialog, Anwendung läuft weiter, Aufnahmen bleiben erhalten.
18. **HiDPI.** Auf einem Bildschirm mit 150 % Windows-Skalierung aufnehmen.
    Erwartet: Ausschnitt entspricht genau dem gezogenen Rechteck, Bild ist
    scharf, bei normal gezoomtem Browser erscheint keine dpi-Warnung.
19. **Aufräumen.** Anwendung schließen, `%TEMP%` prüfen.
    Erwartet: der Ordner `scorecap-*` ist gelöscht.

## Paket und Selbst-Update

Diese Punkte gelten für die installierte Fassung, nicht für den Start aus dem
Quellcode.

1. **Installation.** `ScoreCap-win-Setup.exe` aus dem Release ausführen.
   Erwartet: SmartScreen-Hinweis (unsigniert), nach *Trotzdem ausführen*
   installiert sich die App nach `%LocalAppData%\ScoreCap` und startet.
2. **Symbol.** Taskleiste und Startmenü ansehen.
   Erwartet: blaues Notensymbol, nicht das Python-Standardsymbol.
3. **Voller Durchlauf im Paket.** Aufnehmen, sortieren, zuschneiden, als PDF
   exportieren.
   Erwartet: identisch zum Start aus dem Quellcode.
4. **Kein Update vorhanden.** App mit der neuesten Version starten.
   Erwartet: kein Hinweis unten rechts, keine Fehlermeldung, keine Verzögerung
   beim Öffnen des Fensters.
5. **Update vorhanden, beim Schließen.** Eine neuere Version veröffentlichen,
   die installierte ältere starten, warten bis „ist bereit — wird beim
   Schließen installiert" erscheint, App schließen, wieder öffnen.
   Erwartet: die App ist jetzt die neue Version.
   Per Skript prüfbar: `%LocalAppData%\ScoreCap\current\ScoreCap.exe --selftest out.txt`
   meldet `velopack: installed=True current=<neue Version>`.
5a. **Update vorhanden, sofort.** Wie oben, aber *Jetzt neu starten* klicken.
   Erwartet: ohne Aufnahmen startet die App direkt neu in der neuen Version;
   mit Aufnahmen erscheint vorher die Rückfrage, und *Nein* lässt alles, wie es
   ist.
6. **Ohne Netz.** Netzwerk trennen und starten.
   Erwartet: App läuft normal, kein Hinweis, kein Fehlerdialog.
7. **Delta-Paket.** Im zweiten Release die angehängten Dateien prüfen.
   Erwartet: eine `*-delta.nupkg` liegt bei — sonst hat der Schritt
   *Fetch the previous release* nicht gegriffen und jedes Update lädt voll.

## Automatisch bereits geprüft

- `RegisterHotKey` für `Ctrl+Shift+S` gibt gegen das laufende Windows `True`
  zurück und lässt sich wieder freigeben.
- Fenster startet mit echter Qt-Windows-Plattform, zeigt sich und schließt
  sauber (Tempordner wird entfernt).
- Bildplatzierung im PDF stimmt auf unter 1 pt mit dem berechneten Layout überein.
- Das gebaute Paket besteht seinen Selbsttest: PDF-Erzeugung und Fensteraufbau
  laufen im gepackten Zustand.
- Selbst-Update auf einer echten Installation durchgelaufen (0.2.1 → 0.3.0,
  noch mit Klick-Knopf): die installierte Kopie meldet danach
  `velopack: installed=True current=0.3.0`, Release v0.3.0 trägt ein
  62-KB-Delta-Paket.
- Verkleinern eines echten 58-MB-Exports (9 Seiten, 26 Aufnahmen): 1,7 MB in
  1,1 s, gerenderte Seiten pixelgleich, Fußzeilentext erhalten.
- Laden und Anbieten über den Thread-Pool mit realistischer Dauer und
  erzwungener Garbage Collection, einschließlich Schließen des Fensters
  während eines laufenden Checks.
