"""ParetoBundle — 8-Dimensionales Bewertungsmodell für Sprint 2.3b.

Dieses Modul definiert das zentrale Datenmodell für die Pareto-Front-
Berechnung und die Score-Aggregation über alle 8 Pareto-Achsen.

Die 8 Dimensionen (und ihre Richtung):
    1. travel_km         — Gesamte Reisedistanz (minimieren)
    2. revenue_usd       — Erwarteter Gate-Revenue (maximieren)
    3. fatigue_score     — Kumulierter Fatigue-Score (minimieren)
    4. max_away_streak   — Längste konsekutive Auswärtsfolge, liga-weit (minimieren)
    5. off_day_variance  — Varianz der Spieltag-Dichte über Teams (minimieren)
    6. tv_slot_score     — TV-Slot-Attraktivität (maximieren)
    7. event_friction    — Friction durch lokale Events (minimieren)
    8. constraint_violations — Harte Constraint-Verletzungen (muss 0 sein)

Für Dominanz-Vergleiche werden alle Dimensionen als "niedriger = besser"
normiert (revenue_usd und tv_slot_score werden negiert).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

from .data_loader import Team
from .event_conflicts import LocalEvent, event_friction_score, load_local_events
from .player_fatigue import compute_fatigue_report
from .revenue import RevenueModel, build_division_rivals, season_revenue
from .season import Season
from .travel import compute_season_travel
from .tv_slots import TvSlotConfig, compute_tv_slot_score


# ====================================================================
# ParetoBundle
# ====================================================================

@dataclass(frozen=True)
class ParetoBundle:
    """8-dimensionales Score-Bundle für die Pareto-Front.

    Alle Werte sind absolute Scores (nicht Deltas wie in ScoreBundle).
    """
    travel_km: float            # Gesamtdistanz aller Teams (km)
    revenue_usd: float          # Erwarteter Liga-Revenue (USD)
    fatigue_score: float        # Kumulierter Fatigue-Score (player_fatigue.py)
    max_away_streak: int        # Worst-Case Auswärts-Streak (Tage), liga-weit
    off_day_variance: float     # Varianz der Spieltag-Dichte (niedriger = gleichmäßiger)
    tv_slot_score: float        # Summe aller Spiel-TV-Scores (höher = besser)
    event_friction: float       # Summe der Event-Friction-Penalties (niedriger = besser)
    constraint_violations: int  # Hard-Constraint-Verletzungen (0 = valid)

    # ---- Dominanz-Logik ----

    def _normalized(self) -> Tuple[float, ...]:
        """Alle Dimensionen als "kleiner = besser"-Vektor für Dominanz-Checks.

        revenue_usd und tv_slot_score werden negiert (higher = better → flip).
        """
        return (
            self.travel_km,
            -self.revenue_usd,       # maximieren → negieren
            self.fatigue_score,
            float(self.max_away_streak),
            self.off_day_variance,
            -self.tv_slot_score,     # maximieren → negieren
            self.event_friction,
            float(self.constraint_violations),
        )

    def dominates(self, other: "ParetoBundle") -> bool:
        """Gibt True zurück, wenn self other dominiert.

        A dominiert B, wenn A in allen Dimensionen ≤ B ist und
        mindestens in einer Dimension strikt < B (kleiner = besser).
        """
        a = self._normalized()
        b = other._normalized()
        at_least_one_better = False
        for ai, bi in zip(a, b):
            if ai > bi:
                return False
            if ai < bi:
                at_least_one_better = True
        return at_least_one_better

    def is_valid(self) -> bool:
        return self.constraint_violations == 0

    def to_dict(self) -> Dict:
        return asdict(self)

    @property
    def dimension_names(self) -> Tuple[str, ...]:
        return (
            "travel_km",
            "revenue_usd",
            "fatigue_score",
            "max_away_streak",
            "off_day_variance",
            "tv_slot_score",
            "event_friction",
            "constraint_violations",
        )


# ====================================================================
# ParetoPoint — Bundle + zugehöriger Plan
# ====================================================================

@dataclass
class ParetoPoint:
    """Ein Punkt auf der Pareto-Front: Score-Bundle + zugehöriger Plan."""
    bundle: ParetoBundle
    season: Season
    label: str = ""          # z.B. "anchor_travel_min" oder "interior_3"
    profile_used: str = ""   # welches Profil diesen Plan generiert hat
    seed_used: int = 42
    # Review-Fix Runde 2 (2026-06-10, Punkt 0): Publish-Gate-Ergebnis je Punkt.
    # None = nicht gemessen (alte Aufrufer); sonst via publish_gate.publishable_
    # report (Baseline = baseline_season). ACHTUNG: die Pareto-SA selbst ist
    # (noch) nicht regel-gewahr — Punkte koennen NICHT PUBLIZIERBAR sein; das
    # wird hier sichtbar gemacht statt verschwiegen.
    publishable: Optional[bool] = None
    publish_gate_summary: str = ""


# ====================================================================
# Hilfsfunktionen für off_day_variance
# ====================================================================

def _compute_off_day_variance(season: Season, team_ids: List[str]) -> float:
    """Liga-Varianz der mittleren Spieltag-Gaps über Teams.

    Audit A11 (Sprint A-2): Die frühere Definition als „Varianz der
    Spieltag-Dichte" war unter dem aktuellen Generator (fixe Spielanzahl je
    Team, keine Doubleheader) effektiv **konstant** über alle SA-Pläne und
    diskriminierte daher nicht — die Pareto-Dimension trug keine Information.
    Stattdessen messen wir jetzt eine Größe, die mit dem Schedule wirklich
    variiert: die **Varianz der team-spezifischen mittleren Gaps** zwischen
    aufeinanderfolgenden Spieltagen.

    Vorgehen je Team T:
      1. Sortierte distinkte Spieltage von T bestimmen.
      2. Gaps (in Tagen) zwischen aufeinanderfolgenden Spieltagen.
      3. Mittlerer Gap je Team mean_T.
    Über alle Teams: Varianz von {mean_T}. Niedriger = gleichmäßigere
    Off-Day-Verteilung zwischen Teams (= „fairer" über die Liga).
    """
    if not team_ids or not season.games:
        return 0.0
    per_team_mean_gap: List[float] = []
    for tid in team_ids:
        play_days = sorted({g.date for g in season.games
                            if g.home == tid or g.away == tid})
        if len(play_days) < 2:
            continue
        gaps = [
            (play_days[i + 1] - play_days[i]).days
            for i in range(len(play_days) - 1)
        ]
        per_team_mean_gap.append(sum(gaps) / len(gaps))
    if len(per_team_mean_gap) < 2:
        return 0.0
    mean = sum(per_team_mean_gap) / len(per_team_mean_gap)
    return sum((m - mean) ** 2 for m in per_team_mean_gap) / len(per_team_mean_gap)


def _validate_constraints(season: Season, team_ids: List[str]) -> int:
    """Zählt Hard-Constraint-Verletzungen (AC-2.1.8 + AC-2.1.9).

    Gibt die Gesamtzahl der Verletzungen zurück (0 = valid).
    """
    from .player_fatigue import max_consecutive_away_days, max_games_without_off_day
    violations = 0
    for tid in team_ids:
        if max_consecutive_away_days(season, tid) > 13:
            violations += 1
        if max_games_without_off_day(season, tid) > 20:
            violations += 1
    return violations


# ====================================================================
# compute_pareto_bundle — zentraler Aggregator
# ====================================================================

def compute_pareto_bundle(
    season: Season,
    teams: List[Team],
    events: Optional[List[LocalEvent]] = None,
    tv_cfg: Optional[TvSlotConfig] = None,
    revenue_model: Optional[RevenueModel] = None,
    validate_hard_constraints: bool = True,
) -> ParetoBundle:
    """Berechnet das vollständige 8-dimensionale ParetoBundle für einen Plan.

    Args:
        season:                   Der zu bewertende MLB-Saisonplan.
        teams:                    Liste aller 30 Teams (für Travel + Revenue).
        events:                   Lokale Events; wenn None, wird data/local_events.json geladen.
        tv_cfg:                   TV-Slot-Konfiguration; wenn None, data/tv_slots.json geladen.
        revenue_model:            Revenue-Modell; wenn None, data/revenue_model.json geladen.
        validate_hard_constraints: Wenn True, werden AC-2.1.8/9 geprüft.

    Returns:
        ParetoBundle mit allen 8 Dimensionen.
    """
    team_ids = [t.id for t in teams]

    # 1. Travel
    travel_report = compute_season_travel(season, teams)
    travel_km = travel_report.total_km

    # 2. Revenue
    if revenue_model is None:
        revenue_model = RevenueModel.load()
    rivals = build_division_rivals(teams)
    revenue_usd = season_revenue(season, revenue_model, rivals)

    # 3. Fatigue
    fatigue_report = compute_fatigue_report(season, team_ids)
    fatigue_score = fatigue_report.league_total_fatigue
    max_away_streak = fatigue_report.worst_consec_away

    # 4. Off-Day-Variance
    off_day_variance = _compute_off_day_variance(season, team_ids)

    # 5. TV-Slot-Score
    if tv_cfg is None:
        tv_cfg = TvSlotConfig.load()
    tv_report = compute_tv_slot_score(season, tv_cfg)
    tv_slot_score = tv_report.total_score

    # 6. Event-Friction
    if events is None:
        events = load_local_events()
    friction_report = event_friction_score(season, events)
    event_friction = friction_report.total_score

    # 7. Hard-Constraint-Verletzungen
    if validate_hard_constraints:
        cv = _validate_constraints(season, team_ids)
    else:
        cv = 0

    return ParetoBundle(
        travel_km=travel_km,
        revenue_usd=revenue_usd,
        fatigue_score=fatigue_score,
        max_away_streak=max_away_streak,
        off_day_variance=off_day_variance,
        tv_slot_score=tv_slot_score,
        event_friction=event_friction,
        constraint_violations=cv,
    )
