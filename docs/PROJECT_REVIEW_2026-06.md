# Projekt-Review & Schwachstellen-Liste (Stand 2026-06-02)

**Zweck:** Das gesamte Projekt feature-für-feature gegen den Stand der Technik (Open-Source-
Sport-Scheduling, wissenschaftliche Literatur, publizierte MLB-Daten) prüfen und priorisiert
auflisten, **was für echte MLB-Tauglichkeit noch zu schwach ist oder fehlt**. Ehrlich, mit
Quellen, ohne Schönfärberei.

> Bewertungsskala: ✅ MLB-tauglich · 🟡 brauchbar, aber ausbaubedürftig · 🔴 zu schwach / fehlt.

---

## 0 — Was bereits stark ist (verifiziert)

- **Reisemodell ist validiert.** Unsere Haversine-„lineare Meilen zwischen Ballparks" treffen
  publizierte MLB-2024-Zahlen auf ~1 %: SEA 76.142 km ≈ 47.300 mi (publiziert **47.441 mi**),
  PIT 43.024 km ≈ 26.700 mi (publiziert **26.411 mi**). „Lineare Meilen" ist die
  Industrie-Standardmethodik — wir nutzen sie korrekt. ✅
- **Warm-Start schlägt den realen Plan** (Reise −5,4 % 2024 / −2,6 % 2025) bei **0 CBA-
  Verletzungen** — auf der Achse, die für die Liga zählt, sind wir besser als der Profi-Plan. ✅
- **Determinismus** (bit-identisch je Seed), **332 Tests**, ehrlicher Backtest-Harness,
  CO₂/Fairness mit zitierten Quellen. ✅

---

## 1 — Priorität P0 (blockiert echten MLB-Einsatz)

### P0-1 🔴 AC-2.1.8 (≤13 Auswärtstage) ist im From-Scratch-Generator NICHT garantiert
**Was:** Der Kalt-Start lässt je nach Seed **3–6 Teams >13 Tage** (worst ~17–20). Das ist eine
**CBA-Verletzung** → ein solcher Plan ist für die Liga unbrauchbar, egal wie gut die Reise ist.
**Stand Technik:** Das ist das **Traveling Tournament Problem** (APX-hart). Exakt lösbar nur
~10–18 Teams; für 30 nutzt die Literatur Branch-and-Price oder kommerzielle Solver
(Gurobi/CPLEX). Sieben CP-SAT-Standardansätze wurden hier bereits als intraktabel belegt
(`docs/Q10_ANALYSE_UND_RECHERCHE.md`).
**Empfehlung:** (a) **Kurzfristig MLB-tauglich:** Warm-Start zum *einzigen* Produktionspfad
machen — er ist nachweislich CBA-konform und repariert sogar reale Verletzungen. (b)
**Mittelfristig:** Branch-and-Price mit kommerziellem Solver als separates, beschaffungs-
gegatetes Item (die ehrliche, in der Literatur belegte Lösung für 30-Team-TTP).
**Quellen:** Anagnostopoulos et al. (TTSA); Easton/Nemhauser/Trick (TTP Benchmarks);
Trick, *Adventures in Sports Scheduling*.

---

## 2 — Priorität P1 (Qualität deutlich unter Stand der Technik / fehlende Realregeln)

### P1-1 🟡 From-Scratch-Generator: +9 % Reise vs. real, 2025 intraktabel
**Was:** Kalt-Start (CP-SAT+SA) erreicht ~+9 % über dem realen Plan; für 2025 liefert CP-SAT
sogar UNKNOWN. **Empfehlung:** Warm-Start als Default formalisieren (umgesetzt: `--warm-start`),
From-Scratch nur noch als Algorithmus-Validierung. Optional Kalt-Start verstärken (s. P1-5).

### P1-2 🔴 Keine Doubleheader-Planung
**Was:** Der Generator erzeugt **0 Doubleheader**; der reale Plan nutzt **29** (Day-Night-DH
zur Verdichtung + Wetter-Makeups). Roundtrip erhält DH jetzt (Bug gefixt), aber wir können
keine planen. **Stand Technik:** DHs sind ein Standard-Verdichtungswerkzeug realer Planer.
**Empfehlung:** DH als optionalen Constraint/Move einführen (gezielte Day-Night-DH zur Reise-/
Trip-Verdichtung; Makeup-Logik im Disruption-Handler). **Aufwand: mittel-hoch.**

### P1-3 🔴 Fehlende echte MLB-Hard-Constraints (Charter Track D, größtenteils unbestehend)
- **Getaway-Day / Reise-Feasibility:** unrealistische Back-to-Backs (Nachtspiel → Tagspiel über
  mehrere Zeitzonen) werden nicht geflaggt. 🔴
- **National-TV-Fenster** (ESPN/FOX/TBS Exklusivslots) als harte Anforderung — fehlt. 🔴
- **Venue-Verfügbarkeits-Kalender** (NFL-Shared-Stadien, Konzerte): aktuell nur *weiche*
  Event-Friction, kein harter Belegungskalender. 🟡
- **Marquee-/Feiertags-Pins** (Opening Day, 4. Juli, Jackie-Robinson-Day, Memorial/Labor Day):
  fehlen als Pins/Incentives. 🔴
**Empfehlung:** D1 (Getaway/Feasibility) + Feiertags-Pins zuerst (klar, datenarm); TV-Fenster +
Venue-Kalender brauchen echte MLB-Quelldaten (nicht erfinden — recherchieren/abklären).

### P1-4 🔴 Keine Erklärbarkeit / Audit (für „verteidigbare" Pläne)
**Was:** Officials müssen jeden Plan prüfen + verteidigen. Es fehlen: **Compliance-Report**
(jede harte Regel ↔ CBA-Artikel, mit Messwert), **maschinenlesbares Constraint-Provenance-
Register**, **menschenlesbare Plan-Begründung** (Reise-Highlights, wo Trade-offs gemacht
wurden). **Empfehlung:** `src/compliance.py` + `src/explain.py` (Charter D4/D5). **Aufwand:
mittel.**

### P1-5 🟡 Pareto-Optimizer schwächer als der Travel-Optimizer
**Was:** `optimize_pareto` nutzt nur Shift/Swap (kein Geo-Move) → vom reise-optimalen Start aus
schwach; die Phasen-Regler beißen erst bei starkem Gewicht + vielen Iterationen, und auch dann
ist die Fenster-Wirkung physikalisch gedeckelt (TV ~+5–8 %, Revenue ~0 %). **Stand Technik:**
TTP-Metaheuristiken nutzen große Nachbarschaften (Ejection Chains, GRASP, SwapTeams/Rounds).
**Empfehlung:** Geo-Move + ggf. TTP-Nachbarschaften in `optimize_pareto` portieren, damit der
multi-objektive Pfad so stark ist wie der Travel-Pfad. **Aufwand: mittel** (heikle inkrementelle
Energie-Buchhaltung).

---

## 3 — Priorität P2 (Verfeinerungen / Modell-Validierung)

### P2-1 🟡 Revenue-Modell nur auf Liga-Summe geeicht, nicht pro Spiel validiert
Multiplikatives Heuristik-Modell, −1,4 % zur Sportico-Liga-Summe — aber pro Team/Spiel nicht
gegen echte Gate-/Attendance-Daten geprüft. **Empfehlung:** sobald MLB Daten liefert,
pro-Team/Spiel validieren (JSON ist austauschbar — Architektur ist gut).

### P2-2 🟡 TV-Modell heuristisch
`expected_slot_value` + `team_pick_prob` sind Heuristiken; keine echten Broadcaster-
Pick-Regeln. **Empfehlung:** echte TV-Fenster-Daten (überschneidet mit P1-3).

### P2-3 🟡 CO₂ + Fairness nicht im Standard-Report/Dashboard (Charter C3)
Module existieren (`sustainability.py`, `fairness.py`), sind aber noch nicht in Backtest-Report
+ Dashboard verdrahtet. CO₂-Faktor ist Single-Aircraft-Näherung (737-800). **Empfehlung:** C3
verdrahten; optional flottenspezifischer Emissionsmix.

### P2-4 🟡 Travel-Modell: optionale Flughafen-Routing-Verfeinerung
Aktuell Großkreis Stadt↔Stadt (= Industrie-Standard, ~1 % genau). Echte Flugdistanzen
(Flughafen-Koordinaten + Routing/Wind) wären exakter, aber geringe Priorität. **Empfehlung:**
Team-Flughafen-Koordinaten statt Stadtzentren (kleiner, sauberer Gewinn).

### P2-5 🟡 Geo-Move ist Greedy (nächster Partner)
Funktioniert gut (Reise −23,6 %→−9 % bzw. Warm-Start schlägt real), aber kein
Ejection-Chain/2-opt-über-Trips. **Empfehlung:** stärkere Nachbarschaft, Richtung NBA-
Benchmark (3,8 % über Untergrenze).

### P2-6 🟢 Off-Day-Varianz wird in der Pareto-SA als ~konstant behandelt
Dokumentierte Näherung (Spielanzahl/Team konstant unter Moves). Geringe Auswirkung.

### P2-7 🟡 Test-Infrastruktur: langsame CP-SAT-Tests nur CI
Volle-Saison-Tests (>45 s) laufen nicht in der Sandbox. **Empfehlung:** ein schnelles
Reduced-Instance-Smoke-Set (z. B. 8–10 Teams) für lokale Läufe.

---

## 4 — Vorgeschlagene Reihenfolge

1. **P0-1** entscheiden: Warm-Start-only als MLB-Produktionspfad festschreiben (sofort
   CBA-konform) — und Branch-and-Price als separates Beschaffungs-Item dokumentieren.
2. **P1-3 (D1 + Feiertags-Pins)** + **P1-4 (Compliance + Explain)** — machen Pläne
   verteidigbar; datenarm, hoher Stakeholder-Wert.
3. **P1-2 (Doubleheader)** + **P1-5 (Pareto-Geo-Move)** — Reise/Verdichtung + stärkere Regler.
4. **P2-3 (C3 Reporting)**, **P2-4 (Flughafen-Koordinaten)**, **P2-1/2 (Modell-Validierung mit
   echten Daten)**.

---

## 5 — Quellen
- Anagnostopoulos, Michel, Van Hentenryck, Vergados (2006), *A simulated annealing approach to
  the TTP*; Easton/Nemhauser/Trick, *TTP Description and Benchmarks*; Trick, *Adventures in
  Sports Scheduling* (cs.cmu.edu/~ACO/dimacs/trick.html); INFORMS *Interfaces* Sports Scheduling.
- Publizierte MLB-2024-Reisemeilen (arizonasports.com; Nestico, *Measuring MLB Team Travel
  Distance*) — Validierung des Reisemodells.
- Surrogat-Methodik: Vergleiche Kriging vs. RBF vs. RSM (researchgate/Springer) → measured-grid.
- CO₂: ICAO CAEP / EUROCONTROL (3,16 kg CO₂/kg Jet-A); Wikipedia *Fuel economy in aircraft*.
- Eigene Belege: `docs/SPRINT_3_DIAGNOSIS_TRAVEL.md`, `docs/Q10_ANALYSE_UND_RECHERCHE.md`,
  `docs/SEASON_PHASES.md`, `docs/CBA_DEFINITIONS.md`.
