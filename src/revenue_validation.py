"""Pro-Team-Strukturvalidierung des Revenue-Modells (P2-1).

Bisher war das Revenue-Modell nur auf die **Liga-Summe** geeicht (−1,4 % vs.
Sportico). Dieses Modul prüft die **Pro-Team-Struktur** gegen reale, öffentlich
verfügbare 2024-Heim-Zuschauerzahlen (ESPN; ``data/real_attendance_2024.json``).
Attendance ist ein starker Proxy für Gate-Revenue — wenn unser Modell die Teams
ähnlich rankt wie die reale Attendance, bildet es die Zugkraft-Struktur korrekt
ab (auch ohne MLBs internen Gate-Report).

Kennzahlen (alle ohne externe Abhängigkeiten berechnet):
- **Spearman-Rangkorrelation** (Rang-Treue: rankt das Modell die Teams wie die
  Realität?) — die wichtigste Größe, robust gegen Niveau-Unterschiede.
- **Pearson-Korrelation** (linearer Zusammenhang Modell-Revenue ↔ Attendance).
- **Verhältnis-Streuung** Modell/Attendance (zeigt, wie proportional das Modell
  zur Attendance skaliert; >1 Streuung ist normal, da Revenue ≠ Attendance).
- **Rang-Ausreißer**: Teams, deren Modell-Rang stark vom Attendance-Rang abweicht
  — die konkreten Stellen, an denen die Priors mit echten Daten aufzufrischen wären.

Reines Reporting/Validierung — verändert das Modell nicht.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .season import Season
from .revenue import RevenueModel, team_revenue

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_real_attendance(year: int = 2024, path: Optional[Path] = None) -> Dict[str, int]:
    path = path or (DATA_DIR / f"real_attendance_{year}.json")
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: int(v) for k, v in raw["home_attendance"].items()}


# ---------------- Statistik-Helfer (ohne scipy) ----------------

def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


def _ranks(vs: Sequence[float]) -> List[float]:
    """Durchschnittsränge (1-basiert, ties = Mittelwert)."""
    order = sorted(range(len(vs)), key=lambda i: vs[i])
    ranks = [0.0] * len(vs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vs[order[j + 1]] == vs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # 1-basiert
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    return pearson(_ranks(xs), _ranks(ys))


# ---------------- Report ----------------

@dataclass(frozen=True)
class RevenueStructureReport:
    year: int
    per_team: Dict[str, Tuple[float, int, float]]   # tid -> (model_rev, attendance, ratio)
    pearson: float
    spearman: float
    ratio_mean: float
    ratio_spread: float                              # max/min Verhältnis
    rank_outliers: List[Tuple[str, int, int, int]]   # (tid, model_rank, att_rank, |Δrank|)

    def summary(self) -> Dict[str, float]:
        return {
            "year": self.year,
            "n_teams": len(self.per_team),
            "pearson": round(self.pearson, 3),
            "spearman": round(self.spearman, 3),
            "ratio_spread": round(self.ratio_spread, 2),
            "n_rank_outliers": len(self.rank_outliers),
        }


def validate_revenue_structure(
    season: Season,
    model: RevenueModel,
    rivals,
    attendance: Dict[str, int],
    *,
    outlier_rank_gap: int = 6,
) -> RevenueStructureReport:
    """Vergleicht Modell-Pro-Team-Revenue mit realer Attendance.

    ``outlier_rank_gap``: ab welcher Rang-Differenz ein Team als Ausreißer gilt.
    """
    tids = list(attendance.keys())
    model_rev = {t: team_revenue(season, t, model, rivals) for t in tids}
    revs = [model_rev[t] for t in tids]
    atts = [float(attendance[t]) for t in tids]

    per_team = {t: (model_rev[t], attendance[t], model_rev[t] / attendance[t])
                for t in tids}
    ratios = [per_team[t][2] for t in tids]
    ratio_mean = sum(ratios) / len(ratios)
    ratio_spread = max(ratios) / min(ratios) if min(ratios) > 0 else 0.0

    # Ränge (1 = höchster)
    model_rank = {t: r for t, r in zip(
        tids, _ranks([-model_rev[t] for t in tids]))}
    att_rank = {t: r for t, r in zip(
        tids, _ranks([-float(attendance[t]) for t in tids]))}
    outliers = []
    for t in tids:
        gap = abs(int(model_rank[t]) - int(att_rank[t]))
        if gap >= outlier_rank_gap:
            outliers.append((t, int(model_rank[t]), int(att_rank[t]), gap))
    outliers.sort(key=lambda x: -x[3])

    return RevenueStructureReport(
        year=season.season,
        per_team=per_team,
        pearson=pearson(revs, atts),
        spearman=spearman(revs, atts),
        ratio_mean=ratio_mean,
        ratio_spread=ratio_spread,
        rank_outliers=outliers,
    )
