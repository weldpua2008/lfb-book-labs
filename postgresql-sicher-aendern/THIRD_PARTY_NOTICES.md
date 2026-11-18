# Drittanbieter: Herkunft, Version und tatsächliche Weitergabe

Stand 18.11.2026. Dieses Quellcodepaket enthält ursprünglichen Python-/SQL-Laborcode und ursprüngliche Labordokumentation unter 0BSD. Es enthält **kein Buchmanuskript**, keine vendorte Bibliothek, kein Image und keine ausführbare Drittanbieter-Binärdatei. Die folgenden Programme werden bei Ausführung separat benötigt oder durch referenzierte offizielle Images separat bezogen. Ihre Rechte werden nicht durch 0BSD ersetzt.

| Bestandteil | Beobachtete Version / Herkunft | Lizenzgrundlage | Tatsächliche Weitergabe durch dieses Paket |
|---|---|---|---|
| PostgreSQL-Server und Werkzeuge (`psql`, `pg_dump`, `pg_restore`, `pg_basebackup`, `pg_verifybackup`, `pg_upgrade`) |18.7 und17.12; PostgreSQL Global Development Group; offizielle `postgres`-Images, Digests in `images.lock.json`/`Dockerfile.upgrade` | [PostgreSQL License](https://www.postgresql.org/about/licence/) | **Keine** PostgreSQL-Quellen oder -Binaries. SQL-Dateien sind ursprüngliche Laborbeispiele, keine kopierten PostgreSQL-Quellen. |
| Docker Official Image PostgreSQL: Packaging-/Entrypoint-Repository | `docker-library/postgres`; die beiden fixierten Image-Digests dokumentieren die konkret benutzte Fassung | Packaging-Code: [MIT-Lizenz des offiziellen Repositorys](https://raw.githubusercontent.com/docker-library/postgres/master/LICENSE); enthaltene Laufzeitprogramme haben eigene Lizenzen | **Keine** Entrypoint-/Packaging-Quellen kopiert oder geändert, keine Images weiterverteilt. `Dockerfile.upgrade` ist ein ursprüngliches Rezept, das getrennt bezogene Images referenziert. |
| Debian-Basis und darin enthaltene Bibliotheken | Debian 13 (trixie), aarch64; beide getesteten PostgreSQL-Images, u.a.ICU 76 | Unterschiedliche Paketlizenzen; maßgeblich sind die jeweiligen Dateien unter `/usr/share/doc/<Paket>/copyright` im bezogenen Image; [Debian-Lizenzgrundlagen](https://www.debian.org/legal/licenses/) | **Keine** Debian-Pakete/Binaries im Begleitpaket. Keine pauschale Umkennzeichnung der Distribution als 0BSD oder als einzelne Lizenz. |
| Python und Standardbibliothek | HostPython 3.14.6; Python Software Foundation | [PSF License Version 2 und zugehörige Hinweise](https://docs.python.org/3.14/license.html) | **Keine** Python-Laufzeit oder Standardbibliotheksquellen vendort. Der Laborcode importiert nur separat installierte Standardbibliotheksmodule. |
| Docker Engine /CLI/Desktop | Getesteter Engine 29.8.2 unter DockerDesktop; separat vom Leser bereitgestellt | Jeweilige Produkt-/Komponentenbedingungen des separat installierten Docker-Produkts, nicht0BSD dieses Labors | **Keine** Engine-, CLI- oder Desktop-Komponente mitgeliefert. |

## Lokal gebautes Upgradeimage

Das Rezept kopiert lokal `/usr/lib/postgresql/17` und `/usr/share/postgresql/17` aus dem fixierten offiziellen 17.12-Image in das fixierte offizielle 18.7-Image. Dadurch enthält **das lokal vom Leser gebaute Image** PostgreSQL 17- und 18-Binär-/Shared-Dateien sowie die Debian-Laufzeit des Basisimages. Dieses abgeleitete Image wird im öffentlichen Begleitpaket **nicht** verteilt. Wer später selbst ein Image verteilt, muss dessen tatsächliche Komponenten, Lizenztexte und Weitergabepflichten gesondert prüfen; diese Tabelle ist keine vollständige Software-Stückliste eines Images.

## Dokumentationsquellen und Lizenz des eigenen Pakets

Versions-/Semantikaussagen verweisen auf die offiziellen PostgreSQL-Dokumente und Release Notes; deren Volltexte werden nicht mitgeliefert. Der 0BSD-Lizenztext für ursprüngliche eigene Dateien entspricht der [OSI-Referenz 0BSD](https://opensource.org/license/0bsd). Er erfasst nur ursprünglichen Laborcode und ursprüngliche Labordokumentation im erlaubten Export, nicht das Manuskript, Produktmarken oder fremde Komponenten.
