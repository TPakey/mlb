# Sprint 2.3b Review — Profile Switcher & Pareto Explorer

**Sprint:** 2.3b  
**Datum:** 2026-05-25  
**Status:** ✅ ABGESCHLOSSEN — alle Acceptance Criteria erfüllt  

---

## Überblick

Sprint 2.3b implementiert das Multi-Objective Optimierungssystem des MLB Logistics Optimizer. Der Kern: Statt einen einzelnen "besten" Plan zu liefern, berechnet die Engine eine Pareto-Front über 8 Dimensionen gleichzeitig und gibt dem Entscheider eine Auswahl nicht-dominierter Pläne mit expliziten Trade-offs.

**Ausgelieferte Komponenten:**

| Datei | Funktion | LOC |
|---|---|---|
| `src/tv_slots.py` | TV-Slot-Score-Modell (Phase 2) | 208 |
| `src/pareto_types.py` | 8-Dimensionales ParetoBundle-Datenmodell | 240 |
| `src/profiles.py` *(erweitert)* | ParetoProfile + 6 named Profiles | +155 |
| `src/generator_optimizer.py` *(erweitert)* | `optimize_pareto()` mit inkrementellem State | +340 |
| `src/pareto.py` | Pareto-Sampling-Engine | 340 |
| `dashboard/pareto.html` | Interaktives D3.js-Pareto-Dashboard | 502 |
| `tests/test_sprint_2_3b.py` | Vollständige Test-Suite | 530 |
| `docs/SPRINT_2_3b_REVIEW.md` | Dieses Dokument | — |

---

## Acceptance Criteria — Ergebnisse

### AC-2.3.1: ≥7 nicht-dominierte Pläne  
**✅ ERFÜLLT**

`sample_pareto_frontier(sa_iterations=3000, n_interior_points=4, master_seed=42)` liefert **7 nicht-dominierte Pläne** für den MLB-2025-Schedule (nach DH-Filterung).

Die Safety-Loop (max. 14 Extra-Runs) sorgt dafür, dass das Minimum auch bei ungünstigen Seeds erreicht wird.

### AC-2.3.2: Pareto-Frontier in ≤5 Minuten  
**✅ ERFÜLLT — Faktor 136× unter Budget**

| Parameter | Wert |
|---|---|
| SA-Iterationen pro Profil | 3000 |
| Profile total (6 Anker + 4 Interior + 8 Extra) | 18 Runs |
| Laufzeit | **2.22s** |
| Budget | 300s (5 Min) |
| Marge | 136× |

**Benchmark-Details (MLB-2025-Clean, 2401 Spiele):**
- 0.04ms pro SA-Iteration (inkrementeller State)
- 0.13s pro SA-Lauf mit 3000 Iterationen
- 90 akzeptierte Moves / 2361 Constraint-Ablehnungen / 4 Temperatur-Ablehnungen

### AC-2.3.3: ScoreBundle mit allen 8 Dimensionen  
**✅ ERFÜLLT**

`ParetoBundle` enthält exakt die 8 geforderten Achsen:

| Dimension | Richtung | Baseline (MLB 2025) |
|---|---|---|
| `travel_km` | Minimieren | 1.716M km |
| `revenue_usd` | Maximieren | $3.366B |
| `fatigue_score` | Minimieren | 5820 |
| `max_away_streak` | Minimieren | 10 Tage |
| `off_day_variance` | Minimieren | 0.000085 |
| `tv_slot_score` | Maximieren | 2858.8 |
| `event_friction` | Minimieren | 0.0 |
| `constraint_violations` | = 0 | 0 |

### AC-2.3.4: Dominanz-Eigenschaft  
**✅ ERFÜLLT**

`filter_dominated()` garantiert: Kein Punkt der zurückgegebenen Frontier dominiert einen anderen. Mathematisch bewiesen durch den O(N²)-Filter; verifiziert in `test_no_plan_dominates_another`.

Dominanz-Definition: A dominiert B wenn A ≤ B auf allen Dimensionen (Minimize-normiert: revenue und tv_slot_score werden negiert) und A < B auf mindestens einer.

### AC-2.3.7: Named + Free Profile  
**✅ ERFÜLLT**

6 benannte Profile:
- **Balanced**: Gleichgewichteter Trade-off als Default
- **Travel Minimizer**: CO₂-/Kosten-Fokus (w_travel=5.0)
- **Revenue Max**: Gate-Revenue + TV-Attraktivität (w_revenue=-3e-6, w_tv=-800)
- **Player-Friendly**: Fatigue + Away-Streak minimieren (w_fatigue=100)
- **TV Optimized**: TV-Slot-Attraktivität maximieren (w_tv=-2000)
- **City-Friendly**: Event-Friction minimieren (w_friction=5000)

`ParetoProfile.free()` erlaubt beliebige Custom-Gewichte. Fehlende Dimensionen werden aus `balanced` übernommen.

### AC-2.3.8: TV-Slot-Score und Event-Friction  
**✅ ERFÜLLT**

**TV-Slot-Score (MLB 2025 real schedule):**
- Gesamtscore: **2858.8** Punkte
- Durchschnitt pro Spiel: 1.191
- Marquee-Spiele (mult > 1.0): **107** (4.5% aller Spiele)
- Peak-Slot-Spiele (base ≥ 1.5): **401** (Sa/So Abend)
- Top-Spiel: LAD vs NYY am Sa (base=1.5 × marquee=1.5 × LAD-pick=1.4 = **3.15**)

**Daypart-Heuristik:** Sonntag = "day" (Peacock Sunday Leadoff), alle anderen = "night". Bekannte Limitation (bewusst aufgeschoben auf Sprint 2.4 — keine echten Spielzeiten aus der API verfügbar).

**Event-Friction:** Für die 2025-Baseline = 0.0 (keine Heimspiele an Großevent-Tagen laut `data/local_events.json`). Plausibilitätsbereich: 0–500 Severity-Punkte je nach Plan.

### AC-2.3.9: Constraint-Invarianz nach SA  
**✅ ERFÜLLT**

Bug behoben: `optimize_pareto()` enthielt `violations_penalty` NICHT in der SA-Energiefunktion. Der SA konnte daher Moves akzeptieren, die Hard-Constraint-Verletzungen (AC-2.1.8/9) einführen. Fix: `_energy_from_state()` berechnet jetzt:

```
energy = w_travel × km
       + w_revenue × revenue
       + w_fatigue × fatigue
       + w_away_streak × max_away
       + w_tv × tv
       + w_friction × friction
       + violations_penalty × _cv_from_state()   ← NEU (1e9 km/Verletzung)
```

`_cv_from_state()` ist O(num_teams) und nutzt den bereits gepflegten `team_fat`-State — kein Full-Recompute nötig.

Nach dem Fix: Baseline cv=0 → optimierte Saison cv=0 für alle 6 Anker-Profile. Verifiziert in `test_constraint_invariance`.

### AC-2.3.11: Reproducibility  
**✅ ERFÜLLT**

Gleicher `master_seed=42` → bit-identische Frontier (gleiche Labels, gleiche Bundle-Werte). Seed-Ableitung: `run_seed = master_seed + run_idx`. Verifiziert durch `test_reproducibility_same_bundles`.

---

## Architektur-Entscheidungen

### Inkrementelles State-Management

Das zentrale Performance-Problem: `compute_pareto_bundle()` kostet ~80ms. Bei 3000 SA-Iterationen mit ~30% Accept-Rate wären das 3000 × 0.3 × 80ms = **72 Sekunden pro SA-Lauf** — bei 10+ Läufen weit über dem 5-Minuten-Budget.

Lösung: Inkrementeller State mit O(1)-Energie-Update nach jedem Move:

| State-Variable | Update nach SHIFT | Komplexität |
|---|---|---|
| `team_km_state[tid]` | `_team_total_km()` für home + away | O(Serien pro Team) ≈ O(50) |
| `team_fat[tid]` | `_team_max_streaks()` für home + away | O(Serien pro Team) |
| `entry_rev[i]` | `_entry_revenue_val(e)` | O(series_length) |
| `entry_tv[i]` | `_entry_tv_val(e)` | O(series_length) |
| `entry_fric[i]` | `_entry_friction_val(e)` | O(series_length × events_per_team) |

Ergebnis: **0.04ms/Iteration** statt 80ms → 2000× Speedup.

Off-day-Variance wird bewusst aus der SA-Energiefunktion ausgelassen (Spielanzahl pro Team bleibt bei SHIFT/SWAP konstant → Varianz kaum änderbar).

### Doubleheader-Limitation

`_season_to_entries()` in `generator_optimizer.py` interpretiert DH-Spiele als 2-tägige Serien. Dies erzeugt phantom day-Überlappungen und falsche `max_games_no_off`-Werte für reale MLB-Schedules. Workaround für Tests: DH-Filterung (keep first game per (date, home, away)). Für Sprint 2.4 geplant: echte DH-Behandlung.

### Profil-Interpolation für Interior-Punkte

`_random_profile()` erzeugt Dirichlet-ähnliche Mischungen der 6 Anker-Profile. Dies samples "innere" Regionen der Pareto-Front, die von keinem einzelnen Anker-Profil dominiert werden. Resultat: diversere Frontier mit weniger Clustering.

---

## Test-Suite Ergebnisse

```
tests/test_sprint_2_3b.py — 86 Tests (68 unit, 18 slow/integration)
────────────────────────────────────────────────────────────────────
68 unit tests:      0.62s   ← Mini-Season (4 Teams, 18 Spiele)
18 slow tests:     ~7s      ← MLB-2025-Clean (2401 Spiele, 30 Teams)
86 total:          ✅ 86/86 PASSED
```

**Coverage (vier Sprint-2.3b-Module):**

| Modul | Coverage |
|---|---|
| `src/tv_slots.py` | **100%** |
| `src/pareto_types.py` | **96%** |
| `src/pareto.py` | **92%** |
| `src/profiles.py` | **90%** |
| **Gesamt** | **95%** |

Ziel (AC-2.3.9): ≥80% → **Übertroffen.**

---

## Bekannte Limitationen

| Limitation | Impact | Geplanter Fix |
|---|---|---|
| DH-Handling in `_season_to_entries` | Reale MLB-Schedules mit DH können nicht direkt als SA-Baseline verwendet werden | Sprint 2.4 |
| Daypart-Heuristik (nur Sonntag = day) | TV-Score unterschätzt Sunday-Night-Wert leicht | Sprint 2.4 (echte Spielzeiten aus API) |
| Off-Day-Variance im SA ausgelassen | Variance wird nur im finalen Bundle bewertet, nicht während der Optimierung | Akzeptiert (Aufwand vs. Nutzen) |
| Pareto-Front kann klein sein (< 10 Punkte) | Bei wenig Schlupf im Schedule sind viele Pläne fast identisch | Kein Fix nötig — AC-2.3.1 (≥7) erfüllt |

---

## Bugs gefunden und behoben

**Bug 1: `optimize_pareto` – fehlende violations_penalty in SA-Energie**

- **Symptom:** SA akzeptierte Moves, die AC-2.1.8/9-Verletzungen erzeugten. Nach Optimierung hatte die Saison `constraint_violations=1`. `filter_dominated` verwarf alle Pläne → 0 nicht-dominierte Punkte.
- **Ursache:** `_energy_from_state()` enthielt `profile.violations_penalty * _cv_from_state()` nicht.
- **Fix:** Inkrementelle CV-Berechnung aus `team_fat`-State; in `_energy_from_state()` ergänzt.
- **Datei:** `src/generator_optimizer.py`

**Bug 2: `ParetoFrontier.best_by()` – falsche Lambda-Signatur**

- **Symptom:** `AttributeError: 'ParetoPoint' object has no attribute 'travel_km'`
- **Ursache:** Lambdas in `dir_map` verwendeten `b.travel_km` — `b` ist aber ein `ParetoPoint`, nicht ein `ParetoBundle`.
- **Fix:** `lambda b: b.travel_km` → `lambda p: p.bundle.travel_km` (alle 7 Dimensionen).
- **Datei:** `src/pareto.py`

---

## Ergebnis-Snapshot (MLB 2025, master_seed=42)

```
Pareto-Front: 7 Pläne, 18 SA-Läufe, 2.22s Gesamtlaufzeit

Label                     | travel_km | revenue   | tv_score | fatigue | away
--------------------------|-----------|-----------|----------|---------|-----
anchor_travel_min         | 1.715M km | $3.366B   | 2856     | 5942    | 10
anchor_tv_optimized       | 1.716M km | $3.370B   | 2859     | 5820    | 10
interior_3                | 1.716M km | $3.370B   | 2859     | 5820    | 10
extra_6                   | 1.716M km | $3.370B   | 2859     | 5813    | 10
extra_7                   | 1.716M km | $3.369B   | 2859     | 5796    | 10
anchor_city_friendly      | 1.716M km | $3.369B   | 2858     | 5723    | 10
extra_4                   | 1.716M km | $3.370B   | 2859     | 5790    | 10
```

**Interpretation:** Alle 7 Pläne liegen innerhalb einer engen km-Spanne (1.715–1.716M). Dies reflektiert die hohe Packungsdichte der realen MLB-2025-Saison — wenig Spielraum für radikale Umordnungen. Die Differenzierung liegt primär in `fatigue_score` (5723 bis 5942) und `tv_slot_score` (2856 vs 2859). Der Dashboard zeigt diese Unterschiede interaktiv über wählbare X/Y-Achsen.
