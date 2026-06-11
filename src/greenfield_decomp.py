"""Sprint 5.4+ — Runden-/Fenster-Dekomposition (Rolling-Horizon) für green-field.

Skaliert den green-field Solver, indem nicht der ganze Horizont auf einmal gelöst wird,
sondern **Zeitfenster** nacheinander mit Gurobi re-optimiert werden (Large-Neighborhood-
Search über die Zeit): pro Fenster werden die in diesem Fenster liegenden Spiele optimal
auf die Fenstertage verteilt — mit **Reise-Kontinuität** (Eintritts-Stadt jedes Teams =
Endstadt aus dem vorherigen Fenster). Sweep über die Fenster (mehrere Pässe möglich).

Im Gegensatz zur per-Team-Dekomposition (`branch_and_price`) löst jedes Fenster ein
**team-gekoppeltes** Sub-MIP → es kann die Konsistenz-Spalten gemeinsam erzeugen und
verbessert dadurch nachweislich über den Bootstrap, bleibt aber klein/tractabel.

Lizenz: wie `greenfield_gurobi` automatisch aus `.env`. Reduzierte Instanzen laufen unter
der Restricted License; mit Jonas' Key skalieren längere Horizonte/ mehr Teams.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from .distance import haversine_km  # type: ignore
from .greenfield_gurobi import GreenfieldInstance, GurobiUnavailable, _make_env
from .branch_and_price import greedy_feasible_schedule, decompose_to_columns


@dataclass
class WindowResult:
    status: str
    objective_km: float
    games: List[Tuple[int, str, str]] = field(default_factory=list)
    bootstrap_km: float = 0.0
    n_windows: int = 0
    passes: int = 0
    runtime_s: float = 0.0


def _team_location_before(schedule: List[Tuple[int, str, str]], team: str,
                          day0: int, home: str) -> str:
    """Stadt (host) des letzten Spiels von ``team`` VOR ``day0``; sonst Heimstadt."""
    last_day, last_loc = -1, home
    for (d, h, v) in schedule:
        if d < day0 and (h == team or v == team) and d > last_day:
            last_day, last_loc = d, h
    return last_loc


def _total_cost(schedule, inst, tbi) -> float:
    cols = decompose_to_columns(schedule, inst, tbi)
    return sum(c.cost_km for c in cols.values())


def solve_greenfield_windowed(
    inst: GreenfieldInstance, *, window_days: int = 7, passes: int = 2,
    window_time_s: float = 10.0, verbose: bool = False,
) -> WindowResult:
    """Rolling-Horizon-Re-Optimierung eines feasiblen green-field Plans.

    Startet vom greedy Bootstrap, hält die Zuordnung *welches Spiel in welchem
    Fenster* fest (garantiert Feasibilität/Quoten) und re-optimiert je Fenster die
    **Tagewahl + Reise** team-gekoppelt mit Gurobi, inkl. Eintritts-Kontinuität.
    """
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except Exception as exc:  # pragma: no cover
        raise GurobiUnavailable(f"gurobipy nicht verfügbar: {exc}") from exc
    import time
    t0 = time.time()
    ids = inst.ids
    tbi = {t.id: t for t in inst.teams}

    schedule = greedy_feasible_schedule(inst)
    bootstrap_km = _total_cost(schedule, inst, tbi)

    # Fenster-Grenzen
    bounds = list(range(0, inst.n_days, window_days)) + [inst.n_days]
    windows = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]

    env = _make_env(verbose=verbose)
    try:
        for _pass in range(passes):
            for (w0, w1) in windows:
                wdays = list(range(w0, w1))
                # Spiele dieses Fensters (Zuordnung fix aus aktuellem Plan)
                wgames = [(h, v) for (d, h, v) in schedule if w0 <= d < w1]
                if not wgames:
                    continue
                teams_here = sorted({t for (h, v) in wgames for t in (h, v)})
                entry = {t: _team_location_before(schedule, t, w0, t) for t in teams_here}
                is_last = (w1 == inst.n_days)

                m = gp.Model(f"win_{w0}_{w1}", env=env)
                m.Params.OutputFlag = 0
                m.Params.TimeLimit = window_time_s
                G = list(range(len(wgames)))
                x = m.addVars([(g, d) for g in G for d in wdays], vtype=GRB.BINARY)
                for g in G:
                    m.addConstr(gp.quicksum(x[g, d] for d in wdays) == 1)
                # ≤1 Spiel/Team/Tag im Fenster
                for t in teams_here:
                    for d in wdays:
                        inv = [g for g in G if t in wgames[g]]
                        m.addConstr(gp.quicksum(x[g, d] for g in inv) <= 1)
                # Stadt je Team/Tag (+ virtueller Eintrittstag w0-1 = entry-Stadt)
                cities = ids
                days_ext = [w0 - 1] + wdays
                p = m.addVars([(t, c, d) for t in teams_here for c in cities
                               for d in days_ext], vtype=GRB.BINARY)
                for t in teams_here:
                    # Eintritts-Anker
                    for c in cities:
                        m.addConstr(p[t, c, w0 - 1] == (1 if c == entry[t] else 0))
                    for d in wdays:
                        m.addConstr(gp.quicksum(p[t, c, d] for c in cities) == 1)
                        # Spielort bestimmt Stadt
                        for g in G:
                            if t not in wgames[g]:
                                continue
                            host = wgames[g][0]
                            m.addConstr(p[t, host, d] >= x[g, d])
                        # Persistenz an Off-Days im Fenster
                        play_td = gp.quicksum(x[g, d] for g in G if t in wgames[g])
                        for c in cities:
                            m.addConstr(p[t, c, d] - p[t, c, d - 1] <= play_td)
                            m.addConstr(p[t, c, d - 1] - p[t, c, d] <= play_td)
                # Reise (inkl. Eintritts-Leg w0-1→w0); im letzten Fenster Heim-Rückleg
                trav = []
                for t in teams_here:
                    for d in wdays:
                        for c in cities:
                            for c2 in cities:
                                if c == c2:
                                    continue
                                y = m.addVar(lb=0.0, ub=1.0)
                                m.addConstr(y <= p[t, c, d - 1])
                                m.addConstr(y <= p[t, c2, d])
                                m.addConstr(y >= p[t, c, d - 1] + p[t, c2, d] - 1)
                                trav.append(haversine_km(tbi[c].lat, tbi[c].lon,
                                                         tbi[c2].lat, tbi[c2].lon) * y)
                    if is_last:
                        for c in cities:
                            if c != t:
                                trav.append(haversine_km(tbi[c].lat, tbi[c].lon,
                                                         tbi[t].lat, tbi[t].lon)
                                            * p[t, c, wdays[-1]])
                m.setObjective(gp.quicksum(trav), GRB.MINIMIZE)
                m.optimize()
                if m.SolCount > 0:
                    new_assign = {}
                    for g in G:
                        for d in wdays:
                            if x[g, d].X > 0.5:
                                new_assign[g] = d
                    candidate = [(d, h, v) for (d, h, v) in schedule
                                 if not (w0 <= d < w1)]
                    for g in G:
                        h, v = wgames[g]
                        candidate.append((new_assign[g], h, v))
                    candidate.sort()
                    # Nur übernehmen, wenn die GLOBALE Reise nicht steigt (das Fenster-
                    # Ziel ignoriert den Exit-Leg → greedy könnte sonst leicht
                    # verschlechtern). Garantiert: Ergebnis ≤ Bootstrap (monoton).
                    if _total_cost(candidate, inst, tbi) <= _total_cost(schedule, inst, tbi) + 1e-9:
                        schedule = candidate
                m.dispose()
        env.dispose()
    except gp.GurobiError as exc:
        try:
            env.dispose()
        except Exception:
            pass
        raise GurobiUnavailable(
            f"Gurobi (Fenster-Dekomposition) scheiterte (evtl. Restricted-Größenlimit; "
            f"akademische Lizenz in .env): {exc}") from exc

    final_km = _total_cost(schedule, inst, tbi)
    return WindowResult(status="OK", objective_km=final_km, games=sorted(schedule),
                        bootstrap_km=bootstrap_km, n_windows=len(windows),
                        passes=passes, runtime_s=time.time() - t0)
