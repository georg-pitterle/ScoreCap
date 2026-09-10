# Manueller Abnahmetest

Voraussetzung: `python -m scorecap` läuft, ein Browser mit einer mehrzeiligen
Partitur ist geöffnet.

1. **Hotkey über fremdem Fenster.** Browser fokussieren, `Ctrl+Shift+S` drücken.
   Erwartet: Bildschirm dunkelt ab, Fadenkreuz erscheint.
2. **Auswahl.** Rechteck über eine Notenzeile ziehen und loslassen.
   Erwartet: ScoreCap kommt nach vorn, die Aufnahme steht in der Liste und auf
   der Vorschauseite.
3. **Serienaufnahme.** Ohne das Fenster anzufassen: Hotkey, ziehen, im Browser
   weiterscrollen, Hotkey, ziehen — zehnmal hintereinander.
   Erwartet: ScoreCap bleibt minimiert, der Browser behält Fokus und
   Scrollposition, nach jeder Aufnahme erscheint kurz „Aufnahme N", jeder
   Hotkey greift sofort.
4. **Rückkehr über Taskleiste.** Nach der Serie ScoreCap aus der Taskleiste
   holen.
   Erwartet: Vorschau enthält alle Aufnahmen der Serie in der richtigen
   Reihenfolge.
5. **Abbruch.** Hotkey drücken, `Esc` drücken.
   Erwartet: keine neue Aufnahme, keine Fehlermeldung, Fenster kommt zurück.
6. **Zu kleine Auswahl.** Hotkey drücken, nur wenige Pixel ziehen.
   Erwartet: keine neue Aufnahme, keine Fehlermeldung.
7. **Seitenfüllung.** So viele Zeilen aufnehmen, bis eine zweite Seite beginnt.
   Erwartet: Seite eins ist gleichmäßig gefüllt, nichts überlappt, alle Bilder
   haben dieselbe Breite.
8. **Umsortieren.** Einen Eintrag in der Liste an eine andere Position ziehen.
   Erwartet: Vorschau folgt der neuen Reihenfolge.
9. **Neu aufnehmen.** Eintrag wählen, *Neu aufnehmen*, neues Rechteck ziehen.
   Erwartet: Bild wird an derselben Listenposition ersetzt.
10. **Zuschneiden.** Eintrag wählen, *Zuschneiden*, Rechteck ziehen, OK.
    Erwartet: Vorschau zeigt den beschnittenen Ausschnitt. *Zurücksetzen* stellt
    das volle Bild wieder her.
11. **Löschen und Undo.** Eintrag löschen, dann `Strg+Z`.
    Erwartet: Eintrag ist wieder da, an derselben Position.
12. **Fußzeile.** In den Einstellungen die Fußzeile aus- und wieder einschalten.
    Erwartet: `1 von N` verschwindet und erscheint wieder, zentriert unten.
13. **Export.** *Als PDF exportieren*, speichern, im PDF-Reader öffnen.
    Erwartet: Seiten sehen exakt aus wie die Vorschau, A4, sauber druckbar.
14. **Export-Fehler.** Die exportierte Datei im Reader geöffnet lassen und
    erneut auf denselben Namen exportieren.
    Erwartet: Fehlerdialog, Anwendung läuft weiter, Aufnahmen bleiben erhalten.
15. **HiDPI.** Auf einem Bildschirm mit 150 % Windows-Skalierung aufnehmen.
    Erwartet: Ausschnitt entspricht genau dem gezogenen Rechteck, Bild ist
    scharf, bei normal gezoomtem Browser erscheint keine dpi-Warnung.
16. **Aufräumen.** Anwendung schließen, `%TEMP%` prüfen.
    Erwartet: der Ordner `scorecap-*` ist gelöscht.

## Automatisch bereits geprüft

- `RegisterHotKey` für `Ctrl+Shift+S` gibt gegen das laufende Windows `True`
  zurück und lässt sich wieder freigeben.
- Fenster startet mit echter Qt-Windows-Plattform, zeigt sich und schließt
  sauber (Tempordner wird entfernt).
- Bildplatzierung im PDF stimmt auf unter 1 pt mit dem berechneten Layout
  überein; Punkte 1-14 decken das ab, was nur ein Mensch sehen kann.
