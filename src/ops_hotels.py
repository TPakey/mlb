"""Hotel-Empfehlung mit Buchungshistorie (Scheduler-Ops).

Travel-Ops eines MLB-Clubs wählt das Mannschaftshotel jeder Gast-Stadt nach
mehreren Kriterien gleichzeitig: **Nähe zum Stadion** (kurze, planbare Transfers),
**Komfort-/Qualitäts-Tier**, **Security-Tier** (eigener Dienst, kontrollierte
Anlieferung) und der **eigenen Buchungshistorie** (bewährte „preferred
properties" mit guten Bewertungen vs. unbekannte Häuser, die erst auditiert
werden müssen).

Diese Engine bewertet Kandidaten transparent und gibt eine **begründete
Empfehlung** plus die Historie-Lesart aus. Die Kandidaten-/Historie-Daten liefert
in Produktion der Club (`data/team_hotels.json` ist illustrativer Seed); die
Engine selbst ist real und datenunabhängig.

Score = gewichtete Summe aus:
- Nähe (Distanz Hotel→Stadion, näher = besser; via Haversine)
- Qualität (tier 1–5)
- Security (security_tier 1–5)
- Historie (Anzahl positiver Vor-Aufenthalte × Rating; neue Häuser = Audit-Flag)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .distance import haversine_km
from .data_loader import load_teams, teams_by_id

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class HotelCandidate:
    name: str
    lat: float
    lon: float
    tier: int = 3
    security_tier: int = 3
    nightly_rate_usd: Optional[float] = None
    past_stays: int = 0
    past_rating: Optional[float] = None
    notes: str = ""


@dataclass(frozen=True)
class HotelWeights:
    proximity: float = 0.40
    quality: float = 0.20
    security: float = 0.25
    history: float = 0.15


@dataclass(frozen=True)
class HotelScore:
    hotel: HotelCandidate
    distance_km: float
    score: float                 # 0..100
    breakdown: Dict[str, float]
    history_note: str

    @property
    def is_vetted(self) -> bool:
        return self.hotel.past_stays >= 3 and (self.hotel.past_rating or 0) >= 4.0


def load_team_hotels(path: Optional[Path] = None) -> Dict[str, List[HotelCandidate]]:
    path = path or (DATA_DIR / "team_hotels.json")
    raw = json.loads(Path(path).read_text(encoding="utf-8"))["hotels"]
    out: Dict[str, List[HotelCandidate]] = {}
    for tid, lst in raw.items():
        out[tid] = [HotelCandidate(**h) for h in lst]
    return out


def _history_note(h: HotelCandidate) -> str:
    if h.past_stays == 0:
        return "Neues Haus — vor Buchung Security-Audit + Vor-Ort-Check empfohlen."
    if h.past_stays >= 3 and (h.past_rating or 0) >= 4.0:
        return f"Preferred property — {h.past_stays} Vor-Aufenthalte, {h.past_rating:.1f}★."
    return f"{h.past_stays} Vor-Aufenthalt(e), {h.past_rating or '–'}★ — brauchbar, weiter beobachten."


def score_hotel(h: HotelCandidate, ballpark_lat: float, ballpark_lon: float, *,
                weights: HotelWeights = HotelWeights(),
                max_useful_km: float = 25.0) -> HotelScore:
    dist = haversine_km(h.lat, h.lon, ballpark_lat, ballpark_lon)
    # Teil-Scores auf 0..1
    prox = max(0.0, 1.0 - min(dist, max_useful_km) / max_useful_km)
    qual = (h.tier - 1) / 4.0
    sec = (h.security_tier - 1) / 4.0
    hist_raw = min(h.past_stays, 10) / 10.0 * ((h.past_rating or 0) / 5.0)
    parts = {
        "proximity": weights.proximity * prox,
        "quality": weights.quality * qual,
        "security": weights.security * sec,
        "history": weights.history * hist_raw,
    }
    score = 100.0 * sum(parts.values())
    return HotelScore(hotel=h, distance_km=dist, score=score,
                      breakdown={k: round(100 * v, 1) for k, v in parts.items()},
                      history_note=_history_note(h))


def recommend_hotels(team_id: str, *,
                     candidates: Optional[List[HotelCandidate]] = None,
                     weights: HotelWeights = HotelWeights(),
                     tbi: Optional[Dict] = None) -> List[HotelScore]:
    """Rangliste der Hotel-Kandidaten für die Gast-Stadt von ``team_id``.

    ``candidates`` optional — fehlen sie, werden die (illustrativen) Seed-Hotels
    aus ``data/team_hotels.json`` genutzt. Bestes Hotel zuerst.
    """
    tbi = tbi or teams_by_id(load_teams())
    bp = tbi[team_id]
    if candidates is None:
        candidates = load_team_hotels().get(team_id, [])
    scored = [score_hotel(h, bp.lat, bp.lon, weights=weights) for h in candidates]
    scored.sort(key=lambda s: -s.score)
    return scored


def recommendation_markdown(team_id: str, scores: List[HotelScore],
                            city: str = "") -> str:
    L: List[str] = []
    L.append(f"### Hotel-Empfehlung — {city or team_id}")
    if not scores:
        L.append("- Keine Kandidaten hinterlegt. Club-Buchungshistorie importieren "
                 "(`data/team_hotels.json`-Schema).")
        return "\n".join(L)
    best = scores[0]
    L.append(f"**Empfehlung: {best.hotel.name}** "
             f"(Score {best.score:.0f}/100, {best.distance_km:.1f} km zum Stadion). "
             f"{best.history_note}")
    L.append("")
    L.append("| Rang | Hotel | Score | km→Stadion | Tier | Sec | Rate | Historie |")
    L.append("|---:|---|---:|---:|:--:|:--:|---:|---|")
    for i, s in enumerate(scores, 1):
        rate = f"${s.hotel.nightly_rate_usd:.0f}" if s.hotel.nightly_rate_usd else "–"
        L.append(f"| {i} | {s.hotel.name} | {s.score:.0f} | {s.distance_km:.1f} | "
                 f"{s.hotel.tier} | {s.hotel.security_tier} | {rate} | {s.history_note} |")
    return "\n".join(L)
