# MLB Logistics Optimizer — Briefing für einen unabhängigen KI-Review

> **An das prüfende Modell:** Dies ist ein Onboarding, kein Lösungsblatt. Es gibt dir
> einen präzisen Überblick über Aufbau, Datengrundlage, Konventionen und darüber, wie du
> **alles selbst ausführen und nachprüfen** kannst. Es sagt dir **bewusst nicht**, wo das
> Projekt schwach ist — **das sollst du eigenständig herausfinden.** Vertraue keiner
> Behauptung in den Repo-Dokumenten ungeprüft; verifiziere sie am Code und durch eigene
> Läufe. „Messen statt behaupten" ist das Leitprinzip dieses Projekts — wende es auch auf
> das Projekt selbst an.

---

## 0 — Deine Aufgabe

Führe ein **gründliches, unabhängiges technisches Review** durch. Ziel ist, **selbst** die
Stellen zu finden, an denen es noch hakt — fachlich, methodisch, in der Datenqualität, im
Code, in der Test-Abdeckung, in der Skalierbarkeit, in der Korrektheit der harten Regeln.
Bilde dir ein eigenes Urteil über Produktionsreife. Belege jeden Befund reproduzierbar
(Datei/Zeile, Messung, Gegenbeispiel) statt zu spekulieren.

Der **Qualitätsmaßstab** des Projekts: ein echtes US-Major-League-Baseball-Team bzw. die
Liga soll den Optimierer **direkt nutzen** können. Bewerte mit diesem Anspruch — nicht als
Demo, sondern als auszulieferndes Produkt.

Arbeitssprache mit dem Projektinhaber (Jonas): **Deutsch**.

---

## 1 — Was das Projekt ist

Ein Optimierer für den **MLB-Saisonspielplan**: 30 Teams, eine volle reguläre Saison
(~2.430 Spiele auf Tagesebene). Er soll den Plan nach **Reisedistanz** und weichen Faktoren
(Wetter, Stadtfeste, Stadion-Konflikte, TV-Fenster, Fairness, CO₂, Revenue) optimieren und
dabei **alle harten Liga-/CBA-Regeln** einhalten. Es gibt zwei Hauptpfade:

1. **Warm-Start / Travel-Optimierung** (Produktionspfad): nimmt einen realen, regelkonformen
   Plan als Start und verbessert ihn per Simulated Annealing.
2. **Green-field / from scratch**: erzeugt einen Plan komplett neu (CP-SAT/Gurobi,
   Branch-and-Price, Fenster-Dekomposition).

Zusätzlich: ein Disruption-Handler (Rainouts/Hurricanes), eine Pareto-Mehrziel-Exploration,
eine What-if-Engine, ein Compliance-Report, eine Operations-Suite (Hotels/Routing/Security)
und mehrere Dashboards.

---

## 2 — Repository-Landkarte (Stand des Reviews)

~51 Module in `src/` (~13.300 Zeilen), 35 Test-Dateien (~433 nicht-slow Tests), 18 Tools,
17 Datendateien, 62 Dokumente in `docs/`, dazu `regulations/`.

```
src/
  season.py              Datenmodell: Game / GameSeries / Season (Tagesebene)
  data_loader.py         Stammdaten (teams.json) laden + validieren
  loaders.py             MLB-Stats-API-JSON → Season (Team-ID-Mapping)
  datasources/           Adapter (local_file, sportsdata_io, base)
  timezones.py           DST-korrekte Zeitzonen-Offsets
  distance.py / travel.py  Haversine-Reise, Saison-Reisekennzahlen
  generator.py           CP-SAT-Generator (Struktur/Feasibility)
  generator_optimizer.py SA-Travel-Optimierer (Energie: km + Penalty-Terme; gegated)
  column_generation.py / colgen/   HAP / Column-Generation (OR-Tools)
  compliance.py          Compliance-Report: jede harte Regel ↔ Quelle + Messwert
  feasibility.py         Reise-Envelope-Feasibility (aus Realdaten kalibriert)
  player_fatigue.py      CBA-Fatigue-Metriken (away-days, games-no-off)
  start_times.py         Startzeit-Schicht (V(C)(6)-(9), gegated)   [neuer Block]
  schedule_rules.py      Strukturregeln V(C)(13)/(14)/(15)          [neuer Block]
  balanced_schedule.py   MLB-2023+-Matchup-Format (B3)              [neuer Block]
  greenfield_gurobi.py   Green-field TTP-MIP (Gurobi)               [neuer Block]
  branch_and_price.py    Dantzig-Wolfe / B&P, Event-Branching       [neuer Block]
  greenfield_decomp.py   Rolling-Horizon-Fenster-Dekomposition      [neuer Block]
  chronobiology.py       Jet-Lag-Index (konservativ, gegated)       [neuer Block]
  revenue.py / revenue_validation.py   Gate-Revenue-Modell + Validierung
  tv_slots.py            TV-Slot-Scoring
  pareto.py / pareto_types.py / profiles.py   Mehrziel-Pareto
  whatif.py / whatif_core/   What-if-Szenarien
  disruption*.py / repair_*.py   Disruption-Handler + Reparatur-Strategien
  ops_routing.py / ops_security.py / ops_hotels.py / ops_dossier.py   Ops-Suite
  holidays.py / event_conflicts.py / sustainability.py / fairness.py / explain.py
  config.py              .env-Loader (Secrets/Keys)
  legacy/                abgelöste Sprint-0-Module (nicht Produktionspfad)
tools/    CLI: backtest, validate_season, validate_revenue_model, greenfield_demo,
          measure_start_times, diagnose_e2_2025, generate_trip_dossier, api (FastAPI), …
data/     teams.json, mlb_schedule_2024/2025.json, appendix_c_travel_times.json,
          revenue_model.json, real_attendance_2024.json, tv_slots.json, local_events.json,
          team_hotels.json, city_ops_profiles.json, team_airports.json, holiday_pins.json, …
docs/     Sprint-Charters, Reviews, Handover-Dokumente, Entscheidungs-Records
regulations/  CBA Article V (verbatim), Appendix C, Mess-/Befund-Berichte
dashboard/    HTML/JS-Dashboards (Pareto, Ops, Index)
```

Einstieg in den Code: `src/season.py` (Datenmodell) → `src/main.py` (Pipeline/CLI) →
`tools/backtest.py` (Optimizer vs. realer Plan) → `src/compliance.py` (Regel-Check).

---

## 3 — Umgebung & alles selbst ausführen (RUNBOOK)

Eine vollständige Befehlsliste liegt in **`RUNBOOK.md`**. Kurzfassung:

```bash
# Abhängigkeiten
pip install pytest ortools==9.10.4067 numpy pandas geopy python-dateutil tzdata \
            hypothesis pyflakes --break-system-packages
# optional für den green-field Pfad:
pip install gurobipy --break-system-packages    # ohne Lizenz: größenlimitierte Tests

# Aus dem Projektroot, mit PYTHONPATH:
export PYTHONPATH="$(pwd)"; export PATH="$HOME/.local/bin:$PATH"

# Test-Suite (schnell):  -m "not slow"
python -m pytest -q -m "not slow"
# Einzelne Suiten:       python -m pytest -q tests/test_sprint_3_compliance.py
# Optimizer vs. real:    python -m tools.backtest --season 2024 --warm-start
# Compliance messen:     siehe RUNBOOK
# Green-field-Demos:     python -m tools.greenfield_demo --method monolithic|bnp|windowed …
```

Hinweise, die du verifizieren solltest (statt sie zu glauben):
- Es gibt **gegatete** Features (Default aus). Prüfe selbst, ob der Default-Pfad wirklich
  deterministisch/bit-identisch ist und ob die Gates sauber greifen.
- Einige langsame CP-SAT-Tests sind als `slow` markiert. Prüfe, was unter `not slow`
  **nicht** abgedeckt ist.
- `gurobipy` läuft hier unter einer **Restricted License** (größenlimitiert). Mit einem
  echten Schlüssel in `.env` (`GRB_WLSACCESSID/GRB_WLSSECRET/GRB_LICENSEID`) skalieren die
  green-field Solver auf größere Instanzen.

---

## 4 — Datengrundlage (faktischer Bestand — Provenienz selbst bewerten)

Die Datendateien tragen i. d. R. `_source`/`_note`/Rating-Felder. **Lies sie und urteile
selbst**, was belastbar echt, was kalibrierter Proxy und was illustrativer Seed ist, und
welche Konsequenzen das für die Ergebnis-Aussagen hat:

- `teams.json` — 30 Teams mit Koordinaten/Zeitzonen/Dach/Stadion.
- `mlb_schedule_2024.json`, `mlb_schedule_2025.json` — reale Saisonpläne (MLB-Stats-API).
  **Achte auf die Semantik dieser Daten** und was sie für datum-basierte Auswertungen bedeuten.
- `appendix_c_travel_times.json` — offizielle CBA-Reisezeiten (transkribiert).
- `revenue_model.json` + `real_attendance_2024.json` — Revenue-Modell + Validierungsreferenz.
- `tv_slots.json`, `local_events.json`, `team_hotels.json`, `city_ops_profiles.json`,
  `team_airports.json`, `holiday_pins.json` — gemischte Provenienz.

Frage dich bei **jeder** Datei: echt / Proxy / Seed? aktuell? vollständig? Wird sie für eine
**harte** Entscheidung oder nur fürs Scoring genutzt? Was passiert, wenn sie falsch ist?

---

## 5 — Nicht verhandelbare Konventionen (prüfe Einhaltung)

1. **Determinismus:** gleicher Seed → bit-identisches Ergebnis; neue Features gegated,
   Default off → Output unverändert. *Prüfe, ob das überall wirklich stimmt.*
2. **Jede harte Regel ↔ Quelle:** harte Constraints müssen auf einen verbindlichen Wortlaut
   zeigen (CBA Article V verbatim in `regulations/`). *Prüfe, ob „hart" jeweils berechtigt ist
   und ob etwas Hartes fehlt oder fälschlich weich/hart eingestuft wurde.*
3. **Daten-Ehrlichkeit:** echt vs. Proxy vs. Seed markiert. *Prüfe, ob Aussagen/Visuals
   diese Grenzen respektieren oder Proxys als Fakten verkaufen.*
4. **Messen statt behaupten:** jede Behauptung sollte gegen den realen 2024- UND 2025-Plan
   gemessen sein. *Prüfe, ob Messungen reproduzierbar sind und die Schlüsse tragen.*

---

## 6 — Wie sich das Projekt selbst dokumentiert (kritisch lesen)

`docs/` (Sprint-Charters, Reviews, Handover, Entscheidungs-Records) und `regulations/`
(CBA-Wortlaut + Mess-/Befundberichte) enthalten die **Selbsteinschätzung** des Projekts.
Nutze sie als Orientierung — aber behandle sie als **Behauptungen, nicht als Wahrheit**:
verifiziere am Code und durch eigene Läufe. Wenn Doku und Code auseinanderlaufen, ist genau
das ein Befund. Es ist ausdrücklich erwünscht, dass du Lücken findest, die in der Doku noch
**nicht** stehen.

---

## 7 — Vorschlag für Audit-Dimensionen (Fragen, keine Antworten)

Arbeite dich gern an diesen Achsen entlang — die Antworten sollst du selbst erarbeiten:

- **Korrektheit der harten Regeln:** Sind alle bindenden Article-V-Regeln modelliert *und*
  durchgesetzt? Gibt es Wege, sie still zu verletzen? Stimmen die Formeln mit dem Wortlaut?
- **Optimierer-Garantien:** Bewahrt jeder akzeptierte Schritt die Regeln? Was passiert an
  Saison-Rändern, am All-Star-Break, bei Doubleheadern, bei Relokationen?
- **Datenrealismus:** Halten die Ergebnis-Zahlen (km/CO₂/USD/Fatigue) einer Prüfung gegen
  unabhängige Quellen stand? Sind Proxys angemessen kalibriert und als solche kenntlich?
- **Determinismus & Reproduzierbarkeit:** Wirklich bit-identisch? Externe/Zeit-/Zufalls-
  Quellen im Kernpfad? Funktioniert alles offline?
- **Test-Abdeckung:** Was ist *nicht* getestet? Sind die Tests aussagekräftig oder
  tautologisch? Was verbergen die `slow`-/`skip`-Pfade?
- **Skalierbarkeit:** Was läuft real in akzeptabler Zeit auf voller Saison — und was nur auf
  Spielzeug-Instanzen? Wo sind die harten Tractability-Grenzen?
- **Produktionsreife:** Was fehlt noch konkret, bevor ein MLB-Scheduler das Tool benutzen
  könnte? Welche Annahmen würden in der Praxis brechen?

Liefere am Ende eine priorisierte, belegte Befundliste (Schweregrad, Reproduktion,
Vorschlag) — und sei dabei so ehrlich und unbeschönigt wie das Projekt selbst es einfordert.
