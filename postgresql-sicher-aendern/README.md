# PostgreSQL sicher ändern – Begleitlabor

Dieses eigenständige Labor enthält ursprünglichen Python-/SQL-Code, synthetische Daten und technische Labordokumentation. Das Buchmanuskript gehört nicht zu diesem Paket. Der ursprüngliche Laborcode und die ursprüngliche Labordokumentation stehen unter **0BSD**; gesonderte Drittanbieterrechte stehen in `THIRD_PARTY_NOTICES.md`.

## Start

Voraussetzungen: Python 3.14 und Docker mit Linux-arm64-Unterstützung. Referenzumgebung am 18.11.2026: Python 3.14.6, Docker Engine 29.8.2, PostgreSQL 18.7; Major-Quelle 17.12. Die Images werden separat von Docker Hub bezogen, nicht in diesem Paket weiterverteilt. Digests stehen in `images.lock.json` und `Dockerfile.upgrade`.

Aus `postgresql-sicher-aendern/`:

```sh
python3 run_lab.py preflight
python3 run_lab.py fixture --size standard
python3 run_lab.py run-suite --include-upgrades
python3 -m unittest discover -s tests -v
python3 run_lab.py export
```

Gezielte Übung:

```sh
python3 run_lab.py run-suite --only CH04,CH05
python3 run_lab.py run-suite --only CH20,CH21 --include-upgrades
```

Der Runner akzeptiert ausschließlich eigene feste Container-/Datenbanknamen und Besitzlabels. Kein Hostport und keine Produktionsverbindung; psql läuft im eigenen Container. Die logische Replikation nutzt ein dediziertes internes Netz. Laborpasswörter sind absichtlich öffentliche synthetische Werte. `reset` löscht ausschließlich das markierte eigene `shop`-Schema. Fremde Container/Volumes werden nicht bereinigt.

## Daten und Grenzen

Die Nordlicht Warenhandel GmbH ist erfunden. `standard` erzeugt 2.000 Kunden, 200 Produkte, 24.000 Aufträge, 72.000 Positionen, 23.525 Zahlungen und 200 Bestandszeilen. E-Mail-Adressen verwenden `example.invalid`. Geld wird in EUR-Cent und optional einer migrierten EUR-Spalte abgebildet. `small`/`large` erzeugen 2.400/120.000 Aufträge; Kapitelabnahme verwendet Standardgröße.

Die PostgreSQL-Container erhalten zusammen höchstens 5 GiB deklarierte RAM-Limits. Eine konservative Arbeitsdiskprüfung begrenzt das Labor zunächst auf 25 GiB. CPU-/Cache-/Docker-Effekte verändern Messungen; lokale Zeiten sind keine Produktionsprognose.

## 24 Kapitelübungen

Die stabilen IDs **CH01–CH24** werden in `chapter-map.json` mit Funktion, Befehl und Abnahmekriterium zugeordnet. Code liegt in `cases/`, gemeinsame SQL in `sql/`.

- CH01–06: Änderungskarte, deterministischer Seed, drei Messläufe, Snapshots, Locks/Timeouts und tatsächlich gestartete logische/physische Restores.
- CH07–12: Alt-/Bridge-/finale App, Spaltenänderungen, fortsetzbarer Backfill, Constraints, Concurrent-Indizes und Preismodell-Dossier.
- CH13–19: tatsächliche Query-Pläne, falsche Indexhypothese, Statistiken, Deadlock, persistenter Verbindungspool, VACUUM, Partitionen, Drift und Lastregression.
- CH20–24: tatsächlich `pg_upgrade --check`/`--copy`17.12→18.7, unabhängiger Dump/Restore, logische Replikation, Sequenz-/DDL-Nachführung, Single-Writer-Gates, absichtliche No-go-Abnahme und begrenzter Rückabgleich.

Ein früher Snapshot kann Werte festhalten; ein fehlgeschlagener Unique-CIC kann ungültig sein und dennoch Eindeutigkeit erzwingen. Nach Wegfall der alten Spalte kann eine Fallback-Bridge diese nicht mehr referenzieren: Vor Contract muss die finale App bereitstehen. Ein startbarer alter COPY-Cluster enthält keine neuen Zielschreibvorgänge. Logische Replikation übernimmt weder beliebige DDL noch Sequenzstände. Eine zurückliegende Sequenz bedeutet nicht zwangsläufig sofortige Kollision.

Full-Backup mit gestreamtem WAL und Klonstart ist kein vollständiger Archivierungs-/PITR-Test. Link-Modus wird nicht ausgeführt. Rollenfences simulieren Clientrouting; es findet kein DNS-/Proxywechsel statt. Der Backfill prüft Änderungen an vorhandenen Zeilen, nicht beliebige neue Insertfrontiers.

## Eigene Ergebnisse

Jeder Lauf schreibt ausschließlich lokal nach `outputs/<Kennung>/`. Rohe Sessions, Sicherungsdateien, Hostangaben und Laufprotokolle werden nicht mit diesem Quellcodepaket veröffentlicht. `summary.json`, `SUMMARY.md` und `MEASUREMENTS.md` unterscheiden pass/fail/skip. `accepted-run.json` wird lokal nur nach 24×pass, Endmanifest und unverändertem Quellsnapshot erzeugt. Ein fremder erfolgreicher Lauf ist keine Abnahme Ihrer Umgebung.

Der öffentliche Export enthält keine Images, Binaries, Sicherungen, Rohlogs oder privaten Hostpfade. Leser erzeugen den vollständigen Beleg mit dem eigenen Lauf. Änderungen an Übungen benötigen neue gezielte Prüfungen.

## Geld-Backfill und Zielvertrag

`cases/migrations.py:expand` installiert `sql/expand.sql` und `sql/money_batch_function.sql`. Die Batchfunktion verlangt READ COMMITTED, sperrt den eindeutigen Checkpoint vor der Auswahl, nutzt FOR NO KEY UPDATE und verweigert unvollständige UPDATE-RETURNING-Mengen. Fehlende Marke:P0002; unterdrückte Zeile/Marke:P0001. `finished` bezeichnet ausschließlich veränderliches Scanende, keine Fachfreigabe. Der Controller wiederholt ganze55P03/57014-Versuche begrenzt (max500Versuche insgesamt).

CH07 trennt NOT-VALID-Anlage und Validierung von der letzten DDL-Phase. Der Ziel-CHECK schließt numeric NaN aus. `sql/money_roles.sql` prüft den Besitz fester lokaler Geldrollen; `sql/money_acceptance.sql` verweigert falsche Euro/Cent-, Positions- oder Zahlungsbeziehungen unter vorherigem Schreibfence. Diese Mikropfade sind keine vollständige Anwendungsauslieferung.
