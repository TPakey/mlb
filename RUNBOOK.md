# RUNBOOK — Setup & Reproduktion (für den unabhängigen Review)

Alle Befehle aus dem **Projektroot**. Begleitend zu `AI_REVIEW_BRIEFING.md`. Ziel: du
kannst jede Behauptung des Projekts selbst nachstellen und kritisch prüfen.

## 1 — Abhängigkeiten

```bash
pip install pytest ortools==9.10.4067 numpy pandas geopy python-dateutil tzdata \
            hypothesis pyflakes --break-system-packages
# Green-field-Pfad (optional; ohne Lizenz nur größenlimitierte Restricted License):
pip install gurobipy --break-system-packages
```

Umgebung pro Shell:

```bash
export PYTHONPATH="$(pwd)"
export PATH="$HOME/.local/bin:$PATH"
```

## 2 — Tests

```bash
# Schnelle Suite (CP-SAT-Schwergewichte sind als 'slow' ausgeschlossen):
python -m pytest -q -m "not slow" -p no:cacheprovider

# Vollständig (langsam; einige CP-SAT-Tests brauchen viel Zeit/CPU):
python -m pytest -q -p no:cacheprovider

# Einzelne Bereiche:
python -m pytest -q tests/test_sprint_3_compliance.py        # Compliance-Regeln
python -m pytest -q tests/test_invariants.py                 # Property-Tests (hypothesis)
python -m pytest -q tests/test_sprint_5_1_starttimes.py      # Startzeit-Schicht
python -m pytest -q tests/test_sprint_5_2_compliance.py      # Strukturregeln + SA-Guard
python -m pytest -q tests/test_sprint_5_4_greenfield.py      # green-field MIP (Gurobi)
python -m pytest -q tests/test_sprint_5_4_branch_and_price.py # B&P / Column Generation
python -m pytest -q tests/test_sprint_5_4_decomposition.py   # Fenster-Dekomposition
python -m pytest -q tests/test_sprint_5_5_chronobiology.py   # Jet-Lag-Index

# Lint:
python -m pyflakes src/ tools/
```

Was du selbst beurteilen solltest: Welche Pfade sind unter `-m "not slow"` **nicht**
abgedeckt? Sind die Tests substanziell oder tautologisch? Welche `pytest.skip`/`importorskip`
verstecken etwas?

## 3 — Optimizer vs. realer Plan (Backtest)

```bash
# Warm-Start (Produktionspfad): realen Plan optimieren, gegen ihn vergleichen
python -m tools.backtest --season 2024 --warm-start
python -m tools.backtest --season 2025 --warm-start
# Ergebnisreporte landen in output/ (md/html/json)
# Achtung: Default-Iterationen sind sehr hoch (lange Laufzeit) — Code lesen, ggf. kürzen.

# From-scratch (nur Algorithmus-Validierung; nicht Produktionspfad):
python -m tools.backtest --season 2024
```

## 4 — Compliance / Regel-Checks selbst rechnen

```bash
python - <<'PY'
from pathlib import Path
from src.data_loader import load_teams, teams_by_id as tbi
from src.datasources.local_file import LocalFileAdapter
from src.compliance import compliance_report
from src.start_times import load_real_start_times, load_exempt_pks
teams = tbi(load_teams())
for y in (2024, 2025):
    s = LocalFileAdapter(base_dir="data").fetch_season_schedule(y)
    p = Path("data")/f"mlb_schedule_{y}.json"
    real = load_real_start_times(p, teams)
    # Review-Runde 2: volle V(C)(8)-Abdeckung + V(C)(5) brauchen die expliziten
    # CBA-Ausnahmen (SNB-Heuristik, Reschedules) — sonst misst man die
    # CBA-eigenen Ausnahmefaelle als Verstoesse.
    resched, snb = load_exempt_pks(p, teams)
    rep = compliance_report(s, teams_by_id=teams, start_min=real,
                            espn_snb_pks=snb, rescheduled_pks=resched)
    print(y, "is_compliant:", rep.is_compliant,
          "| harte Fehlschläge:", [c.rule_id for c in rep.hard_failures])
    print(rep.to_json()[:0] or "")   # rep.to_json() für den vollen maschinenlesbaren Report
PY
```

Prüfe: Ist `is_compliant` für beide Jahre plausibel? Wenn nicht — warum (Datensemantik vs.
echter Verstoß)? Sind alle bindenden Regeln überhaupt im Report? Fehlt eine?

## 5 — Startzeit-/Reisezeit-Messungen

```bash
python -m tools.measure_start_times       # V(C)(8)/(9)/(6) gegen reale Startzeiten
python -m tools.diagnose_e2_2025 40000    # Warum 2025 anders optimiert als 2024
```

## 6 — Green-field (Gurobi) — drei Methoden

```bash
# Direktes MIP (klein halten ohne Voll-Lizenz):
python -m tools.greenfield_demo --method monolithic --teams NYY,BOS,TBR \
       --games-per-pair 2 --days 9 --max-consecutive 4
# Branch-and-Price / Column Generation:
python -m tools.greenfield_demo --method bnp        --teams NYY,BOS,TBR --games-per-pair 2 --days 9
# Rolling-Horizon-Fenster-Dekomposition (skaliert größer):
python -m tools.greenfield_demo --method windowed   --teams LAD,SDP,SFG,SEA --games-per-pair 2 --days 20

# Lizenzstatus:
python -c "from src.greenfield_gurobi import gurobi_status; print(gurobi_status())"
```

Mit echtem Gurobi-Key in `.env` (`GRB_WLSACCESSID`, `GRB_WLSSECRET`, `GRB_LICENSEID`) fällt
das Größenlimit; dann größere `--teams`/`--days` testen. Beurteile selbst: Wie weit skaliert
jede Methode wirklich? Wo bricht es (Größe vs. NP-Härte)? Ist die Reise-km-Zielfunktion in
allen Pfaden konsistent definiert?

## 7 — Weitere Tools

```bash
python -m tools.validate_season --season 2024        # Saison-Struktur-Sanity
python -m tools.validate_revenue_model               # Revenue vs. reale Attendance
python -m tools.generate_trip_dossier --team NYY --season 2024 --out output/nyy.md
python -m tools.inspect_schedule data/mlb_schedule_2024.json
```

## 8 — Determinismus selbst nachweisen

```bash
python - <<'PY'
from src.data_loader import load_teams
from src.datasources.local_file import LocalFileAdapter
from src.season import detect_all_star_break
from src.generator_optimizer import GeneratorConfig, OptimizerConfig, optimize_travel
teams = load_teams()
real = LocalFileAdapter(base_dir="data").fetch_season_schedule(2024)
cfg = GeneratorConfig(season=2024, season_start=real.season_start, season_end=real.season_end,
                      all_star_break=detect_all_star_break(real), num_search_workers=1,
                      random_seed=42, enforce_fatigue_constraints=True)
oc = OptimizerConfig(iterations=5000, move_mix_geo=0.35, seed=42, fatigue_lambda=1_000_000.0)
a = optimize_travel(real, teams, cfg, oc)[1].final_km
b = optimize_travel(real, teams, cfg, oc)[1].final_km
print("final_km gleich:", a == b, a, b)
PY
```

Prüfe weiter: Sind die *gegateten* Zusatzterme (feas/holiday/ptet/chrono) bei Default 0
wirklich wirkungslos (bit-identisch)? Bricht irgendein Pfad den Determinismus (Zeit, Zufall,
Netz, Dict-Ordering)?

---

**Bewertungsrahmen:** Maßstab ist „von einem MLB-Scheduler direkt nutzbar". Liefere eine
priorisierte Befundliste mit Schweregrad, Reproduktionsschritten und Verbesserungsvorschlag.
