"""Reise-Fairness-Metriken (Sprint 3, Track C2).

Reine km-Minimierung kann einzelne Teams systematisch benachteiligen: wenn die
Liga-Gesamtdistanz sinkt, aber ein paar Westküsten-Teams überproportional viel
fliegen, leidet die **Wettbewerbsintegrität** (müde Teams spielen schlechter).
Officials brauchen daher eine Kennzahl, *wie gleich* die Reiselast verteilt ist.

Zwei Maße:

1. **Gini-Koeffizient** der Pro-Team-Reise-km. 0 = perfekt gleich verteilt,
   1 = maximale Ungleichheit. Standard-Ungleichheitsmaß (Lorenz-Kurve).
   Formel (für n Werte x, aufsteigend sortiert):
       G = ( 2·Σ i·x_i ) / ( n·Σ x_i )  −  (n+1)/n        (i = 1..n)
   Diese Form ist die gebräuchliche unverzerrte Sample-Berechnung.

2. **Disparity-Ratio** = max(km) / min(km). Intuitiv lesbar ("das am meisten
   reisende Team fliegt X-mal so weit wie das am wenigsten reisende").

Beide sind *abgeleitete Report-Kennzahlen* (kein neues Pareto-Ziel), damit die
bestehende 8-D-ParetoBundle-Invariante und alle Tests stabil bleiben.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

from .travel import SeasonTravelReport


def gini(values: Sequence[float]) -> float:
    """Gini-Koeffizient einer nicht-negativen Werteliste (0 = gleich, →1 = ungleich).

    Gibt 0.0 zurück für leere Liste, einen einzelnen Wert oder Summe 0.
    """
    xs = sorted(float(v) for v in values)
    n = len(xs)
    if n < 2:
        return 0.0
    total = sum(xs)
    if total <= 0:
        return 0.0
    # i = 1..n (1-basiert)
    weighted = sum((i + 1) * x for i, x in enumerate(xs))
    return (2.0 * weighted) / (n * total) - (n + 1) / n


def disparity_ratio(values: Sequence[float]) -> float:
    """max/min der Werte. Gibt 0.0 zurück, wenn min <= 0 oder Liste leer."""
    xs = [float(v) for v in values]
    if not xs:
        return 0.0
    lo = min(xs)
    if lo <= 0:
        return 0.0
    return max(xs) / lo


@dataclass(frozen=True)
class FairnessReport:
    """Verteilung der Reiselast über die 30 Teams."""
    gini: float
    disparity_ratio: float
    max_km: float
    min_km: float
    mean_km: float
    max_team: str = ""
    min_team: str = ""
    per_team_km: Dict[str, float] = field(default_factory=dict)


def compute_fairness_report(travel: SeasonTravelReport) -> FairnessReport:
    """Berechnet die Fairness-Kennzahlen aus einem SeasonTravelReport."""
    per_team = {tid: log.total_km for tid, log in travel.by_team.items()}
    values: List[float] = list(per_team.values())
    if not values:
        return FairnessReport(gini=0.0, disparity_ratio=0.0,
                              max_km=0.0, min_km=0.0, mean_km=0.0)
    max_team = max(per_team, key=lambda t: per_team[t])
    min_team = min(per_team, key=lambda t: per_team[t])
    return FairnessReport(
        gini=gini(values),
        disparity_ratio=disparity_ratio(values),
        max_km=max(values),
        min_km=min(values),
        mean_km=sum(values) / len(values),
        max_team=max_team,
        min_team=min_team,
        per_team_km=per_team,
    )
