# Sprint-Plan — Aufarbeitung der Review-Findings

**Basis:** `docs/REVIEW_EXTERN.md` (2026-05-27)
**Ziel:** Alle Critical- und Major-Findings vor MLB-Übergabe schließen, Minor + Aufräumen danach.
**Geplant:** 6 Sprints (2.7 → 2.12), ~3–4 Wochen Gesamtaufwand.

---

## Reihenfolge — Begründung

Die Sprints sind **nicht** nach Severity sortiert, sondern nach **Abhängigkeit**. Wer C2 (TV-Slot) vor C1 (AC-2.1.8) fixt, muss danach alle TV-Score-Zahlen erneut prüfen, sobald die AC-Verifikation auf der neuen Definition läuft und das System eventuell andere Pläne produziert.

```
Sprint 2.7   ─→  Sprint 2.8   ─→  Sprint 2.9   ─→  Sprint 2.10  ─→  Sprint 2.11  ─→  Sprint 2.12
CBA-          Pipeline-          TV/Revenue-       What-if-          SA & DST          Cleanup
Definition    Konsolidierung     Realismus         Härtung           & Detail          & Polish
(Foundation)  (Klarheit)         (Stakeholder-     (UI-Vorbereitung) (Engine-          (Repo-
                                  Vertrauen)                          Korrektheit)      Hygiene)
```

**Warum diese Reihenfolge:**

1. **Sprint 2.7 zuerst** — weil C1 (falsche AC-Definition) die *Wahrheits-Grundlage* ist. Solange das System eine andere Größe misst als die CBA verlangt, ist jeder Test-Pass und jede Optimierungs-Aussage über AC-2.1.8 wertlos. Alle Folge-Sprints müssen ihre Behauptungen gegen die *korrigierte* Definition verifizieren.

2. **Sprint 2.8 als zweites** — weil drei parallele Pipelines (M10) jede einzelne nachfolgende Korrektur verdoppeln. Wer C2 in der neuen Pipeline fixt, muss entscheiden, ob er die alte mitfixt oder nicht. Erst Code-Klarheit, dann inhaltliche Fixes.

3. **Sprint 2.9 vor Sprint 2.10** — weil What-if-Fixes (M3/M4/M5) auf die ParetoBundle-Komponenten zugreifen. Wenn TV-Score und Revenue erst in 2.9 korrigiert werden, müssen What-if-Tests in 2.10 schon mit der korrekten Berechnung laufen.

4. **Sprint 2.11 vor 2.12** — die Engine-Korrektheits-Fixes (w_off_day, DST) können neue Pareto-Pläne produzieren. Erst dann ist sinnvoll, Demo-Skripte, Dashboard und Snapshots final zu polieren.

5. **Sprint 2.12 zuletzt** — Aufräumen ergibt nur Sinn, wenn der Code-Stand stabil ist.

---

# Sprint 2.7 — CBA-Definition-Fix (Foundation)

**Dauer-Schätzung:** 3–5 Arbeitstage
**Risiko:** Hoch — kann die ganze Optimierungs-Story verschieben.
**Behebt:** C1, C3, N1, N2, Test-Definitions-Bug aus `test_off_day_breaks_streak`

## Sprint-Goal

Das System misst und garantiert AC-2.1.8 unter der **korrekten CBA-Definition** ("days away from home", Off-Days in der Roadtrip zählen mit). Alle Tests und Berichte verwenden diese Definition.

## Vorarbeit (vor dem Sprint!)

- [ ] **AC-2.1.8-Definition mit echter MLB-Quelle abklären.** Das CBA-PDF, das aktuelle MoU, oder ein Telefonat mit MLB-Ops. **Wichtigste Frage:** Was ist eine "Roadtrip" formal? Inklusive Off-Days mittendrin? Inklusive Reise-Tag vor dem ersten Auswärtsspiel?
- [ ] Entscheidung dokumentieren in `docs/CBA_DEFINITIONS.md` mit Quelle, Datum, Ansprechpartner.

## Tasks

| # | Task | Datei(en) | Aufwand |
|---|---|---|---|
| 2.7.1 | Neue Definition implementieren | `src/player_fatigue.py` | 0.5d |
| 2.7.2 | Inkrementeller Streak-Tracker im SA an neue Definition anpassen | `src/generator_optimizer.py` (`_team_max_streaks`) | 1d |
| 2.7.3 | AC-2.1.8-Constraint in Column-Generation an neue Definition anpassen | `src/column_generation.py` (`pricing_subproblem`, Z. 301–313) | 1d |
| 2.7.4 | Tests umschreiben: `test_off_day_breaks_streak` invertieren; neue Tests für die Off-Day-Roadtrip-Fälle | `tests/test_fatigue_constraints.py` | 0.5d |
| 2.7.5 | Dokstring `_periodic_break_days` korrigieren, Default `max_gap=21` setzen, AC-2.1.8-Beweis komplett entfernen | `src/generator.py` | 0.25d |
| 2.7.6 | `GeneratorConfig`-Validierung: `Optional[Tuple]`, Pre-Check für `season_end < season_start` | `src/generator.py` | 0.25d |
| 2.7.7 | Full-Season-Run mit Seed 42 + 7 + 11 + 17 unter neuer Definition — empirische Verifikation, dass SA-Penalty λ=1M auch unter der schärferen Definition zu 0 Violations konvergiert | Notebook / Skript | 0.5–1d |
| 2.7.8 | Sprint-Review-Doc + Update `GESAMTBERICHT_FUER_REVIEW.md` (falscher Pigeonhole-Beweis raus, neuer rein) | `docs/` | 0.5d |

## Definition of Done

- [ ] `max_consecutive_away_days` zählt unter korrekter Definition (Off-Day in Roadtrip zählt mit).
- [ ] Reproduktions-Snippet aus dem Review (`Auswärts/Auswärts/Off/Auswärts/Auswärts`) liefert 5, nicht 2.
- [ ] Voller Generator-Lauf mit Seed 42 liefert weiterhin 0 AC-Violations unter neuer Definition. Falls nicht: SA-Parameter empirisch nachtunen (`travel_optimizer_iterations`, `start_temperature`).
- [ ] Mindestens 3 weitere Seeds (7, 11, 17) liefern ebenfalls 0 Violations.
- [ ] `tests/test_fatigue_constraints.py` testet die neue Definition; alter `test_off_day_breaks_streak` ist invertiert oder umbenannt.
- [ ] `docs/CBA_DEFINITIONS.md` existiert mit Quelle.

## Risiken

- **Risiko A:** Unter der schärferen Definition kann der bestehende SA-Penalty nicht mehr alle Violations entfernen. Empirisch wahrscheinlich, weil die echte Definition strikter ist als die jetzt implementierte. → Mitigation: Iteration-Budget hochsetzen (2M statt 700k), oder Pre-Repair-Schritt einbauen.
- **Risiko B:** Die Column-Generation-Pipeline produziert dann Length-1-Violations in Series-Matching, die unter alter Definition gerade noch toleriert wurden. → Akzeptieren und dokumentieren, oder eine zweite Iteration der Phase-B-Matching dranhängen.
- **Risiko C:** Falls MLB die Definition nicht eindeutig liefern kann: beide Größen im Bundle führen (`max_consecutive_away_days`, `max_days_away_from_home`) und im UI klar trennen.

---

# Sprint 2.8 — Pipeline-Konsolidierung

**Dauer-Schätzung:** 2–3 Arbeitstage
**Risiko:** Mittel — kein algorithmischer Inhalt, aber viel Verschieben.
**Behebt:** M10, M11, M12, A1, A2, A3, A4, A6

## Sprint-Goal

Es gibt genau **eine** Schedule-Pipeline im Hauptpfad. `python -m src.main` ruft sie auf. Alles andere ist entweder gelöscht oder unter `src/legacy/` mit klarem README.

## Tasks

| # | Task | Datei(en) | Aufwand |
|---|---|---|---|
| 2.8.1 | Pipeline-Entscheidung dokumentieren: ist `generator.py` der Hauptpfad? Oder die Column-Generation aus Sprint 2.3a? | `docs/ARCHITECTURE_DECISION.md` | 0.5d |
| 2.8.2 | `main.py` umstellen auf den gewählten Hauptpfad (aktuell ruft es `optimizer.optimize` aus dem alten System) | `src/main.py` | 0.5d |
| 2.8.3 | Alten Code unter `src/legacy/` verschieben: `schedule_generator.py`, `optimizer.py`, `scoring.py`, `constraints.py`, `validation.py`, `soft_factors.py`, `ai_explainer.py`, `metrics.py`. README mit "deprecated, see X" hinzufügen | `src/legacy/` | 0.5d |
| 2.8.4 | `tests/test_end_to_end.py` umschreiben oder löschen | `tests/` | 0.5d |
| 2.8.5 | `TradeoffProfile` rausnehmen oder in `legacy/profiles.py` verschieben | `src/profiles.py` | 0.25d |
| 2.8.6 | Dead Code aus `generator.py` entfernen: `_repair_fatigue_violations`, `_greedy_starts_with_fatigue`, toter `if series_starts is None:`-Branch | `src/generator.py` | 0.25d |
| 2.8.7 | `two_phase_repair.py` löschen (wird nirgends importiert) | `src/` | 0.1d |
| 2.8.8 | `dashboard/build_dashboard.py` vs. `build_real_dashboard.py` — eine wählen, andere entfernen | `dashboard/` | 0.25d |
| 2.8.9 | `.gitignore` ergänzen: `.coverage*`, `pytest-cache-files-*`, `.pytest_cache/`, `.hypothesis/` | repo root | 0.1d |

## Definition of Done

- [ ] `git grep -l "from .schedule_generator\|from src.schedule_generator"` liefert nur Treffer in `src/legacy/` oder `tests/legacy/`.
- [ ] `python -m src.main --season 2026 --optimize` läuft und benutzt die aktuelle Pipeline (CP-SAT + SA).
- [ ] Test-Suite läuft ohne den Alt-Pfad. Anzahl der Tests kann sinken; das ist OK.
- [ ] Keine "dead function"-Warnungen mehr (z.B. `vulture src/` schweigt für die genannten Funktionen).
- [ ] Repo enthält keine `.coverage`-Artefakte mehr.

## Risiken

- **Risiko A:** Der alte Pfad ist eventuell noch in `dashboard/index.html` referenziert. → vor dem Verschieben grep.
- **Risiko B:** Sprint-1-Präsentation (`MLB_Optimizer_Sprint1_Review.pptx`) zeigt den alten Pfad. → akzeptieren als historisches Dokument, in Sprint 2.12 mit neuer PPTX überschreiben.

---

# Sprint 2.9 — TV/Revenue-Modell-Realismus

**Dauer-Schätzung:** 3–5 Arbeitstage
**Risiko:** Mittel-Hoch — neue Datenquelle (Game-Start-Time aus Stats API).
**Behebt:** C2, M9, N3, N4, N12

## Sprint-Goal

`tv_slot_score` und `revenue_usd` reflektieren die tatsächliche TV-/Gate-Realität: Sunday Night Baseball wird modelliert, Saturday-Day vs. -Night wird unterschieden, Division-Rival-Bonus stapelt mit Marquee-Faktor, Doubleheader-Typen sind differenziert.

## Vorarbeit

- [ ] Klären, ob Game-Start-Time aus der MLB Stats API verlässlich für 2026 verfügbar ist. Falls nein (Plan-Phase ohne fixe Times): Übergangs-Heuristik definieren.

## Tasks

| # | Task | Datei(en) | Aufwand |
|---|---|---|---|
| 2.9.1 | Daypart-Entscheidung als Optimierungs-Variable im SA (statt Heuristik): pro Heimspiel-Tag `daypart[g] ∈ {day, night}`, eingeschränkt durch Wochentag-Verfügbarkeit der Slots | `src/tv_slots.py`, `src/generator_optimizer.py` | 1.5d |
| 2.9.2 | Alternative (falls 2.9.1 zu groß): probabilistische Slot-Gewichtung — pro Wochentag eine Mix-Wahrscheinlichkeit (z.B. Samstag 70% night, 30% day) und `slot_value` als gewichteten Erwartungswert berechnen | `src/tv_slots.py` | 0.5d |
| 2.9.3 | Revenue-Modell: Division-Rival-Bonus multiplikativ stapeln statt verdrängen | `src/revenue.py` (Z. 108–115) | 0.25d |
| 2.9.4 | Doubleheader-Typ aus Stats API oder per Heuristik bestimmen statt immer "split_admission" | `src/revenue.py` (`_doubleheader_type`) | 0.5d |
| 2.9.5 | `_is_night_game` mit echter Start-Time aus Stats API oder konsistenter mit 2.9.1/2.9.2 | `src/revenue.py` | 0.25d |
| 2.9.6 | `revenue_model.json`: Note ergänzen, dass 2024-Kalibrierung für 2026 verwendet wird; idealerweise Update auf 2025-Daten falls verfügbar | `data/revenue_model.json` | 0.25d |
| 2.9.7 | Validator erweitern: prüfen, dass NBC Sunday Night Slots tatsächlich angefahren werden | `tools/validate_revenue_model.py` | 0.5d |
| 2.9.8 | Tests: neue Unit-Tests für Sunday-Night, Saturday-Day, BOS@NYY (Rival + Marquee) | `tests/test_tv_slots.py` (neu), `tests/test_revenue.py` | 1d |

## Definition of Done

- [ ] Score-Verteilung über die Saison zeigt, dass Sunday-Night-Slots tatsächlich vergeben werden (mind. 27 erwartet, da NBC Sunday Night ~27 Spiele pro Saison hat).
- [ ] BOS@NYY-Spiel an Wochenende bekommt `marquee_mult × rival_bonus`, nicht nur eines von beiden.
- [ ] Reproduktions-Snippet aus C2 produziert nicht mehr `_daypart_for_weekday(6) == 'day'` als monolithische Antwort.
- [ ] `season_revenue` vs. Sportico-Liga-Total bleibt im Toleranzfenster (`< 1%`) — eichen, falls verschoben.

## Risiken

- **Risiko A:** Pre-Season-Pläne haben keine fixen Start-Times (die werden später zugeteilt). → 2.9.1 ist möglicherweise architektonisch besser als 2.9.2.
- **Risiko B:** Wenn Sunday Night Baseball als Variable optimiert wird, kann die Pareto-Front aufgespannter werden — `n_interior_points=4` reicht eventuell nicht mehr.

---

# Sprint 2.10 — What-if-Härtung

**Dauer-Schätzung:** 2–3 Arbeitstage
**Risiko:** Niedrig — gut isolierbar.
**Behebt:** M3, M4, M5, N6

## Sprint-Goal

`whatif_force_series`, `whatif_blackout` und `repair_local` liefern entweder einen **garantiert validen** Plan oder eine klare Fehlermeldung — keine stillen Double-Bookings, keine verschwindenden Spiele, keine ungewollten All-Star-Break-Belegungen.

## Tasks

| # | Task | Datei(en) | Aufwand |
|---|---|---|---|
| 2.10.1 | `_find_free_slot`: All-Star-Break-Check ergänzen | `src/whatif.py` (Z. 229–279) | 0.25d |
| 2.10.2 | `whatif_force_series` "neue Serie einfügen"-Branch: vor Insert Konflikte mit `home`/`away` an forced_days prüfen, kollidierende Spiele wie in Schritt 3 verschieben | `src/whatif.py` (Z. 450–462) | 0.5d |
| 2.10.3 | `repair_local`: unreschedulable Spiele entweder behalten (mit Flag) oder Dokstring an Code anpassen + alle Aufrufer hinweisen, dass `len(new_season.games) < len(original.games)` möglich ist | `src/repair_local.py` | 0.5d |
| 2.10.4 | `analyze_team_impact.travel_delta_km`: durch `compute_team_travel(team)` ersetzen statt 500km-Proxy | `src/whatif.py` (Z. 786–802) | 0.25d |
| 2.10.5 | Post-Whatif-Validator: nach jedem Whatif-Ergebnis `compute_pareto_bundle(validate_hard_constraints=True)` aufrufen und Warnung im `WhatIfResult.warnings` ablegen, falls `constraint_violations > 0` | `src/whatif.py` | 0.25d |
| 2.10.6 | Tests: Double-Booking-Szenario explizit testen, All-Star-Break-Test, repair_local-Game-Count-Test | `tests/test_whatif.py`, `tests/test_repair_local.py` | 0.5–1d |

## Definition of Done

- [ ] `whatif_force_series(season, ..., forced_start=date(2026, 7, 4))` mit einer Saison, in der NYY am 4.7. schon NYY@LAA hat, produziert entweder einen validen Plan (LAA verschoben) oder gibt `feasible=False` mit klarer Warnung.
- [ ] `whatif_blackout` legt keine Serie in den All-Star-Break.
- [ ] `repair_local` mit Hurricane-Milton-Szenario: entweder Game-Count bleibt konstant, oder die Reduktion ist explizit im Report ausgewiesen.

## Risiken

- **Risiko A:** Wenn `repair_local` unreschedulable Spiele zukünftig behält, müssen Downstream-Module damit umgehen (sie haben aktuell aus Versehen schon damit zu tun). → grep durch Aufrufer.

---

# Sprint 2.11 — SA-Korrektheit + DST

**Dauer-Schätzung:** 3–4 Arbeitstage
**Risiko:** Mittel — SA-Performance-Tuning kann nervig werden.
**Behebt:** M1, M2, M6, M7, M8, N5, N7, N8, N9, N10

## Sprint-Goal

Das SA optimiert **genau die Energiefunktion**, die das ParetoBundle bewertet. Timezone-Hops sind DST-korrekt. Inkrementelle Updates sind sauber und performant.

## Tasks

| # | Task | Datei(en) | Aufwand |
|---|---|---|---|
| 2.11.1 | `w_off_day` im SA aktivieren: per-Team-Spieltag-Dichte inkrementell führen oder alle K Iterationen voll neu berechnen | `src/generator_optimizer.py` (`_energy_from_state`) | 1d |
| 2.11.2 | DST-aware Timezone-Offsets: `zoneinfo.ZoneInfo(tz).utcoffset(game_date)` pro Reise-Segment statt statischem Lookup | `src/distance.py`, `src/travel.py` | 0.5d |
| 2.11.3 | `Team.timezone` im Loader gegen DST-fähige Timezone-Liste validieren (raise im Loader, nicht erst zur Laufzeit) | `src/data_loader.py` | 0.25d |
| 2.11.4 | Pareto-Frontier-Edge-Case: wenn `len(non_dominated) == 0`, klare Diagnose + Least-Bad-Fallback | `src/pareto.py` | 0.5d |
| 2.11.5 | Pareto-Anker-Diversifikation: pro Profil einen leicht abweichenden CP-SAT-Seed verwenden | `src/pareto.py` | 0.25d |
| 2.11.6 | `_no_team_overlap` von O(N) auf O(log N): sortierte Intervall-Struktur pro Team | `src/generator_optimizer.py` | 1d |
| 2.11.7 | `_entry_revenue_val(e)` Caching innerhalb von `_apply_shift_update` / `_revert_shift` | `src/generator_optimizer.py` | 0.25d |
| 2.11.8 | `_random_profile`: Dirichlet-Sampling statt Uniform-Simplex | `src/pareto.py` | 0.25d |
| 2.11.9 | Empirische Verifikation: Seed-42-Lauf vorher vs. nachher (km, revenue, fatigue, walltime) — Regression-Test | Notebook | 0.5d |

## Definition of Done

- [ ] SA-Energie ≡ `profile.compute_energy(bundle)` (modulo numerische Toleranz `1e-6`).
- [ ] Phoenix-Reise im August: korrekte DST-Hops gegen `zoneinfo`-Ground-Truth.
- [ ] Walltime nach Sprint nicht > 30% schlechter als vorher (M7-Optimierung sollte das kompensieren).
- [ ] Pareto-Frontier ist auch bei einem ungünstigen Seed nicht leer.

## Risiken

- **Risiko A:** DST-Korrektur ändert Reise-km in der Größenordnung. Bisherige "1.955M km"-Benchmark verschiebt sich. → in Sprint-Review neue Baseline-Zahlen festschreiben.
- **Risiko B:** w_off_day im SA macht die Energiefunktion teurer; eventuell muss Iteration-Budget hoch.

---

# Sprint 2.12 — Cleanup + Production-Polish

**Dauer-Schätzung:** 2–3 Arbeitstage
**Risiko:** Niedrig.
**Behebt:** Restliche Minor, A5, Doku-Updates, OAK-Daten

## Sprint-Goal

Repo ist in einem Zustand, den du einer externen Person übergeben könntest, ohne dass ihre erste Stunde aus "was ist denn das hier?" besteht.

## Tasks

| # | Task | Datei(en) | Aufwand |
|---|---|---|---|
| 2.12.1 | `data/teams.json` — OAK-Daten für 2026 bestätigen (Sacramento ja/nein) | `data/teams.json` | 0.25d |
| 2.12.2 | Stakeholder-PPTX neu: aktuelle Architektur, Pareto-Front, What-if, AC-Garantien (mit korrigierter Definition aus 2.7), MLB-Stats-API-Integration aus 2.9 | `docs/MLB_Optimizer_Sprint2_Review.pptx` | 1–1.5d |
| 2.12.3 | `GESAMTBERICHT_FUER_REVIEW.md` von Grund auf neu — der aktuelle ist mit C1/C2/C3-Falschaussagen durchsetzt | `docs/` | 0.5d |
| 2.12.4 | Property-Based-Tests via `hypothesis` (steht im `requirements.txt`, wird aber nicht benutzt): Generator-Outputs gegen invariante Eigenschaften (Game-Count, Heim/Auswärts-Balance, Range-Constraints) | `tests/test_invariants.py` (neu) | 1d |
| 2.12.5 | README aktualisieren — die Quickstart-Beschreibung beschreibt noch die Sprint-1-Pipeline | `README.md` | 0.5d |
| 2.12.6 | Optional: REST-API-Skelett (FastAPI) — `tools/api.py` wie im Handover 2.7 als Option B vorgeschlagen | `tools/` | 1–2d |

## Definition of Done

- [ ] PPTX enthält keine Sprint-1-Folien mehr ohne explizites "historisch"-Label.
- [ ] Property-Tests laufen in CI mit mindestens 200 Hypothesis-Examples pro Test.
- [ ] README beschreibt die echte Pipeline.

---

# Sprint-Übersicht

| Sprint | Dauer | Severity-Coverage | Blockt |
|---|---|---|---|
| 2.7 — CBA-Definition | 3–5d | C1, C3 + 2 Minor | alle folgenden Sprints inhaltlich |
| 2.8 — Pipeline-Konsolidierung | 2–3d | M10–M12, 5× Aufräumen | 2.9–2.12 organisatorisch |
| 2.9 — TV/Revenue | 3–5d | C2 + 4 Minor | 2.10 (What-if liest die Bundles) |
| 2.10 — What-if-Härtung | 2–3d | M3, M4, M5, N6 | — |
| 2.11 — SA + DST | 3–4d | M1, M2, M6–M8 + 4 Minor | — |
| 2.12 — Cleanup | 2–3d | Rest | — |

**Gesamt:** 15–23 Arbeitstage. Bei einem 5-Tage-Sprint-Rhythmus also **3–5 Wochen**.

---

# Was *nach* den Sprints passieren sollte

Diese Punkte sind nicht im Plan, weil sie über das Review hinausgehen — aber sie sind die natürliche Fortsetzung:

1. **CI/CD-Pipeline.** Aktuell laufen Tests manuell. Mindestens `pytest` + `mypy` + `vulture` auf jedem PR.
2. **Stakeholder-Workshop.** Vor der MLB-Übergabe: die Pareto-Front mit echten MLB-Ops durchgehen. Eventuell zeigt sich, dass eine Dimension fehlt oder doppelt gewertet wird.
3. **Performance-Profiling.** Sprint 2.11 enthält M8 (Overlap-Check), aber ein echter Profiler-Lauf (z.B. `py-spy`) würde die heißen Pfade präziser zeigen.
4. **Daten-Refresh-Routine.** `revenue_model.json` muss jährlich nach Liga-Schluss neu kalibriert werden. Ein Skript dafür gehört dauerhaft ins Repo.

---

# Anhang — Mapping Finding → Sprint

| Finding | Sprint | Task |
|---|---|---|
| C1 (AC-2.1.8-Def) | 2.7 | 2.7.1–2.7.4 |
| C2 (TV-Slot-Heuristik) | 2.9 | 2.9.1 oder 2.9.2 |
| C3 (Pigeonhole-Doku) | 2.7 | 2.7.5 |
| M1 (w_off_day) | 2.11 | 2.11.1 |
| M2 (DST) | 2.11 | 2.11.2 |
| M3 (whatif double-booking) | 2.10 | 2.10.2 |
| M4 (whatif All-Star-Break) | 2.10 | 2.10.1 |
| M5 (repair_local löscht Spiele) | 2.10 | 2.10.3 |
| M6 (Pareto leer) | 2.11 | 2.11.4 |
| M7 (Pareto-Anker-Diversität) | 2.11 | 2.11.5 |
| M8 (Overlap-Check O(N)) | 2.11 | 2.11.6 |
| M9 (Division-Rival-Stack) | 2.9 | 2.9.3 |
| M10 (drei Pipelines) | 2.8 | 2.8.1–2.8.4 |
| M11 (Dead Code Generator) | 2.8 | 2.8.6 |
| M12 (toter Branch) | 2.8 | 2.8.6 |
| N1, N2 | 2.7 | 2.7.6 |
| N3, N4 | 2.9 | 2.9.4, 2.9.5 |
| N5 | 2.11 | 2.11.8 |
| N6 | 2.10 | 2.10.4 |
| N7 | 2.11 | 2.11.7 |
| N8 | 2.11 | (Inline in 2.11.1) |
| N9 | 2.11 | (Inline in 2.11.1) |
| N10 | 2.11 | 2.11.3 |
| N11 | 2.12 | 2.12.1 |
| N12 | 2.9 | 2.9.6 |
| A1–A6 | 2.8 | 2.8.3, 2.8.5, 2.8.7–2.8.9 |
