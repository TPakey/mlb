# Architektur-Entscheidung — Offizieller Schedule-Pfad

**Datum:** 2026-05-27 (Sprint 2.8)
**Behebt:** M10, A1, A2, A6
**Status:** Verbindlich.

## Entscheidung

Der **offizielle Hauptpfad** zur Schedule-Erzeugung ist:

```
generator.generate()            # CP-SAT: feasibler Plan (NoOverlap + periodische Break-Days)
  → generator_optimizer.optimize_travel()   # SA: Travel-Minimierung + Fatigue-Penalty + AC-2.1.8-Repair
  → pareto.sample_pareto_frontier()         # optional: Multi-Objective-Front (8 Dimensionen)
```

unterstützt von: `pareto_types`, `profiles` (ParetoProfile), `tv_slots`,
`revenue`, `player_fatigue`, `travel`, `distance`, `season`, `matchup_extractor`,
`data_loader`, `datasources`, `event_conflicts`, sowie der What-if-/Disruption-
Schicht (`whatif`, `disruption`, `repair_local`, `repair_regenerate`,
`repair_venue_swap`).

`python -m src.main` ruft seit Sprint 2.8 **diesen** Pfad auf (vorher fälschlich
die alte `optimizer.optimize`-Pipeline — Review M10).

## Warum generator.py (CP-SAT + SA) und nicht die Column-Generation (2.3a)?

Beide sind valide. Ausschlaggebend für die Wahl als *Hauptpfad*:

- **Vollständigkeit:** Die gesamte aktuelle Funktionalität (Pareto-Explorer,
  What-if-Engine, Disruption-/Repair-Schicht, Revenue-/TV-/Event-Scoring) ist
  auf dem `generator.py`-Pfad und dem `ParetoBundle` aufgebaut. Die
  Column-Generation (`two_phase_pacing` + `column_generation` + `series_matching`)
  ist eine akademisch saubere Alternative, deckt aber nicht die volle Pipeline ab.
- **Reproduzierbarkeit:** `num_search_workers=1` + deterministische Seeds.
- **Die Column-Generation bleibt** als dokumentierter, akademisch fundierter
  Backup-/Vergleichspfad im Core (`src/`), NICHT in `legacy/`. Sie ist bei einer
  MLB-Übergabe als zweites, unabhängiges Korrektheits-Argument wertvoll.

## Was nach `src/legacy/` verschoben wurde (Sprint 0/1-Prototyp)

`schedule_generator`, `optimizer`, `scoring`, `constraints`, `soft_factors`,
`ai_explainer`, `metrics`, `penalties`, `tradeoff_profiles` (vormals
`TradeoffProfile` in `profiles.py`), sowie die separaten Validatoren
`validation` und `validation_v2`. Außerdem das tote `two_phase_repair`.

Diese Module sind **deprecated**. Sie werden vom Hauptpfad nicht importiert.
Imports auf Basis-Module (`data_loader`, `distance`, `season`) wurden auf
`..`-Relativimporte umgestellt; legacy-interne Importe bleiben `.`.

### validation vs. validation_v2 (Review A2)

`validation_v2` erweitert `validation`, wird aber von **keinem** aktiven Modul
importiert (nur `tools/validate_season.py` und `tests/test_infrastructure.py`
nutzen `validation` für den Sprint-1-Regressions-Check gegen echte MLB-Daten).
Beide leben daher gemeinsam unter `src/legacy/`. Der Hauptpfad validiert
Fatigue-/Hard-Constraints über `player_fatigue` + `pareto_types.compute_pareto_bundle`.

## Tests & Tools

- `tests/legacy/test_end_to_end.py` testet weiterhin den Legacy-Pfad (Importe auf
  `src.legacy.*` umgestellt) und ist damit klar als Legacy-Test markiert.
- `tools/validate_season.py` und `tests/test_infrastructure.py` nutzen jetzt
  `src.legacy.validation`.

## Nachtrag (Sprint 3, 2026-06-07): Warm-Start ist der Produktionspfad

Innerhalb des oben festgelegten `generator.py`-Pfades ist seit P0 der
**Warm-Start** der **einzige Produktionspfad** (CBA-konform, schlägt den realen
Plan); From-Scratch ist nur noch Algorithmus-Validierung. Details + Begründung:
`docs/DECISION_P0_PRODUCTION_PATH.md`. `python -m src.main` nutzt Warm-Start als
Default; `--from-scratch` ist das Validierungs-Flag.

Neu in Sprint 3 (P1-3/P1-4), als Reporting-Schicht auf demselben Pfad:
`src/feasibility.py` (Getaway-Day-/Reise-Feasibility), `src/holidays.py`
(Feiertags-Pins), `src/compliance.py` (Regel↔Quelle-Compliance-Report,
maschinenlesbar) und `src/explain.py` (menschenlesbare Plan-Begründung).

## Dashboards (Review A6)

`dashboard/build_dashboard.py` (konsumierte Outputs der alten `main.py`) wurde
nach `dashboard/legacy/` verschoben. `build_real_dashboard.py` (Validierungs-
basiert) bleibt vorerst. Ein konsolidiertes Stakeholder-Dashboard auf Basis des
Pareto-Outputs ist Teil von Sprint 2.12.
