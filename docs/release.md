# Wie ein Release entsteht

`main` ist immer auslieferbar; es gibt keinen Entwicklungszweig. Bei jedem Push
nach `main` aktualisiert [release-please](https://github.com/googleapis/release-please)
einen offenen Release-PR: es sammelt die Commits seit dem letzten Release, leitet
daraus die nächste Version ab (`fix:` → Patch, `feat:` → Minor, `feat!:` → Major)
und schreibt den Changelog.

Solange dieser PR offen liegt, ist nichts veröffentlicht. **Der Merge ist die
Veröffentlichung**: er erzeugt Tag und Release, und erst dann baut der Workflow
das Paket, prüft es mit dem Selbsttest und hängt Setup, portables ZIP und
Delta-Paket an das Release. Ein Tag wie `v1.4.0` bezeichnet damit unveränderlich
den Stand, aus dem ein Paket entstanden ist.

Vorabversionen laufen über Tags der Form `v1.4.0-beta.1`.

**Einmalig einzustellen:** unter *Settings → Actions → General → Workflow
permissions* muss „Allow GitHub Actions to create and approve pull requests"
angehakt sein. GitHub verbietet das standardmäßig, und der Workflow scheitert
sonst mit „GitHub Actions is not permitted to create or approve pull requests" —
unabhängig davon, dass er `pull-requests: write` anfordert.

Auf dem Release-PR selbst startet CI gar nicht erst: er ändert nur Changelog,
Manifest und `scorecap/_version.py`, und genau diese Dateien stehen in
`paths-ignore` von `ci.yml`. Der Release-Workflow testet ohnehin erneut, bevor er
packt. Der Filter muss am Auslöser sitzen: Läufe aus Bot-PRs hält GitHub vor
jeder Job-Bedingung zur Freigabe zurück („workflow awaiting approval"). Damit der
PR in diesen drei Dateien bleibt, steht die Version nicht in `pyproject.toml`,
sondern wird dort dynamisch aus `_version.py` gelesen.

Das Release entsteht zunächst als **Entwurf** und wird erst veröffentlicht,
wenn Setup, Pakete und Update-Feed angehängt sind. Sonst wäre es für die Minuten
des Builds öffentlich die neueste Version, ohne dass installierte Kopien sich
darauf aktualisieren könnten — und ein gescheiterter Build hinterließe ein leeres
Release.
