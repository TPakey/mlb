# Sprint 2.3 Charter — Profile Switcher + Pareto Explorer

**Periode:** 2026-05-23 bis ca. 2026-06-05 (1,5–2 Wochen)
**Wertversprechen:** Tradeoff-Klarheit — *"Was kostet uns Player Health an Revenue?"*

---

## Re-Framing

Sprint 2.2 hat uns das **Score-Bundle** und **drei diskrete Alternativen pro
Disruption** gebracht. Sprint 2.3 macht den nächsten konzeptionellen Schritt:
Statt drei festen Antworten liefert die Engine **N Pläne entlang der
Pareto-Front** über mehreren Score-Dimensionen. Ein MLB-Ops-Manager fragt
nicht mehr "welche der drei nehme ich?", sondern "wo auf der Frontier von
Travel ↔ Revenue ↔ Player-Health ↔ TV-Slots will ich landen?"

Sprint 2.2 ist Disruption Resilience — Sprint 2.3 ist **strategische
Auswahlhilfe für die ganze Saison**.

---

## Architektur — die sieben Phasen

### Phase 1 — Generator-Sliding-Window (Task #15)

**Was:** CP-SAT-Modell um Per-Team-Per-Day-Booleans erweitern, daraus
Sliding-Window-Constraints ableiten:
- AC-2.1.9: max 20 Spieltage in jedem 21-Tage-Fenster pro Team
- AC-2.1.8: max 13 konsekutive Auswärtstage pro Team

**Warum zuerst:** Sprint 2.1/2.2 verletzen diese ACs systematisch (BAL
hat 109 Spieltage ohne Off-Day). Wenn der Fatigue-Score auf der Pareto-
Achse landen soll, muss er auf ehrlichen Daten basieren.

**Deliverables:**
- Erweitertes `src/generator.py` mit Sliding-Window-Constraints
- `xfail`-Marker in `tests/test_fatigue_constraints.py` entfernt (Tests grün)
- Performance-Regression-Test: Solver-Zeit darf max 60 s sein

### Phase 2 — Erweiterte Score-Dimensionen

**Was:** Zwei neue Score-Module, sodass wir die volle "8-Kategorien-Bewertung"
laut Sprint-2-Charter haben.

**TV-Slot-Score (`src/tv_slots.py` + `data/tv_slots.json`):**
- Definition von Premium-Slots: Sa Abend (FOX Saturday), So Abend (ESPN Sunday Night),
  Fr Abend (Apple TV+ Friday Night), MLB Network various
- Bewertung pro Spiel: Slot-Attraktivität × Matchup-Attraktivität
- Marquee-Bonus für klassische Rivalitäten (NYY-BOS, LAD-SFG, CHC-STL, etc.)

**Local-Event-Friction (`src/event_conflicts.py` + `data/local_events.json`):**
- Kuratierte Event-Liste 2026 pro MLB-Stadt: Stadtfeste, Marathons,
  College-Football-Heimspiele, Großkonzerte
- Score pro Plan: Anzahl Heimspiele in Konflikt-Tagen × Severity-Faktor
- Datenquellen-Recherche: gründlich, ~50–80 datierte Events insgesamt

**Die 8 Pareto-Achsen:**
1. Travel-km
2. Revenue (USD)
3. Player-Fatigue (kumulierter Fatigue-Score)
4. Max-Away-Streak (Worst-Case pro Liga)
5. Off-Day-Balance (Stability)
6. TV-Slot-Score
7. Local-Event-Friction
8. Constraint-Violations (muss 0 sein, gefiltert)

### Phase 3 — Multi-Objective-SA mit ε-Constraint

**Was:** Erweiterung des bestehenden `generator_optimizer.py` SA-Layers
um:
- Score-Bundle-Bewertung (gewichtete Linearkombination + ε-Schranken)
- ε-Constraint-Modus: minimiere Dimension X, halte alle anderen unter
  vorgegebenen ε-Werten

**Methode:** ε-Constraint als Hauptmethode (findet auch nicht-konvexe
Pareto-Bereiche), Weighted-Sum als schneller Anker-Finder für Extrema.

**Reproduzierbarkeit:** Pro Pareto-Punkt eigener Seed (derived from
Master-Seed + Index). Damit ist die Frontier deterministisch.

### Phase 4 — Pareto-Sampling-Engine

**Was:** Orchestrator-Wrapper, der:
1. Erst **Anker-Pläne** rechnet: Single-Objective-Optima pro Dimension
   (min-Travel, max-Revenue, min-Fatigue, …) — das sind die Pareto-Extrema
2. Dann **dazwischen ε-Constraint-Punkte** streut: Gewichts-/ε-Vektoren
   systematisch durchgehen
3. **Dominanz-Filter** über alle gesammelten Pläne anwenden
4. Liefert N ≥ 7 nicht-dominierte Pläne

**Deliverable:** `src/pareto.py` + `tests/test_pareto.py`

### Phase 5 — Profile-System (Named + Free)

**Two Modes:**

**Named-Mode** mit 6 vorgefertigten Profilen:
- `travel_min` — minimiert km, alle anderen sekundär
- `revenue_max` — maximiert Revenue, alle anderen sekundär
- `player_friendly` — minimiert Fatigue + max-Away-Streak
- `stability_first` — minimiert Plan-Änderungen vs. Vorlage
- `tv_optimized` — maximiert TV-Slot-Score
- `balanced` — neutrale Gewichtung über alle Dimensionen

**Free-Mode:** beliebiger Gewichtsvektor via CLI/API oder JSON-Eingabe.

Beide Modi nutzen dieselbe SA-Pipeline, nur mit unterschiedlich
parametrisiertem Score-Bundle.

**Deliverable:** `src/profiles.py` + `data/profile_definitions.json`

### Phase 6 — Dashboard-Visualisierung

**Was:** Neues Panel `pareto.html` integriert ins bestehende Dashboard.
- Interaktiver 2D-Pareto-Plot (Recharts oder D3) mit Achsen-Selektor
- Pareto-Front als Linie, Anker-Profile als gelabelte Punkte,
  Streupunkte als feinere Marker
- Hover-Tooltip pro Plan: alle 8 Scores, Plan-Snapshot-Button
- "Switch to this profile"-Knopf öffnet Plan-Detail-View

**Deliverable:** `dashboard/pareto.html` + Bauskript-Erweiterung

### Phase 7 — Tests + Review

**Test-Pyramide:**
- Unit-Tests pro Score-Funktion und ε-Constraint-Logik
- Property-Tests: jeder Pareto-Punkt ist nicht-dominiert
- Integration-Tests: voller Pareto-Lauf reproduzierbar
- Snapshot-Test: Visualisierung erzeugt erwartete SVG

**Coverage-Ziel:** ≥ 80 % aller neuen Module.

---

## Acceptance Criteria — alle müssen grün sein

| # | Kriterium | Test |
|---|---|---|
| AC-2.3.1 | ≥ **7 nicht-dominierte Pläne** in einem Lauf | Pareto-Property-Test |
| AC-2.3.2 | Pareto-Frontier-Berechnung in **≤ 5 Minuten** | Timer-Test |
| AC-2.3.3 | **Score-Bundle vollständig** (alle 8 Kategorien) | Schema-Test |
| AC-2.3.4 | **Pareto-Dominanz-Validierung** mathematisch: kein Punkt dominiert anderen | Math-Property-Test |
| AC-2.3.5 | **2D-Plot** mit Achsen-Selektor im Dashboard | Snapshot/E2E-Test |
| AC-2.3.6 | **Anker-Profile** erkannt und gelabelt (min/max pro Dimension + balanced) | Unit-Test |
| AC-2.3.7 | **Named + Free Profile-Modus** beide getestet | Integration-Test |
| AC-2.3.8 | **TV-Slot-Score** und **Local-Event-Friction** gegen reale 2024-Saison berechenbar; Plausibilitäts-Range definiert | Model-Sanity-Test |
| AC-2.3.9 | **≥ 80 % Coverage** der neuen Module (pareto, tv_slots, event_conflicts, profiles) | pytest-cov |
| AC-2.3.10 | **AC-2.1.8 + AC-2.1.9 jetzt erzwungen** (Task #15): voller MLB-Plan hält Limits ein | bisher xfail → grün |
| AC-2.3.11 | **Reproduzierbarkeit**: gleicher Master-Seed → bit-identische Frontier | Idempotenz-Test |
| AC-2.3.12 | **Performance-Regression**: Sprint-2.1-Generator nach Task #15 weiterhin ≤ 60 s | Timer-Test |

---

## Geschätzter Aufwand

| Block | Aufwand |
|---|---|
| Phase 1 — Task #15 (CP-SAT-Sliding-Window) | 0,5–1 Tag |
| Phase 2 — TV-Slots + Local-Events (inkl. Recherche) | 1,5 Tage |
| Phase 3 — Multi-Objective-SA + ε-Constraint | 1–1,5 Tage |
| Phase 4 — Pareto-Sampling-Engine + Anker | 0,5 Tag |
| Phase 5 — Profile-System (Named + Free) | 0,5 Tag |
| Phase 6 — Dashboard-Panel | 1 Tag |
| Phase 7 — Tests + Review | 0,5 Tag |
| **Total** | **~6 Tage** |

Im Charter-Rahmen (1,5 Wochen). Die ambitionierte Variante (8 Dimensionen
+ gründliche Events-Recherche) ist hier eingerechnet.

---

## Reihenfolge der Umsetzung

1. **SPRINT_2_3_CHARTER.md** (dieses Dokument) ✅
2. **Recherche-Phase:** TV-Slot-Definitionen + Local-Events 2026
3. **Task #15:** CP-SAT-Sliding-Window-Constraints
4. **TV-Slot-Score-Modul:** `src/tv_slots.py` + Daten
5. **Local-Event-Friction-Modul:** `src/event_conflicts.py` + Daten
6. **Score-Bundle-Erweiterung:** alle 8 Kategorien im `ScoreBundle`
7. **Multi-Objective-SA:** `generator_optimizer.py` erweitern um ε-Constraint
8. **Pareto-Sampling:** `src/pareto.py`
9. **Profile-System:** `src/profiles.py` + JSON
10. **Dashboard:** `dashboard/pareto.html`
11. **Tests + Review-Dokument**

---

## Sprint-Review-Kriterium

Sprint 2.3 gilt als **erfolgreich abgeschlossen**, wenn:

1. Alle 12 ACs grün, automatisierte Tests beweisen das
2. **Pareto-Frontier liefert ≥ 7 echt nicht-dominierte Pläne** in ≤ 5 Minuten
3. **Coverage ≥ 80 %** auf allen vier neuen Modulen
4. **Dashboard zeigt die Frontier** interaktiv mit Achsen-Selektor und
   Profil-Switcher
5. **Demo-Skript** `demo_pareto.py` zeigt den vollen Pareto-Lauf
   end-to-end mit ausgewählten Beispiel-Profilen
6. **Sprint-2.3-Review-Dokument** mit harten Zahlen pro Phase

---

## Bewusst aufgeschoben (Sprint 2.4)

- **Echte Spielzeiten** aus MLB-Stats-API für präzises Day/Night-Modell
  (zur Zeit Sonntag = Day, Rest = Night als Heuristik)
- **What-if-Engine** und Audit-Trail (Sprint-2.4-Stoff)
- **Wettermodell** mit echten historischen Daten (bisher nur im Monats-Faktor)
- **Venue-Aliasing** (Ersatz-Stadion) für Milton-Klasse-Disruptionen
  — alternative für Sprint 2.4+
- **NSGA-II oder andere genetische MO-Solver** — wenn ε-Constraint
  Limitierungen zeigt
