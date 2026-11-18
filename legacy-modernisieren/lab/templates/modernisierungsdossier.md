# Modernisierungsdossier – ausfüllbare Vorlage

Das ausgefüllte Beispiel weiter unten ist synthetisch. Weder eine Firmenhistorie noch eine reale Kundenfreigabe wird behauptet.

## Änderungskarte

- Fachliches Ziel und bestehende Invariante:
- Betroffene Schreiber und Leser einschließlich Batch:
- Heutige Beobachtung / Belegpfad:
- Bekanntes Fehlverhalten, ausdrücklich kein Soll:
- Gewählter Schnitt und begründete Alternative:
- Abnahmekriterien:
- Abbruchsignal und wer entscheiden muss:
- Rückweg vor / nach neuen Schreibvorgängen:
- Betriebs- und Datenrisiko:
- Noch unbewiesene Annahmen:
- Nachweis der Ausführung mit Version und Hash:

## Ausgefülltes synthetisches Beispiel

**Ziel:** Für einen akzeptierten Auftrag nach einem Workerabbruch keinen verlorenen Versandvorgang und bei erneuter Zustellung keine zweite Versandwirkung erzeugen. Ein bestimmter Microservice-Zuschnitt ist kein Teil des Ziels.

**Ausgangsbeleg:** T06 zeigt die Lücke zwischen gespeichertem Auftrag und direktem Versand. Die beobachtete Lücke ist ein Fehler, kein zu konservierendes Sollverhalten.

**Alternative A:** Versand im Monolithen lassen und ebenfalls eine Outbox verwenden. Das kann die gleiche Haltbarkeit des Versandauftrags erreichen, ohne einen zusätzlichen HTTP-Dienst zu betreiben.

**Alternative B:** Separaten Empfänger mit eigenem Schreibrecht auslagern. Gewählt für die Lehre, um Vertrag, Duplikatbehandlung und getrennte Fehler zu zeigen; kein gemessener Wirtschaftlichkeitsvorteil behauptet.

**Abnahme:** T11 muss nach echtem Exit 70 ein offenes Ereignis und eine bereits gespeicherte Versandannahme zeigen. Wiederanlauf muss dieselbe Ereignis-ID erneut zustellen; es bleibt eine Versandwirkung. T13 muss einen zeitweise gestoppten Empfänger sowie die Quarantäne einer ungültigen Nachricht sichtbar machen.

**Abbruch:** Unklare Zahlung, verlorenes Ereignis, unerklärte Betragsabweichung oder doppelte Versandwirkung verhindert die Freigabe. Das Labor behandelt keine echten Rückerstattungen.

**Rückweg:** Eine Routingrücknahme vor Übernahme neuer Daten ist von der Rückübertragung nach neuen Zielschreibvorgängen getrennt. T18 liefert den konkreten Gegenbeweis gegen den bloßen Flagwechsel; neue Daten werden unter Sperrgrenze zurückgeführt.

**Restschuld:** Gemeinsamer Katalog/Bestand, kurze offene Transaktion beim HTTP-Versand, fehlender produktiver Refund-/Void-Prozess und beschränktes Verbraucherinventar. Der nächste Schnitt folgt einem nachgewiesenen Problem; kein pauschaler weiterer Dienst wird empfohlen.

**Status:** Erwartete Beleg-IDs sind in der Vorlage benannt. Ihr tatsächlich bestandener Stand muss aus `evidence/results.json` gelesen werden; diese Vorlage ist kein Ersatz für das Ausführungsprotokoll.
