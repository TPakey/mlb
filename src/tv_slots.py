"""TV-Slot-Score-Modul (Sprint 2.3b Phase 2).

Berechnet den TV-Slot-Wert eines Plans als gewichtete Summe über alle
Heimspiele:

    tv_slot_score(game) =
        slot_base_value(weekday, daypart)
        × marquee_multiplier(home, away)
        × historic_pick_prob(home)

Interpretation:
- Höherer Score = attraktiverer TV-Plan (mehr wertvolle Matchups in
  wertvollen Slots).
- Der Score ist dimensionslos (Multiplikatoren) und dient als eine der
  8 Pareto-Achsen in Sprint 2.3b.

Daypart-Modell (Sprint 2.9 / Review C2 — probabilistischer Erwartungswert):
Da in der Plan-Phase keine fixen Spielzeiten aus der MLB-Stats-API vorliegen
(diese werden erst später zugeteilt), modellieren wir den Slot-Wert pro
Wochentag als **Erwartungswert** über das realistische Day/Night-Verhältnis:

    expected_slot_value(weekday) = Σ_dp  P(dp | weekday) · slot_value(weekday, dp)

Die Mischwahrscheinlichkeiten `daypart_mix_by_weekday` stammen aus
data/tv_slots.json (mit konservativen Defaults, falls nicht vorhanden).

Damit wird der frühere C2-Bug behoben: vorher bekam JEDES Sonntagsspiel "day"
(1.05) — der 1.6er-Premium-Slot "NBC Sunday Night Baseball" wurde NIE gewertet —
und JEDES Samstagsspiel "night" (1.50), wodurch Saturday-Day-Games überbewertet
wurden. Der Erwartungswert kreditiert nun den Sunday-Night-Premium anteilig und
unterscheidet Saturday-Day von -Night.

Dieses Modell ist mit der inkrementellen SA-Berechnung konsistent (der Wert
hängt nur vom Wochentag ab, nicht vom Datums-Kontext). Eine spätere
Erweiterung mit echten Stats-API-Spielzeiten oder einer daypart-
Entscheidungsvariable im SA (Plan 2.9.1) ist möglich.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional

from .season import Game, Season


DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Default-Day/Night-Mischwahrscheinlichkeiten pro Wochentag (0=Mo..6=So),
# falls data/tv_slots.json kein `daypart_mix_by_weekday` enthaelt.
# Begruendung siehe Modul-Docstring + docs/TV_SLOT_RESEARCH.md:
# MLB-Spiele sind werktags abend-dominiert; Samstag stark gemischt (FOX
# Afternoon + Primetime); Sonntag tag-dominiert mit einem NBC-Sunday-Night-Slot.
_DEFAULT_DAYPART_MIX: Dict[int, Dict[str, float]] = {
    0: {"day": 0.25, "night": 0.75},
    1: {"day": 0.15, "night": 0.85},
    2: {"day": 0.15, "night": 0.85},
    3: {"day": 0.15, "night": 0.85},
    4: {"day": 0.12, "night": 0.88},
    5: {"day": 0.55, "night": 0.45},   # Samstag: Afternoon + Primetime gemischt
    6: {"day": 0.88, "night": 0.12},   # Sonntag: Tag-dominiert + 1 NBC-Sunday-Night
}


@dataclass(frozen=True)
class TvSlotConfig:
    """In-Memory-Repräsentation der TV-Slot-Parameter aus data/tv_slots.json."""
    # slot_value_by_weekday_daypart: weekday (int) -> "day"|"night" -> float
    slot_values: Dict[int, Dict[str, float]]
    # marquee_matchups: (team_a, team_b) -> multiplier (symmetrisch)
    marquee_multipliers: Dict[FrozenSet[str], float]
    # historic_pick_prob: team_id -> float
    pick_prob: Dict[str, float]
    # daypart_mix: weekday -> {"day": p, "night": p}  (Erwartungswert-Modell, C2-Fix)
    daypart_mix: Dict[int, Dict[str, float]] = field(default_factory=lambda: dict(_DEFAULT_DAYPART_MIX))
    # default pick_prob für unbekannte Teams
    default_pick_prob: float = 1.0

    def slot_value(self, weekday: int, daypart: str) -> float:
        """Basiswert für weekday (0=Mo..6=So) und daypart ("day"|"night")."""
        row = self.slot_values.get(weekday, {})
        return row.get(daypart, 0.85)  # 0.85 = Conservative Default

    def expected_slot_value(self, weekday: int) -> float:
        """Erwarteter Slot-Wert eines Spiels an `weekday` (C2-Fix, Sprint 2.9).

        Gewichtet die day/night-Slot-Werte mit der realistischen
        Day/Night-Mischwahrscheinlichkeit. Damit fliesst der Sunday-Night-
        Premium (1.6) anteilig ein und Saturday-Day wird nicht mehr als Night
        gewertet. Haengt nur vom Wochentag ab → inkrementalitaets-sicher fuer
        den SA.
        """
        mix = self.daypart_mix.get(weekday)
        if not mix:
            # Fallback: reiner Night-Wert (konservativ, wie historisches Verhalten)
            return self.slot_value(weekday, "night")
        total_p = sum(mix.values()) or 1.0
        return sum(
            (p / total_p) * self.slot_value(weekday, dp)
            for dp, p in mix.items()
        )

    def marquee_mult(self, home: str, away: str) -> float:
        """Marquee-Multiplikator für ein Matchup (1.0 wenn kein Marquee-Bonus)."""
        key = frozenset({home, away})
        return self.marquee_multipliers.get(key, 1.0)

    def team_pick_prob(self, team_id: str) -> float:
        return self.pick_prob.get(team_id, self.default_pick_prob)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "TvSlotConfig":
        """Lädt die Konfiguration aus data/tv_slots.json."""
        path = path or (DATA_DIR / "tv_slots.json")
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)

        # slot_values: Schlüssel sind Strings ("0".."6") → int-Konvertierung
        raw_sv = raw["slot_value_by_weekday_daypart"]
        slot_values: Dict[int, Dict[str, float]] = {}
        for k, v in raw_sv.items():
            if k.startswith("_"):
                continue
            wd = int(k)
            slot_values[wd] = {
                dp: float(val)
                for dp, val in v.items()
                if not dp.startswith("_")
            }

        # marquee_multipliers: Liste von {teams: [...], bonus_multiplier: float}
        marquee_multipliers: Dict[FrozenSet[str], float] = {}
        for entry in raw.get("marquee_matchups", []):
            teams = frozenset(entry["teams"])
            marquee_multipliers[teams] = float(entry["bonus_multiplier"])

        # historic_pick_prob: direkt als Dict
        raw_pp = raw.get("historic_pick_prob", {})
        pick_prob = {
            k: float(v)
            for k, v in raw_pp.items()
            if not k.startswith("_")
        }

        # daypart_mix_by_weekday (optional) — Erwartungswert-Modell (C2-Fix)
        raw_mix = raw.get("daypart_mix_by_weekday", {})
        daypart_mix: Dict[int, Dict[str, float]] = {}
        for k, v in raw_mix.items():
            if k.startswith("_"):
                continue
            daypart_mix[int(k)] = {
                dp: float(val) for dp, val in v.items() if not dp.startswith("_")
            }
        if not daypart_mix:
            daypart_mix = dict(_DEFAULT_DAYPART_MIX)

        return cls(
            slot_values=slot_values,
            marquee_multipliers=marquee_multipliers,
            pick_prob=pick_prob,
            daypart_mix=daypart_mix,
        )


@dataclass(frozen=True)
class GameTvScore:
    """TV-Score-Komponenten für ein einzelnes Spiel."""
    game_date: date
    home_team: str
    away_team: str
    weekday: int          # 0=Mo..6=So
    daypart: str          # "day" | "night"
    slot_base: float
    marquee_mult: float
    pick_prob: float
    total: float          # slot_base × marquee_mult × pick_prob


@dataclass
class TvSlotReport:
    """Aggregierter TV-Slot-Score für einen vollständigen Plan."""
    total_score: float
    avg_per_game: float
    top_games: List[GameTvScore]          # Top-10 nach Score
    by_team: Dict[str, float]             # Heim-Team → kumulierter Score
    by_weekday: Dict[int, float]          # Weekday → kumulierter Score
    marquee_games_count: int              # Spiele mit marquee_mult > 1.0
    peak_slot_count: int                  # Spiele mit slot_base >= 1.5 (Sa/So Abend)


# ====================================================================
# Score-Berechnung
# ====================================================================

def game_tv_score(game: Game, cfg: TvSlotConfig) -> GameTvScore:
    """Berechnet den TV-Score für ein einzelnes Spiel (Erwartungswert-Modell)."""
    wd = game.date.weekday()           # 0=Mo..6=So
    base = cfg.expected_slot_value(wd)
    mult = cfg.marquee_mult(game.home, game.away)
    pp = cfg.team_pick_prob(game.home)
    return GameTvScore(
        game_date=game.date,
        home_team=game.home,
        away_team=game.away,
        weekday=wd,
        daypart="expected",   # Erwartungswert über day/night (siehe Modul-Docstring)
        slot_base=base,
        marquee_mult=mult,
        pick_prob=pp,
        total=base * mult * pp,
    )


def compute_tv_slot_score(
    season: Season,
    cfg: Optional[TvSlotConfig] = None,
) -> TvSlotReport:
    """Berechnet den TV-Slot-Score für einen vollständigen Plan.

    Args:
        season:  Der zu bewertende MLB-Saisonplan.
        cfg:     TvSlotConfig; wenn None, wird data/tv_slots.json geladen.

    Returns:
        TvSlotReport mit Gesamtscore und Detailaufschlüsselung.
    """
    if cfg is None:
        cfg = TvSlotConfig.load()

    scores: List[GameTvScore] = []
    by_team: Dict[str, float] = {}
    by_weekday: Dict[int, float] = {}

    for g in season.games:
        s = game_tv_score(g, cfg)
        scores.append(s)
        by_team[g.home] = by_team.get(g.home, 0.0) + s.total
        by_weekday[s.weekday] = by_weekday.get(s.weekday, 0.0) + s.total

    total = sum(s.total for s in scores)
    n = max(len(scores), 1)
    top_games = sorted(scores, key=lambda x: x.total, reverse=True)[:10]
    marquee_count = sum(1 for s in scores if s.marquee_mult > 1.0)
    # "Peak"-Slots = hochwertige Wochenend-Erwartungswerte (Sa/So). Schwelle an
    # das Erwartungswert-Modell angepasst (vorher 1.5 für reine Night-Werte).
    peak_count = sum(1 for s in scores if s.slot_base >= 1.1)

    return TvSlotReport(
        total_score=total,
        avg_per_game=total / n,
        top_games=top_games,
        by_team=by_team,
        by_weekday=by_weekday,
        marquee_games_count=marquee_count,
        peak_slot_count=peak_count,
    )
