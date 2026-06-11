# HANDOVER — Sprint 3 (Stand 2026-06-02)

**Für: die nächste Session (mich selbst).** Dieses Dokument macht dich in einem neuen Chat
sofort arbeitsfähig, ohne den langen Verlauf erneut zu lesen. Lies zuerst dieses Dokument,
dann bei Bedarf die verlinkten Detail-Docs.

---

## 0 — Orientierung in 30 Sekunden

- **Produkt:** MLB-Saison-Optimierer, 30 Teams, 2.430 Spiele. Pipeline: CP-SAT (Feasibility)
  → Simulated Annealing (Reise + Fatigue). Bewertung über 8 Dimensionen (`ParetoBundle`).
- **Zielnutzer:** MLB League Officials / Season Schedulers. Maßstab: **die echte MLB muss es
  direkt nutzen können** (siehe Memory `feedback_development_approach`).
- **Arbeitsstil (verbindlich):** erst durchdenken → OSS/Literatur recherchieren → integrieren
  oder fundiert selbst bauen → **messen statt behaupten**. Qualität vor Geschwindigkeit
  (lange Laufzeit OK).
- **Sprache:** mit Jonas immer **Deutsch**.

**Wichtigste Detail-Docs:**
`docs/PROJECT_REVIEW_2026-06.md` (priorisierte Schwachstellen) ·
`docs/SPRINT_3_DIAGNOSIS_TRAVEL.md` (Reise-Diagnose + Fix) ·
`docs/SEASON_PHASES.md` (Phasen/Tuner/Kalibrierung) ·
`docs/SPRINT_3_PLAN.md` (Sprint-Charta) · `docs/Q10_ANALYSE_UND_RECHERCHE.md` (AC-2.1.8/TTP) ·
`docs/CBA_DEFINITIONS.md` (verbindliche AC-Definitionen).

---

## 1 — Der zentrale Befund dieser Session

**Ausgangslage (schockierend):** Der Backtest zeigte, dass unser *From-Scratch*-Plan auf JEDER
Dimension schlechter war als der echte MLB-Plan (Reise +23,6 %, 5 CBA-Verletzungen ...).

**Ursache (datenbasiert diagnostiziert):** Der SA verschob nur **Termine**, baute aber nie die
**Road-Trip-Komposition** um → gleich viele Flüge wie real, aber **~18 % längere Flüge** (keine
geografische Clusterung der Auswärtsgegner). Wurzel: reise-blinde CP-SAT-Stufe + zu schwacher
SA-Move-Satz.

**Zwei Fixes, beide umgesetzt + gemessen:**
1. **Geo-Move** im Travel-SA (`optimize_travel`): löst eine Auswärtsserie heraus und setzt sie
   neben den geografisch nächsten Auswärtsgegner desselben Teams → Reise +23,6 % → **+9 %**.
2. **Warm-Start** (Jonas' Idee): vom **realen Plan** starten statt from-scratch. Schlägt den
   realen Plan: **2024 −5,4 % Reise / 0 CBA-Verletzungen**, **2025 −2,6 % / repariert sogar die
   1 reale Verletzung** (worst_away 14→13). Umgeht auch die CP-SAT-Intraktabilität von 2025.

**Konsequenz / Produktempfehlung:** **Warm-Start ist der Produktionspfad.** From-Scratch nur
zur Algorithmus-Validierung. (Noch NICHT formal als „einziger" Pfad festgeschrieben → P0, s. u.)

**Reisemodell ist validiert:** Haversine „lineare Meilen" treffen publizierte MLB-2024-Meilen
auf ~1 % (SEA 76.142 km ≈ 47.300 mi vs. publ. 47.441 mi). Kein Schwachpunkt.

---

## 2 — Was diese Session konkret gebaut hat (Dateien + Verhalten)

### Track B — Backtest (`tools/backtest.py`)
- `load_real_baseline(year)`, `generate_our_plan(...)` (Kalt-Start), **`improve_real_plan(...)`
  (Warm-Start)**. Report MD+HTML+JSON nach `output/backtest/`.
- CLI: `python -m tools.backtest --season 2024 [--warm-start] [--baseline-only]`.
- Warm-Start nutzt `travel_optimizer_iterations=6_000_000`.

### Track C — CO₂ + Fairness
- `src/sustainability.py`: `CO2_KG_PER_KM = 3.16 (ICAO) × 3.98 (737-800) = 12.58`;
  `compute_co2_report(travel)`. Beleg: `docs/SUSTAINABILITY_RESEARCH.md`.
- `src/fairness.py`: `gini(values)`, `disparity_ratio()`, `compute_fairness_report(travel)`.
- **Offen (P2):** noch nicht in Standard-Report/Dashboard verdrahtet (Charter C3).

### Travel-Fix (`src/generator_optimizer.py`, `src/generator.py`)
- **Geo-Move** in `optimize_travel`: `OptimizerConfig.move_mix_geo = 0.35`; vorberechnete
  `nearest_partners` (Top-2); Akzeptanz rein über SA-Energie (km + λ·Fatigue, λ=1e6) — kein
  extra Guard (Energie schützt AC-2.1.8/9).
- **Bug gefixt (Doubleheader):** `SeriesEntry.day_game_counts` erhält DH beim Roundtrip
  (`_entry_from_games` / `_entries_to_season`). Vorher gingen DH-Spiele verloren (2432→2400).
- **Bug gefixt (Blackout):** `_start_ok()` + `_bo_ok()` — SA-Moves UND `_greedy_fatigue_repair`
  respektieren jetzt `home_blackout_days` (Disruption). War latent in shift/swap.
- **Defaults:** `GeneratorConfig.travel_optimizer_iterations = 3_000_000` (moderat, für
  interaktive Pfade), `travel_optimizer_shift_max_days = 8`. Offizielle Läufe setzen höher:
  `main.py --travel-iterations` default **6_000_000**, Backtest 6M.

### Saison-Phasen (`src/phases.py`)
- `SchedulePhase(name, start, end, multipliers)`, `PhasePlan` (JSON load/save).
  `PHASE_KEYS = ("revenue","tv","friction")` — pro-Spiel lokalisierbare Ziele.
- Integriert in `optimize_pareto(..., phase_plan=...)`: `_pm(d,key)` skaliert die per-Serie-
  Beiträge in `_entry_revenue_val/_entry_tv_val/_entry_friction_val` pro Tag. **Ohne phase_plan
  bit-identisch** (Determinismus erhalten).
- Beispiel: `data/season_phases_example.json`.

### Tuner-Feedback-Schleife (echte Zahlen)
- `tools/tuning.py: evaluate_tuning(profile_weights, phase_plan_dict, season_year, seed,
  warm_iterations=1_000_000, pareto_iterations=80_000)` → Warm-Start + gewichtete Pareto-Opt →
  Dict {dimensions (real vs ours + Δ%), windows (pro Fenster), summary}.
- CLI: `python -m tools.tune_run --config <export.json> --season 2024`.
- API: `POST /tune/evaluate` in `tools/api.py` (+ CORS für file://-Dashboard).
  Start: `uvicorn tools.api:app`.

### Regler-Dashboard (`dashboard/phase_tuner.html`)
- Globale Regler (alle steuerbaren Dims) + Phasen-Regler (TV/Revenue/Friction pro Fenster).
- **Live-Schätzung** aus `CALIB`-Konstante (eingebettet, kalibriert). Button **„Diesen Plan
  rechnen"** → `POST /tune/evaluate` → echte Werte. Export-JSON unten.
- Slider-Reichweite: w_tv bis 20×, w_revenue bis 15× (damit starke Gewichte erreichbar, wo der
  Hebel beißt).

### Kalibrierung (`tools/build_calibration.py` → `data/phase_calibration.json`)
- Methodik (recherchiert): **gemessenes Raster + monotone Interpolation** (kein GP/RBF —
  Auditierbarkeit, wenige Stützstellen). Multiplikator-Sweep MIT Phasenplan bei festem starkem
  Gewicht (`STRONG_WEIGHT tv=-3000`, `CAL_ITERS=80_000`).
- **Gemessenes Ergebnis (ehrlich):** Warm-Start hebt Fenster-TV **+54 %** / Revenue **+51 %**
  über real. Der **Phasen-Multiplikator** zusätzlich: TV **~+5–8 %** (sättigt ~mult 4),
  Revenue **~0 %** (physikalisch gedeckelt — Matchups/Wochenenden fix). Globale Gewichte ~1–2 %.
- Neu vermessen: `python -m tools.build_calibration --dim tv|revenue`.

### Tests (neu, alle grün)
`tests/test_sprint_3_backtest.py` (7+2 slow), `_sustainability_fairness.py` (9),
`_phases.py` (7+1 slow), `_tuning.py` (2 slow). Gesamt 332 Test-Funktionen im Projekt.

---

## 3 — Belastbare Kennzahlen (zum Zitieren)

| | real 2024 | Warm-Start (wir) | From-Scratch (wir) |
|---|---:|---:|---:|
| Reise-km | 1.709.835 | **1.617.761 (−5,4 %)** | ~1.86–1.90M (+9 %) |
| CBA-Verletzungen | 0 | **0** | 3–6 |
| worst_away | 11 | 13 (≤13 ok) | 17–20 |
| real 2025 | 1.715.743 / 1 Verl. | **1.671.345 (−2,6 %) / 0 Verl.** | CP-SAT UNKNOWN |

Fenster-TV (Saisonstart, vs real): Warm-Start **+54 %**; Phasen-Regler zusätzlich ~+5–8 %.

---

## 4 — Gotchas (Sandbox & Projekt) — WICHTIG

- **Sandbox-Bash:** jeder Aufruf frisch (kein cwd-/env-/Background-Übertrag zwischen Aufrufen!),
  **max ~45 s**, **kann KEINE Dateien löschen** (`rm` → „Operation not permitted"; stattdessen
  überschreiben), `pip install ... --break-system-packages`. Für Ad-hoc-Skripte `PYTHONPATH=.`.
  Lange Generator-Läufe (>45 s) NICHT am Stück möglich → Iterationen reduzieren oder splitten.
- **Pfade:** Repo in Bash unter `/sessions/<id>/mnt/MLB Logistics Optimizer/`; Datei-Tools
  unter `/Users/jonas/MLB Logistics Optimizer/`.
- **Determinismus:** `num_search_workers=1` + fixer Seed → bit-identisch. Nicht brechen.
- **Slow-Tests:** `@pytest.mark.slow` = CI-only (volle Saison >45 s). Lokal `-m "not slow"`.
- **xfail:** AC-2.1.8 in `tests/test_fatigue_constraints.py` (strict=False) — bewusst offen.
- **2025 Kalt-Start:** CP-SAT intraktabel → immer Warm-Start nutzen.
- **optimize_pareto** wurde verändert (phase_plan-Param) — beim Anfassen Determinismus prüfen
  (68 Tests in `test_sprint_2_3b.py`).

---

## 5 — Nächste Schritte (priorisiert, aus `PROJECT_REVIEW_2026-06.md`)

**P0 (Blocker):** AC-2.1.8 ≤13 ist im From-Scratch nicht garantiert (CBA-rote-Linie).
→ Entscheidung mit Jonas: **Warm-Start-only als Produktionspfad festschreiben** (sofort
konform). Branch-and-Price/kommerzieller Solver (Gurobi/CPLEX) als separates Item.

**P1:** (a) Doubleheader-Planung fehlt. (b) Realregeln fehlen: Getaway-Day/Reise-Feasibility,
National-TV-Fenster, Venue-Verfügbarkeitskalender, Feiertags-Pins. (c) Compliance-Report +
menschenlesbare Plan-Begründung (`src/compliance.py`, `src/explain.py`) — Pläne „verteidigbar"
machen. (d) Pareto-Optimizer verstärken (Geo-Move + TTP-Nachbarschaften portieren).

**P2:** CO₂/Fairness in Report+Dashboard (C3); Flughafen- statt Stadtkoordinaten; Revenue/TV
pro Spiel mit echten Daten validieren; stärkere Geo-Nachbarschaft; schnelles Reduced-Instance-
Test-Set.

**Jonas' zuletzt vorgeschlagene Richtung:** P0 entscheiden, dann **P1 (Getaway-Days +
Feiertags-Pins + Compliance/Erklärbarkeit)** — datenarm, hoher Stakeholder-Wert.

---

## 6 — Schnellbefehle

```bash
# Backtest gegen echten Plan (Warm-Start schlägt real):
python -m tools.backtest --season 2024 --warm-start
# Offizielle Saison-Generierung (Warm-Start, beste Qualität):
python -m src.main --source-season 2024 --warm-start
# Tuner-Config rechnen (echte Zahlen):
python -m tools.tune_run --config <export.json> --season 2024
# Kalibrierung neu vermessen:
python -m tools.build_calibration --dim tv --season 2024
# API für das Dashboard:
uvicorn tools.api:app          # POST /tune/evaluate
# Schnelle Tests:
python -m pytest -m "not slow" -q -p no:cacheprovider
```
