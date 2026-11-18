# Laboränderungen

## 2026-11-18 – Methodengrenzen für Auftragslesen und Storno

- `GET /v1/orders/{id}` und `POST /v1/orders/{id}/cancel` vor Routing/Datenzugriff ausdrücklich getrennt. Andere Methoden werden mit `405 METHOD_NOT_ALLOWED` und passendem `Allow`-Header abgewiesen.
- Bestehende Gruppe T12 um tatsächlich ausgeführte GET-/PUT-Storno- und POST-Lese-Gegenproben erweitert. Auftrag, Bestand, Outbox, Provider und Versand bleiben beim abgewiesenen Aufruf unverändert; vorgesehener und wiederholter POST-Storno geben die Reservierung einmal frei.
- Gezielte Probe, vollständige 22/22-Szenariosuite und sieben unabhängige HTTP-Preisgrenzen bestanden. Neuer identischer JAR-Neubau in T01 belegt; aktuelle Hashes stehen in `evidence/runtime-manifest.json` und im Versionsregister.
- Vorherige Ausführungsbelege unter `evidence/before-method-guards/` erhalten. Der alte Leserexport ist für den neuen Quellstand nicht mehr gültig und muss vor Veröffentlichung neu erzeugt werden.

## 2026-11-18 – Vertragsbeschreibung präzisiert

- Den vorhandenen Backfill als `INSERT … SELECT *` zwischen gleich aufgebauten Fixture-Tabellen beschrieben. Die ausdrückliche Feldübersetzung betrifft den API-Adapter, nicht eine im SQL nicht vorhandene Spaltenliste. Keine Änderung des ausführbaren Labors; der Quellcodeexport muss die neuen Dokumenthashes berücksichtigen.

## 2026-11-18 – erste ausführbare Fassung

- Kanonischen Vertrag für die erfundene Firma Havelblick Technikservice festgelegt.
- Fünf lokale Stufenprofile mit erhaltener Altberechnung und bewusst falscher Preisextraktion bereitgestellt; gemeinsame Laborverdrahtung offen dokumentiert.
- Echte HTTP-Payment-/Versandsimulatoren, Rollenrechte und PostgreSQL-Persistenz eingebaut.
- Eigener Workerprozess besitzt den reproduzierbaren Exit-70-Crashpunkt nach fremdem Commit.
- Sicheren Preis-Shadow, absichtlich unsicheren Shadow und Datenrückweg nach Zielschreiben implementiert.
- Ausführbaren Timer-/CSV-Verbraucher ergänzt; Zeit- und Dateiabhängigkeit liegen an sichtbaren Nähten.
- Netzwerk nach lokaler Prüfung als normales Compose-Bridge-Netz mit ausschließlich Loopback-Publikation eingerichtet; der vorherige interne Bridge-Modus ließ die Hostports nicht erreichbar werden.
- Preisvergleich normalisiert nur die alte echte Uhrzeit gegenüber der injizierten festen Testuhr, keine Geldfelder.
- Abgleich prüft alle fachlichen Geldkomponenten, nicht nur Gesamtbetrag und Status.
