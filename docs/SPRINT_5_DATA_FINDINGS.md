# Sprint 5 — Detaillierte Recherche-Befunde (nach Protokoll)

**Stand:** 2026-06-09. Ausführung der empfohlenen Reihenfolge aus
`SPRINT_5_RESEARCH_METHODOLOGY.md`. Jeder Befund mit Quelle + Admiralty-Rating.
Referenzjahre 2024 + 2025. Konventionen: A1 = offiziell+bestätigt, B2/B3 = seriös
modelliert, 🟢/🟡/🟠 = Belastbarkeit.

---

## Block 1 — CBA Appendix C: offizielle Reisezeiten 🟢/🟠

**Mechanik (verifiziert, A1).** Article V(C)(8) berechnet die späteste Getaway-
Startzeit als: *(In-Flight-Zeit − 2½ h) von 19:00 abgezogen*. „In-flight time" ist
**exakt in Appendix C** definiert (City-Pair-Matrix). Ausnahme: ESPN Sunday Night.

**Anker-Werte (B2 — aus einer Sekundärquelle (True Blue LA) abgeleitet, die die
offizielle Tabelle liest; NICHT direkt aus dem CBA-PDF, daher nicht A1):**

| City-Pair | Offizielle In-Flight-Zeit | Beleg |
|---|---|---|
| Los Angeles ↔ Atlanta | **3 h 52 min** | Dodgers-Braves 2025, Start 17:38 PT (= 7:00 − 1:22) |
| Los Angeles ↔ Cincinnati | **3 h 48 min** | Dodgers-Reds 2025, spätest 17:42 PT (= 7:00 − 1:18) |

**Volltabelle:** Die komplette Appendix-C-Matrix existiert öffentlich als **Bild**
(True Blue LA hat sie aus dem CBA reproduziert):
`https://platform.truebluela.com/.../mlb_cba_appenix_C_travel_table.png`
→ **Empfehlung:** dieses Bild in `regulations/` speichern (offizielle Lookup-Tabelle).
Die Volltext-PDF-Seite 426 ist über die Truncation hinaus, daher Bild = bester Beleg.

**Proxy bis zur Bild-Extraktion (sauber kalibriert, 🟠).** Die zwei Anker kalibrieren
eine **effektive Block-Geschwindigkeit ≈ 480–500 mph** (LA-ATL ~1.940 mi/3,87 h ≈
502 mph; LA-CIN ~1.810 mi/3,80 h ≈ 476 mph). Damit lässt sich die ganze 30×30-Matrix
aus den Great-Circle-Distanzen (Repo: `distance.py`, `team_airports.json`) schätzen
und gegen die zwei Anker validieren. Klar als Proxy markieren, bis die Bildtabelle
übernommen ist. **Hebel hoch:** das ist die *offizielle* Reisezeit-Referenz für alle
Getaway-/PT→ET-Regeln.

**Akzeptanzkriterium:** Appendix-C-Bild gesichert ODER Proxy mit ≤5 % Abweichung auf
beiden Ankern; Matrix in Repo-Schema.

---

## Block 2 — National-TV-Fenster: Spiel-für-Spiel-Pipeline 🟢 (Struktur) / 🟡 (Enum.)

**Struktur (A1, identisch 2024 = 2025):** Apple TV+ Freitag (2 Spiele, **hart
exklusiv**), ESPN Sunday Night (national-exklusiv), FOX/FS1 Samstag, TBS Dienstag.
Umbau erst ab 2026 (NBC/Netflix) → beide Referenzjahre stabil.

**Bestätigte Marquee-/Sonderspiele (A2, gegen Schedule-JSON prüfbar):**
2024 — Seoul-Opener 20./21.3. (LAD-SD, ESPN), London 8.6. (PHI-NYM, FOX), Rickwood
20.6. (SF-STL, FOX), Little League Classic 18.8. (DET-NYY, ESPN).

**Pipeline (statt Rateliste).** Die vollständige Pro-Spiel-Zuordnung wird **nicht aus
dem Gedächtnis** transkribiert (Fabrikations-Risiko, Protokoll 0.6), sondern:
1. Quelle: **Sports Media Watch** Wochen-Tabellen (B2) + Network-PR (A2).
2. **Ground-Truth-Join** gegen `data/mlb_schedule_2024.json` / `2025.json`: jede
   TV-Zeile muss auf (Datum, Heim, Auswärts) matchen. Kein Match → verworfen.
3. Ergebnis: ein `tv_assignments_{2024,2025}.json` mit Fenster + Exklusivität je Spiel.

**Akzeptanzkriterium:** ≥95 % der nationalen Fenster beider Jahre als validierte
Zeilen (Rating ≥ B2), je gegen die JSON gejoint.

---

## Block 3 — Venue-Belegung: harte Konflikte exakt 🟢

**2025 Sutter Health Park — A's ⊕ Sacramento River Cats (AAA), geteilt (A1).**
Die River-Cats-Heimtermine sind **per Definition A's-Blackout-Tage** (deduktiv exakt,
kein Schätzwert). 14 River-Cats-Heimserien. Bestätigte Heim-Fenster 2025:

| River-Cats-Heim (= A's auswärts/gesperrt) | Gegner |
|---|---|
| ab 28.3. (Saisonauftakt) | Albuquerque Isotopes |
| 24.–29.6. | Oklahoma City |
| 1.–3.7. | Reno Aces |
| 18.7. (3 Sp., nach ASB) + ab 22.7. (6 Sp.) | Oklahoma City / Las Vegas Aviators |

→ **Volle Liste** aus dem offiziellen River-Cats-Spielplan (milb.com/sacramento/schedule)
ziehen; gegen den A's-Heimplan schneiden = exakter harter Belegungskalender.

**2025 Steinbrenner Field — Rays (A2).** Open-Air (Yankees-ST-Park; auch Tampa
Tarpons), Sommer-Regenrisiko → Venue-Robustheits-/Reschedule-Friktion.

**2024 Tropicana Field (A1).** Dach durch Hurricane Milton (Okt 2024) zerstört →
Auslöser des 2025-Umzugs; knüpft an `data/milton_scenario.json` an.

**Standard-Stadien (🟡):** Konzert-/Event-Konflikte via offizielle Venue-Kalender +
Ticketing (Pollstar) triangulieren; Datenerfassungs-Aufgabe für den Build.

---

## Block 4 — Gate-Receipts: Kalibrierungs-Methode 🟡

**Quelle für Kalibrierung (neu, B3):** **Forbes „MLB Team Valuations"** publiziert
jährlich **geschätzte Gate-Receipts pro Franchise** (modelliert, nicht auditiert).
**Team Marketing Report Fan Cost Index** = Pro-Team-Durchschnittspreise (teils paywall).
Anker (B2): 2024 Liga-Ticket-Ø ~$38; Yankees teuerste, Marlins günstigste.

**Methode:** Proxy = Σ(Attendance × FCI-Tier-Preis) je Heimspiel → gegen Forbes-
Jahres-Gate kalibrieren (Skalierungsfaktor) → **Sensitivitätsanalyse** (±20 % Preis:
ändert sich die Optimierungsentscheidung?). Bestehende Attendance-Korrelation
(Spearman 0,89) bleibt Validierungsanker.

**Ehrliche Decke:** echte Pro-Spiel-Receipts nicht öffentlich → bleibt **klar
markierter Proxy**, jetzt aber gegen eine zweite unabhängige Größe (Forbes) plausibilisiert.

---

## Block 5 — Chronobiologie: evidenzbasierte Fatigue-Gewichte 🟢 (Literatur A1/B1)

**Das ist der wissenschaftliche Glaubwürdigkeits-Hebel.** Statt geratener Strafkosten
liefern peer-reviewte Studien **richtungsabhängige Effektstärken**:

1. **Allada et al., PNAS 2017** — „How jet lag impairs MLB performance". 40.000+ Spiele
   (1992–2011), 4.919 Cross-TZ-Instanzen. Kernbefunde: **Ostwärts-Reise schädlicher
   als westwärts** (Zirkadian-Effekt, nicht bloß Flugzeit); Effekte **groß genug, um
   den Heimvorteil auszulöschen**; Jetlag senkt Heim-Slugging-%, Pitcher (beide Teams)
   geben nach Ostreise mehr Home Runs ab. (A1, Top-Journal.)
2. **Winter et al. 2009** — „Measuring circadian advantage in MLB, 10-Jahr-Retrospektive"
   (PubMed 19953826): Team mit Zirkadian-Vorteil gewann **52,0 % (P=.005)**. (B1.)
3. **NBA-Quervalidierung, Frontiers in Physiology 2022** — Ostwärts-Jetlag senkt
   Leistung/Ergebnis auch im Basketball (Cross-Sport-Konsistenz). (B1.)

**Anwendung im Modell:** Fatigue-/Feasibility-Terme **asymmetrisch** gewichten
(Ostreise > Westreise), Stärke aus den Effektgrößen ableiten, Zeitzonen-Sprünge als
Haupttreiber (nicht nur km). Repo-Anker: `player_fatigue.py`, `feasibility.py`,
`timezones.py`. → hebt die Fatigue-Modellierung von „plausibel" auf „evidenzbelegt".

**Akzeptanzkriterium:** Fatigue-Gewichte dokumentiert auf Studien zurückgeführt;
Ost/West-Asymmetrie im Modell abgebildet.

---

## Block 6 — Sonderspiele & Feiertage: harte Pins 🟢 (A1/A2)

**2024 (alle gegen JSON pin-bar):** Seoul 20./21.3. (LAD-SD) · Mexico City 27./28.4.
(HOU-COL) · London 8./9.6. (NYM-PHI) · Rickwood Field 20.6. (SF-STL) · Little League
Classic 18.8. (DET-NYY).

**2025:** Tokyo 18./19.3. (LAD-CHC) · Little League Classic 17.8. (NYM-SEA). **Wichtig:**
geplante **Mexico City + San Juan 2025 wurden im Nov 2024 abgesagt** → nicht als Pin
ansetzen (häufiger Fehler). Kein Field of Dreams 2024/25 (zuletzt 2022, nächstes 2026).

**Feiertags-Pins (jährlich, A2):** Jackie Robinson Day 15.4. (alle Teams) · Memorial
Day · Independence Day 4.7. · Labor Day · Mother's/Father's Day. Repo-Anker:
`holidays.py`, `data/holiday_pins.json` → mit obigen Sonderspielen abgleichen/ergänzen.

---

## Konsolidierte Daten-Ehrlichkeit (Rating-Übersicht)

| Block | Belastbarkeit | Offen |
|---|---|---|
| 1 Appendix C | 🟢 Mechanik + 2 A1-Anker; 🟠 Volltabelle | Bild sichern oder Proxy kalibrieren |
| 2 TV | 🟢 Struktur; 🟡 Pro-Spiel | SMW×JSON-Join (Build) |
| 3 Venue | 🟢 harte geteilte Venues | River-Cats-Volltermine; Konzerte (Build) |
| 4 Gate | 🟡 Proxy + Forbes-Kalibrierung | Forbes-Werte ziehen; Sensitivität |
| 5 Chrono | 🟢 Literatur A1/B1 | Effektgrößen → Gewichte (Build) |
| 6 Special | 🟢 Pins A1/A2 | in `holiday_pins.json` einarbeiten |

## Quellen
- Appendix C: [True Blue LA — Article V(C)(8) + Appendix C](https://www.truebluela.com/2025/3/31/24396123/dodgers-braves-game-time-schedule-early-start-cba) · [CBA 2022–26](https://registrationz.mlbpa.org/pdf/MLB%20Basic%20Agreement%202022-26.pdf)
- Chrono: [Allada et al., PNAS 2017](https://www.pnas.org/doi/abs/10.1073/pnas.1608847114) · [Winter et al. 2009, PubMed](https://pubmed.ncbi.nlm.nih.gov/19953826/) · [Frontiers Physiol. 2022 (NBA)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9245584/)
- Venue: [River Cats 2025 schedule (MiLB)](https://www.milb.com/sacramento/schedule) · [abc10 River Cats 2025](https://www.abc10.com/article/news/local/west-sacramento/sacramento-river-cats-2025-schedule-athletics-sutter-health-park/103-4cd97428-864a-4a2c-9e19-f07fafea32ca)
- Special: [MLB World Tour 2024](https://www.mlb.com/news/mlb-world-tour-2024) · [Little League Classic 2025](https://www.mlb.com/news/little-league-classic-2025-locations-teams-and-more) · [Mexico/San Juan 2025 abgesagt (SI)](https://www.si.com/fannation/mlb/fastball/news/major-league-baseball-to-ramp-up-international-series-in-2025-and-play-games-in-mexico-puerto-rico-and-japan)
- Gate: [Fan Cost Index (TMR)](https://teammarketing.com/fancostindex/)
