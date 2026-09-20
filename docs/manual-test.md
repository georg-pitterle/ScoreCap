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
   *Bearbeiten → Ganzes Bild* zeigt wieder den vollen Screenshot. Mit
   abgeschaltetem Auto-Trim in den Einstellungen bleibt der Rand erhalten.
10. **Seitenfüllung.** So viele Zeilen aufnehmen, bis eine zweite Seite beginnt.
   Erwartet: Seite eins ist gleichmäßig gefüllt, nichts überlappt, alle Bilder
   haben dieselbe Breite.
10a. **Systemende mit Teilungspfeil.** Ein System aufnehmen, hinter dessen
    Ende Teilungspfeile stehen, dazu ein System ohne.
    Erwartet: die Notenlinien beider Systeme enden auf derselben Höhe am
    rechten Satzrand, die Pfeile stehen außerhalb im Seitenrand. Mit
    abgeschaltetem „Notenlinien bündig ausrichten" enden die Linien des
    Pfeil-Systems wieder früher.
10b. **Systemanfang mit Klammer.** Ein System mit geschweifter Klammer vor den
    Notenlinien aufnehmen oder importieren, dazu Systeme ohne.
    Erwartet: alle Notenlinien beginnen am linken Satzrand, die Klammer steht
    im Seitenrand.
11. **Umsortieren.** Einen Eintrag in der Liste an eine andere Position ziehen.
   Erwartet: Vorschau folgt der neuen Reihenfolge.
12. **Neu aufnehmen.** Eintrag wählen, *Neu aufnehmen*, neues Rechteck ziehen.
   Erwartet: Bild wird an derselben Listenposition ersetzt.
13. **Zuschneiden.** Eintrag wählen, *Bearbeiten*, auf *Zuschneiden*
    schalten, Rechteck ziehen, OK.
    Erwartet: außerhalb der Auswahl dunkelt das Bild ab, die Vorschau zeigt den
    beschnittenen Ausschnitt. *Ganzes Bild* stellt den vollen Screenshot wieder her.
13a. **Zuschnitt nachbessern.** *Bearbeiten* bei einer beschnittenen Aufnahme,
    auf *Zuschneiden* schalten: eine Ecke ziehen, dann eine Kante, dann innen.
    Erwartet: der Mauszeiger zeigt vorher jeweils Diagonal-, Seiten- bzw.
    Verschiebepfeile; Ecke ändert zwei Kanten, Kante eine, innen verschiebt
    den Rahmen ohne Größenänderung. Nach *Ganzes Bild* lassen sich die
    Bildkanten hereinziehen.
13b. **Radieren.** *Bearbeiten*, über eine Seitenzahl oder einen
    Bleistiftstrich ziehen, dann noch einmal woanders, *Radierung zurück*, OK.
    Erwartet: das Fenster geht groß auf und steht gleich auf *Radierer*; jede
    gezogene Fläche wird sofort weiß, *Radierung zurück* nimmt nur die letzte
    weg. Nach *Übernehmen* zeigen Vorschaubild und A4-Vorschau dieselben
    weißen Flächen, das PDF ebenso. `Strg+Z` macht Zuschnitt und Radierungen
    in einem Schritt rückgängig. Ein Wechsel auf *Zuschneiden* lässt die
    weißen Flächen stehen, auch *Ganzes Bild* löscht sie nicht.
13c. **Zuschnitt nach dem Radieren.** Eine Aufnahme mit einer Seitenzahl am
    Rand: die Seitenzahl wegradieren, *Übernehmen*.
    Erwartet: der Zuschnitt rückt nach, die Aufnahme wird um den frei
    gewordenen weißen Rand kleiner. Mit abgeschaltetem Auto-Trim in den
    Einstellungen bleibt der Zuschnitt, wie er war. Ein selbst enger
    gezogener Zuschnitt wird nie wieder weiter.
13d. **Aus der Vorschau auswählen.** Mehrere Aufnahmen, rechts in der
    A4-Vorschau auf die dritte klicken, dann auf den weißen Rand daneben.
    Erwartet: der Klick auf die Aufnahme markiert links den dritten Eintrag
    und scrollt ihn ins Bild; der Klick auf den Rand ändert die Auswahl
    nicht.
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
    zuschneiden, in einer anderen etwas wegradieren, `Strg+S`, Namen vergeben,
    ScoreCap schließen, neu starten, `Strg+O`, Projekt öffnen.
    Erwartet: dieselben Aufnahmen in derselben Reihenfolge, Zuschnitt und
    Radierungen sind erhalten, die Vorschau gleich. Titelleiste zeigt den
    Projektnamen. Ein Projekt aus einer älteren ScoreCap-Version öffnet
    weiterhin, einfach ohne Radierungen.
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

## Scans

1. **Import per Dialog.** *Scans importieren …*, ein mehrseitiges Scan-PDF
   wählen.
   Erwartet: Fenster bleibt bedienbar, die Statuszeile zählt die Seiten mit,
   danach „N Systeme aus M Seiten importiert".
2. **Drag&Drop.** Ein JPG und ein TIFF aus dem Explorer ins Fenster ziehen.
   Erwartet: beide werden importiert; eine `.txt` wird nicht angenommen.
3. **Schräg und mit Bundschatten.** Eine Buchseite leicht schräg und nicht
   ganz flach scannen.
   Erwartet: Notenlinien in der Vorschau waagrecht, Papier überall weiß, kein
   Schatten, kein dunkler Rand.
4. **Systeme.** Eine Klavier- und eine Chorpartitur mit Liedtext importieren.
   Erwartet: je ein Eintrag pro System, Liedtext beim richtigen System,
   Seitenzahlen und Kopfzeilen nicht in den Aufnahmen.
5. **Titel zurückholen.** Erstes System einer Seite mit Titel wählen,
   *Bearbeiten*, auf *Zuschneiden* schalten, oberen Rand des Rahmens
   hochziehen.
   Erwartet: der Titel ist wieder da.
6. **Bereinigung umstellen.** Nach dem Import in den Einstellungen *Scans
   drucken in* auf *Graustufen* stellen, ohne neu zu importieren.
   Erwartet: Vorschau zeigt sofort weiche Kanten; das exportierte PDF ist
   deutlich größer. Bildschirmaufnahmen im selben Projekt ändern sich nicht.
7. **Undo und Projekt.** Nach einem Import `Strg+Z`, dann erneut importieren,
   speichern, schließen, öffnen.
   Erwartet: Undo nimmt den ganzen Import zurück; das Projekt kommt mit allen
   Zuschnitten wieder.
8. **Schließen während des Imports.** Großes PDF importieren und sofort
   schließen.
   Erwartet: schließt nach höchstens einer Seite, keine Fehlermeldung, `%TEMP%`
   aufgeräumt.

## Sprache

1. **Windows auf Deutsch.** App starten.
   Erwartet: Oberfläche deutsch, Tooltip von *Öffnen …* nennt `Strg+O`,
   Fragen beim Schließen mit deutschen Knöpfen.
2. **Windows auf Englisch** (oder in den Einstellungen *English*, neu starten).
   Erwartet: Oberfläche englisch, `Ctrl+O`, PDF-Fußzeile „1 of 3“, Statuszeile
   „1 capture, 1 page“ bzw. „3 captures, 2 pages“.
3. **Sprache umstellen.** In den Einstellungen die Sprache wechseln.
   Erwartet: Hinweis, dass sie beim nächsten Start wechselt; nach dem Neustart
   gilt sie.

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
