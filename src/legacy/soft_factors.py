"""Soft-Factor-Bewertung für Serien.

Berechnet pro Serie einen Strafterm, der in die Zielfunktion einfliesst.
Beispiele:
- Heimserie in Boston Anfang April → Wetter-Strafe
- Heimserie in San Diego während Comic-Con → Event-Strafe
- Heimserie in Cincinnati am Opening Day → Bonus (Tradition)
- Premier-Matchup (NYY vs. BOS) nicht in Primetime-Wochenende → Strafe

Alle Gewichte sind transparent gehalten und können später kalibriert werden.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Tuple

from ..data_loader import Team
from .schedule_generator import Series, slot_to_date, SERIES_LENGTH


@dataclass
class SoftScore:
    series: Series
    penalty: float
    reasons: List[str]


def series_window(slot: int) -> Tuple[date, date]:
    start = slot_to_date(slot)
    return start, start + timedelta(days=SERIES_LENGTH - 1)


def _overlaps(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return not (a_end < b_start or b_end < a_start)


def score_series(
    series: Series,
    teams_by_id: Dict[str, Team],
    soft_factors: dict,
    primetime_index: Dict[Tuple[str, str], int] | None = None,
) -> SoftScore:
    """Berechnet Strafe (höher = schlechter) für eine einzelne Serie."""
    s_start, s_end = series_window(series.slot)
    penalty = 0.0
    reasons: List[str] = []

    home = teams_by_id[series.home]

    # 1) Event-/Wetter-Konflikte am Heimstandort
    for ev in soft_factors["events"]:
        if home.id not in ev.team_ids:
            continue
        if _overlaps(s_start, s_end, ev.start, ev.end):
            # Severity 1..5 → Strafe-Skala: 50 pro Severity-Punkt
            p = ev.severity * 50.0
            # Opening-Day-Parade ist umgekehrt: das WOLLEN wir am Eröffnungstag
            if ev.name == "Opening-Day-Parade":
                if series.slot == 0:
                    p = -200.0  # Bonus für Cincinnati am Opening Day
                else:
                    p = 0.0
            penalty += p
            if p != 0:
                reasons.append(f"{ev.name} ({ev.reason})")

    # 2) Kaltwetter-Heimspiele Anfang Saison
    if home.cold_weather and home.roof == "open" and series.slot < 2:
        penalty += 80.0
        reasons.append(f"Kaltwetter-Standort {home.city} in Slot {series.slot}")

    # 3) Heisswetter-Tagserien — Vereinfachung: Standorte in 'hot_july_cities'
    #    bekommen leichten Aufschlag im Hochsommer (Slot 14–17 ≈ Juli)
    hot_cities = soft_factors["weather_profiles"]["hot_july_cities_open_roof"]
    if home.id in hot_cities and 14 <= series.slot <= 17:
        penalty += 30.0
        reasons.append(f"Sommerhitze in {home.city}")

    # 4) Primetime-Matchups sollten an Wochenenden (gerade Slot-Indizes
    #    repräsentieren symbolisch Mi–Fr-Serien, ungerade Sa–Mo). Wir
    #    bestrafen Premier-Matchups, die NICHT auf "Wochenend-Slot" liegen.
    if primetime_index is not None:
        key1 = (series.home, series.away)
        key2 = (series.away, series.home)
        weight = primetime_index.get(key1, primetime_index.get(key2, 0))
        if weight > 0 and series.slot % 2 == 0:
            p = weight * 20.0
            penalty += p
            reasons.append(f"Premier-Matchup {series.home}-{series.away} nicht im Wochenend-Slot")

    return SoftScore(series=series, penalty=penalty, reasons=reasons)


def build_primetime_index(soft_factors: dict) -> Dict[Tuple[str, str], int]:
    idx: Dict[Tuple[str, str], int] = {}
    for entry in soft_factors.get("tv_primetime_matchups", []):
        a, b = entry["teams"]
        w = int(entry["weight"])
        idx[(a, b)] = w
        idx[(b, a)] = w
    return idx


def total_soft_penalty(
    schedule_series: List[Series],
    teams_by_id: Dict[str, Team],
    soft_factors: dict,
) -> Tuple[float, List[SoftScore]]:
    pt = build_primetime_index(soft_factors)
    scores = [score_series(s, teams_by_id, soft_factors, pt) for s in schedule_series]
    return sum(sc.penalty for sc in scores), scores
