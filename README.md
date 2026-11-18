# Begleitlabore zu den Büchern von Lorenz Falkenthal-Bauer

Dieses Repository enthält die ausführbaren synthetischen Lehrfälle zu **PostgreSQL sicher ändern** und **Legacy modernisieren, während der Betrieb läuft**. Die Buchmanuskripte und Cover sind nicht enthalten.

- [PostgreSQL-Labor: Voraussetzungen und Start](postgresql-sicher-aendern/README.md)
- [Legacy-Labor: Voraussetzungen und Start](legacy-modernisieren/lab/README.md)
- [Havelblick: Fach- und API-Vertrag](legacy-modernisieren/lab-contract.md)

Jedes Labor hat eigene Anleitungen, feste lokale Namen und Daten. Eine zweite Verzeichniskopie erzeugt keine zweite isolierte Laufzeit. Verwenden Sie jeweils nur einen Aufbau desselben Labors und führen Sie dessen Proben nacheinander aus. Resetbefehle löschen die benannten synthetischen Labordaten; sie sind keine Produktionswerkzeuge.

Die Referenzläufe verwenden Linux-aarch64-Container unter Docker Desktop auf macOS. Andere Plattformen sind damit nicht als geprüft ausgewiesen. Für die ersten Image- und JDBC-Downloads ist Internet nötig. Es werden keine Images, Drittanbieter-Binärdateien oder echten Kundendaten verteilt.

## Herkunft und Lizenz

Die ursprünglichen Beispiele und die Labordokumentation wurden für diese Buchprojekte mit KI erstellt, überarbeitet und mit ausgeführten Proben geprüft. Modelle können Fehler machen; ein erfolgreicher Referenzlauf ist keine Freigabe Ihrer Umgebung und keine Produktionsgarantie. Konkrete Fassungen und Grenzen stehen im Paketmanifest und den jeweiligen Anleitungen.

Die [0BSD-Lizenz](LICENSE) gilt für den ursprünglichen Laborcode und die ursprüngliche Labordokumentation, soweit entsprechende Rechte eingeräumt werden können. Damit wird keine Behauptung über die Schutzfähigkeit KI-generierter Bestandteile verbunden. Drittanbietertexte behalten ihre eigenen Hinweise; deren Umfang steht in den jeweiligen THIRD_PARTY_NOTICES und im Legacy-Lizenzinventar. Buchtext und Cover werden durch dieses Paket nicht lizenziert.

Die Dateimanifeste ordnen den ursprünglichen Dateien 0BSD zu, ohne dafür ausführbare Referenzquellen nachträglich zu verändern. Fremde Lizenztexte sind getrennt markiert. Offizielle Dokumentationsseiten werden verlinkt; ihre Volltexte werden nicht mitgeliefert.

## Fassungen

Die erste Buchausgabe verwendet getrennte Releasepakete mit den Tags `postgresql-1.0.0` und `legacy-1.0.0`. Verwenden Sie die im jeweiligen Buch genannte Fassung und prüfen Sie den SHA-256 des ZIP-Archivs gegen dessen SHA256SUMS. Der aktuelle Entwicklungszweig kann später abweichen. Die öffentlichen Pakete enthalten keine privaten Laufprotokolle; eigene vollständige Ergebnisse entstehen lokal beim Testlauf.
