# Sprint 5 — Wissenschaftlich fundiertes Recherche-Protokoll

**Zweck.** Nicht „was haben wir gefunden", sondern **wie** wir jede Datenart so
recherchieren, dass das Ergebnis MLB-prüffest ist: nachvollziehbar, quellenbelegt,
trianguliert, mit ehrlich markierten Lücken. Dieses Dokument ist der Methoden-Rahmen
für die Datengrundlage von Sprint 5.2; die bisherigen Funde stehen in
`SPRINT_5_DATA_RESEARCH.md`.

**Leitsatz.** Eine Zahl ohne Quelle, Datum und Reliabilitäts-Rating ist im
MLB-Kontext wertlos. Jedes Datum trägt seine Herkunft mit sich.

---

## 0 — Methoden-Rahmen (gilt für ALLE Punkte)

### 0.1 Daten-Qualitäts-Dimensionen (DAMA-Standard)
Jede Datenart wird gegen sieben Dimensionen geprüft: **Vollständigkeit**
(Coverage über beide Jahre, alle 30 Teams), **Genauigkeit** (stimmt der Wert),
**Konsistenz** (widerspruchsfrei zu anderen Quellen/zum Schedule), **Aktualität**
(passend zum Referenzjahr), **Validität** (richtiges Format/Domäne), **Eindeutigkeit**
(keine Dubletten), **Herkunft/Provenienz** (Quelle dokumentiert).

### 0.2 Quellen-Hierarchie (Primär > Sekundär > Tertiär)
1. **Primärquellen** — offizielle, autoritative Dokumente: der CBA-Vertrag selbst,
   MLB-/Network-Pressemitteilungen, Stadion-Betreiber-Kalender, Liga-Veröffentlichungen,
   Geschäftsberichte. *Immer zuerst.*
2. **Sekundärquellen** — qualifizierter Fachjournalismus mit Faktencheck: ESPN, The
   Athletic, AP, Sports Media Watch, Baseball America. Zur Triangulation und für
   Aufbereitung.
3. **Tertiärquellen** — Aggregatoren/Wikis (Wikipedia, Statista-Zusammenfassungen).
   Nur als Einstieg/Querverweis, nie als alleiniger Beleg.

### 0.3 Reliabilitäts-Bewertung — Admiralty Code (NATO-Standard)
Jede Datenzeile bekommt ein zweistelliges Rating: **Quellenzuverlässigkeit A–F**
(A = vollständig zuverlässig … F = nicht beurteilbar) × **Informations­glaubwürdigkeit
1–6** (1 = bestätigt durch andere Quellen … 6 = nicht beurteilbar). Beispiel:
offizieller CBA = **A1**; SMW-TV-Liste = **B2**; Ticketing-Aggregator für Konzerte =
**C3**. So wird „wie sicher ist das" maschinen- und prüflesbar.

### 0.4 Triangulation
**Mindestens zwei unabhängige Quellen** je harter Faktenzeile. Stimmen sie überein →
Rating hoch. Widersprechen sie sich → beide dokumentieren, Konflikt markieren, nicht
stillschweigend eine wählen.

### 0.5 Ground-Truth-Abgleich (projektspezifisch, der stärkste Test)
Das Projekt **besitzt die echten Spielpläne** (`data/mlb_schedule_2024.json`,
`2025.json`). Jede TV- und Venue-Zuordnung muss auf ein **real existierendes Spiel**
(Datum + Heim/Auswärts) treffen. Eine TV-Zeile, die zu keinem Spiel passt, ist
automatisch falsch. Das ist unser eingebautes Validierungs-Orakel — wissenschaftlich
gesehen ein objektiver Konsistenz-Check gegen einen Goldstandard.

### 0.6 Umgang mit Lücken & Proxys
Fehlende Daten werden **nicht erfunden**. Drei erlaubte Reaktionen: (a) explizit als
Lücke markieren; (b) dokumentierter Proxy mit offengelegter Annahme **plus
Sensitivitätsanalyse** (wie stark hängt das Ergebnis an der Annahme); (c) Beschaffung
an MLB delegieren. Nie (d) „plausibel raten ohne Kennzeichnung".

### 0.7 Reproduzierbarkeit
Ein **Recherche-Log** (Quelle, Abrufdatum, Suchbegriff, Rating) wird je Datenart
geführt, sodass ein Dritter die Recherche exakt nachvollziehen kann — das ist das
wissenschaftliche Kernkriterium (Replizierbarkeit).

---

## 1 — National-TV-Fenster

**Forschungsfrage.** Welches konkrete Spiel lief 2024 bzw. 2025 in welchem nationalen
Fenster, mit welcher Exklusivität — und welche Scheduling-Restriktion folgt daraus?

**Benötigte Felder (pro Eintrag):** Datum · Startzeit (ET) · Heim · Auswärts ·
Netzwerk (ESPN/FOX/FS1/TBS/Apple) · Fenster-Typ (national-exklusiv / regional /
Doubleheader) · Blackout-Implikation · Quelle · Rating.

**Quellen-Hierarchie konkret:**
- Primär: MLB.com National-Broadcast-Ankündigungen; Network-PR (ESPN Press Room, FOX
  Sports PR, Apple Newsroom) — geben die *exklusiven, gepinnten* Spiele.
- Sekundär: **Sports Media Watch** „MLB TV schedule" (kompiliert wöchentlich die
  nationalen Fenster) — ideal für die Pro-Woche-Tabelle. Awful Announcing für FOX/ESPN-Slates.
- Ground-Truth: jede Zeile gegen die Schedule-JSON prüfen.

**Methode.** Pro Saison eine Woche-für-Woche-Tabelle aufbauen; jede Zeile gegen den
echten Plan abgleichen; Exklusivitätstyp aus der PR ableiten (Apple-Freitag = hart
exklusiv; ESPN-Sonntag = national; FOX-Samstag = teils regional).

**Validitätsbedrohungen & Kontrollen.** (a) **Flex/Nachträge**: FOX/ESPN ergänzen
Spiele mitten in der Saison → Snapshot-Datum festhalten, „as scheduled" markieren.
(b) **Reschedules** (Regen) verschieben TV-Spiele → über die JSON gegenprüfen.
(c) Regionale vs. nationale Exklusivität nicht verwechseln (nur national-exklusive
erzeugen ein hartes Constraint).

**Akzeptanzkriterium.** ≥95 % der nationalen Fenster beider Saisons als Spiel-Zeilen
erfasst, jede gegen die JSON validiert, jede mit Rating ≥ B2.

---

## 2 — CBA-Reiseklauseln

**Forschungsfrage.** Welche *harten, vertraglich bindenden* Scheduling-Regeln gelten
2024/25 — im exakten Wortlaut — und wie formalisiert man sie maschinenlesbar?

**Benötigte Felder (pro Regel):** Artikel-Nummer · Verbatim-Text · formalisiertes
Prädikat (maschinenlesbar) · hart/weich · Quelle · Rating.

**Quellen-Hierarchie konkret:**
- Primär (einzig zulässig für den Wortlaut): das **Basic Agreement 2022–2026** selbst
  (= A1). Inklusive **Appendix C (Travel Times)** — die offiziellen In-Flight-Zeiten,
  auf die V(C)(8)/(9) verweisen; **bisher noch nicht extrahiert** → To-do.
- Vergleich: CBA 2017–2021 (Änderungs-Diff, schon belegt: ebenfalls 20-Tage-Regel).
- Sekundär: Baseball Prospectus „Article V" Analysen — nur zur Interpretation, nie als Wortlaut.

**Methode.** Volltext-Extraktion von Article V; jede Klausel als (Verbatim → Prädikat)
abbilden; gegen den realen 2024-Plan testen (ist er compliant?). **Appendix C** als
Tabelle ziehen und mit den im Repo verwendeten Reisezeiten abgleichen.

**Validitätsbedrohungen & Kontrollen.** (a) **Falsche Vertragsversion** → nur
2022–26 für die Referenzjahre. (b) **Interpretation ≠ Wortlaut** → Sekundärquellen nie
zitieren, wo der Vertrag selbst spricht. (c) **Annahmen, die wie Regeln aussehen** →
siehe AC-2.1.8-Befund (das „13-Tage"-Limit war keine Regel). Lehre: jede Regel muss
auf eine Vertragszeile zeigen, sonst ist sie eine markierte Annahme.

**Akzeptanzkriterium.** Alle Article-V(C)-Klauseln verbatim + formalisiert; Appendix C
extrahiert; realer Plan testbar compliant; jede Regel A1-belegt oder als Annahme markiert.

---

## 3 — Venue-Belegung

**Forschungsfrage.** An welchen Tagen ist ein MLB-Stadion 2024/25 *nicht* für ein
Heimspiel verfügbar (geteilte Nutzung, Konzert, Event, Lease-/Ordnungs-Limit)?

**Benötigte Felder (pro Konflikt):** Venue · Datum(sbereich) · Event-Typ · Schwere
(harter Blackout vs. weiche Friktion) · Co-Tenant (falls geteilt) · Quelle · Rating.

**Quellen-Hierarchie konkret:**
- Primär: **Stadion-Betreiber-Eventkalender** (offizielle Venue-Site); bei geteilten
  Venues der **Co-Tenant-Spielplan** (z. B. Sacramento-River-Cats-Heimtermine =
  A's-Blackout-Tage 2025; Tampa-Tarpons für Steinbrenner Field); **Lease-/City-
  Ordinance-Dokumente** für Day-Game-Limits (V(C)(8) verweist genau darauf).
- Sekundär: Pollstar/Songkick/Ticketmaster (Konzerttermine), Lokaljournalismus.
- Ground-Truth: Konflikt-Tage gegen die Heimspieltage in der JSON schneiden.

**Methode.** Pro Stadion × Jahr alle Nicht-MLB-Events im Saisonfenster enumerieren;
auf Heimspiel-Kollisionen mappen. **Für geteilte Venues** die Belegung *deduktiv* aus
dem Co-Tenant-Plan ableiten (mathematisch exakt: River-Cats-Heim ⇒ A's-Auswärts).

**Validitätsbedrohungen & Kontrollen.** (a) **Aggregator-Unvollständigkeit**
(Ticketing zeigt nicht jedes Event) → mit Venue-Kalender triangulieren. (b)
**Einmal- vs. wiederkehrend** unterscheiden. (c) **Saisonfenster-Filter** (nur
Konflikte innerhalb der MLB-Saison zählen). (d) Geteilte Venues sind die *harten*
Fälle und haben Priorität vor Konzert-Friktion.

**Akzeptanzkriterium.** Alle harten geteilten-Venue-Konflikte 2025 exakt aus
Co-Tenant-Plänen abgeleitet; Standard-Stadien mit dokumentierter Coverage-Tiefe;
jede Zeile A2–C3 geratet.

---

## 4 — Gate-Receipts / Revenue

**Forschungsfrage.** Wie schätzen wir Pro-Spiel-Einnahmen so genau wie öffentlich
möglich — und wo ist die ehrliche Decke?

**Benötigte Felder:** pro Spiel: Attendance (vorhanden) · geschätzter Ticket-Preis-
Tier · abgeleiteter Gate-Proxy. Pro Team-Saison: **Forbes-Gate-Receipt-Schätzung**
(Jahres-Summe) zur Kalibrierung · Fan-Cost-Index-Pro-Team · Quelle · Rating.

**Quellen-Hierarchie konkret:**
- Primär (nicht öffentlich): club-/MLB-interne Finanzreports → realistisch *nicht*
  beschaffbar.
- Bester öffentlicher Ersatz: **Forbes „MLB Team Valuations"** — publiziert jährlich
  **geschätzte Gate-Receipts pro Franchise** (modelliert, nicht auditiert = B3).
  **Team Marketing Report Fan Cost Index** (Pro-Team-Durchschnittspreise, teils
  paywall). Statista-Aggregationen.
- Ground-Truth-Kalibrierung: Proxy-Summe je Team-Saison gegen Forbes-Jahres-Schätzung
  abgleichen → Skalierungsfaktor.

**Methode (wissenschaftlich sauber).** Proxy = Attendance × geschätzter Durchschnitts­-
preis (FCI-Tier). Dann **Kalibrierung**: Σ(Proxy je Heimspiel) ≈ Forbes-Jahres-Gate →
Faktor bestimmen. Danach **Sensitivitätsanalyse**: wie stark verändert ±20 % Preis das
Optimierungsergebnis? Wenn robust → Proxy tragfähig. Validierung gegen die schon
gemessene Attendance-Korrelation (Spearman 0,89).

**Validitätsbedrohungen & Kontrollen.** (a) **Sekundärmarkt ≠ Face Value** → nur
Face-Value/FCI nutzen. (b) **Dynamic Pricing & Premium-Seating** verzerren Mittelwerte
→ als Annahme offenlegen. (c) **Forbes ist modelliert** (B3), kein Audit → nie als
„echt" labeln. (d) Gate ≠ Gesamtrevenue (kein Media/Sponsoring) → Scope klar abgrenzen.

**Akzeptanzkriterium.** Kalibrierter Proxy mit dokumentierter Annahme + Sensitivitäts­-
analyse; klar als Proxy (nicht „echte Receipts") markiert; gegen Forbes plausibilisiert.

---

## 5 — Reichen vier Datenarten? (Nein.) — Erweiterte Daten-Taxonomie

Die vier sind die *bekannten Blocker*. Ein MLB-prüffestes System braucht mehr. Kandidaten,
nach Hebel sortiert; viele sind im Repo schon angelegt und nur zu vertiefen:

| # | Dimension | Warum nötig | Repo-Stand |
|---|---|---|---|
| 5 | **Reisezeiten/Geo** — exakte Stadion-Koords, **CBA Appendix C In-Flight-Zeiten**, Zeitzonen | Kern der Optimierung; Appendix C ist die *offizielle* Reisezeit-Referenz | teils (`distance`, `timezones`, `team_airports`) |
| 6 | **Wetter/Klima** — Niederschlags-Wahrscheinlichkeit je Stadt/Monat, Dach-Status, Hurrikan-Saison | Rainout-Risiko, Getaway-Regeln, Venue-Robustheit | teils (`ops_security` Klimatologie) |
| 7 | **Sonderspiele/Serien** — International (Seoul/London/Mexiko/Tokio), Field of Dreams, Little League Classic, Rickwood, Feiertage (4. Juli, Memorial/Labor Day, Jackie Robinson Day 15.4.) | harte Pins + Revenue-/Reise-Sonderfälle | teils (`holidays`, `holiday_pins`) |
| 8 | **Schedule-Format-Regeln** — Balanced Schedule (seit 2023), Divisions-/Interleague-Struktur, Serienlängen-Normen | definiert den *zulässigen Lösungsraum* | implizit im Generator |
| 9 | **Spieler-Belastung / Chronobiologie** — peer-reviewte Jetlag-/Zirkadian-Literatur (MLB-spezifisch) | wissenschaftliche Fundierung der Fatigue-/Getaway-Heuristiken | `player_fatigue`, `feasibility` |
| 10 | **Nachfrage-Treiber der Attendance** — Wochentag, Gegner-Zugkraft, Promotions, Schulferien, Wetter | schärft das Revenue-Modell über reinen Preis hinaus | Proxy in `revenue` |
| 11 | **RSN-/Blackout-Territorien** — regionale Sender-Gebiete | lokale TV-Verfügbarkeit, ergänzt nationale Fenster | offen |
| 12 | **Ops-Daten** — Hotel-Historie, Ground-Transport, EMS/Security | die Ops-Suite (5.3) | Seeds vorhanden (`ops_*`) |

**Wissenschaftliche Fundierung (Punkt 9) konkret:** Es existiert begutachtete
Literatur zu MLB-Reise/Zirkadian-Effekten (Jetlag und Leistungseinbußen, West-vs-Ost-
Asymmetrie, Heimvorteil-Modulation). Diese Studien liefern *evidenzbasierte Gewichte*
für die Fatigue-Terme — statt geratener Strafkosten. Recherche-Methode hier: gezielte
Literatur-Suche (Google Scholar/PubMed), Studien nach Stichprobe/Peer-Review filtern,
Effektstärken extrahieren, als kalibrierte Parameter einziehen.

---

## 6 — Mein aktueller Überblicks-Stand (ehrliche Selbsteinschätzung)

| Datenart | Wie gut habe ich es | Aufwand bis „MLB-fest" |
|---|---|---|
| **CBA** (Pkt 2) | 🟢 am besten — Wortlaut verbatim, A1; Befund AC-2.1.8 geklärt | klein (nur Appendix C nachziehen) |
| **TV-Fenster** (Pkt 1) | 🟢 Struktur sicher; Spiel-für-Spiel offen | mittel (Fleißarbeit + JSON-Abgleich) |
| **Venue** (Pkt 3) | 🟡 harte geteilte-Venue-Fälle sicher; Konzert-Coverage dünn | mittel-hoch (30 Stadien × 2 J) |
| **Gate-Receipts** (Pkt 4) | 🟡 Methode klar; Forbes-Kalibrierung noch nicht gezogen | mittel; Decke bleibt Proxy |
| **Reise/Appendix C** (Pkt 5) | 🟠 Quelle lokalisiert (im CBA), noch nicht extrahiert | klein-mittel, hoher Hebel |
| **Chronobiologie** (Pkt 9) | 🟠 weiß, dass Literatur existiert; noch nicht systematisch | mittel, hoher Glaubwürdigkeits-Hebel |

**Fazit:** Am festesten stehe ich beim **CBA** (verbatim + korrigierter Befund). Den
größten *unterschätzten* Hebel sehe ich bei **Appendix C (offizielle Reisezeiten)** und
der **chronobiologischen Literatur** — beides macht das System von „plausibel
parametriert" zu „evidenzbelegt", und genau das beeindruckt eine MLB-Prüfung.

---

## 7 — Empfohlene Recherche-Reihenfolge (nach Hebel × Sicherheit)

1. **CBA Appendix C** extrahieren (klein, A1, hoher Hebel — offizielle Reisezeiten).
2. **TV Spiel-für-Spiel** 2024/25 mit JSON-Abgleich (sicher, fleißig).
3. **Venue** geteilte Venues exakt (River Cats/Tarpons-Pläne) → dann Konzert-Coverage.
4. **Forbes-Kalibrierung** des Gate-Proxys + Sensitivitätsanalyse.
5. **Chronobiologie-Literatur** für evidenzbasierte Fatigue-Gewichte.
6. **Sonderspiele/Feiertage** (Pkt 7) als harte Pins vervollständigen.
