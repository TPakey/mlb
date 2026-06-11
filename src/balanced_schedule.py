"""Sprint 5.4 (GAP-B3) — MLB Balanced-Schedule-Format (seit 2023).

Seit 2023 spielt jedes Team gegen **jedes** andere Team; die Spielzahl pro Paarung
folgt einem festen Schema (162 Spiele/Team):

| Kategorie            | Gegner | Spiele/Paar | Summe |
|----------------------|--------|-------------|-------|
| Intra-Division       | 4      | 13          | 52    |
| Intra-League (andere Div.) | 10 | 6 oder 7   | 64    |
| Interleague          | 15     | 3 oder 4    | 46    |
|                      |        |             | **162** |

Dieses Modul stellt das Format als **strukturelle Constraints** bereit — sowohl zur
**Validierung** eines beliebigen Plans (B3-Compliance) als auch als **Matchup-Quoten-
Matrix** für den green-field Solver (Sprint 5.4 / Gurobi). Die konkrete 6/7- bzw.
3/4-Zuteilung rotiert jährlich; wir **leiten sie aus einer realen Referenzsaison ab**
(damit die Matrix einem echten, gültigen MLB-Jahr entspricht) statt sie zu raten.

Verifiziert gegen real 2024: 60 Intra-Div-Paare (13), 150 Intra-League (6/7),
225 Interleague (3/4) — plus wenige Makeup-Artefakte (ein 14/5/8), die als solche
toleriert werden.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List

from .data_loader import Team
from .season import Season

# Kanonische Spiele/Paar je Kategorie (Sets erlauben die jährliche 6/7- bzw. 3/4-Rotation)
CANON = {
    "intra-div": {13},
    "intra-league": {6, 7},
    "interleague": {3, 4},
}
EXPECTED_TOTAL = 162


def category(a: Team, b: Team) -> str:
    if a.league == b.league and a.division == b.division:
        return "intra-div"
    if a.league == b.league:
        return "intra-league"
    return "interleague"


@dataclass(frozen=True)
class FormatViolation:
    kind: str           # "pair-count" | "team-total" | "missing-opponent"
    detail: str


def derive_matchup_matrix(
    season: Season, teams: List[Team],
) -> Dict[str, Dict[str, int]]:
    """Symmetrische Matchup-Quoten-Matrix (team→team→Spiele) aus einer
    Referenzsaison. Doubleheader/Makeups zählen als regulär gespielte Spiele.
    """
    ids = [t.id for t in teams]
    idset = set(ids)
    m: Dict[str, Dict[str, int]] = {a: {b: 0 for b in ids if b != a} for a in ids}
    for g in season.games:
        if g.home in idset and g.away in idset:
            m[g.home][g.away] += 1
            m[g.away][g.home] += 1
    return m


def canonicalize_matrix(
    matrix: Dict[str, Dict[str, int]], teams_by_id: Dict[str, Team],
) -> Dict[str, Dict[str, int]]:
    """Bereinigt Makeup-Artefakte: jede Paarung wird auf den nächsten kanonischen
    Kategorie-Wert gesetzt (z. B. 14→13, 8→7, 5→6). Liefert eine **gültige**
    Format-Matrix als Solver-Ziel. Per-Team-Totals können danach leicht von 162
    abweichen (Artefakt-Bereinigung) — wird vom Aufrufer geprüft.
    """
    out: Dict[str, Dict[str, int]] = {a: {} for a in matrix}
    for a, row in matrix.items():
        for b, c in row.items():
            cat = category(teams_by_id[a], teams_by_id[b])
            allowed = CANON[cat]
            out[a][b] = min(allowed, key=lambda v: (abs(v - c), v))
    return out


def validate_format(
    season: Season, teams: List[Team], *, artifact_tolerance: int = 2,
) -> List[FormatViolation]:
    """B3-Compliance: prüft, dass jeder Plan dem Balanced-Format entspricht.

    - jede Paarung in der kanonischen Spielzahl ihrer Kategorie (kleine
      Makeup-Abweichungen bis ``artifact_tolerance`` Paare je Kategorie werden
      toleriert, da as-played-Daten Rainout-Makeups enthalten);
    - jedes Team spielt gegen **alle** 29 anderen (kein fehlender Gegner);
    - Team-Total ≈ 162 (±2 Makeup-Varianz).
    """
    tbi = {t.id: t for t in teams}
    matrix = derive_matchup_matrix(season, teams)
    viols: List[FormatViolation] = []

    # fehlende Gegner
    for a, row in matrix.items():
        missing = [b for b, c in row.items() if c == 0]
        if missing:
            viols.append(FormatViolation(
                "missing-opponent", f"{a} spielt nicht gegen {sorted(missing)}"))

    # Paar-Zählungen je Kategorie
    off_by_cat: Dict[str, int] = defaultdict(int)
    seen = set()
    for a, row in matrix.items():
        for b, c in row.items():
            key = frozenset((a, b))
            if key in seen:
                continue
            seen.add(key)
            cat = category(tbi[a], tbi[b])
            if c not in CANON[cat]:
                off_by_cat[cat] += 1
    for cat, n in off_by_cat.items():
        if n > artifact_tolerance:
            viols.append(FormatViolation(
                "pair-count",
                f"{n} {cat}-Paar(e) außerhalb {sorted(CANON[cat])} "
                f"(Toleranz {artifact_tolerance} = Makeup-Artefakte)"))

    # Team-Totals
    for a, row in matrix.items():
        tot = sum(row.values())
        if abs(tot - EXPECTED_TOTAL) > 2:
            viols.append(FormatViolation(
                "team-total", f"{a}: {tot} Spiele (Soll {EXPECTED_TOTAL} ±2)"))
    return viols


def round_robin_matrix(team_ids: List[str], games_per_pair: int) -> Dict[str, Dict[str, int]]:
    """Kleine Balanced-Format-Matrix für reduzierte Instanzen (Tests/Solver-Smoke):
    jedes Team spielt jedes andere ``games_per_pair`` mal (symmetrisch)."""
    return {a: {b: games_per_pair for b in team_ids if b != a} for a in team_ids}


def format_summary() -> dict:
    """Maschinenlesbare Format-Spezifikation (für Reports/Doku)."""
    return {
        "season_format": "MLB Balanced Schedule (2023+)",
        "games_per_team": EXPECTED_TOTAL,
        "categories": {
            "intra-div": {"opponents": 4, "games_per_pair": sorted(CANON["intra-div"]), "sum": 52},
            "intra-league": {"opponents": 10, "games_per_pair": sorted(CANON["intra-league"]), "sum": 64},
            "interleague": {"opponents": 15, "games_per_pair": sorted(CANON["interleague"]), "sum": 46},
        },
    }
