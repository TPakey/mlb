# HANDOVER — Stand nach Sprint 3 (2026-06-07)

**Für die nächste Session.** Macht dich sofort arbeitsfähig. Lies zuerst dies,
dann bei Bedarf die verlinkten Detail-Docs.

## 0 — Orientierung

MLB-Saison-Optimierer, 30 Teams, 2.430 Spiele. Pipeline: realer Plan →
**Warm-Start** (`optimize_travel`, SA mit Geo-Move + Fatigue/Feasibility/Holiday)
→ optional Pareto-Front (8 Dim). Warm-Start ist der **einzige Produktionspfad**
(P0, `docs/DECISION_P0_PRODUCTION_PATH.md`). Mit Jonas immer **Deutsch**. Maßstab:
**MLB muss es direkt nutzen können.** Arbeitsstil: erst durchdenken → recherchieren
→ messen statt behaupten → Qualität vor Tempo.

## 1 — Was in Sprint 3 alles dazukam (diese Session)

**P0** Warm-Start-only festgeschrieben (`main.py` Default; `--from-scratch` =
Validierung). **P1-3** Getaway-Feasibility (`src/feasibility.py`), Feiertags-Pins
(`src/holidays.py`). **P1-4** Compliance-Report (`src/compliance.py`,
maschinenlesbar, Hard-Rule↔CBA-Quelle) + Plan-Begründung (`src/explain.py`,
inkl. CO₂/Fairness). **P1-2** Doubleheader-Verdichtung (`src/doubleheaders.py`).
**P1-5** Geo-Move + Feasibility/Holiday-Terme auch in `optimize_pareto`. **P2**:
CO₂/Fairness im Backtest-Report; Revenue pro Team gegen reale Attendance validiert
(Spearman 0,89, `docs/REVENUE_VALIDATION_2024.md`); Flughafen-Koordinaten-Analyse
(`docs/AIRPORT_COORDINATES_2024.md`, Default bleibt Stadt); Reduced-Instance-Smoke
+ HAP-Tests als `slow`; stärkere Geo-Nachbarschaft (`geo_topk`).

**Scheduler-Operations-Suite (NEU):** pro Auswärts-Trip operative Dossiers —
Routing (`ops_routing`), Security-Briefing (`ops_security`), Hotel-Empfehlung
(`ops_hotels`), Dossier-Generator (`ops_dossier` + `tools/generate_trip_dossier`).
Design: `docs/OPS_SUITE_DESIGN.md`. Beispiel: `docs/EXAMPLE_TRIP_DOSSIER_NYY_2024.md`.

## 2 — Wichtige Konventionen (NICHT brechen)

- **Determinismus:** `num_search_workers=1` + fixer Seed → bit-identisch. Alle
  neuen SA-Terme/Moves sind **gegated** (feas_lambda/holiday_lambda/geo_topk=2/
  enable_dh_compression default → bit-identisch). Energie `+ 0.0` ist bit-treu.
- **Tests:** `python -m pytest -m "not slow" -q -p no:cacheprovider`. Volle
  30-Team-CP-SAT-Tests sind `@slow` (CI-only). Schnelle Generator-Smoke:
  `tests/test_reduced_smoke.py`.
- **Sandbox:** jeder Bash-Aufruf frisch, max ~45 s, kann nicht löschen (überschreiben),
  `pip install --break-system-packages`. Lange SA-Läufe splitten.
- **Neue Defaults bleiben aus** — alle Sprint-3-Features sind opt-in.

## 3 — Belastbare Kennzahlen

Warm-Start 2024: −5,4 % Reise / 0 CBA-Verletzungen. Geo-Move im Pareto: −0,7 %.
`geo_topk=6` (200k Iter): −1,1 % vs topk=2. Feasibility-Term: behebt die von der
km-only-SA *erzeugten* Envelope-Verstöße (0/2 wie real). Holiday-Term: hebt
Memorial/Labor-Day-Slates über den realen Plan. Revenue-Struktur Spearman 0,89.

## 4 — Nächste sinnvolle Schritte (priorisiert)

**Externe Daten (einzige echte „100 % MLB-tauglich"-Blocker — Jonas/MLB-Ops):**
National-TV-Fenster, Venue-Belegungskalender (hart), echte Gate-Receipts,
CBA-Wortlaut AC-2.1.8. Details: `docs/STATUS_REVIEW_2026-06-07.md`.

**Algorithmik (optional):** Branch-and-Price/Gurobi (From-Scratch MLB-tauglich);
volle TTP-Nachbarschaften (Ejection Chains, 2-opt über Trips) über `geo_topk`
hinaus; DH-Compression v2 (Compression + Pull-in).

**Ops-Suite-Ausbau:** Club-Hotel-Buchungsdaten importieren; Maps-API ans
Routing; lokale EMS/PD-Liaison-Anbindung; Ops-Dossier ins Dashboard.

## 5 — Schnellbefehle

```bash
# Produktionsplan (Warm-Start, alle Verbesserungen):
python -m src.main --source-season 2024 --geo-topk 6 --feas-lambda 50000 --holiday-lambda 5000 --dh-compression
# Backtest gegen real (jetzt mit CO₂/Fairness):
python -m tools.backtest --season 2024 --warm-start
# Revenue-Struktur gegen reale Attendance validieren:
python -m tools.validate_revenue_model
# Flughafen- vs Stadt-Koordinaten:
python -m tools.compare_airport_distance --season 2024
# Trip-Operations-Dossier:
python -m tools.generate_trip_dossier --team NYY --season 2024 --out output/ops/NYY_2024.md
# Schnelle Tests:
python -m pytest -m "not slow" -q -p no:cacheprovider
```
