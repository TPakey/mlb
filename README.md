# MLB Logistics Optimizer

KI-gestützter Optimierer für den MLB-Saisonkalender. Minimiert Reisedistanzen, respektiert sportliche und CBA-Regeln und bewertet weiche Faktoren (Revenue, TV-Slots, lokale Events, Spieler-Fatigue) über eine Pareto-Front.

## Was das Tool tut

Der MLB-Spielplan umfasst rund 2.430 Spiele in einer Regulärsaison (30 Teams × 162 Spiele). Dieses Tool baut einen mathematisch optimierten Alternativplan, der:

- Reisedistanzen minimiert (Flugzeit-basiert, DST-korrekte Zeitzonen-Hops)
- harte Regeln einhält (Serienstruktur, Heim/Auswärts-Balance, All-Star-Break, AC-2.1.9 ≤ 20 konsekutive Spieltage; „≤ 13 Tage auswärts"/AC-2.1.8 ist seit 2026-06-09 ein *weiches* Qualitätsziel, kein CBA-Erfordernis — siehe regulations/FINDING_AC-2.1.8_vs_CBA.md)
- mehrere Ziele gegeneinander abwägt (Reise, Revenue, TV-Slot-Attraktivität, Fatigue, Event-Friction) und eine **Pareto-Front** alternativer Pläne liefert
- **What-if-Analysen** erlaubt (Serie erzwingen, Stadion-Blackout, Hurricane-Disruption) mit Validitäts-Garantien
- in einem interaktiven Dashboard visualisiert wird

## Architektur (Hauptpfad — siehe docs/ARCHITECTURE_DECISION.md)

```
MLB Logistics Optimizer/
├── data/                       Stammdaten & Modell-Parameter
│   ├── teams.json              30 Teams + Stadien + Koordinaten + Timezones
│   ├── tv_slots.json           TV-Slot-Werte + Daypart-Mix + Marquee-Matchups
│   ├── revenue_model.json      Gate-Revenue-Modell (Sportico-kalibriert)
│   ├── soft_factors.json       Wetter, lokale Events, Stadion-Konflikte
│   └── mlb_schedule_2024.json  Echter Plan als Quoten-/Vergleichsbasis
├── src/                        Python-Code (Hauptpfad)
│   ├── generator.py            Stufe 1: CP-SAT — feasibler Plan (NoOverlap, Break-Days)
│   ├── generator_optimizer.py  Stufe 2: Simulated Annealing (Travel + Fatigue-Repair)
│   ├── pareto.py / pareto_types.py  Multi-Objective Pareto-Front (8 Dimensionen)
│   ├── profiles.py             ParetoProfile-Gewichtungen
│   ├── player_fatigue.py       AC-2.1.8/9 (CBA "days away from home", siehe CBA_DEFINITIONS.md)
│   ├── travel.py / distance.py Reisemodell (Haversine + Charter + DST-Hops)
│   ├── tv_slots.py / revenue.py TV-Slot- & Revenue-Scoring
│   ├── whatif.py → whatif_core/  What-if-Engine (Subpackage: types/helpers/force/blackout/compare/impact)
│   ├── disruption.py + repair_*.py  Disruption-/Repair-Strategien
│   ├── column_generation.py → colgen/  HAP/Column-Generation-Pipeline (Subpackage: patterns/rmp/pricing/engine/hap)
│   ├── two_phase_pacing.py + series_matching.py  Phase-A-Pacing + Phase-B-Slot-Matching
│   ├── legacy/                 Deprecated Sprint-0/1-Prototyp (siehe legacy/README.md)
│   └── main.py                 CLI-Einstiegspunkt
├── dashboard/                  Interaktives HTML-Dashboard (D3 Pareto-Explorer)
├── tools/                      CLI & Service: api.py (REST), demo_pareto, whatif_demo, validate_revenue_model
└── docs/                       Reviews, Handovers, Architektur-Entscheidungen, Q10-Analyse
```

> **Hinweis (A20/A21-Refactor, 2026-05-31):** `column_generation.py` und `whatif.py`
> wurden in die Subpackages `src/colgen/` bzw. `src/whatif_core/` aufgeteilt. Die
> Original-Dateien bleiben als dünne öffentliche Fassaden — alle Importe
> `from src.column_generation import X` / `from src.whatif import X` funktionieren
> unverändert.

## Schnellstart

```bash
pip install -r requirements.txt

# PRODUKTIONSPFAD (Default = Warm-Start): realen Vorjahresplan als Startpunkt
# nehmen und optimieren. Schlägt den realen MLB-Plan auf Reisedistanz UNTER
# voller Regel-Konformität (gemessen 2026-06-10, Seed 42, 3M Iter, Publish-Gate
# PASS: 2024 −2,4 %, 2025 −1,9 %; mehr Iterationen → mehr Ersparnis).
# Regel-Schutzterme (V(C)(11)-PTET, Reise-Envelope, V(C)(13)) sind seit dem
# Review-Fix 2026-06-10 DEFAULT AKTIV; jeder Output muss das PUBLISH-GATE
# bestehen (kein neuer harter/struktureller Verstoß ggü. der Baseline — gemessen
# mit src/publish_gate.py, nicht behauptet). EHRLICHER HINWEIS: der frühere
# Claim „−5,4 % und voll CBA-konform (0 Verletzungen)" war FALSCH — die höhere
# km-Zahl entstand durch harte Regelverstöße (V(C)(11): 18×/2024, 28×/2025;
# Reise-Envelope; Dutzende V(C)(13)-Fenster); Beleg + Messreihe:
# docs/REVIEW_2026-06-10_INDEPENDENT_AI.md. Alt-Verhalten: --legacy-bitident
# (Output wird dann als NICHT PUBLIZIERBAR markiert).
# Seit P0 der EINZIGE Auslieferungspfad — Begründung: docs/DECISION_P0_PRODUCTION_PATH.md
python -m src.main --source-season 2024

# NUR Algorithmus-Validierung (NICHT MLB-tauglich; AC-2.1.9/≤20 strukturell garantiert,
# AC-2.1.8/≤13 ist weiches Ziel). Green-field-Tauglichkeit ist Sprint-5.4-Ziel (Branch-and-Price).
python -m src.main --season 2026 --from-scratch

# Optionale weiche SA-Terme + DH-Verdichtung (Feiertag/DH Default aus;
# feas/ptet/sched13 sind Produktions-Default und nur via --legacy-bitident aus):
#   --holiday-lambda 5000 bevorzugt volle Feiertags-Slates + Marquee-Spiele an Feiertagen
#   --dh-compression      verdichtet zu lange Road-Trips per Day-Night-Doubleheader
python -m src.main --source-season 2024 --holiday-lambda 5000 --dh-compression

# Backtest gegen den echten MLB-Plan (Glaubwürdigkeits-Vergleich):
python -m tools.backtest --season 2024 --warm-start   # warm-start: schlägt real
python -m tools.backtest --season 2024                # from-scratch (Validierung)

# ── Externe Daten & Lizenz (Runde 3 — EIN Einstiegspunkt) ─────────────────
# Provenienz-Registry ALLER Datendateien (Quelle/Rating/Refresh/Validierung):
#   docs/DATA_PROVENANCE.md
python -m tools.update_external_data --status     # was ist da, was fehlt
python -m tools.update_external_data --all        # Retrosheet-Originalpläne (Gold,
                                                  # Rating A) + Broadcast-Fakten laden,
                                                  # kreuzvalidieren, Manifest erneuern
python -m tools.update_external_data --measure-original  # offline: V(C)(13)/(14)
                                                  # auf dem ORIGINALPLAN messen
# Gurobi-Lizenz (auf DEINEM Rechner, nie in Sandboxen — Code ist einmalig):
python -m tools.setup_gurobi --key <aktivierungscode>   # grbgetkey + .env + Beweis-Solve
python -m tools.setup_gurobi --validate                  # Voll-Lizenz nachweisen

# Zusätzlich die Pareto-Front berechnen:
python -m src.main --season 2026 --pareto

# Validatoren & Demos:
python -m tools.validate_revenue_model      # Revenue-Struktur vs. reale Attendance (Spearman)
python -m tools.compare_airport_distance    # Flughafen- vs. Stadt-Koordinaten
python -m tools.demo_pareto                 # Pareto-Front-Demo
python -m tools.whatif_demo --scenario all  # What-if-Szenarien (force/blackout/compare)

# Scheduler-Operations: Trip-Dossier je Team (Routing + Hotel + Security-Briefing):
python -m tools.generate_trip_dossier --team NYY --season 2024 --out output/ops/NYY_2024.md
#   → docs/OPS_SUITE_DESIGN.md, Beispiel docs/EXAMPLE_TRIP_DOSSIER_NYY_2024.md
# Ops-Suite im Dashboard (alle 30 Teams interaktiv → dashboard/ops.html):
python dashboard/build_ops_dashboard.py --season 2024

# Sprint 4 — optionale, gegatete Erweiterungen (alle Default aus):
#   --oropt-share 0.0     EXPERIMENTELL: OR-opt-Move; Messung zeigt kein
#                         Produktions-Win → aus lassen (docs/SPRINT_4_REVIEW.md)
#   Venue-Compliance (hart, opt-in) + DH-v2 Pull-in: siehe docs/SPRINT_4_REVIEW.md

# REST-API (optional, Sprint 2.12.6):
pip install fastapi "uvicorn[standard]"
uvicorn tools.api:app --reload             # http://127.0.0.1:8000/docs (OpenAPI)
```

## Methodik (Kurzfassung)

1. **Stufe 1 — CP-SAT (Google OR-Tools):** platziert alle Serien als Intervalle
   mit NoOverlap pro Team. Periodische Break-Days garantieren strukturell
   AC-2.1.9 (max 20 Spieltage je 21-Tage-Fenster).
2. **Stufe 2 — Simulated Annealing:** minimiert Reise-km bei gleichzeitiger
   Fatigue-Penalty (λ = 1e6) und einem gezielten AC-2.1.8-Repair, der zu lange
   Road-Trips aufbricht.
3. **Pareto-Front:** SA-Läufe über benannte Profile + zufällige Mischprofile
   (Dirichlet-Sampling) liefern eine Menge nicht-dominierter Pläne über 8
   Dimensionen (Reise, Revenue, Fatigue, Away-Streak, Off-Day-Varianz, TV-Slot,
   Event-Friction, Constraint-Violations).
4. **What-if & Disruption:** schnelle lokale Re-Planung mit Validitäts-Checks.

Wichtige Definitions-Grundlage: [docs/CBA_DEFINITIONS.md](docs/CBA_DEFINITIONS.md)
(AC-2.1.8 = "days away from home", Off-Days in der Road-Trip zählen mit).
Reproduzierbarkeit: `num_search_workers=1` + feste Seeds.

## Daten-Quellen

- **Teams & Stadien**: kuratiert, basiert auf MLB Stats API (`docs.statsapi.mlb.com`). Hinweis: Athletics 2025–2027 interim in West Sacramento (Sutter Health Park), danach Las Vegas.
- **Revenue/TV**: Sportico/Statista-kalibriert (2024; siehe `revenue_model.json` Kalibrier-Hinweis).
- **Events / Wetter**: kuratierte Listen (siehe `docs/LOCAL_EVENTS_RESEARCH.md`).

## Status

Forschungsprototyp mit Produktdenken. Vollständige Übersicht: [docs/GESAMTBERICHT_FUER_REVIEW.md](docs/GESAMTBERICHT_FUER_REVIEW.md).

**Bekannte offene Limitation — AC-2.1.8 (max 13 „days away from home"):** wird unter
der korrigierten CBA-Definition (Off-Days zählen mit) durch SA + Repair stark
reduziert, aber bei der Saison-Dichte nicht garantiert auf ≤13 eliminiert. Eine
strukturelle Garantie ist nachweislich nur über fortgeschrittene OR-Methodik
(matchup-bewusste HAP / Branch-and-Price) erreichbar — die Standard-CP-SAT-Wege
sind als intraktabel belegt (sieben Ansätze). Ein optionaler gefensterter
CP-SAT-LNS-Repair (`enable_lns_ac218_repair`, default aus) senkt die realen
Verletzungen weiter, ohne ≤13-Beweis. Volle Analyse mit Literatur-Recherche:
[docs/Q10_ANALYSE_UND_RECHERCHE.md](docs/Q10_ANALYSE_UND_RECHERCHE.md).
