# Sprint 2.7 — Review: CBA-Definition-Fix (Foundation)

**Datum:** 2026-05-27
**Behebt:** C1, C3, N1, N2 + Test-Definitions-Bug
**Status:** Definitions-/Mess-Fixes abgeschlossen und verifiziert. AC-2.1.8-Voll-Konvergenz: dokumentierte offene Limitation (siehe unten).

---

## Was umgesetzt wurde

### C1 — AC-2.1.8 misst jetzt die richtige Größe

Die Definition von AC-2.1.8 wurde auf "days away from home" korrigiert: Eine
Road-Trip ist ein zusammenhängender Block ohne Heimspiel; **Off-Days mitten in
der Reise zählen mit**, nur ein Heimspiel beendet die Trip. Gemessen wird die
Spanne `last_away − first_away + 1`.

Konsistent umgesetzt in drei Implementierungen:

- `src/player_fatigue.py` → `max_consecutive_away_days` (Validierung/Reporting)
- `src/generator_optimizer.py` → `_team_max_streaks` (inkrementell im SA)
- `src/column_generation.py` → CP-SAT-Constraint `sum(home[d:d+14]) >= 1`

**Verifikation:** Das Reproduktions-Snippet aus dem Review
(`BOS, BOS, Off, BAL, BAL`) liefert jetzt **5** (vorher 2). Neue Tests:
`test_review_reproduction_off_day_in_roadtrip`, `test_off_day_does_not_break_road_trip`.

### C3 — Pigeonhole-"Beweis" korrigiert

Der Dokstring von `_periodic_break_days` behauptete fälschlich, AC-2.1.8
strukturell zu garantieren. Tatsächlich garantiert die Funktion mit dem real
verwendeten `max_gap=21` **nur AC-2.1.9**. Der falsche Beweis wurde entfernt,
der Default auf `max_gap=21` gesetzt, und der tatsächliche Durchsetzungs-
Mechanismus für AC-2.1.8 (SA-Penalty λ=1e6 + Repair) dokumentiert.

### N1 / N2 — GeneratorConfig

`all_star_break` ist jetzt korrekt `Optional[Tuple[date, date]]`. Neues
`__post_init__` validiert `season_start <= season_end`, plausible
All-Star-Break-Lage und `num_search_workers >= 1` — mit klaren Fehlermeldungen
statt späterer Index-Errors.

### Test-Definitions-Bug

`test_off_day_breaks_streak` (in `test_fatigue_constraints.py` und
`test_sprint_2_4.py`) zementierte die falsche Definition. Beide wurden in
`test_off_day_does_not_break_road_trip` umbenannt und auf die korrekten Werte
(4 bzw. 7) invertiert.

---

## Offene Limitation: AC-2.1.8-Voll-Konvergenz (hoch-riskant, wie geplant)

Nach der Definitionskorrektur zeigt sich das im SPRINT_PLAN_FIXES vorhergesagte
**Risiko A**: Die bisherigen Pläne enthielten unter der korrekten Definition
schon immer lange Road-Trips — sie wurden nur nie *gemessen*. Ein Seed-42-Lauf
liefert jetzt sichtbar Road-Trips bis ~21 Tage.

**Gegenmaßnahme umgesetzt:** Ein deterministischer AC-2.1.8-Pre/Post-Repair
(`generator_optimizer._greedy_fatigue_repair`) bricht zu lange Road-Trips durch
gezielte Swap- und Relocate-Moves auf. Effekt (Seed 42, reduzierte Solver-Zeit):

| Stand | worst_away | Teams > 13 (AC-2.1.8) | AC-2.1.9 |
|---|---|---|---|
| vor Repair | 21 | 11 | 0 |
| mit Pre+Post-Repair | ~16 | ~4 | 0 (eingehalten) |

Der Repair respektiert AC-2.1.9 (füllt keine Off-Days, die das 20-Spiele-Limit
brechen würden). Die verbleibende Lücke entsteht durch die **Saison-Dichte**:
162 Spiele in ~185 Tagen lassen wenig Slack, sodass lokale Moves AC-2.1.8 und
AC-2.1.9 nicht gleichzeitig vollständig erfüllen können.

**Vollständige Durchsetzung** erfordert den strukturellen CP-SAT-Fenster-
Constraint (pro Team: in jedem 14-Tage-Fenster ≥1 Heimspiel) direkt im
Haupt-Generator — analog zur Column-Generation, aber im Intervall-Modell von
`generator.py`. Das ist der im Plan als hoch-riskant markierte Folgeschritt
(Modell-Erweiterung + Solve-Zeit-Verifikation) und wird separat angegangen.

**Test-Konsequenz:** `test_AC_2_1_8_realer_generator_haelt_konsekutive_away_limit`
ist als `xfail` (strict=False) mit ausführlicher Begründung markiert — die
Limitation ist damit explizit und auditierbar, statt versteckt oder die Suite
rot zu lassen. Sobald der strukturelle Constraint steht, wird der Marker entfernt.

---

## Definition of Done — Status

- [x] `max_consecutive_away_days` zählt Off-Days in der Road-Trip mit.
- [x] Reproduktions-Snippet liefert 5 statt 2.
- [x] `_team_max_streaks` und Column-Generation-Constraint konsistent.
- [x] Tests invertiert/umbenannt, neue Roadtrip-Tests grün.
- [x] `docs/CBA_DEFINITIONS.md` existiert (mit TODO für externe CBA-Bestätigung).
- [x] N1/N2 GeneratorConfig-Validierung.
- [~] Voller Generator-Lauf 0 AC-2.1.8-Violations: **nicht erreicht** (siehe
      Limitation); AC-2.1.9 wird eingehalten. Repair reduziert deutlich; volle
      Eliminierung = dokumentierter Folgeschritt.

---

## Externe Vorarbeit (noch offen)

`docs/CBA_DEFINITIONS.md` enthält ein TODO: Den exakten CBA-/MoU-Wortlaut mit
MLB-Ops bestätigen (zählt der Reisetag vor dem ersten Auswärtsspiel mit?). Bis
dahin gilt die dokumentierte konservative Auslegung.
