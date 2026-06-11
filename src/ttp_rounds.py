"""Sprint 5.4+ — Runden-/Pattern-basierte green-field Formulierung (TTP, kompakt).

Der nächste Forschungsschritt nach der per-Team-Dekomposition: statt den vollen
**Tages**-Horizont zu indizieren, wird **runden-indexiert** modelliert — jede Mannschaft
spielt **genau einmal pro Runde** (klassische Traveling-Tournament-Struktur). Das ist die
natürliche Spalten-/Pattern-Sicht (eine Runde = ein perfektes Matching der Teams) und
**deutlich kompakter**: Rundenzahl R = games_per_pair·(n−1) ≪ Anzahl Kalendertage. Dadurch
löst dieses Modell Instanzen, an denen das tag-indizierte monolithische MIP
(`greenfield_gurobi`) am Restricted-Größenlimit scheitert.

Pattern-Bezug: die Heim/Auswärts-Folge eines Teams über die Runden IST sein
Home-Away-Pattern (HAP); das Modell wählt simultan Pattern + Gegnerzuordnung + Reise.
Roadtrip-Länge (konsekutive Auswärtsrunden) ist direkt als Constraint ausdrückbar
(strukturelles AC-2.1.8-Analogon).

Danach: `rounds_to_days()` bildet die Runden auf Kalendertage ab (mit Off-Day-Abstand),
sodass das Ergebnis in die übrige Pipeline (Season/Compliance/SA) passt.

Lizenz: automatisch aus `.env` (s. `greenfield_gurobi`). n muss gerade sein
(perfektes Matching je Runde). Reduzierte n laufen unter der Restricted License.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .data_loader import Team
from .distance import haversine_km  # type: ignore
from .greenfield_gurobi import GurobiUnavailable, _make_env, directed_quota_from_matchup
from .balanced_schedule import round_robin_matrix


@dataclass
class RoundResult:
    status: str
    objective_km: Optional[float]
    rounds: List[Tuple[int, str, str]] = field(default_factory=list)  # (round, host, visitor)
    n_rounds: int = 0
    runtime_s: float = 0.0
    gap: Optional[float] = None


def solve_ttp_rounds(
    teams: List[Team], games_per_pair: int = 2, *,
    max_road_trip: int = 3, time_limit_s: float = 30.0, mip_gap: float = 0.0,
    verbose: bool = False,
) -> RoundResult:
    """Kompakte runden-indizierte TTP-Lösung (Reise-km-minimal).

    Variablen: h[i,j,r] (i hostet j in Runde r), p[i,c,r] (Stadt von i in Runde r).
    Constraints: jede Mannschaft genau 1 Spiel/Runde; Matchup-Quoten; Stadt =
    Gastgeber; ≤``max_road_trip`` konsekutive Auswärtsrunden. Ziel: Σ Reise (Runden-
    Transitionen + Heim-Anker), linearisiert (McCormick).
    """
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except Exception as exc:  # pragma: no cover
        raise GurobiUnavailable(f"gurobipy nicht verfügbar: {exc}") from exc
    import time
    t0 = time.time()
    ids = [t.id for t in teams]
    n = len(ids)
    if n % 2 != 0:
        raise ValueError("Runden-Formulierung braucht eine GERADE Teamzahl "
                         "(perfektes Matching je Runde).")
    tbi = {t.id: t for t in teams}
    hq = directed_quota_from_matchup(round_robin_matrix(ids, games_per_pair))
    R = games_per_pair * (n - 1)
    rounds = list(range(R))
    dist = {(a, b): haversine_km(tbi[a].lat, tbi[a].lon, tbi[b].lat, tbi[b].lon)
            for a in ids for b in ids if a != b}

    try:
        env = _make_env(verbose=verbose)
        m = gp.Model("ttp_rounds", env=env)
        m.Params.TimeLimit = time_limit_s
        m.Params.MIPGap = mip_gap
        if not verbose:
            m.Params.OutputFlag = 0

        h = m.addVars([(i, j, r) for i in ids for j in ids if i != j for r in rounds],
                      vtype=GRB.BINARY, name="h")
        p = m.addVars([(i, c, r) for i in ids for c in ids for r in rounds],
                      vtype=GRB.BINARY, name="p")

        # (1) jede Mannschaft genau 1 Spiel je Runde
        for i in ids:
            for r in rounds:
                m.addConstr(gp.quicksum(h[i, j, r] for j in ids if j != i)
                            + gp.quicksum(h[j, i, r] for j in ids if j != i) == 1)
        # (2) Matchup-Quoten (gerichtet, Heim)
        for i in ids:
            for j in ids:
                if i != j:
                    m.addConstr(gp.quicksum(h[i, j, r] for r in rounds) == hq[i][j])
        # (3) Stadt = Gastgeber
        for i in ids:
            for r in rounds:
                m.addConstr(gp.quicksum(p[i, c, r] for c in ids) == 1)
                m.addConstr(p[i, i, r] == gp.quicksum(h[i, j, r] for j in ids if j != i))
                for k in ids:
                    if k != i:
                        m.addConstr(p[i, k, r] == h[k, i, r])
        # (4) ≤max_road_trip konsekutive Auswärtsrunden (away = 1 - p[i,i,r])
        L = max_road_trip
        if L < R:
            for i in ids:
                for r0 in range(R - L):
                    m.addConstr(gp.quicksum(1 - p[i, i, r0 + k] for k in range(L + 1)) <= L)
        # (5) Reise (Runden-Transitionen + Heim-Anker), McCormick
        trav = []
        for i in ids:
            for r in rounds[1:]:
                for c in ids:
                    for c2 in ids:
                        if c == c2:
                            continue
                        y = m.addVar(lb=0.0, ub=1.0)
                        m.addConstr(y <= p[i, c, r - 1])
                        m.addConstr(y <= p[i, c2, r])
                        m.addConstr(y >= p[i, c, r - 1] + p[i, c2, r] - 1)
                        trav.append(dist[(c, c2)] * y)
            for c in ids:
                if c != i:
                    trav.append(dist[(i, c)] * p[i, c, rounds[0]])
                    trav.append(dist[(c, i)] * p[i, c, rounds[-1]])
        m.setObjective(gp.quicksum(trav), GRB.MINIMIZE)
        m.optimize()

        smap = {GRB.OPTIMAL: "OPTIMAL", GRB.TIME_LIMIT: "TIME_LIMIT",
                GRB.INFEASIBLE: "INFEASIBLE"}
        res = RoundResult(status=smap.get(m.Status, str(m.Status)),
                          objective_km=None, n_rounds=R, runtime_s=time.time() - t0)
        if m.SolCount > 0:
            res.objective_km = m.ObjVal
            try:
                res.gap = m.MIPGap
            except Exception:
                res.gap = None
            for i in ids:
                for j in ids:
                    if i != j:
                        for r in rounds:
                            if h[i, j, r].X > 0.5:
                                res.rounds.append((r, i, j))
            res.rounds.sort()
        m.dispose()
        env.dispose()
        return res
    except gp.GurobiError as exc:
        raise GurobiUnavailable(
            f"Gurobi (Runden-TTP) scheiterte (evtl. Restricted-Größenlimit; "
            f"akademische Lizenz in .env): {exc}") from exc


def rounds_to_days(round_games: List[Tuple[int, str, str]],
                   day_gap: int = 1, start_day: int = 0) -> List[Tuple[int, str, str]]:
    """Bildet Runden auf Kalendertage ab: Runde r → Tag start_day + r·day_gap
    (day_gap>1 fügt Off-Days zwischen den Runden ein)."""
    return sorted((start_day + r * day_gap, h, v) for (r, h, v) in round_games)
