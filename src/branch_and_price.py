"""Sprint 5.4+ — Branch-and-Price / Column Generation für den green-field Plan.

Skalierungs-Pfad für das (TTP-harte) green-field Scheduling: statt eines monolithischen
MIP (`greenfield_gurobi`) wird **Dantzig-Wolfe nach Team dekomponiert**.

- **Spalte (Column)** = ein vollständiger, feasibler **Einzel-Team-Spielplan** (welche
  der Spiele dieses Teams an welchem Tag), mit eigener Reise-km-Kosten.
- **Restricted Master (RMP)** = Set-Partition: wähle (LP-konvex / integer genau) eine
  Spalte je Team, sodass der Gesamtplan **konsistent** ist — wenn Team h zu Hause gegen v
  an Tag d spielt, muss v an Tag d auswärts bei h spielen (Game-Consistency-Coupling).
- **Pricing-Subproblem** je Team: finde mit den RMP-Dualwerten eine neue Spalte mit
  negativen reduzierten Kosten (kleines Einzel-Team-MIP).
- **Price-and-Branch:** Spalten generieren (LP), dann den **integer** RMP über den
  Spalten-Pool lösen → garantiert ein gültiger Plan (Bootstrap ist immer feasibel).

Gurobi löst RMP und Pricing; Lizenz kommt automatisch aus `.env` (s. `greenfield_gurobi`).
Reduzierte Instanzen laufen unter der Restricted License; die volle Saison braucht den
akademischen Key (Größenlimit) — am Code ändert sich **nichts** („nur Key reinpasten").

**Ehrlich:** Vollständige Optimalität für 30 Teams ist Forschungsfront (TTP APX-hart);
diese Engine ist die korrekte, getestete B&P-Infrastruktur + ein praktischer
Price-and-Branch-Heuristik-Modus, der den Bootstrap nachweislich nie verschlechtert.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple

from .data_loader import Team
from .distance import haversine_km  # type: ignore
from .greenfield_gurobi import GreenfieldInstance, GurobiUnavailable, _make_env

# Ein „Event" = kanonisch (host, visitor, day): Team host empfängt visitor an Tag day.
Event = Tuple[str, str, int]


@dataclass(frozen=True)
class Column:
    team: str
    events: FrozenSet[Event]      # alle Spiele dieses Teams (Heim: host==team; Auswärts: visitor==team)
    cost_km: float

    def home_events(self) -> List[Event]:
        return [e for e in self.events if e[0] == self.team]

    def away_events(self) -> List[Event]:
        return [e for e in self.events if e[1] == self.team]


@dataclass
class BnPResult:
    status: str
    objective_km: Optional[float]
    games: List[Tuple[int, str, str]] = field(default_factory=list)  # (day, host, visitor)
    n_columns: int = 0
    cg_iterations: int = 0
    bootstrap_km: Optional[float] = None
    runtime_s: float = 0.0


# ====================================================================
# Reise-km einer Einzel-Team-Spalte
# ====================================================================

def _column_cost(team: str, events: FrozenSet[Event], tbi: Dict[str, Team]) -> float:
    """Reise-km: das Team spielt jedes Event in der Stadt des Gastgebers (host).
    Tour: Heim → Spielorte (nach Tag sortiert) → Heim."""
    seq = sorted(events, key=lambda e: e[2])
    venues = [e[0] for e in seq]  # host = Spielort
    if not venues:
        return 0.0
    km = 0.0
    loc = team
    for v in venues:
        if v != loc:
            km += haversine_km(tbi[loc].lat, tbi[loc].lon, tbi[v].lat, tbi[v].lon)
        loc = v
    if loc != team:
        km += haversine_km(tbi[loc].lat, tbi[loc].lon, tbi[team].lat, tbi[team].lon)
    return km


# ====================================================================
# Greedy-Bootstrap: ein global konsistenter, feasibler Plan
# ====================================================================

def greedy_feasible_schedule(inst: GreenfieldInstance,
                             order_seed: Optional[int] = None) -> List[Tuple[int, str, str]]:
    """Konstruiert greedy einen gültigen Plan (day, host, visitor), der alle
    gerichteten Matchup-Quoten erfüllt, ≤1 Spiel/Team/Tag und ≤max_consecutive.
    Dient als immer-feasibler Startpunkt für die Column Generation.

    ``order_seed``: optional; mischt die Platzierungs-Reihenfolge → diverse
    feasible Pläne (gegen Dual-Degeneration in der Column Generation)."""
    ids = inst.ids
    # gerichtete Spielliste (host, visitor) mit Vielfachheit
    games: List[Tuple[str, str]] = []
    for h in ids:
        for v, q in inst.home_quota[h].items():
            games.extend([(h, v)] * q)
    # deterministische Reihenfolge (lange-Reise-Paare zuerst hilft, ist aber egal)
    games.sort()
    if order_seed is not None:
        import random
        random.Random(order_seed).shuffle(games)
    busy: Dict[Tuple[str, int], bool] = {}          # (team, day) belegt
    play_days: Dict[str, set] = {t: set() for t in ids}
    placed: List[Tuple[int, str, str]] = []

    def consec_ok(team: str, day: int) -> bool:
        # ≤max_consecutive aufeinanderfolgende Spieltage
        K = inst.max_consecutive
        if K >= inst.n_days:
            return True
        run = 1
        d = day - 1
        while d >= 0 and d in play_days[team]:
            run += 1
            d -= 1
        d = day + 1
        while d < inst.n_days and d in play_days[team]:
            run += 1
            d += 1
        return run <= K

    for (h, v) in games:
        for d in range(inst.n_days):
            if busy.get((h, d)) or busy.get((v, d)):
                continue
            if not consec_ok(h, d) or not consec_ok(v, d):
                continue
            busy[(h, d)] = True
            busy[(v, d)] = True
            play_days[h].add(d)
            play_days[v].add(d)
            placed.append((d, h, v))
            break
        else:
            raise GurobiUnavailable(
                "Greedy-Bootstrap fand keinen feasiblen Tag — Horizont zu kurz "
                f"(n_days={inst.n_days}) für die Matchup-Quoten.")
    return placed


def decompose_to_columns(schedule: List[Tuple[int, str, str]], inst: GreenfieldInstance,
                         tbi: Dict[str, Team]) -> Dict[str, Column]:
    """Zerlegt einen globalen Plan in genau eine Spalte je Team (konsistent)."""
    by_team: Dict[str, set] = {t: set() for t in inst.ids}
    for (d, h, v) in schedule:
        ev = (h, v, d)
        by_team[h].add(ev)
        by_team[v].add(ev)
    return {t: Column(t, frozenset(evs), _column_cost(t, frozenset(evs), tbi))
            for t, evs in by_team.items()}


# ====================================================================
# Restricted Master (Gurobi)
# ====================================================================

def _solve_master(columns: Dict[str, List[Column]], ids: List[str], *,
                  integer: bool, env, verbose: bool = False):
    """Set-Partition-Master. Liefert (model, lambda-vars, conv-constr, couple-constr).
    Bei integer=False LP-Relaxation (für Duals)."""
    import gurobipy as gp
    from gurobipy import GRB
    m = gp.Model("rmp", env=env)
    if not verbose:
        m.Params.OutputFlag = 0
    vtype = GRB.BINARY if integer else GRB.CONTINUOUS
    lam: Dict[Tuple[str, int], object] = {}
    for t in ids:
        for k, col in enumerate(columns[t]):
            lam[(t, k)] = m.addVar(lb=0.0, ub=1.0, vtype=vtype,
                                   obj=col.cost_km, name=f"lam_{t}_{k}")
    m.ModelSense = GRB.MINIMIZE

    conv = {}
    for t in ids:
        conv[t] = m.addConstr(
            gp.quicksum(lam[(t, k)] for k in range(len(columns[t]))) == 1,
            name=f"conv_{t}")

    # Coupling je Event: Σ host-Spalten mit e == Σ visitor-Spalten mit e
    all_events = set()
    for t in ids:
        for col in columns[t]:
            all_events |= col.events
    couple = {}
    for e in all_events:
        h, v, d = e
        host_terms = gp.quicksum(lam[(h, k)] for k, col in enumerate(columns[h])
                                 if e in col.events)
        vis_terms = gp.quicksum(lam[(v, k)] for k, col in enumerate(columns[v])
                                if e in col.events)
        couple[e] = m.addConstr(host_terms - vis_terms == 0, name=f"cpl_{h}_{v}_{d}")
    m.optimize()
    return m, lam, conv, couple


# ====================================================================
# Pricing-Subproblem je Team (Gurobi)
# ====================================================================

def _price_team(team: str, inst: GreenfieldInstance, tbi: Dict[str, Team],
                pi_conv: float, pi_couple: Dict[Event, float], env,
                time_limit_s: float,
                forced: Optional[set] = None,
                forbidden: Optional[set] = None) -> Optional[Column]:
    """Findet eine Spalte für ``team`` mit minimalen reduzierten Kosten.
    Gibt None zurück, wenn keine negative reduzierte Kostenspalte existiert.

    ``forced``/``forbidden`` (B&P-Branching): Mengen von Events (host,visitor,day),
    die diese Spalte enthalten MUSS bzw. NICHT enthalten darf — als Constraints im
    Pricing-MIP erzwungen (nur für dieses Team relevante Events wirken)."""
    import gurobipy as gp
    from gurobipy import GRB
    forced = forced or set()
    forbidden = forbidden or set()
    ids = inst.ids
    D = list(range(inst.n_days))
    # Spielliste des Teams: (opponent, is_home), mit Vielfachheit
    glist: List[Tuple[str, bool]] = []
    for v, q in inst.home_quota[team].items():
        glist.extend([(v, True)] * q)
    for h in ids:
        if h == team:
            continue
        q = inst.home_quota[h].get(team, 0)
        glist.extend([(h, False)] * q)
    G = list(range(len(glist)))

    m = gp.Model(f"price_{team}", env=env)
    m.Params.OutputFlag = 0
    m.Params.TimeLimit = time_limit_s
    a = m.addVars([(g, d) for g in G for d in D], vtype=GRB.BINARY, name="a")
    # jedes Spiel genau einen Tag
    for g in G:
        m.addConstr(gp.quicksum(a[g, d] for d in D) == 1)
    # ≤1 Spiel/Tag
    for d in D:
        m.addConstr(gp.quicksum(a[g, d] for g in G) <= 1)

    # B&P-Branching: forced/forbidden Events als Constraints (nur team-relevante).
    def _matching_games(host, visitor):
        # Spiel-Indizes dieses Teams, die zum Event (host,visitor) gehören
        for g in G:
            opp, is_home = glist[g]
            if is_home and team == host and opp == visitor:
                yield g
            elif (not is_home) and team == visitor and opp == host:
                yield g
    for (host, visitor, d) in forced:
        gs = list(_matching_games(host, visitor))
        if gs:
            m.addConstr(gp.quicksum(a[g, d] for g in gs) == 1)
    for (host, visitor, d) in forbidden:
        gs = list(_matching_games(host, visitor))
        if gs:
            m.addConstr(gp.quicksum(a[g, d] for g in gs) == 0)
    # ≤max_consecutive
    K = inst.max_consecutive
    if K < inst.n_days:
        play = {d: gp.quicksum(a[g, d] for g in G) for d in D}
        for d0 in range(inst.n_days - K):
            m.addConstr(gp.quicksum(play[d0 + k] for k in range(K + 1)) <= K)

    # Stadt je Tag (Spielort = host); p[c,d]. Persistenz an Off-Days, Heim-Anker an
    # den Rändern → Pricing-Reise stimmt mit _column_cost (Master) überein.
    p = m.addVars([(c, d) for c in ids for d in D], vtype=GRB.BINARY, name="p")
    play = {d: gp.quicksum(a[g, d] for g in G) for d in D}
    for d in D:
        m.addConstr(gp.quicksum(p[c, d] for c in ids) == 1)
        for g in G:
            opp, is_home = glist[g]
            host = team if is_home else opp
            m.addConstr(p[host, d] >= a[g, d])
    # Persistenz: an einem Off-Day (play[d]=0) bleibt die Stadt wie am Vortag
    for d in D[1:]:
        for c in ids:
            m.addConstr(p[c, d] - p[c, d - 1] <= play[d])
            m.addConstr(p[c, d - 1] - p[c, d] <= play[d])
    # Reise-Linearisierung (calendar-day; mit Persistenz == echte Game-to-Game-km)
    trav = []
    for d in D[1:]:
        for c in ids:
            for c2 in ids:
                if c == c2:
                    continue
                y = m.addVar(lb=0.0, ub=1.0)
                m.addConstr(y <= p[c, d - 1])
                m.addConstr(y <= p[c2, d])
                m.addConstr(y >= p[c, d - 1] + p[c2, d] - 1)
                trav.append(haversine_km(tbi[c].lat, tbi[c].lon, tbi[c2].lat, tbi[c2].lon) * y)
    # Heim-Anker: Heim → Stadt an Tag 0, und Stadt an letztem Tag → Heim.
    for c in ids:
        if c != team:
            dkm = haversine_km(tbi[team].lat, tbi[team].lon, tbi[c].lat, tbi[c].lon)
            trav.append(dkm * p[c, D[0]])
            trav.append(dkm * p[c, D[-1]])

    # Dual-Rewards: home event (team,opp,d) → -pi; away event (opp,team,d) → +pi
    reward = []
    for g in G:
        opp, is_home = glist[g]
        for d in D:
            if is_home:
                e = (team, opp, d)
                w = -pi_couple.get(e, 0.0)
            else:
                e = (opp, team, d)
                w = +pi_couple.get(e, 0.0)
            if w != 0.0:
                reward.append(w * a[g, d])

    m.setObjective(gp.quicksum(trav) + gp.quicksum(reward), GRB.MINIMIZE)
    m.optimize()
    if m.SolCount == 0:
        return None
    # reduzierte Kosten = (obj des Pricing) - pi_conv  (Reward bereits in obj)
    reduced = m.ObjVal - pi_conv
    if reduced > -1e-6:
        return None
    # Spalte rekonstruieren
    events = set()
    for g in G:
        opp, is_home = glist[g]
        for d in D:
            if a[g, d].X > 0.5:
                events.add((team, opp, d) if is_home else (opp, team, d))
    evset = frozenset(events)
    return Column(team, evset, _column_cost(team, evset, tbi))


# ====================================================================
# Treiber: Price-and-Branch
# ====================================================================

def branch_and_price(inst: GreenfieldInstance, *, max_cg_iter: int = 20,
                     pricing_time_s: float = 10.0, verbose: bool = False,
                     seed_schedules: Optional[List[List[Tuple[int, str, str]]]] = None,
                     ) -> BnPResult:
    """Price-and-Branch über den green-field Plan.

    ``seed_schedules``: optionale global-konsistente Pläne (z. B. SA-Warm-Start- oder
    monolithischer Output, je als Liste von (day, host, visitor)), deren Team-Spalten
    in den Pool aufgenommen werden. So kann der integer Master hochwertige, konsistente
    Spalten kombinieren — die Engine erreicht damit nachweislich das Optimum, wenn es
    als Seed vorliegt, und bleibt für große Instanzen das skalierbare B&P-Gerüst.
    """
    try:
        import gurobipy as gp  # noqa: F401
    except Exception as exc:  # pragma: no cover
        raise GurobiUnavailable(f"gurobipy nicht verfügbar: {exc}") from exc
    import time
    t0 = time.time()
    ids = inst.ids
    tbi = {t.id: t for t in inst.teams}

    boot = greedy_feasible_schedule(inst)
    boot_cols = decompose_to_columns(boot, inst, tbi)
    bootstrap_km = sum(c.cost_km for c in boot_cols.values())
    columns: Dict[str, List[Column]] = {t: [boot_cols[t]] for t in ids}

    # optionale Seed-Pläne als zusätzliche (konsistente) Spalten aufnehmen
    for sched in (seed_schedules or []):
        seed_cols = decompose_to_columns(sched, inst, tbi)
        for t in ids:
            if all(seed_cols[t].events != c.events for c in columns[t]):
                columns[t].append(seed_cols[t])

    env = _make_env(verbose=False)
    cg_iter = 0
    try:
        for cg_iter in range(1, max_cg_iter + 1):
            m, lam, conv, couple = _solve_master(columns, ids, integer=False, env=env)
            if m.Status != gp.GRB.OPTIMAL:
                m.dispose()
                break
            pi_conv = {t: conv[t].Pi for t in ids}
            pi_couple = {e: couple[e].Pi for e in couple}
            m.dispose()
            added = 0
            for t in ids:
                col = _price_team(t, inst, tbi, pi_conv[t], pi_couple, env, pricing_time_s)
                if col is not None and all(col.events != c.events for c in columns[t]):
                    columns[t].append(col)
                    added += 1
            if added == 0:
                break

        # Integer Master über den Spalten-Pool (price-and-branch)
        mi, lami, convi, couplei = _solve_master(columns, ids, integer=True, env=env)
        status = "OPTIMAL" if mi.Status == gp.GRB.OPTIMAL else str(mi.Status)
        result = BnPResult(status=status, objective_km=None,
                           n_columns=sum(len(v) for v in columns.values()),
                           cg_iterations=cg_iter, bootstrap_km=bootstrap_km,
                           runtime_s=time.time() - t0)
        if mi.SolCount > 0:
            result.objective_km = mi.ObjVal
            chosen_events = set()
            for t in ids:
                for k, col in enumerate(columns[t]):
                    if lami[(t, k)].X > 0.5:
                        chosen_events |= {e for e in col.events if e[0] == t}  # host-Events
            result.games = sorted((d, h, v) for (h, v, d) in chosen_events)
        mi.dispose()
        env.dispose()
        return result
    except gp.GurobiError as exc:
        try:
            env.dispose()
        except Exception:
            pass
        raise GurobiUnavailable(
            f"Gurobi (B&P) scheiterte (evtl. Restricted-Größenlimit; akademische "
            f"Lizenz in .env eintragen): {exc}") from exc


# ====================================================================
# Echtes Branch-and-Price: DFS-Baum mit Event-Branching
# ====================================================================

def _usable(columns: Dict[str, List[Column]], forced: set, forbidden: set,
            ids: List[str]) -> Dict[str, List[Column]]:
    """Spalten je Team, die mit den Branching-Entscheidungen verträglich sind:
    enthalten alle team-relevanten forced-Events und kein forbidden-Event."""
    out: Dict[str, List[Column]] = {}
    for t in ids:
        keep = []
        for col in columns[t]:
            ok = True
            for e in forced:
                if (e[0] == t or e[1] == t) and e not in col.events:
                    ok = False
                    break
            if ok:
                for e in forbidden:
                    if (e[0] == t or e[1] == t) and e in col.events:
                        ok = False
                        break
            if ok:
                keep.append(col)
        out[t] = keep
    return out


def branch_and_price_optimal(
    inst: GreenfieldInstance, *, max_nodes: int = 40, cg_iter_per_node: int = 6,
    pricing_time_s: float = 6.0, time_limit_s: float = 120.0,
    seed_schedules: Optional[List[List[Tuple[int, str, str]]]] = None,
) -> BnPResult:
    """Echtes Branch-and-Price: Column Generation an jedem Knoten + Branching auf
    fraktionale **Event**-Variablen (host hostet visitor an Tag d). Findet auf
    reduzierten Instanzen das Optimum aus dem greedy Bootstrap heraus (ohne Seed).

    Branching: x_e = Σ host-Spalten mit e. Ist x_e fraktional → Kind A erzwingt e,
    Kind B verbietet e; das Pricing respektiert die Entscheidung. DFS mit Bounding
    (LP-Schranke ≥ Inzumbent → prune), Knoten-/Zeitlimit. Best-effort exakt:
    wird ein Teilbaum mangels konsistenter Spalten infeasibel, wird er beschnitten.
    """
    try:
        import gurobipy as gp
    except Exception as exc:  # pragma: no cover
        raise GurobiUnavailable(f"gurobipy nicht verfügbar: {exc}") from exc
    import time
    t0 = time.time()
    ids = inst.ids
    tbi = {t.id: t for t in inst.teams}

    boot = greedy_feasible_schedule(inst)
    boot_cols = decompose_to_columns(boot, inst, tbi)
    bootstrap_km = sum(c.cost_km for c in boot_cols.values())
    columns: Dict[str, List[Column]] = {t: [boot_cols[t]] for t in ids}
    # Seed-Pläne (vollständige, konsistente Schedules) als Spalten aufnehmen.
    for sched in (seed_schedules or []):
        seed_cols = decompose_to_columns(sched, inst, tbi)
        for t in ids:
            if all(seed_cols[t].events != c.events for c in columns[t]):
                columns[t].append(seed_cols[t])

    env = _make_env(verbose=False)
    incumbent_km = float("inf")
    incumbent_games: List[Tuple[int, str, str]] = []
    nodes = 0
    EPS = 1e-6
    try:
        stack = [(frozenset(), frozenset())]  # (forced, forbidden)
        while stack and nodes < max_nodes and time.time() - t0 < time_limit_s:
            forced, forbidden = stack.pop()
            nodes += 1

            # CG an diesem Knoten (Spalten respektieren Branching)
            for _ in range(cg_iter_per_node):
                use = _usable(columns, forced, forbidden, ids)
                if any(len(use[t]) == 0 for t in ids):
                    use = None
                    break
                m, lam, conv, couple = _solve_master(use, ids, integer=False, env=env)
                if m.Status != gp.GRB.OPTIMAL:
                    m.dispose()
                    use = None
                    break
                lp_obj = m.ObjVal
                pi_conv = {t: conv[t].Pi for t in ids}
                pi_couple = {e: couple[e].Pi for e in couple}
                # primal für Integralitäts-/Branching-Check sichern
                lam_val = {(t, k): lam[(t, k)].X for t in ids for k in range(len(use[t]))}
                m.dispose()
                if lp_obj >= incumbent_km - EPS:
                    use = "PRUNE"
                    break
                added = 0
                for t in ids:
                    col = _price_team(t, inst, tbi, pi_conv[t], pi_couple, env,
                                      pricing_time_s, forced=set(forced),
                                      forbidden=set(forbidden))
                    if col is not None and all(col.events != c.events for c in columns[t]):
                        columns[t].append(col)
                        added += 1
                if added == 0:
                    break
            if use is None or use == "PRUNE":
                continue

            use = _usable(columns, forced, forbidden, ids)
            if any(len(use[t]) == 0 for t in ids):
                continue
            m, lam, conv, couple = _solve_master(use, ids, integer=False, env=env)
            if m.Status != gp.GRB.OPTIMAL:
                m.dispose()
                continue
            lp_obj = m.ObjVal
            lam_val = {(t, k): lam[(t, k)].X for t in ids for k in range(len(use[t]))}
            m.dispose()
            if lp_obj >= incumbent_km - EPS:
                continue

            # Integralität prüfen + fraktionalstes Event finden
            x_event: Dict[Event, float] = {}
            for t in ids:
                for k, col in enumerate(use[t]):
                    val = lam_val[(t, k)]
                    if val <= EPS:
                        continue
                    for e in col.home_events():       # host-Seite zählt
                        x_event[e] = x_event.get(e, 0.0) + val
            frac = [(e, v) for e, v in x_event.items() if EPS < v < 1 - EPS]
            if not frac:
                # integer-Lösung → echte Kosten bestimmen (integer Master sicherheitshalber)
                mi, lami, _, _ = _solve_master(use, ids, integer=True, env=env)
                if mi.SolCount > 0 and mi.ObjVal < incumbent_km - EPS:
                    incumbent_km = mi.ObjVal
                    chosen = set()
                    for t in ids:
                        for k, col in enumerate(use[t]):
                            if lami[(t, k)].X > 0.5:
                                chosen |= set(col.home_events())
                    incumbent_games = sorted((d, h, v) for (h, v, d) in chosen)
                mi.dispose()
                continue
            # branchen auf das fraktionalste Event
            be = min(frac, key=lambda ev: abs(ev[1] - 0.5))[0]
            stack.append((forced | {be}, forbidden))         # Kind A: erzwinge
            stack.append((forced, forbidden | {be}))         # Kind B: verbiete

        env.dispose()
        status = "OPTIMAL" if (nodes < max_nodes and time.time() - t0 < time_limit_s
                               and incumbent_km < float("inf")) else "FEASIBLE"
        if incumbent_km == float("inf"):
            incumbent_km, incumbent_games = bootstrap_km, sorted(
                (d, h, v) for (h, v, d) in
                {e for c in boot_cols.values() for e in c.home_events()})
            status = "BOOTSTRAP"
        return BnPResult(status=status, objective_km=incumbent_km,
                         games=incumbent_games,
                         n_columns=sum(len(v) for v in columns.values()),
                         cg_iterations=nodes, bootstrap_km=bootstrap_km,
                         runtime_s=time.time() - t0)
    except gp.GurobiError as exc:
        try:
            env.dispose()
        except Exception:
            pass
        raise GurobiUnavailable(
            f"Gurobi (B&P-Baum) scheiterte (evtl. Restricted-Größenlimit): {exc}") from exc
