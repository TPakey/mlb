"""Sprint 5.4 — Green-field Schedule-Solver mit Gurobi (Branch-and-Bound/-Price-Pfad).

Erzeugt einen Spielplan **from scratch** (nicht Warm-Start): weist jedem geforderten
Matchup einen Spieltag zu, hält die harten Struktur-/CBA-Regeln ein und minimiert die
**reale Reisedistanz** (Travelling-Tournament-Formulierung, Distanz linearisiert über
ein Stadt-Persistenz-Modell).

**Lizenz — „nur Key reinpasten":** Der Solver liest die Gurobi-Lizenz automatisch aus
`.env` (`src/config.py`):
- Web License Service (WLS, akademisch): `GRB_WLSACCESSID`, `GRB_WLSSECRET`, `GRB_LICENSEID`.
- ODER `gurobi.lic` (Named-User) via `GRB_LICENSE_FILE` bzw. Default-Pfad.
Ohne Lizenz läuft die **Restricted License** (größenlimitiert) → kleine Instanzen lösen
sofort; die volle 30-Team-Saison braucht die akademische Lizenz (Größenlimit + TTP-Härte).
Nichts am Code ändern — Jonas trägt die drei WLS-Werte in `.env` ein, fertig.

**Ehrliche Einordnung:** Das direkte MIP löst reduzierte Instanzen (wenige Teams)
optimal. Die volle Saison ist TTP-hart (APX-hart, vgl. Q10); die akademische Lizenz hebt
das Größenlimit, der Tractability-Pfad für 30 Teams ist die Spalten-Generierung /
Branch-and-Price (Dekomposition; HAP-Gerüst in `src/colgen`). Dieses Modul liefert den
korrekten, getesteten green-field Kern + das vollständige Lizenz-Plumbing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from .data_loader import Team
from .distance import haversine_km  # type: ignore
from . import config


class GurobiUnavailable(RuntimeError):
    """gurobipy nicht installiert oder Lizenz/Größenlimit verhindert das Lösen."""


# ====================================================================
# Lizenz-Status & Environment
# ====================================================================

def gurobi_status() -> dict:
    """Diagnose: ist gurobipy da, welche Lizenz, voll oder restricted?"""
    import importlib.util
    if importlib.util.find_spec("gurobipy") is None:  # pragma: no cover
        return {"available": False, "message": "gurobipy nicht installiert"}
    wls = config.get_gurobi_wls()
    licfile = config.get_gurobi_license_file()
    try:
        env = _make_env(verbose=False)
        env.dispose()
    except Exception as exc:
        return {"available": True, "licensed": False,
                "message": f"Env-Start fehlgeschlagen: {exc}"}
    source = "WLS (.env)" if wls else ("gurobi.lic (GRB_LICENSE_FILE)" if licfile
                                       else "Default/Restricted")
    return {"available": True, "licensed": True, "license_source": source,
            "message": f"Gurobi einsatzbereit über: {source}"}


def _make_env(verbose: bool = False):
    """Baut ein Gurobi-Env. Nutzt WLS-Credentials aus .env, sonst Default
    (Default findet eine gurobi.lic automatisch; sonst Restricted License)."""
    import gurobipy as gp
    wls = config.get_gurobi_wls()
    if wls:
        env = gp.Env(empty=True)
        env.setParam("WLSACCESSID", wls["WLSACCESSID"])
        env.setParam("WLSSECRET", wls["WLSSECRET"])
        env.setParam("LICENSEID", wls["LICENSEID"])
        if not verbose:
            env.setParam("OutputFlag", 0)
        env.start()
        return env
    env = gp.Env(empty=True)
    if not verbose:
        env.setParam("OutputFlag", 0)
    env.start()
    return env


# ====================================================================
# Instanz-Definition
# ====================================================================

@dataclass(frozen=True)
class GreenfieldInstance:
    """Reduzierte green-field Instanz.

    ``teams``: Team-Stammdaten (Koordinaten für Reise). ``home_quota[i][j]`` =
    Anzahl Spiele, die i gegen j ZUHAUSE austrägt (gerichtet). ``n_days`` = Horizont.
    """
    teams: List[Team]
    home_quota: Dict[str, Dict[str, int]]
    n_days: int
    max_consecutive: int = 20          # V(C)(12)

    @property
    def ids(self) -> List[str]:
        return [t.id for t in self.teams]


def round_robin_instance(teams: List[Team], games_per_pair: int,
                         n_days: int, max_consecutive: int = 20) -> GreenfieldInstance:
    """Symmetrische Round-Robin-Instanz: jedes Paar spielt ``games_per_pair`` Spiele,
    Heimrecht gleichmäßig (i hostet die Hälfte, j die andere). Für Tests/Solver-Smoke.
    """
    ids = [t.id for t in teams]
    hq: Dict[str, Dict[str, int]] = {a: {b: 0 for b in ids if b != a} for a in ids}
    for a, b in combinations(ids, 2):
        ha = games_per_pair // 2
        hb = games_per_pair - ha
        hq[a][b] = ha
        hq[b][a] = hb
    return GreenfieldInstance(teams=teams, home_quota=hq, n_days=n_days,
                              max_consecutive=max_consecutive)


# ====================================================================
# Ergebnis
# ====================================================================

@dataclass
class GreenfieldResult:
    status: str
    objective_km: Optional[float]
    games: List[Tuple[int, str, str]] = field(default_factory=list)  # (day, home, away)
    runtime_s: float = 0.0
    gap: Optional[float] = None


# ====================================================================
# MIP (TTP-Formulierung, Distanz über Stadt-Persistenz linearisiert)
# ====================================================================

def solve_greenfield(inst: GreenfieldInstance, *, time_limit_s: float = 30.0,
                     mip_gap: float = 0.0, verbose: bool = False) -> GreenfieldResult:
    """Löst die green-field Instanz mit Gurobi.

    Variablen:
      h[i,j,d] ∈ {0,1}  — i hostet j an Tag d.
      p[i,c,d] ∈ {0,1}  — Team i ist an Tag d in Stadt c (1 Stadt/Tag, persistiert
                          an Off-Days = bleibt am letzten Ort).
    Constraints: Matchup-Quoten; ≤1 Spiel/Team/Tag; Stadt-Konsistenz; Persistenz;
      ≤max_consecutive konsekutive Spieltage. Ziel: Σ Reisedistanz (linearisiert).
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
    D = list(range(inst.n_days))
    dist = {(a, b): haversine_km(tbi[a].lat, tbi[a].lon, tbi[b].lat, tbi[b].lon)
            for a in ids for b in ids if a != b}

    try:
        env = _make_env(verbose=verbose)
        m = gp.Model("greenfield", env=env)
        m.Params.TimeLimit = time_limit_s
        m.Params.MIPGap = mip_gap
        if not verbose:
            m.Params.OutputFlag = 0

        # h[i,j,d]
        h = m.addVars([(i, j, d) for i in ids for j in ids if i != j for d in D],
                      vtype=GRB.BINARY, name="h")
        # p[i,c,d] — Stadt c von Team i an Tag d
        p = m.addVars([(i, c, d) for i in ids for c in ids for d in D],
                      vtype=GRB.BINARY, name="p")

        # (1) Matchup-Quoten (gerichtet, Heim)
        for i in ids:
            for j in ids:
                if i == j:
                    continue
                m.addConstr(gp.quicksum(h[i, j, d] for d in D) == inst.home_quota[i][j])

        # (2) ≤1 Spiel je Team/Tag
        for i in ids:
            for d in D:
                m.addConstr(
                    gp.quicksum(h[i, j, d] for j in ids if j != i)
                    + gp.quicksum(h[j, i, d] for j in ids if j != i) <= 1)

        # (3) Stadt-Konsistenz: genau eine Stadt/Tag; spielt i an Tag d, ist die Stadt
        #     determiniert (Heim=eigene Stadt; Auswärts=Stadt des Gastgebers).
        for i in ids:
            for d in D:
                m.addConstr(gp.quicksum(p[i, c, d] for c in ids) == 1)
                # Heim: hostet i jemanden → p[i,i,d]=1
                for j in ids:
                    if j == i:
                        continue
                    m.addConstr(p[i, i, d] >= h[i, j, d])
                    # Auswärts bei j → p[i,j,d]=1
                    m.addConstr(p[i, j, d] >= h[j, i, d])

        # play[i,d] = spielt Team i an Tag d?
        play = {(i, d): (gp.quicksum(h[i, j, d] for j in ids if j != i)
                         + gp.quicksum(h[j, i, d] for j in ids if j != i))
                for i in ids for d in D}

        # (4) ≤max_consecutive konsekutive Spieltage (V(C)(12))
        K = inst.max_consecutive
        if K < inst.n_days:
            for i in ids:
                for d0 in range(inst.n_days - K):
                    m.addConstr(gp.quicksum(play[(i, d0 + k)] for k in range(K + 1)) <= K)

        # (4b) Stadt-Persistenz an Off-Days: spielt i an Tag d NICHT, bleibt die Stadt
        #      wie am Vortag → echte Reise-km (kein „Teleport" gratis an Off-Days).
        for i in ids:
            for d in D[1:]:
                for c in ids:
                    m.addConstr(p[i, c, d] - p[i, c, d - 1] <= play[(i, d)])
                    m.addConstr(p[i, c, d - 1] - p[i, c, d] <= play[(i, d)])

        # (5) Reise-Linearisierung: y[i,c,c',d] = p[i,c,d-1] * p[i,c',d]
        trav_terms = []
        y = {}
        for i in ids:
            for d in D[1:]:
                for c in ids:
                    for c2 in ids:
                        if c == c2:
                            continue
                        yv = m.addVar(vtype=GRB.CONTINUOUS, lb=0.0, ub=1.0,
                                      name=f"y_{i}_{c}_{c2}_{d}")
                        y[(i, c, c2, d)] = yv
                        m.addConstr(yv <= p[i, c, d - 1])
                        m.addConstr(yv <= p[i, c2, d])
                        m.addConstr(yv >= p[i, c, d - 1] + p[i, c2, d] - 1)
                        trav_terms.append(dist[(c, c2)] * yv)

        # (5b) Heim-Anker: Heim → Stadt an Tag 0, und letzte Stadt → Heim.
        for i in ids:
            for c in ids:
                if c != i:
                    trav_terms.append(dist[(i, c)] * p[i, c, D[0]])
                    trav_terms.append(dist[(c, i)] * p[i, c, D[-1]])

        m.setObjective(gp.quicksum(trav_terms), GRB.MINIMIZE)
        m.optimize()

        status_map = {GRB.OPTIMAL: "OPTIMAL", GRB.TIME_LIMIT: "TIME_LIMIT",
                      GRB.INFEASIBLE: "INFEASIBLE", GRB.SUBOPTIMAL: "SUBOPTIMAL"}
        status = status_map.get(m.Status, str(m.Status))
        result = GreenfieldResult(status=status, objective_km=None,
                                  runtime_s=time.time() - t0)
        if m.SolCount > 0:
            result.objective_km = m.ObjVal
            try:
                result.gap = m.MIPGap
            except Exception:
                result.gap = None
            for i in ids:
                for j in ids:
                    if i == j:
                        continue
                    for d in D:
                        if h[i, j, d].X > 0.5:
                            result.games.append((d, i, j))
            result.games.sort()
        m.dispose()
        env.dispose()
        return result
    except gp.GurobiError as exc:
        # Restricted-License-Größenlimit o. ä. — klar melden
        raise GurobiUnavailable(
            f"Gurobi konnte das Modell nicht lösen (evtl. Restricted-License-"
            f"Größenlimit; für große Instanzen die akademische Lizenz in .env "
            f"eintragen): {exc}") from exc


def directed_quota_from_matchup(
    matchup: Dict[str, Dict[str, int]],
) -> Dict[str, Dict[str, int]]:
    """Teilt eine symmetrische Matchup-Matrix (Gesamtspiele/Paar) gerichtet in
    Heim-Quoten auf (i hostet die Hälfte, deterministisch nach ID-Reihenfolge)."""
    ids = sorted(matchup)
    hq: Dict[str, Dict[str, int]] = {a: {} for a in ids}
    for a in ids:
        for b in matchup[a]:
            if a < b:
                tot = matchup[a][b]
                hq[a][b] = tot // 2
                hq.setdefault(b, {})[a] = tot - tot // 2
    return hq
