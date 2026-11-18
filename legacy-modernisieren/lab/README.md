# Havelblick-Labor: drei Umbauetappen

**Havelblick Technikservice ist erfunden.** Dieses ausführbare Lehrsystem zeigt begrenzte, tatsächlich überprüfbare Modernisierungsschritte. Es ist weder eine echte Unternehmensanwendung noch ein Beleg für garantierte Produktionsverfügbarkeit. Der verbindliche Fach-/API-Vertrag steht in [../lab-contract.md](../lab-contract.md).

## Start und vollständige Probe

Im öffentlichen Begleitquellcode zuerst in `legacy-modernisieren/lab` wechseln. Voraussetzungen: Docker mit Compose und Python 3, keine lokale Java-Installation. Geprüfte Plattform: Docker Desktop, Linux `aarch64`, PostgreSQL 18.7 und Temurin 21.0.13+9. Der JDK-Build umfasst den Compiler und das Archivierungswerkzeug; kein Maven-/Gradle-Download ist nötig. Der Build lädt den gepinnten JDBC-Treiber vom offiziellen Ursprung und prüft seinen SHA-256. Das öffentliche Quellpaket enthält keinen JDBC-Binärdownload.

```sh
./lab.sh build
./lab.sh up
./lab.sh test
```

Die Suite wartet auf die drei HTTP-Dienste, setzt nur ihre eigenen synthetischen Daten zurück, wechselt die Ausführungsstufen und erzeugt [evidence/results.json](evidence/results.json), [evidence/results.md](evidence/results.md) und [evidence/raw-events.json](evidence/raw-events.json). Ein Test gilt erst mit seinem tatsächlichen Ergebnis als bestanden. Die Kapitelzuordnung steht im Feld `chapters` der einzelnen Testgruppen in der erzeugten Datei `evidence/results.json`.

`./lab.sh reset-data` löscht ausschließlich die Daten dieses Fixtures. `./lab.sh reset` entfernt die Compose-Dienste und ihr eigenes Datenvolume und initialisiert neu. `./lab.sh down` stoppt/entfernt nur die Dienste und das eigene Netzwerk; das Volume bleibt erhalten. Es werden keine anderen Container angehalten oder bereinigt.

## Laufende Stufen

```sh
./versions/00-legacy/run.sh
./versions/01-price-attempt/run.sh
./versions/01-price/run.sh
./versions/02-shipping/run.sh
./versions/03-replacement/run.sh
```

Diese Pfade sind ausführbare **Stufenprofile**, keine behaupteten historischen Git-Commits. Sie verwenden einen gemeinsamen HTTP-/Datenbank-Laborrahmen. Die ursprüngliche Berechnung in `LegacyPrice`, die absichtlich falsche frühe Rundung, das isoliert kompilierbare `pricing`-Modul, `CompatibilityAdapter`, die unterschiedliche Versandübergabe und die neue Auftragstabelle sind im Sourcebaum erhalten. `OrderService` enthält sichtbar die Übergangsverdrahtung; das ist keine Behauptung vollständig bereinigter Architektur.

| Stufe | Ausgeführter Unterschied | Beabsichtigter Fehler / Grenze |
|---|---|---|
| `00-legacy` | Alte Berechnung, direkt gebundene echte Uhr, Remote-Payment und JDBC; direkter Versand nach Commit | UNKNOWN wiederholt mit anderem Schlüssel; Absturzlücke vor Versand; alter Bericht |
| `01-price-attempt` | Extraktion rundet Einzelpreis vor Multiplikation | 6783 statt 6782 Cent im Gegenfall; kein freigegebener Stand |
| `01-price` | Preis-Modul und austauschbare Zeit-/Payment-/Persistence-Ports | Preisgleichheit geprüft; bekannte Payment-/Versandschwächen bleiben |
| `02-shipping` | Stabiles Payment-Reconcile, atomare Outbox, eigener Workerprozess und separater Versanddienst | Mehr Betriebskomponenten; begrenzte Fehlertoleranz, keine globale Exactly-once-Garantie |
| `03-replacement` | Neue Auftragstabelle, v2-Vertrag, v1-Adapter, Backfill, Shadow, Kohorten, Rückmigration und Abschaltprüfung | Gemeinsamer Katalog/Bestand bleibt explizite Restkopplung |

Die feste Testuhr ab der Naht ist `2026-01-15T09:30:00Z`. Der alte Pfad verwendet tatsächlich die Systemuhr. Der Golden-Vergleich entfernt allein `created_at` und prüft die Zeitquelle gesondert; Centbeträge werden niemals weg-normalisiert. Eine breitere Normalisierung wird als Gegenbeispiel ausgeführt.

## Lokale Schnittstellen

- Anwendung: `http://127.0.0.1:18890`
- Payment-Simulator: `http://127.0.0.1:18891`
- Versand-Simulator: `http://127.0.0.1:18892`
- PostgreSQL: nur im Compose-Netzwerk, kein Hostport.

Diese HTTP-Server haben absichtlich keine Produktionsauthentifizierung. Laborsteuerung und Fehlereinspeisung sind lokale Testhilfen. Alle Geheimnisse sind feste, ausschließlich lokale Fixture-Zugangsdaten. Es gibt keine echte Autorisierung bei einem Zahlungsanbieter, keine Geldbewegung und keinen realen Versand.

Beispiel für die alte Antwortform:

```sh
curl -sS http://127.0.0.1:18890/v1/orders \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"beispiel-1","sku":"WARTUNG","quantity":3,"customer_group":"TREUE"}'
```

Das ist ein synthetischer Beispielrequest. Der berechnete Sollwert für diese Lehrregel ist 6782 Cent. Die API ist bewusst auf eine Produktposition pro Auftrag begrenzt.

## Methodengrenzen der Auftragsressource

Der Leseweg `GET /v1/orders/{id}` und der Storno `POST /v1/orders/{id}/cancel` prüfen die Methode vor Routing und Datenzugriff. Andere Methoden erhalten `405` mit `Allow: GET` beziehungsweise `Allow: POST`. Die erweiterte Gruppe T12 prüft insbesondere, dass ein GET auf den Stornopfad weder Auftrag, Bestand, Outbox, Providerfreigabe noch Versand verändert. Der vorgesehene POST und seine Wiederholung bleiben zulässig. Dies ist eine gezielte Grenze dieser Ressource, keine vollständige HTTP-/Sicherheitszertifizierung des Laborservers.

## Versandcrash selbst ausführen

In Stufe `02-shipping` oder `03-replacement` wird zusammen mit dem Auftrag eine Outboxzeile gespeichert. Ein normaler Worker verarbeitet jeweils ein Ereignis:

```sh
./lab.sh worker
./lab.sh worker --crash-after-send
./lab.sh worker
```

Der mittlere Befehl beendet einen **eigenen Java-Prozess mit Exitcode 70**, nachdem der Versanddienst seine Annahme bereits gespeichert hat, aber vor lokaler Bestätigung. Die nächste Zustellung erreicht den Dienst erneut. Dessen eindeutige Ereignis-/Auftragszuordnung verhindert im nachgewiesenen Fall eine zweite Versandwirkung. Das ist ein idempotenter Empfänger bei mindestens einmaliger Zustellung, keine verteilte atomare Transaktion.

Der Worker sperrt Auftrag vor Outbox, passend zum Stornopfad, und prüft den Zustand unter den Locks neu. Er hält während des kurzen HTTP-Aufrufs eine Transaktion offen; das ist eine bewusst einfache, durchsatzbegrenzende Laborlösung. Die Spalte `attempts` zählt nur Versuche, deren lokale Transaktion committet wurde. Ein Prozessabbruch rollt diese Erhöhung zurück; sie ist daher kein vollständiger Zustellversuchszähler.

## Bekannte Grenze: Storno nach Workerabbruch

Ein zusätzlicher kontrollierter Gegenfall zeigt eine nicht freigegebene Kombination: Nach Versandannahme und Worker-Exit70 bleibt der Auftrag lokal `AUTHORIZED`, die Nachricht `PENDING`. Ein anschließender Storno kann derzeit `CANCELLED` melden und Bestand freigeben, obwohl die fremde Versandannahme bestehen bleibt. Die lokale Sperrreihenfolge beseitigt dieses Fenster nach dem Prozessende nicht. Der Fall ist eine bekannte Grenze des Lehrsystems; verwenden Sie ihn nicht als sicheren Stornoablauf. Der separat geprüfte Normalfall storniert vor Versand, der lokal bereits `SHIPPED` markierte Auftrag wird abgewiesen. Ein allgemeiner Ausgleich realer Versand- oder Zahlungswirkungen ist nicht implementiert.

## Der vergessene Batchjob

Ein wirklicher Java-Timer ruft den Bericht zyklisch ab und schreibt eine Datei über einen `ExportSink`. Die zwei Zyklen im Test verwenden einen verkürzten Abstand von 100 ms; das ist keine Empfehlung für einen nächtlichen Produktionsplan.

```sh
docker compose exec -T app java -Xmx96m -cp 'havelblick.jar:lib/*' \
  havelblick.ReportJob legacy /tmp/havelblick-export.csv 2
```

Vor Abschaltung wird derselbe Verbraucher auf `modern` umgestellt. Der Test führt beide Varianten aus. Registrierte alte Verbraucher verhindern die Abschaltung; ein bloß geänderter Routingprozentsatz genügt nicht. Das Inventar beweist ausschließlich die bekannten synthetischen Verbraucher, nicht die Vollständigkeit eines realen Unternehmensinventars.

## Zielschreibvorgänge und Rückkehr

`route_percent` steuert deterministisch über den Java-Hash des Wiederholungsschlüssels. Die Gegenprobe schaltet nach einem neuen Zielauftrag nur den Router zurück: Der alte Leser findet den Auftrag nicht, obwohl der neue Datensatz noch existiert. Der geprüfte Laborrückweg verlangt eine bestätigte Schreibsperre, geklärte Fremdwirkungen und Zustellarbeit sowie eine ausdrücklich ausgeführte Rückübertragung nach `legacy.orders`. Der technische Guard prüft `PENDING`, entscheidet aber nicht über ungeklärtes `POISON`; eine einzige koordinierende Adminsteuerung bleibt Voraussetzung. Danach werden Beträge und Sichtbarkeit geprüft. Kopierbare Admin-Aufrufe stehen in `scripts/run_scenarios.py`; sie bilden keine universelle Produktions-Rollback-Anleitung.

Der sichere Shadowpfad berechnet nur Preise und vergleicht Ergebnisse. Vorher-/Nachher-Zähler für Bestände, Aufträge, Payment und Versand bleiben gleich. Eine ausdrücklich unsichere Testvariante erstellt dagegen einen synthetischen Auftrag; der Test muss diese Nebenwirkung erkennen. Diese Variante darf nicht als normale Shadowtechnik beschrieben werden.

## Quellen, Lizenzen und Grenzen

[../research/lab-versions-and-sources.json](../research/lab-versions-and-sources.json) verbindet Pins, Digests und Originalquellen. [LICENSE-INVENTORY.md](LICENSE-INVENTORY.md) benennt auch die im JDBC-JAR enthaltenen Lizenztexte. Kopierte Bibliothekslizenztexte bleiben unter `licenses/` erhalten. Keine KI-, Cloud-, GPU- oder Lizenzkäufe werden benötigt.

Nicht implementiert oder nicht vollständig nachgewiesen sind unter anderem Mehrpositionenaufträge, reale Steuerregeln, Refund/Void bei jedem nachgelagerten Fehler, Netzwerkpartitionen über Hosts, produktionsnahe Kapazität, alle möglichen Storno-/Versand-Interleavings und beliebige unregistrierte Verbraucher. Das gemeinsame Datenbanksystem und der kleine JSON-Codec sind Laborvereinfachungen. Die drei Etappen sind technische Lernfälle; die Kapitel erläutern die Entscheidungen, Gegenbeispiele und Transfergrenzen.
