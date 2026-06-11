"""Revenue-Modell fuer Sprint 2.2.

Liefert einen erwarteten USD-Gate-Revenue pro Heimspiel auf Basis eines
multiplikativen Modells:

    expected_revenue(game) = base_team[home]
                            * weekday_factor[weekday]
                            * month_factor[month]
                            * daypart_factor[daypart]
                            * opponent_draw_factor[away]
                            * doubleheader_penalty[dh_type]

Designprinzipien:
- transparent: Modell-Parameter liegen in `data/revenue_model.json`
- ersetzbar:   wenn MLB echte Daten liefert, JSON tauschen — fertig
- validierbar: `tools/validate_revenue_model.py` rechnet das Modell gegen
  Liga-Ist-Werte 2024 und meldet Abweichungen

Wissenschaftliche Grundlage: siehe `docs/REVENUE_MODEL_RESEARCH.md`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set

from .data_loader import Team
from .season import Game, Season


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class RevenueModel:
    """In-Memory-Repraesentation der Modell-Parameter."""
    base_team: Dict[str, float]
    weekday_factor: Dict[int, float]
    month_factor: Dict[int, float]
    daypart_factor: Dict[str, float]
    daypart_factor_sunday: Dict[str, float]
    opponent_draw_factor: Dict[str, float]
    doubleheader_penalty: Dict[str, float]

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "RevenueModel":
        path = path or (DATA_DIR / "revenue_model.json")
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
        return cls(
            base_team={k: float(v) for k, v in raw["base_team"].items()},
            weekday_factor={int(k): float(v) for k, v in raw["weekday_factor"].items()},
            month_factor={int(k): float(v) for k, v in raw["month_factor"].items()},
            daypart_factor={k: float(v) for k, v in raw["daypart_factor"].items()},
            daypart_factor_sunday={k: float(v) for k, v in raw["daypart_factor_sunday"].items()},
            opponent_draw_factor={k: float(v) if isinstance(v, (int, float)) else v
                                   for k, v in raw["opponent_draw_factor"].items()},
            doubleheader_penalty={k: float(v) for k, v in raw["doubleheader_penalty"].items()},
        )


def _expected_daypart_factor(weekday: int, is_sunday: bool,
                              model: "RevenueModel") -> float:
    """Erwarteter Daypart-Faktor (Sprint 2.9 / Review N4).

    Statt der alten monolithischen Heuristik ("Sonntag=day, Rest=night") wird —
    konsistent mit dem TV-Slot-Erwartungswert-Modell (C2) — der Daypart-Faktor
    als gewichteter Erwartungswert über das realistische Day/Night-Verhältnis
    pro Wochentag berechnet. Quelle des Mix: `tv_slots._DEFAULT_DAYPART_MIX`
    (eine gemeinsame Wahrheitsquelle).
    """
    from .tv_slots import _DEFAULT_DAYPART_MIX
    mix = _DEFAULT_DAYPART_MIX.get(weekday, {"night": 1.0})
    factors = model.daypart_factor_sunday if is_sunday else model.daypart_factor
    total_p = sum(mix.values()) or 1.0
    return sum((p / total_p) * factors.get(dp, 1.0) for dp, p in mix.items())


def _doubleheader_type(game: Game,
                        single_admission_pks: Optional[Set[int]] = None) -> str:
    """Doubleheader-Typ eines Spiels (Sprint 2.9 / Review N3).

    `doubleheader_seq=0` → kein DH. Ohne echte Admission-Daten aus der MLB
    Stats API ist die Default-Annahme `split_admission` (MLB bevorzugt diese
    bei *geplanten* Doubleheadern). Makeup-/Wetter-Doubleheader sind dagegen
    häufig `single_admission` — diese können über `single_admission_pks`
    (z.B. vom Disruption-/Repair-Modul befüllt) explizit markiert werden,
    sodass das Modellgewicht `doubleheader_penalty[single_admission]` nicht
    länger totes Gewicht ist.
    """
    if game.doubleheader_seq == 0:
        return "none"
    if single_admission_pks and game.game_pk in single_admission_pks:
        return "single_admission"
    return "split_admission"


def expected_revenue_raw(
    game_date: date, home: str, away: str, dh_seq: int,
    model: RevenueModel,
    division_rivals: Optional[Dict[str, Set[str]]] = None,
    single_admission_pks: Optional[Set[int]] = None,
    game_pk: Optional[int] = None,
) -> float:
    """Erwarteter Gate-Revenue ohne Game-Objekt-Allokation (Audit A6, Sprint A-4).

    Funktional identisch mit `expected_revenue`, akzeptiert aber die einzelnen
    Felder direkt — sodass im SA-Hot-Path (~700k Iterationen × ~3 Aufrufe ×
    ~3 Days = Millionen Aufrufe) keine `Game`-Dataclass-Instanzen mehr
    allokiert werden müssen.
    """
    base = model.base_team.get(home, 0.0)
    if not base:
        return 0.0

    weekday = game_date.weekday()
    month = game_date.month
    is_sunday = (weekday == 6)

    wf = model.weekday_factor.get(weekday, 1.0)
    mf = model.month_factor.get(month, 1.0)
    df = _expected_daypart_factor(weekday, is_sunday, model)

    if away in model.opponent_draw_factor and away not in ("default", "division_rival_bonus"):
        of = model.opponent_draw_factor[away]
    else:
        of = model.opponent_draw_factor.get("default", 1.0)

    if division_rivals and away in division_rivals.get(home, set()):
        rival_bonus = model.opponent_draw_factor.get("division_rival_bonus", 1.0)
        of *= rival_bonus

    if dh_seq == 0:
        dh = "none"
    elif single_admission_pks and game_pk is not None and game_pk in single_admission_pks:
        dh = "single_admission"
    else:
        dh = "split_admission"
    dhp = model.doubleheader_penalty.get(dh, 1.0)

    return base * wf * mf * df * of * dhp


def expected_revenue(game: Game, model: RevenueModel,
                      division_rivals: Optional[Dict[str, Set[str]]] = None) -> float:
    """Erwarteter Gate-Revenue (USD) fuer ein einzelnes Spiel."""
    return expected_revenue_raw(
        game.date, game.home, game.away, game.doubleheader_seq,
        model, division_rivals,
        game_pk=game.game_pk,
    )


def season_revenue(season: Season, model: RevenueModel,
                    division_rivals: Optional[Dict[str, Set[str]]] = None) -> float:
    """Summe der erwarteten Revenue ueber alle Spiele der Saison."""
    return sum(expected_revenue(g, model, division_rivals) for g in season.games)


def team_revenue(season: Season, team_id: str, model: RevenueModel,
                  division_rivals: Optional[Dict[str, Set[str]]] = None) -> float:
    """Erwarteter Gate-Revenue fuer alle Heimspiele eines Teams."""
    return sum(expected_revenue(g, model, division_rivals)
                for g in season.games if g.home == team_id)


def build_division_rivals(teams: List[Team]) -> Dict[str, Set[str]]:
    """Hilfsfunktion: Pro Team die Set der Division-Rivalen."""
    by_div: Dict[str, List[str]] = {}
    for t in teams:
        by_div.setdefault(t.division_key, []).append(t.id)
    rivals: Dict[str, Set[str]] = {}
    for div, members in by_div.items():
        for m in members:
            rivals[m] = set(members) - {m}
    return rivals
