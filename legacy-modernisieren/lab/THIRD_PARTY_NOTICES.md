# Hinweise zu Drittkomponenten

Originaler Havelblick-Laborcode und die ausdrücklich beigefügten originalen Labordokumente stehen unter 0BSD (`LICENSE`). Das lizenziert weder PostgreSQL noch JDK, JDBC-Treiber oder Betriebssystemkomponenten um.

| Komponente | Ursprung / Version | Lizenz | Im öffentlichen Quellpaket verteilt? |
|---|---|---|---|
| Temurin/OpenJDK | [Adoptium-Veröffentlichung](https://adoptium.net/news/2026/10/eclipse-temurin-17021-21013-2505-2701-available),21.0.13+9; offizielles Containerimage, Digest im Dockerfile | GPLv2 mit Classpath Exception für OpenJDK-Teile; weitere Hinweise im unveränderten Image unter `/opt/java/openjdk/legal` | **Nein**, ausschließlich Imageverweis; Nutzer lädt das Originalimage. |
| Ubuntu Noble im JDK-Image | Unveränderte offizielle Temurin-Imagebasis | Mehrere Originallizenzen | **Nein**, kein Image-/Rootfs-Export. |
| PostgreSQL | [Offizielles Projekt](https://www.postgresql.org/),18.7; offizielles Image | [PostgreSQL License](https://www.postgresql.org/about/licence/), Betriebssystemteile separat | **Nein**, ausschließlich Imageverweis. |
| pgJDBC | [Offizieller Download](https://jdbc.postgresql.org/download/),42.7.14 | BSD-2-Clause; Originaltext unter `licenses/META-INF/LICENSE` | **Kein JAR**. `scripts/fetch_dependencies.py` lädt exakt die Originaldatei und prüft den manifestierten SHA-256. Lizenztext liegt zur Einsicht bei. |
| OnGres SCRAM client/common | Im offiziellen pgJDBC42.7.14-JAR,3.2 | Mitgelieferte BSD-Texte unter `licenses/META-INF/licenses/com.ongres.scram/` | **Keine Binärklassen**; nur aus dem Original-JAR erhaltene Lizenztexte. |
| OnGres SASLprep/Stringprep | Im offiziellen pgJDBC42.7.14-JAR,2.2 | Mitgelieferte BSD-Texte unter `licenses/META-INF/licenses/com.ongres.stringprep/` | **Keine Binärklassen**; nur Lizenztexte. |
| Python | Nutzerinstallation, Standardbibliothek; lokal3.14.6 geprüft | PSF-/mitgelieferte Hinweise der eigenen Installation | **Nein**; keine Python-Runtime, keine pip-Pakete beigefügt. |

Der begleitende Export enthält ausschließlich freigegebene Quellen, synthetische Fixtures und technische Dokumente. Manuskripte, Rezensionen, lokale Befehls-/HTTP-Protokolle, Containerdaten, Archive, JAR-Dateien, Images und private Hostpfade gehören nicht hinein. Der Exportplan ist eine Auswahlhilfe für die spätere Veröffentlichung, keine behauptete Veröffentlichung oder unabhängige Lizenzabnahme.
