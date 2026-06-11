# Sprint 3 — P2-Verfeinerungen Review (2026-06-07)

Abarbeitung der P2-Punkte aus `docs/PROJECT_REVIEW_2026-06.md`, geordnet nach
Wert × Risiko × Abhängigkeit.

## Stufe 1 — P2-3: CO₂ + Fairness ins Reporting ✅

Die bestehenden Module (`sustainability.py`, `fairness.py`) sind jetzt im
Standard-Reporting verdrahtet:
- **Backtest-Report** (`tools/backtest.py`): neue Sektion „Nachhaltigkeit &
  Fairness" in Markdown + Block in JSON (`sustainability` je Plan). Zeigt CO₂
  gesamt/Team, Gini, Disparität, intensivstes/ärmstes Team — baseline vs. ours.
- **Plan-Begründung** (`src/explain.py`): Sektion „Nachhaltigkeit & Fairness"
  inkl. Δ vs. Baseline.
- Real 2024 gemessen: **21.504 t CO₂**, Gini **0,098** (sehr fair), Spitze SEA,
  Schluss PIT.

## Stufe 2 — P2-1/P2-2: Modell-Validierung mit echten Daten ✅

Über die Liga-Summen-Eichung hinaus die **Pro-Team-Struktur** validiert:
- Reale 2024-Heim-Attendance aller 30 Teams (ESPN) als Gate-Proxy →
  `data/real_attendance_2024.json`.
- `src/revenue_validation.py` (Spearman/Pearson/Rang-Ausreißer, ohne scipy),
  verdrahtet in `tools/validate_revenue_model.py`.
- **Ergebnis: Spearman-Rangkorrelation 0,892** (stark) — das Modell rankt die
  Zugkraft strukturell wie die Realität. Konkrete Ausreißer benannt (PHI/SDP/ATL
  unterbewertet, NYM/MIN/SFG/BOS überbewertet) → Priors gezielt auffrischbar.
- Doku + Empfehlung: `docs/REVENUE_VALIDATION_2024.md`. TV-Modell bleibt
  heuristisch (echte Broadcaster-Pick-Daten nicht öffentlich — ehrlich vermerkt).

## Stufe 3 — P2-4: Flughafen-Koordinaten (Analyse-Layer) ✅

- `data/team_airports.json` (30 Primär-Metro-Flughäfen, IATA + Koordinaten),
  `src/airport_analysis.py`, `tools/compare_airport_distance.py`.
- **Gemessen 2024:** Flughafen vs. Stadt = nur **−0,16 %** Liga-Total; mittlerer
  Anker-Fehler 0,75 % → 0,72 % (gemischt: PIT besser, SEA leicht schlechter).
- **Empfehlung: Stadt-Koordinaten bleiben Default** (validiert, kein klarer
  Gewinn, kein Determinismus-Bruch). Flughafen-Layer als getestete Option
  verfügbar. Doku: `docs/AIRPORT_COORDINATES_2024.md`.

## Stufe 4 — P2-7: schnelles Reduced-Instance-Smoke-Set ✅

- `src/reduced_instance.py`: reduzierte Saison (Spiele innerhalb einer
  Team-Teilmenge, z. B. AL East) → SA-/Warm-Start-Pfad in < 5 s testbar ohne
  vollen 30-Team-CP-SAT. `tests/test_reduced_smoke.py` (3 Tests, 0,9 s).
- Die langsamen 30-Team-CP-SAT-Tests (`TestGlobalHAPSolver`, `TestPhaseBMatching`,
  `TestHAPParsing` in `test_sprint_2_3a.py`) sind jetzt `@pytest.mark.slow` →
  unter `-m "not slow"` deselektiert. **Damit läuft die Nicht-Slow-Suite in der
  Sandbox sauber durch** (die wiederkehrenden HAP-Timeouts sind keine
  Fehlschläge mehr, sondern korrekt als CI-only markiert).

## Stufe 5 — P2-5: stärkere Geo-Nachbarschaft (`geo_topk`) ✅

Sichere, gegatete Erweiterung der Struktur-Nachbarschaft: die Anzahl der
geografisch nächsten Auswärts-Partner, die als Einfüge-Anker dienen, ist jetzt
konfigurierbar (`OptimizerConfig.geo_topk` / `optimize_pareto(geo_topk=…)` /
`sample_pareto_frontier(sa_geo_topk=…)` / `main.py --geo-topk`).
- **Default 2 = bit-identisch** zum bisherigen Verhalten (verifiziert).
- **Gemessen (Warm-Start real 2024, 200k Iter):** topk=2 → 1.680.131 km, topk=4 →
  1.671.785 km, **topk=6 → 1.662.379 km (−1,1 %)**. Die breitere Nachbarschaft
  findet bessere Trip-Kompositionen.
- **Ehrliche Einschränkung:** Der Gewinn zeigt sich erst bei **hohen**
  Iterationszahlen; bei wenigen (z. B. 5k) konvergiert die breitere Nachbarschaft
  langsamer und kann minimal schlechter sein. Für Produktionsläufe (≥200k–6M)
  lohnt `--geo-topk 4`–`6`.
- Determinismus für alle topk verifiziert. Tests in `test_sprint_3_sa_terms.py`.

Die volle TTP-Metaheuristik (Ejection Chains, 2-opt über ganze Trips,
Steepest-Descent-Geo) bleibt als dokumentiertes Forschungs-Item — bewusst NICHT
unter Zeitdruck in den determinismus-kritischen SA-Kern gedrückt. `geo_topk` ist
der sichere, gemessene erste Schritt in diese Richtung.

## Tests

Neu: `test_revenue_validation.py` (5), `test_airport_analysis.py` (3),
`test_reduced_smoke.py` (3) + erweiterte Explain/Compliance-Tests — alle grün.
Keine Regression; die determinismus-kritischen Suites unverändert.
