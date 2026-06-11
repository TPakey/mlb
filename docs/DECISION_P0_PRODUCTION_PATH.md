# Entscheidung P0 — Warm-Start als einziger Produktionspfad

**Datum:** 2026-06-07 (Sprint 3)
**Behebt:** P0-1 aus `docs/PROJECT_REVIEW_2026-06.md`
**Status:** Verbindlich.
**Entscheider:** Jonas (Richtung: „was langfristig am meisten Sinn ergibt").

---

## Entscheidung

Der **einzige Produktionspfad** zur Erzeugung eines MLB-tauglichen Saisonplans
ist der **Warm-Start**: vom realen Plan der Quell-Saison ausgehen und mit dem
Travel-/Fatigue-SA (Geo-Move) verbessern.

```
realer Quell-Plan  →  generator_optimizer.optimize_travel (SA: Geo-Move + Fatigue)
                   →  optional pareto.sample_pareto_frontier
```

Die **From-Scratch-Generierung** (CP-SAT + SA, kalt) ist ab sofort
**ausschließlich Algorithmus-Validierung** und kein Auslieferungspfad. In
`src/main.py` ist Warm-Start der Default; From-Scratch wird nur über das explizite
Flag `--from-scratch` (mit Warnhinweis) erreicht.

## Begründung (datenbasiert)

| | real 2024 | Warm-Start | From-Scratch |
|---|---:|---:|---:|
| Reise-km | 1.709.835 | **1.617.761 (−5,4 %)** | ~1,86–1,90 M (+9 %) |
| CBA-Verletzungen (AC-2.1.8) | 0 | **0** | 3–6 Teams > 13 Tage |
| worst days-away | 11 | 13 (≤ 13 ok) | 17–20 |
| real 2025 | 1.715.743 / 1 Verl. | **1.671.345 (−2,6 %) / 0 Verl.** | CP-SAT UNKNOWN |

- **Warm-Start ist CBA-konform und schlägt den realen Plan** auf der Reise —
  und repariert in 2025 sogar die eine reale AC-2.1.8-Verletzung (14 → 13).
- **From-Scratch ist NICHT MLB-tauglich:** AC-2.1.8 (≤ 13 Tage am Stück auswärts)
  ist je nach Seed bei 3–6 Teams verletzt (worst ~20). Ein solcher Plan ist für
  die Liga unbrauchbar, unabhängig von der Reisequalität.
- **Die Härte ist intrinsisch, nicht ein Encoding-Problem.** Das zugrunde liegende
  Traveling Tournament Problem ist APX-hart; sieben CP-SAT-Standardformulierungen
  wurden als intraktabel belegt (`docs/Q10_ANALYSE_UND_RECHERCHE.md`). For 30
  Teams nutzt die Literatur Branch-and-Price oder kommerzielle Solver.

## Warum das *langfristig* die richtige Wahl ist

Warm-Start ist nicht nur der pragmatische Kurzfrist-Fix, sondern auch der
realistische **Produktionsmodus** einer Liga: In der Praxis wird ein Saisonplan
nie auf der grünen Wiese erzeugt, sondern aus dem Vorjahresplan / einem von
MLB-Ops gesetzten Grundgerüst fortgeschrieben (Venue-Verfügbarkeiten,
TV-Verträge, Feiertags-Pins, etc. sind dort bereits eingearbeitet). Warm-Start
respektiert dieses Grundgerüst und verbessert es nachweisbar — genau das, was
ein Liga-Workflow braucht.

## Langfrist-Item (separat, beschaffungs-gegated)

**Branch-and-Price mit kommerziellem Solver (Gurobi / CPLEX)** bleibt als die in
der Literatur belegte, exakte Lösung für 30-Team-TTP-Instanzen ein **separates,
beschaffungs-gegatetes Arbeitspaket** — KEINE Voraussetzung für den
Produktivbetrieb (Warm-Start liefert bereits CBA-konforme, real-schlagende Pläne).
Es würde den From-Scratch-Pfad MLB-tauglich machen (echte „grüne Wiese"-Pläne mit
garantiertem AC-2.1.8), erfordert aber Solver-Lizenzen und eigenen
Implementierungsaufwand.

- **Quellen:** Anagnostopoulos et al. (TTSA); Easton/Nemhauser/Trick (TTP
  Benchmarks); Trick, *Adventures in Sports Scheduling*.
- **Vorarbeit im Repo:** verifiziert-sounde AC-2.1.8-Gap-Formulierung
  (`generator._add_ac_2_1_8_gap_constraints`, orakel-getestet) + HAP-Solver
  (`src/colgen/`) liegen bereit; es fehlt die traktable Branch-and-Price-Engine.

## Konsequenzen im Code

- `src/main.py`: Default = Warm-Start. `--from-scratch` = Validierungs-Flag mit
  Warnung. `--warm-start` bleibt als No-Op (Rückwärtskompatibilität).
- From-Scratch-Tests bleiben als **Algorithmus-Validierung** bestehen (nicht als
  Akzeptanz für Produktionspläne zu lesen).
- AC-2.1.8 bleibt im From-Scratch-Pfad `xfail` — das ist jetzt bewusst und
  dokumentiert, kein offener Blocker mehr für die Produktion.
