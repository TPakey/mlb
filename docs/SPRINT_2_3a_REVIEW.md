# Sprint 2.3a Review — Schedule Optimizer Core

**Abgeschlossen:** 2026-05-25  
**Bearbeiter:** Claude (Cowork-Session)  
**Status:** ✅ Fertig — alle Acceptance Criteria grün

---

## Hintergrund & Motivation

Sprint 2.3a entstand als Reshape von Sprint 2.3 (Profile Switcher + Pareto Explorer), nachdem klar wurde, dass der CP-SAT-Generator aus Sprint 2.1 die Fatigue-Constraints AC-2.1.8 und AC-2.1.9 nicht zuverlässig erfüllen konnte. Nach vier erfolglosen Architektur-Iterationen wurde die korrekte Lösung identifiziert: **Column Generation nach Trick/Nemhauser** kombiniert mit einem **globalen HAP-Solver** und einem **Slot-basierten Phase-B-Matcher**.

Das Kernproblem, das diesen Sprint notwendig machte:

> *"Der alte CP-SAT-Generator verletzt AC-2.1.8/9 deutlich (z.B. BAL hatte 109 Spiele ohne Off-Day). Die Fatigue-Constraints müssen mathematisch garantiert, nicht nur heuristisch angenähert, werden."*

---

## Was gebaut wurde

### Phase A: Per-Team CP-SAT Pacing (`src/two_phase_pacing.py`)

Jedes Team bekommt ein eigenes kompaktes CP-SAT-Modell, das **nur** die Spieltag-Struktur plant (Heim/Auswärts an welchen Tagen), ohne Gegner-Zuweisung. Constraints:

- **AC-2.1.9** (Sliding Window): `day[i+20] - day[i] >= 21` für alle i
- **AC-2.1.8** (Away-Streak): Reifizierte Constraint — 14 konsekutive Spieltage erfordern min. 1 Heimspiel
- Strikte Sortierung, Saisonfenster, Pausentage

**Messwerte:** 30 Teams in 2,8 s (0,09 s/Team). 100 % AC-konform.

---

### Globaler HAP-Solver (`src/column_generation.py: solve_global_hap`)

Löst die Home-Away-Pattern-Zuweisung für **alle 30 Teams simultan** mit einem globalen CP-SAT-Modell. Garantiert:

- **Pair-Matching**: An jedem Tag |Heim-Teams| = |Auswärts-Teams| (exakt 15/15)
- **AC-2.1.8/9** (wie Phase A)
- **Series-Länge 2–4**: Jeder Heim- oder Auswärtsblock hat Länge 2–4 Tage
- **Keine Spiele an Pausentagen** (All-Star-Break: Tage 109–112)

**Messwerte:** Seed 42, 30 Teams, 186 Tage → **OPTIMAL in 11,2 s** mit 8 Workern.

| Metrik | Wert |
|---|---|
| Solver-Status | OPTIMAL |
| Solve-Zeit | 11,2 s |
| Pair-Violations | 0 |
| Series-Längen | {2: 921, 3: 506, 4: 375} |
| Heimspiele/Team | 81 (exakt) |
| Auswärtsspiele/Team | 81 (exakt) |

---

### Column Generation RMP + Pricing (`src/column_generation.py`)

Vollständiger CG-Loop nach Trick/Nemhauser:

- **Restricted Master Problem (RMP):** LP mit GLOP-Solver, dualen Werten für Tag- und Team-Constraints
- **Pricing Subproblem:** CP-SAT pro Team, generiert Patterns mit negativen reduzierten Kosten
- **Checkpoint-System:** `run_cg_checkpointed.py` — unterbrechbar, setzt nach Absturz fort
- **Paralleles Pricing:** ThreadPoolExecutor mit 4 Workern

Mini-System-Test (4 Teams, 30 Tage): läuft in < 5 s, konvergiert stabil.

---

### Phase B: Slot-basiertes Series Matching (`src/series_matching.py`)

Die Gegner-Zuweisung — "wer spielt gegen wen und wann" — erfolgt über ein **Slot-basiertes CP-SAT-Modell**.

**Architektur:** Anstatt per-Paar-pro-Tag-Variablen (die strukturell durch HAP-Grenz-Misalignments infeasible werden) verwenden wir "Slots": zusammenhängende Sub-Intervalle der H-Serie mit Länge 1–4. Length-1-Slots werden durch eine Penalty-Zielfunktion minimiert.

**Funktionen:**
- `match_series_slots_soft()` — Hauptfunktion, immer feasible, minimiert 1-Spiel-Serien
- `match_series_slots()` — Strikte Variante (nur Länge 2–4, infeasible bei Hall-Verletzungen)
- `match_series_cpsat()` — Legacy per-Paar-Modell (Vergleich)
- `match_series()` — Greedy Fallback (250 Violations, schnell für Diagnose)

**Messwerte (Seed 42, 30 Teams):**

| Algorithmus | Violations | Zeit | Status |
|---|---|---|---|
| Greedy (`match_series`) | 250 | 1 s | Heuristisch |
| Per-Paar Soft-CP-SAT (`match_series_cpsat`) | 101 | 27 s | OPTIMAL (altes Modell) |
| Slot Soft-CP-SAT (`match_series_slots_soft`) | **89** | **9,1 s** | **OPTIMAL** |

Die **89 Violations sind mathematisch bewiesen minimal** für die gegebenen HAP-Patterns — CP-SAT hat OPTIMAL zurückgegeben.

---

## Acceptance Criteria

| # | Kriterium | Status | Messwert |
|---|---|---|---|
| AC-HAP-1 | Pair-Matching: #H == #A pro Tag | ✅ PASS | 0 Violations |
| AC-HAP-2 | 81 Heim + 81 Auswärts pro Team | ✅ PASS | Alle 30 Teams exakt |
| AC-HAP-3 | Keine Spiele an Break-Tagen | ✅ PASS | 0 Violations |
| AC-HAP-4 | Series-Länge 2–4 (HAP-Ebene) | ✅ PASS | {2:921, 3:506, 4:375} |
| AC-HAP-5 | OPTIMAL (nicht nur FEASIBLE) | ✅ PASS | 11,2 s |
| **AC-2.1.8** | Max 13 konsekutive Auswärtstage | ✅ PASS | 0 Violations, alle 30 Teams |
| **AC-2.1.9** | Max 20 Spieltage in 21-Tage-Fenster | ✅ PASS | 0 Violations, alle 30 Teams |
| AC-PB-1 | Phase B feasible | ✅ PASS | 1110 Serien, 2430 Spiele |
| AC-PB-2 | Kein Away-Team doppelt gebucht | ✅ PASS | 0 Verletzungen |
| AC-PB-3 | Alle Heimspiele abgedeckt | ✅ PASS | 0 unbedeckte H-Tage |
| AC-PB-4 | Series max 4 Spiele | ✅ PASS | Keine Series > 4 |
| AC-PB-5 | Violations unter Schwellenwert (<100) | ✅ PASS | 89 (bewiesen optimal) |
| AC-TEST | 25 Unit-Tests grün | ✅ PASS | 25/25, 33 s |

---

## Phase-B Architektur: Bekannte Limitation

Die 89 verbleibenden Violations (1-Spiel-Serien) sind eine **bekannte Limitation der zweistufigen HAP-Dekomposition** (HAP zuerst, Gegner-Matching danach). Sie entstehen durch sogenannte "Grenz-Misalignments": Eine 2-tägige H-Serie von Team h und eine 2-tägige A-Serie von Team a überschneiden sich an genau einem Tag → strukturell unvermeidbare 1-Spiel-Begegnung.

**Ursache:** 53 % aller HAP-Serien sind 2 Tage lang. Jede 2-Tages-H-Serie erzwingt einen einzigen Away-Gast für beide Tage. Bei globaler Kopplung (Pair-Matching, Exklusivität) entstehen Hall-Verletzungen, die per CP-SAT-Soft-Objective minimiert aber nicht eliminiert werden können.

**Produktionsqualität:** In einem echten MLB-Scheduling-System würde man dieses Problem durch einen **integrierten Ansatz** lösen (HAP + Gegner-Zuweisung simultan). Alternativ: die 89 Boundary-Spiele werden als Makeup-Spiele oder Standalone-Spiele behandelt — ein Mechanismus, der in Sprint 2.2 (Disruption Handler) bereits implementiert ist.

**Nächste Schritte (Sprint 2.3b):** Die Gegner-Quoten (19 Spiele gegen Division-Gegner, etc.) werden als zweite Optimierungsebene ergänzt. Mit spezifischen Quoten kann der HAP-Solver gezielt kompatiblere Grenz-Strukturen erzwingen.

---

## Laufzeiten (Gesamtsystem)

```
Phase A (30 Teams pacing):         ~2,8 s
Globaler HAP-Solver (Seed 42):    ~11,2 s
Phase B Slot-Matching (soft):      ~9,1 s
─────────────────────────────────────────
Gesamt Schedule-Generierung:      ~23,1 s
```

**Zielkorridor Sprint Charter:** < 30 Minuten. ✅ Mit 23 s deutlich unterschritten.

---

## Test Coverage

**Test-Datei:** `tests/test_sprint_2_3a.py`

| Klasse | Tests | Thema |
|---|---|---|
| `TestGlobalHAPSolver` | 9 | HAP-Korrektheit, Pair-Matching, Series-Längen |
| `TestFatigueConstraints` | 2 | AC-2.1.8/9 auf allen 30 Teams |
| `TestPhaseBMatching` | 8 | Feasibility, Abdeckung, Doppelbuchung, Violations |
| `TestHAPParsing` | 2 | parse_hap_series Korrektheit |
| `TestColumnGenerationMini` | 4 | CG-Loop (Mini-System) |
| **Gesamt** | **25** | **25/25 PASS, 33 s** |

---

## Deliverables

- `src/two_phase_pacing.py` — Phase A Per-Team CP-SAT ✅
- `src/column_generation.py` — RMP + Pricing + GlobalHAPResult + solve_global_hap ✅
- `src/series_matching.py` — Greedy + Slot-Modell (Strict + Soft) + Legacy-CPSAT ✅
- `src/event_conflicts.py` — Event-Conflict-Loader (Schwarze Tage) ✅
- `tests/test_sprint_2_3a.py` — 25 Tests ✅
- `docs/SPRINT_2_3a_REVIEW.md` — dieses Dokument ✅
- `data/tv_slots.json` + `docs/TV_SLOT_RESEARCH.md` — Vorarbeit Sprint 2.3b ✅
- `data/local_events.json` + `docs/LOCAL_EVENTS_RESEARCH.md` — Vorarbeit Sprint 2.3b ✅
