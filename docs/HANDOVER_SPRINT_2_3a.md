# Handover-Dokument: Sprint 2.3a (Column Generation für MLB-Scheduling)

**Datum:** 2026-05-23, Ende der Session
**Für die nächste Session:** vollständige Übergabe ohne Kontextverlust
**Aktueller Stand:** Column-Generation-Kern läuft (Mini-Test 4 Teams), aber konvergiert nicht
**Jonas's klare Vorgabe für nächste Session:** Generator darf länger dauern, **wichtig ist Stabilität + Qualität ohne Abbrüche**.

---

## TL;DR — was du sofort wissen musst

1. **Wir bauen Column Generation à la Trick/Nemhauser** für MLB-Scheduling, weil Standard-CP-SAT mit den Fatigue-Constraints (AC-2.1.8/9) UNKNOWN nach 30 s liefert.
2. **Phase A (`src/two_phase_pacing.py`) ist fertig und mathematisch verifiziert.** Pro Team in 0,1 s wird ein AC-2.1.8/9-konformer Pacing-Pattern generiert.
3. **RMP + Pricing-Subproblem (`src/column_generation.py`) sind implementiert**, das Mini-Beispiel (4 Teams, 30 Tage) läuft in 1,2 s, konvergiert aber NICHT — Slack bleibt bei ~3,7 Mismatch-Einheiten.
4. **Nächster konkreter Schritt:** Konvergenz-Tuning des Column-Generation-Loops + Skalierung auf volle 30-Team-Saison.

---

## Was ich ehrlich gelernt habe (Diagnose-Findings)

Vier Architektur-Varianten wurden empirisch getestet:

| Variante | Modell-Größe | Solver-Zeit | Ergebnis |
|---|---|---|---|
| Per-Day-Booleans (Series-Cover) | ~600k Reified-Constraints | UNKNOWN nach 30 s | Modell zu schwer |
| Off-Day-Slots als Pseudo-Series | 716 zusätzliche IntervalVars | UNKNOWN nach 30 s | NoOverlap-Explosion |
| Integriertes Pair-Matching (Home/Away pro Tag und Team) | 11k Bool-Vars | UNKNOWN nach 30 s | Suchraum zu groß |
| SA-Fatigue-Penalty | ~700k Iter | nur 8 % Verbesserung | Moves zu blockiert |

**Schlüssel-Erkenntnis:** Phase A pro Team **allein** löst in 0,1 s — das **Pair-Matching über alle Teams hinweg** ist das harte Problem. Die akademische Literatur (Trick/Nemhauser, Easton) sagt: **HAP-Decomposition + Column Generation** ist der Standard. Das machen sie kommerziell für die echte MLB.

---

## Aktueller Code-Stand

### Bereits geliefert ✅

**`src/two_phase_pacing.py`** — Phase A: Per-Team-Pacing
- `plan_team_pacing(team_id, n_games, n_home, total_days, break_days)` → liefert `TeamPacing`
- AC-2.1.8 (max 13 konsek. Auswärts) und AC-2.1.9 (max 20 in 21 Tagen) als Sliding-Window-Constraints
- Lösungszeit: 0,09 s pro Team, 2,8 s für alle 30 Teams
- `validate_team_pacing()` als Defensiv-Check
- **STATUS: PRODUKTIONSREIF**

**`src/two_phase_repair.py`** — Match-and-Repair (experimental, nicht ausreichend)
- Greedy-Repair mit Distance-Metrik
- Nur 8 % Verbesserung in der Praxis
- **STATUS: nicht produktiv nutzen**, kann entfernt werden

**`src/generator_constraints.py`** — Off-Day-Slot-Ansatz (gescheitert)
- War der erste Versuch mit IntervalVars
- **STATUS: archivieren oder löschen, ersetzt durch Column Generation**

**`src/column_generation.py`** — RMP + Pricing-Subproblem + CG-Loop ⚠️ in Arbeit
- `Pattern` dataclass mit H/A/O-Marken pro Tag
- `solve_rmp()` mit GLOP-LP-Solver + Slack-Variables (Big-M-Method)
- `pricing_subproblem()` als CP-SAT mit dualer Objective (AddElement-basiert)
- `run_column_generation()` Hauptloop
- **STATUS: Mini-Test (4 Teams, 30 Tage) läuft in 1,2 s, aber konvergiert nicht** (Slack bleibt hoch). Skalierung und Konvergenz-Tuning sind nächste Schritte.

**`src/event_conflicts.py`** — Loader für Local Events + Stadium-Bookings (Sprint 2.3b)
- `load_local_events()` lädt aus `data/local_events.json`
- `stadium_bookings_to_blackout_days()` → `home_blackout_days` für Generator
- `event_friction_score()` für Pareto-Achse
- **STATUS: fertig, wartet auf Generator-Anschluss**

### Datendateien
- `data/local_events.json` — 40+ datierte Events 2026 (siehe `docs/LOCAL_EVENTS_RESEARCH.md`)
- `data/tv_slots.json` — Slot-Werte + Marquee-Liste (siehe `docs/TV_SLOT_RESEARCH.md`)
- `data/revenue_model.json` — bereits aus Sprint 2.2

### Tests, die jetzt grün sind
- Alle Sprint-2.1-Tests
- Alle Sprint-2.2-Tests
- `tests/test_fatigue_constraints.py` (15 Unit-Tests, 2 xfail für Generator-Erzwingung)

### Charter / Reviews
- `docs/SPRINT_2_3_CHARTER.md` — originaler Plan (vor Reshape)
- `docs/SPRINT_2_3a_RESHAPE.md` — neuer Plan (Column Generation)

---

## Konkreter Plan für die nächste Session

### Schritt 1: Konvergenz-Diagnose (geschätzt 1–2 h)

Das Mini-Beispiel mit 4 Teams konvergiert nicht. **Erste Aktionen:**

1. Setze `pricing_solver_seconds=10` und `max_iterations=50`, lass laufen.
2. Logge pro Iteration: RMP-Objective, Anzahl Slacks > 0, dual-Werte (min/max).
3. Wenn Patterns immer dieselben Signaturen haben → Dedup-Problem.
4. Wenn reduzierte Kosten stagnieren → Subproblem-Objective falsch skaliert.

**Vermutung:** Die `SCALE = 1000`-Quantisierung der dualen Werte in `pricing_subproblem` verliert zu viel Genauigkeit. Erhöhe auf SCALE=10000 oder verwende Symmetrie-Argument (pro Team).

### Schritt 2: Mathematische Korrektheit verifizieren (1 h)

Verifiziere die reduzierte-Kosten-Formel an einem Hand-Beispiel mit 2 Teams:
```
c_bar(p) = c_p - π_t - Σ_d λ_d * (𝟙[H_d] - 𝟙[A_d])
```
wobei `π_t` aus der Team-Constraint und `λ_d` aus der Pair-Matching-Constraint kommen.

**Achtung-Punkt:** Im Code wird das mit `AddElement(day_vars[i], dual_day_int, var)` modelliert. Prüfen, ob das richtig die "pro Spieltag i, hole das duale für diesen Tag" abbildet.

### Schritt 3: Skalierung auf volle 30-Team-Saison (2–3 h)

1. `teams_meta` aus echten Matchup-Quoten ableiten (Heim/Auswärts-Counts).
2. `total_days = 186`, `break_days` korrekt setzen.
3. **Wichtig:** Jonas hat explizit gesagt, dass **längere Laufzeit OK ist**, solange das Ergebnis sauber wird. Setze daher `pricing_solver_seconds=30` und `max_iterations=200` ohne Sorge um Performance.
4. Monitor: nach jedem RMP-Solve den Slack-Wert ausgeben.

### Schritt 4: Branch-and-Price (falls fraktional, 2–4 h)

Wenn das LP-Optimum fraktional ist, brauchen wir Branching:
1. Wähle Variable x_{t,p} mit Wert nahe 0,5.
2. Branch: `x_{t,p} = 0` und `x_{t,p} = 1` als zwei Subprobleme.
3. Rekursiv lösen.

**Alternative pragmatisch:** Integer-RMP statt LP-RMP. Mit `pywraplp.Solver.CreateSolver("CBC")` als MIP-Solver. Langsamer, aber simpler.

### Schritt 5: Series-Matching (Phase B, 4–6 h)

Wenn das Pattern-Set steht, müssen wir Series konkret zuweisen:
1. Pro Team: cluster konsekutive H/A-Tage zu Series-Blöcken.
2. Globales Bipartite-Matching:
   - Heim-Serie A (Tag d, length 3) muss mit Auswärts-Serie B (Tag d, length 3, gleiche Längen) gepaart werden.
   - Pro (A, B)-Paar: Anzahl Spiele muss Matchup-Quote erfüllen.
3. Implementierung: zweites kleines MIP oder CP-SAT.

### Schritt 6: Validierung (1 h)

```python
from src.player_fatigue import all_teams_pass_fatigue_constraints
ok, viols = all_teams_pass_fatigue_constraints(season, team_ids)
assert ok, f"Verbleibende Verletzungen: {viols}"
```

Erwartet: 0 Verletzungen (das ist der ganze Zweck).

### Schritt 7: Tests + Sprint-2.3a-Review (2–3 h)

- `tests/test_column_generation.py` mit Mini-Saison (4 Teams, deterministisch reproduzierbar)
- `tests/test_phase_b_matching.py`
- `docs/SPRINT_2_3a_REVIEW.md` mit harten Zahlen
- xfail-Marker in `tests/test_fatigue_constraints.py` entfernen
- Sprint-2.3a Memory aktualisieren

---

## Wichtige Architektur-Entscheidungen (NICHT umkehren ohne Diskussion)

1. **Phase A bleibt erste Stufe.** Wurde ausführlich validiert, ist mathematisch sauber.
2. **GLOP als LP-Solver** (in `solve_rmp()`). Falls Integer-Constraints später nötig → CBC oder SCIP.
3. **Big-M = 1e6** in der Slack-Penalisierung. Falls Phase A einzelne Tage NICHT belegen kann → Slacks zeigen das.
4. **`num_search_workers=1` im CP-SAT** für Reproduzierbarkeit (AC-2.1.11).
5. **Pricing-Subproblem nutzt `AddElement(day_vars[i], dual_day_int, ...)`** für die per-day dualen Werte. Falls Konvergenz nicht klappt — DIESE Stelle zuerst prüfen.

---

## Was NACH Sprint 2.3a kommt (Sprint 2.3b — auf Eis)

Diese Phasen aus dem ursprünglichen Sprint-2.3-Charter warten:
- TV-Slot-Score (`src/tv_slots.py`)
- Local-Event-Friction (`src/event_conflicts.py` — Score-Funktion existiert)
- Multi-Objective-SA mit ε-Constraint
- Pareto-Sampling-Engine
- Profile-System (Named + Free)
- Dashboard-Panel mit 2D-Pareto-Plot

Alle diese Phasen können auf dem sauberen Sprint-2.3a-Generator-Output aufbauen.

---

## Wichtige Quellen (akademische Grundlage)

- [Trick: Adventures in Sports Scheduling](https://www.cs.cmu.edu/~ACO/dimacs/trick.html)
- [Easton, Nemhauser, Trick: Solving the Traveling Tournament Problem (2004)](https://link.springer.com/chapter/10.1007/978-3-540-45157-0_6)
- [Barnhart et al.: Branch-And-Price (1998)](https://pubsonline.informs.org/doi/10.1287/opre.46.3.316)
- [Rasmussen, Trick: Round Robin Scheduling Survey](http://www.dcc.ic.uff.br/~celso/artigos/sports-scheduling.pdf)
- [Springer: First-Break-Then-Schedule HAP Sets](https://link.springer.com/article/10.1007/s10951-022-00734-w)

Diese kurz lesen, bevor du den Konvergenz-Debug startest — das spart Sackgassen.

---

## Test-Befunde, die wichtig sind

### Phase A pro Team
```python
from src.two_phase_pacing import plan_team_pacing
from datetime import date
total_days = 186
break_days = {(date(2026,7,13)-date(2026,3,26)).days + i for i in range(4)}
p = plan_team_pacing("NYY", 162, 81, total_days, break_days)
# p.solver_seconds ≈ 0.09s
```

### Column Generation Mini-Test (Stand jetzt)
```python
teams_meta = {'A': (5, 5), 'B': (5, 5), 'C': (5, 5), 'D': (5, 5)}
pool, rmp, log = run_column_generation(teams_meta, 30, set(), max_iterations=10)
# log.iterations=10, log.converged=False (← Problem)
# log.patterns_per_team={'A': 11, 'B': 11, 'C': 11, 'D': 11}
# rmp.objective=3.7M (Slack-Penalty, sollte gegen 0 gehen)
```

### Sprint-2.1-Generator (Baseline, Vergleich)
```python
# OHNE fatigue_constraints (cfg.enforce_fatigue_constraints=False):
# CP-SAT 0.06s, dann SA 16s → Plan mit Verletzungen
# Worst-Case: KCR 109 Spieltage ohne Off-Day, TBR 23 konsek. Auswärts
```

---

## Jonas's letzte Vorgabe (wichtig)

> "Übrigens ist es okay wenn der Prozess den Schedule zu erstellen etwas länger
> dauert solang er stabil ohne Abbrüche und schlechte Ergebnisse funktioniert!"

→ Wir können `pricing_solver_seconds=30`, `max_iterations=100+`, und einen 5-Minuten-Wall-Clock-Run akzeptieren, **wenn das Ergebnis mathematisch sauber ist**. Performance ist nicht das Problem, **Korrektheit und Stabilität** sind.

---

## Kontakt-Punkte für Probleme

| Symptom | Vermutete Stelle | Erste Aktion |
|---|---|---|
| Pricing konvergiert nicht | `pricing_subproblem()` SCALE | SCALE auf 10000 erhöhen |
| RMP Slack bleibt hoch | Initial-Pattern-Pool zu klein | INITIAL_PATTERNS_PER_TEAM auf 5–10 erhöhen |
| Memory-Explosion | Pattern-Pool wächst unkontrolliert | Pattern-Dedup verbessern oder Pool-Cap |
| Series-Matching infeasible | Phase A unkoordiniert | Coordination-Constraint in Phase A einbauen |
| Test_smoke_minimal bricht | Edge-Case mit 1 Serie | Phase A mit n_games<2 abfangen |

---

## Befehle zum schnellen Re-Einstieg

```bash
# Phase A funktioniert (Smoke):
python -m pytest tests/test_generator.py::test_smoke_minimal_quotas -v

# Mini-Test Column Generation:
python -c "
from src.column_generation import run_column_generation
teams_meta = {'A': (5, 5), 'B': (5, 5), 'C': (5, 5), 'D': (5, 5)}
pool, rmp, log = run_column_generation(teams_meta, 30, set(), max_iterations=20, pricing_solver_seconds=5)
print(f'Slack: {rmp.objective/1e6:.2f}, converged: {log.converged}, patterns: {sum(log.patterns_per_team.values())}')
"

# Volle Suite (sollte alle grün sein):
python -m pytest --ignore=tests/test_generator.py -q
```

Viel Erfolg in der nächsten Session — das Fundament steht, jetzt geht's um Konvergenz-Engineering.
