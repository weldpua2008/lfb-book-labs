# Kanonischer Laborvertrag – Havelblick Technikservice

Stand: 18.11.2026. **Havelblick Technikservice ist eine vollständig erfundene Firma.** Quellcode, Kunden, Produkte, Aufträge und Fehlerfälle sind synthetische Lehrmittel. Das Labor behauptet keine reale Unternehmensmigration oder Produktionslast. Dieser Vertrag ist die Referenz für Autoren; eine spätere Änderung erhält einen Eintrag in `lab/CHANGELOG.md`.

## Stack und Betrieb

Ein Java-Stack: Eclipse Temurin JDK 21 LTS im offiziellen Container; `javac` und `jar` aus genau diesem Image, kein Host-Java und kein Maven/Gradle nötig. PostgreSQL 18.7; reiner JDBC-Zugriff über den gepinnten offiziellen pgJDBC-Treiber. Exakte Tags, Digests, SHA-256 und beobachtete Versionen sind in `lab/evidence/runtime-manifest.json` und `research/lab-versions-and-sources.json` festgehalten. Tatsächlich verwendet: Temurin 21.0.13+9, PostgreSQL 18.7 und pgJDBC 42.7.14. Ein nicht vorhandenes Image wird als Blocker dokumentiert, nicht still auf `latest` geändert.

Vier lokale Dienste: Java-Auftrags-API, Java-Payment-Simulator, Java-Versandsimulator und PostgreSQL. Ein Java-Outbox-Worker läuft als eigener kurzlebiger Prozess. HTTP-Hostports nur auf `127.0.0.1`; PostgreSQL erhält keinen Hostport. Projekt/Label `lfb_legacy_book_20261118`. Zielgrenzen: zusammen höchstens 2 GiB Container-RAM, etwa 10 GiB eigener Arbeitsbereich, keine parallelen schweren Lastversuche mit dem PostgreSQL-Buchlabor.

## Verbindliche Fachregeln

Ein Auftrag enthält im Kern genau eine Produktposition; das ist eine bewusste Laborbegrenzung. Mehrpositionenaufträge, reale Steuern, Währungen, Zahlungsabwicklung und Warenwirtschaft werden nicht als abgedeckt behauptet.

- Produkte: `WARTUNG` mit Nettoeinzelpreis `19.995` EUR, `SENSOR` mit `7.125` EUR, `PUMPE` mit `49.995` EUR. Drei Nachkommastellen im Katalog dienen dem Rundungsgegenbeispiel.
- Menge: ganze Zahl 1 bis 20. Bestand wird reserviert, ohne negativ zu werden. Falsches Produkt, falsche Kundengruppe, falsche Menge oder Schlüsselwiederverwendung mit anderem Inhalt werden abgelehnt.
- Gruppen: `STANDARD` ohne Rabatt; `TREUE` mit 5 % ab Menge 3; `PARTNER` mit 10 % ab gerundetem Nettowarenwert von 100 EUR. Schwellen sind Lehrregeln, keine echten Geschäftsbedingungen.
- Zuerst Nettoeinzelpreis mal Menge rechnen und auf Cent mit `HALF_UP` runden. Rabatt darauf berechnen und auf Cent runden. Steuer des synthetischen Falls: 19 % auf Netto nach Rabatt, ebenfalls `HALF_UP`. Betrag = Netto nach Rabatt plus Steuer. Beträge in Antwort und Persistenz sind ganzzahlige Centwerte.
- Beispiel: `WARTUNG`, Menge 3, `TREUE`: Nettowarenwert 5999 Cent, Rabatt 300, Netto 5699, Steuer 1083, Gesamt 6782. Einzelpreis vor Multiplikation zu runden ist ein absichtlicher Fehlversuch und ergibt hier einen anderen Betrag.
- Zahlungsfreigabe ist kein Versand und kein Zahlungseinzug. `UNKNOWN` bedeutet: Wirkung beim Payment-Anbieter ist noch zu klären; nicht automatisch „abgelehnt“.
- Im geprüften Normalfall vor Versand gibt Storno die Reservierung genau einmal frei. Ein lokal bereits `SHIPPED` markierter Auftrag liefert einen Konflikt. Bekannte nicht freigegebene Grenze: Nach Fremdannahme und Worker-Exit70 ist der lokale Auftrag noch `AUTHORIZED`/`PENDING`; der aktuelle Stornopfad kann dann Bestand freigeben, obwohl eine Versandannahme existiert. Dieser Crash-Storno-Zwischenzustand ist keine sichere Stornomöglichkeit. Ein realer Retouren-/Erstattungsprozess ist nicht implementiert.

## API-Verträge

JSON in UTF-8. Die vollständigen Feldnamen bleiben zwischen Kapiteln gleich. Vertragstests werden mit dem echten lokalen HTTP-Simulator ausgeführt, nicht ausschließlich gegen Testdoubles.

| Schnittstelle | Vertrag |
|---|---|
| `POST /v1/orders` | Eingabe `{request_id, sku, quantity, customer_group}`; stabile `request_id` als fachlicher Wiederholungsschlüssel. Antwort enthält `order_id`, `status`, `subtotal_cents`, `discount_cents`, `net_cents`, `tax_cents`, `total_cents`, `created_at`, `backend`. |
| `GET /v1/orders/{id}` | Alte Antwortform; Routing/Adapter übersetzt neuen Speicherzustand. |
| `POST /v1/orders/{id}/cancel` | Wiederholbarer Stornoversuch im geprüften Normalfall; `409` bei lokalem `SHIPPED`. Crash-Storno-Grenze siehe oben. |
| `POST /v2/orders` | Neuer Vertrag `{idempotency_key, product_code, units, segment}`; Adapter übersetzt ausdrücklich, keine stillen Feldalias-Raten. |
| `GET /v2/quote?...` | Reiner Preisvergleich; keine Reservierung, Payment-Autorisierung, Versandwirkung oder Auftragspersistenz. Grundlage des sicheren Shadow-Pfads. |
| Payment `POST /authorize` | `{key, order_id, amount_cents, mode}`; Modi sind Laborhooks. Eindeutiger Schlüssel mit gleichem Inhalt liefert dieselbe Freigabe. Gleicher Schlüssel mit anderem Betrag liefert Konflikt. |
| Payment `GET /authorization?key=...` | Unbekannter Schlüssel liefert `404`; bekannte Freigabe liefert Betrag und Providerreferenz. |
| Versand `POST /dispatch` | `{event_id, order_id, total_cents}`; erneute gleiche `event_id` bewirkt keinen zweiten Versand. Gleiche Ereignis-ID mit anderem Inhalt liefert Konflikt. |
| `GET /legacy/report` | Bewusst übersehener nächtlicher CSV-Verbraucher der alten Daten. Wird erst nach eigener Migration abgeschaltet. |
| Admin-Laborhooks | Reset, Routingquote, Shadow-Variante, Verbraucherregistrierung, Abgleich und Abschaltprüfung sind ausschließlich lokale Testhilfen; genaue verfügbare Routen stehen in `lab/README.md`. |

Fehlerantworten verwenden JSON mit einem `error`-Code. Die Fehlerzuordnung ist im Lehrrahmen begrenzt: Ein unbekanntes Payment-`outcome` oder ein unpassender Betrag führt über `PaymentResponseContract` zu `502/PAYMENT_CONTRACT`. Eine fehlende, leere oder typfalsche `provider_ref` löst dagegen über `Json.string` eine `IllegalArgumentException` aus, die der allgemeine HTTP-Handler als `422/INVALID_INPUT` zuordnet. Diese aus dem Code abgeleitete Zuordnung ist kein vollständig vereinheitlichtes Fehlerprotokoll für fehlerhafte Providerantworten. Zeitouts und Transportfehler sind von fachlicher Ablehnung zu unterscheiden. Zahlungen im Simulator sind reine Datenbankeinträge, keine Geldbewegung.

## Schema und Schreibzuständigkeit

| Schema / Tabelle | Besitzer und Bedeutung |
|---|---|
| `legacy.products`, `legacy.stock`, `legacy.orders` | Alter Auftragspfad; erste beiden enthalten Katalog und reservierbaren Bestand. |
| `modern.orders` | Neuer Auftragspfad. Der begrenzte Fixture-Backfill verwendet `INSERT … SELECT *` zwischen gleich aufgebauten Auftragstabellen; er ist keine allgemeine Vorlage für eine Änderung von Spaltenreihenfolge oder Schema. API-Felder werden im Vertragsadapter ausdrücklich übersetzt. Keine implizite Doppelschreibzuständigkeit. |
| `ops.outbox` | Fachereignisse atomar zusammen mit Auftrag/Reservierung; enthält Ereignis-ID, Payload, Versuche, Bearbeitungszustand und Fehler. |
| `payment.authorizations` | Nur Payment-Dienst schreibt; Schlüssel eindeutig. Providerwirkung darf nicht über einen Auftragstransaktionsrollback „zurückgenommen“ werden. |
| `shipping.dispatches` | Nur Versanddienst schreibt; Ereignis-ID und Auftrag verhindern doppelte fachliche Wirkung. |
| `ops.control`, `ops.consumers`, `ops.audit` | Routing/Abschaltzustand, beobachtete Verbraucher und Laborjournal. Kein vollständiges Unternehmensinventar. |

Eigene Datenbankrollen für Auftrag, Payment und Versand. Ein Architekturtest prüft Paketgrenzen; ein Integrationstest prüft tatsächlich verweigerten Zugriff auf fremde Schreibtabellen. Gemeinsamer PostgreSQL-Server ist eine bewusste lokale Vereinfachung, keine Empfehlung für gemeinsamen Datenbesitz produktiver Dienste.

## Reproduzierbare Zustände und drei Etappen

1. `versions/00-legacy`: Verflochtener Ablauf mit direkter Zeitabfrage, Payment, SQL und Versandkopplung. Bewusste Schwächen: wechselnder Payment-Schlüssel bei ungeklärtem Ausgang; Lücke zwischen Auftragscommit und Versand; versteckter CSV-Verbraucher. Diese beobachteten Fehler sind kein freigegebenes Sollverhalten.
2. `versions/01-price-attempt`: Bewusst falsche Extraktion rundet Einzelpreis zu früh. Der Characterization-Gegenfall muss diesen Zustand zurückweisen.
3. `versions/01-price`: Reines Preis-Modul plus Zeit-/Payment-/Persistence-Nähte. Unveränderte fachliche Preisantworten und echte HTTP-Verträge prüfen. Bekannte Integrationsschwächen bleiben sichtbar, bis eine ausdrücklich benannte Korrektur erfolgt.
4. `versions/02-shipping`: Auftrag und Outbox in einer Transaktion; Worker als eigener Prozess; Versanddienst mit Idempotenz. Payment-UNKNOWN wird mit stabilem Schlüssel geklärt. Crash nach Versandannahme und vor Outboxbestätigung erzwingt Duplikatzustellung ohne Doppelwirkung. Fehlende/ungültige Nachricht wird sichtbar zurückgehalten, nicht still verworfen.
5. `versions/03-replacement`: Neuer Auftragsspeicher und v2-Vertrag; v1-Kompatibilitätsadapter, reiner Shadow-Vergleich, deterministische Kohorten und Kill Switch. Backfill, fachlicher Abgleich und Rückmigration neuer Zieldaten werden tatsächlich ausgeführt. Eine Routingrücknahme allein ist kein Datenrückweg.

Die genannten Versionspfade liegen im Verzeichnis `lab/`. Es handelt sich um ausführbare Stufenprofile mit gemeinsamem Quellkern, nicht um historische Git-Commits. Konkrete Implementierung und gewählte Stufe werden im Ausführungsmanifest festgehalten.

## Verbindliche Belege

Im Referenzlauf vom 18. November 2026 tatsächlich ausgeführt und in 22 bestandenen Szenariogruppen dokumentiert: Preis-Golden-Master mit negativen Fällen; erkannte Übernormalisierung; feste Zeit und echte Uhr; Persistence-Naht gegen echtes PostgreSQL; Payment-Doubles gegen HTTP-Vertrag; verbotener Paket-/Tabellenzugriff; UNKNOWN/Wiederholung; Bestand und Storno; Outboxcrash und Duplikate; Gift-Nachricht; Abgleich einer absichtlichen Abweichung; sichere und absichtlich unsichere Shadow-Variante; fehlgeschlagene Umschaltung; neue Zielschreibvorgänge vor Rückweg; vergessener Batchjob verhindert Abschaltung; reparierter Verbraucher und abschließende Altpfadprüfung.

Nach dem eigenen Szenariolauf enthalten `lab/evidence/results.json` und `results.md` die lokal ausgeführten Gruppen mit Erwartung, Beobachtung und Artefakt. Das Feld `chapters` der einzelnen Ergebnisgruppen ordnet die zugehörigen Buchkapitel zu; es ist kein Nachweis aller denkbaren Aussagen eines Kapitels. Die gesonderte Preisgrenzenprüfung aus der README erzeugt `lab/evidence/price-boundaries.json` mit sieben unabhängig berechneten und über HTTP geprüften Preisgrenzen. Diese Ergebnisdateien entstehen lokal und sind nicht als vorab grüne Leserabnahme im Quellpaket enthalten.

Die Übersicht des früheren Referenzlaufs steht in `../REFERENCE_EXECUTION.json`, bezogen auf das Verzeichnis dieses Vertrags. Sie benennt Fassungen und Grenzen; sie ersetzt nicht den eigenen Lauf. Private redaktionelle Detailprotokolle werden nicht mit dem Quellpaket verteilt. Lokale Laufzeitwerte sind keine Produktionsprognosen. Weitere, nicht ausgeführte Varianten bleiben ausdrücklich als Entscheidungsbeispiele oder offene Prüfungen bezeichnet.
