# Lizenzinventar des Lehrlabors

Stand: 18.11.2026. Dies ist ein Komponenteninventar für den hier verwendeten Stand, keine pauschale Rechtsprüfung oder vollständige Betriebssystem-SBOM.

| Komponente | Stand | Lizenz / Nachweis |
|---|---|---|
| Neuer Havelblick-Java-/SQL-/Python-Code | Arbeitsstand dieses Nutzerprojekts | Neu erstellter Originalcode unter der ausdrücklich festgelegten 0BSD-Lizenz, siehe `LICENSE`. |
| Eclipse Temurin / OpenJDK | 21.0.13+9, offizielles gepinntes Image | GPLv2 mit Classpath Exception für betroffene OpenJDK-Teile; weitere Hinweise im unveränderten Image unter `/opt/java/openjdk/legal`. |
| Ubuntu-Basis des Temurin-Images | Noble, durch Image-Digest fixiert | Mehrere Komponentenlizenzen; Copyrightdateien im offiziellen Image bleiben erhalten. Das Buch darf daraus keine einheitliche Ubuntu-Lizenz ableiten. |
| PostgreSQL | 18.7, offizielles gepinntes Image | [PostgreSQL License](https://www.postgresql.org/about/licence/); Debian-Basis mit weiteren unverändert erhaltenen Hinweisen. |
| pgJDBC | 42.7.14 | BSD-2-Clause-artiger Originaltext in `licenses/META-INF/LICENSE`, aus dem verwendeten JAR extrahiert; [Upstream-Tag](https://github.com/pgjdbc/pgjdbc/blob/REL42.7.14/LICENSE). |
| OnGres SCRAM client/common | 3.2, im pgJDBC-JAR enthalten | Mitgelieferte Texte unter `licenses/META-INF/licenses/com.ongres.scram/`; nicht als selbst entwickelte Authentifizierung ausgeben. |
| OnGres SASLprep/Stringprep | 2.2, im pgJDBC-JAR enthalten | Mitgelieferte Texte unter `licenses/META-INF/licenses/com.ongres.stringprep/`. |
| Python | Host 3.14.6, nur Testorchestrierung | Python-Standardbibliothek, keine zusätzlichen pip-Pakete; PSF-/mitgelieferte Hinweise der Hostinstallation. |

Die JAR-Datei wird beim Build vom offiziellen pgJDBC-Download bezogen und ihr Hash geprüft. Sie ist nur lokaler Buildcache und wird nicht mit dem öffentlichen Quellpaket verteilt. Sie wird nicht entpackt um ihre Lizenzhinweise zu entfernen; die separat extrahierten Texte erleichtern die Prüfung. Werden Bibliotheken oder Images später aktualisiert, ist dieses Inventar erneut abzugleichen. Container-/Java-Ausgaben werden im Versionsmanifest gespeichert; Manifestprüfung ist keine Sicherheitsfreigabe für fremde produktive Systeme.
