"""Off-Day-Slot-basierte Constraints (Sprint 2.3 Task #15; aktiviert in Sprint A-2).

Erzwingt im CP-SAT-Modell:

- **AC-2.1.9 — Off-Day-Frequenz:** max 20 Spieltage in jedem 21-Tage-Fenster
  pro Team (= mindestens 1 Off-Day pro 21-Tage-Fenster).

- **Max konsekutive Play-Days:** maximal `max_gap - 1` Spieltage hintereinander
  ohne Off-Day. Unter der **alten** AC-2.1.8-Definition (Off-Day bricht den
  Auswaerts-Streak) liefert das mit `max_gap=14` auch "max 13 konsekutive
  Auswaerts-Tage". Unter der **korrigierten** Definition aus Sprint 2.7
  ("days away from home" mit Off-Days *in* der Road-Trip) gilt dieser Schluss
  NICHT — eine Road-Trip kann ueber Off-Days hinweg laufen. AC-2.1.8 wird
  daher weiterhin ueber SA-Penalty + Repair in `generator_optimizer` gehandhabt
  (siehe `docs/CBA_DEFINITIONS.md`).

## Modellierungs-Idee

Per-Day-Boolean-Variablen (1 Bool pro Team x Tag) machen das CP-SAT-Modell zu
gross (~150k Reified-Constraints, Solver findet in 30s keine Loesung). Statt
dessen modellieren wir explizite Off-Day-IntervalVars pro Team plus eine
**Order- und Distanz-Constraint**:

1. Pro Team K = total_days - n_games Off-Day-Slots, jeder mit Length=1.
2. Slots werden in `AddNoOverlap` mit den Series-Intervals aufgenommen
   → Off-Days koennen nicht mit Spielen kollidieren.
3. **Order-Constraint:** off[k].start < off[k+1].start fuer alle k.
4. **Distanz-Constraint:** off[k+1].start - off[k].start <= MAX_GAP.
5. **Rand-Constraints:** off[0].start <= MAX_GAP-1; off[K-1].start >= total_days - MAX_GAP.

Mit MAX_GAP=14 folgt:
- Max Tage zwischen zwei Off-Days = 14 → max 13 Spieltage dazwischen
- Max konsekutive Auswaertstage = max 13 (alle Spieltage zwischen Off-Days
  koennten Auswaerts sein) → **AC-2.1.8 erfuellt**
- Max Spieltage in 21-Tage-Fenster = 21 - mind. 1 Off-Day ≤ 20 → **AC-2.1.9 erfuellt**

## Mathematischer Beweis fuer AC-2.1.9 (max 20 Spiele in 21 Tagen)

Sei [w, w+20] ein 21-Tage-Fenster. Annahme: alle 21 Tage sind Spieltage
(Verletzung). Dann gibt es keinen Off-Day in diesem Fenster. Aber wir
haben K Off-Day-Slots geordnet mit Max-Distanz 14. Es muss einen Slot
k geben mit off[k].start < w (oder k=-1, dann off[0].start >= 0). Wenn
off[k+1].start <= off[k].start + 14 < w + 14, dann liegt off[k+1] im
Fenster [off[k].start, w+14]. Da w+14 < w+21, liegt off[k+1] im
Fenster [w, w+20] iff off[k+1].start ∈ [w, w+20]. Das ist eine
einfache Pigeonhole-Argument: Off-Day-Slots ueberdecken die Saison
mit Luecken ≤ 14. Jedes 21-Tage-Fenster enthaelt mindestens einen
Off-Day (weil 14 < 21).

## Performance

Off-Day-Slot-Variante mit Order-Constraint:
- ~720 IntVars (24 × 30 Teams)
- ~720 Distanz-Constraints
- ~720 Order-Constraints (kann ZU IntervalVars erzeugen)
- Erwartete Solver-Zeit: deutlich unter 30 s
"""
from __future__ import annotations

from typing import Dict, List, Set

from ortools.sat.python import cp_model


# Konfiguration
# MAX_GAP = 14 erzwingt AC-2.1.8 (max 13 konsek. Auswaertstage) UND AC-2.1.9
# (max 20 Spieltage in 21-Tage-Fenster) gleichzeitig.
DEFAULT_MAX_OFFDAY_GAP = 14

# Hard-Limits aus AC-2.1.8 / AC-2.1.9 (zur Validierung im Test)
AC_2_1_8_LIMIT_DAYS = 13
AC_2_1_9_WINDOW_DAYS = 21
AC_2_1_9_MAX_GAMES = 20


def add_offday_slots(
    model: cp_model.CpModel,
    series_intervals_by_team: Dict[str, List[cp_model.IntervalVar]],
    games_per_team: Dict[str, int],
    total_days: int,
    break_days: Set[int],
    max_gap: int = DEFAULT_MAX_OFFDAY_GAP,
) -> Dict[str, List[cp_model.IntervalVar]]:
    """Fuegt pro Team K Off-Day-Slots (Length=1) hinzu und erzwingt:

    - AddNoOverlap ueber (Spiele + Off-Days)
    - Order + Max-Gap zwischen aufeinanderfolgenden Off-Days

    Returns:
        team_id -> Liste der Off-Day-IntervalVars (kann leer sein).
    """
    off_intervals_by_team: Dict[str, List[cp_model.IntervalVar]] = {}

    for team_id, team_series in series_intervals_by_team.items():
        n_games = games_per_team.get(team_id, 0)
        K = total_days - n_games

        off_intervals: List[cp_model.IntervalVar] = []
        off_starts: List[cp_model.IntVar] = []

        if K > 0:
            # Sprint A-2 Optimierung: NewIntVar(0, total_days-1) statt
            # Domain.FromValues - kontinuierliche Domains sind im CP-SAT-Solver
            # deutlich schneller zu propagieren als explizit aufgezaehlte. ASB-
            # Tage werden ueber separate model.Add(off != break_day)-Constraints
            # ausgeschlossen.
            for k in range(K):
                off_start = model.NewIntVar(
                    0, total_days - 1, f"off_{team_id}_{k}"
                )
                # Break-Days (ASB) ausschliessen
                for bd in break_days:
                    model.Add(off_start != bd)
                off_iv = model.NewFixedSizeIntervalVar(
                    off_start, 1, f"off_iv_{team_id}_{k}"
                )
                off_intervals.append(off_iv)
                off_starts.append(off_start)

            # Order-Constraint: off[k].start < off[k+1].start
            for k in range(K - 1):
                model.Add(off_starts[k + 1] >= off_starts[k] + 1)

            # Max-Gap-Constraint: off[k+1].start - off[k].start <= max_gap
            for k in range(K - 1):
                model.Add(off_starts[k + 1] - off_starts[k] <= max_gap)

            # Rand: erster Off-Day frueh genug, letzter Off-Day spaet genug
            # off[0].start <= max_gap - 1  (mind. 1 Off-Day in [0, max_gap-1])
            # off[K-1].start >= total_days - max_gap  (mind. 1 Off-Day spaet)
            model.Add(off_starts[0] <= max_gap - 1)
            model.Add(off_starts[K - 1] >= total_days - max_gap)

        off_intervals_by_team[team_id] = off_intervals

        # AddNoOverlap mit Spielen + Off-Days
        all_intervals = list(team_series) + off_intervals
        model.AddNoOverlap(all_intervals)

    return off_intervals_by_team


def expected_max_offday_gap_after_constraint(max_gap: int) -> int:
    """Die maximale Luecke zwischen zwei aufeinanderfolgenden Off-Days
    nach Anwendung der Constraints. Identisch mit `max_gap`."""
    return max_gap
