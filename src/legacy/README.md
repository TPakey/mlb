# src/legacy — Deprecated Sprint-0/1-Pfad

Diese Module sind **deprecated** und werden vom offiziellen Hauptpfad nicht
mehr aufgerufen. Sie bleiben erhalten für historische Nachvollziehbarkeit und
den Sprint-1-Regressions-Check gegen echte MLB-Daten.

**Offizieller Hauptpfad:** siehe `docs/ARCHITECTURE_DECISION.md` →
`src/generator.py` (CP-SAT) + `src/generator_optimizer.py` (SA) + `src/pareto.py`.

## Inhalt

| Modul | Vormals | Zweck (historisch) |
|---|---|---|
| `schedule_generator.py` | Sprint 0 | vereinfachtes Wochen-Slot-Modell |
| `optimizer.py` | Sprint 1 | 7-Dim-SA über `TradeoffProfile` |
| `scoring.py`, `penalties.py` | Sprint 1 | altes Score-System |
| `constraints.py` | Sprint 1 | alte Hard-Constraint-Checks |
| `soft_factors.py` | Sprint 1 | Soft-Event-Gewichtung |
| `ai_explainer.py` | Sprint 1 | Narrative-Generierung |
| `metrics.py` | Sprint 1 | km/CO₂/Kosten-Metriken |
| `tradeoff_profiles.py` | Sprint 0/1 | `TradeoffProfile` (7-Dim) |
| `validation.py`, `validation_v2.py` | Sprint 1/2 | Validierungs-Harness (echte MLB-Daten) |
| `two_phase_repair.py` | Sprint 2.3a | toter Repair-Ansatz (nie importiert) |

Importe auf Basis-Module (`data_loader`, `distance`, `season`) verweisen via
`..` auf den Core; legacy-interne Importe via `.`.
