"""Sprint 5.5 (D1–D3) — Chronobiologie / Jet-Lag-Belastung (konservativ, fair, gegated).

**Evidenzbasis (D1):**
- Song, Severini & Allada (2017), *How jet lag impairs Major League Baseball
  performance*, **PNAS** 114(6):1407–1412 — Ostwärts-Reisen über Zeitzonen beeinträchtigen
  die Leistung stärker als Westwärts; Effekt skaliert mit überquerten Zeitzonen und klingt
  mit Erholung ab (~1 Zeitzone/Tag Resynchronisation).
- Recht, Lew & Schwartz (1995), *Baseball teams beaten by jet lag*, **Nature** 377:583 —
  früher Beleg für Reiserichtungs-Effekt.
- Resynchronisations-Rate ~1 TZ/Tag: Eastman & Burgess (2009), *How To … circadian rhythm*.

**Konservative Diskontierung (D1):** Die Originalstudien (1992–2011 bzw. 1995) entstanden
VOR modernen Charter-Flügen, verschärften CBA-Ruheregeln (Off-Day-Pflichten, PT→ET-Regel)
und Schlaf-/Recovery-Programmen der Clubs. Wir diskontieren die rohen Effektgrößen daher
stark (Default ``DISCOUNT = 0.25``) — die Gewichte sind ein **relativer Belastungsindex**,
keine kausale Leistungsprognose.

**Mapping-Transparenz (D2):** Der Index ist NICHT in „Siege" oder USD übersetzt, sondern
ein dimensionsloses, monoton interpretierbares Maß der akkumulierten zirkadianen
Fehlanpassung. Das Mapping „TZ-Überquerung → Indexpunkte" ist hier offengelegt und über
``DISCOUNT`` / die Richtungs-Gewichte sensitivitätstestbar.

**Fairness / Symmetrie (D3):** Es werden für **alle** Teams **identische** Gewichte und
dasselbe Modell verwendet — kein team-spezifischer Vorteil. Der Index misst nur die durch
den **Reiseplan** auferlegte Belastung; er bevorzugt/benachteiligt kein Team strukturell.
Die Verteilung wird per Gini-Koeffizient als Fairness-Kennzahl ausgewiesen.

**Gating:** reine Analyse-/Reporting-Schicht; **kein** Default-Eingriff in den
deterministischen Optimierpfad. Optional als gegateter Score nutzbar (Default-Gewicht 0).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .season import Season
from .timezones import tz_offset_hours

# --- Gewichte (konservativ, dimensionslos; Quellen siehe Modul-Docstring) ---
# Ostwärts > Westwärts (PNAS 2017). Werte als relative Belastung je überquerter Zeitzone.
EAST_WEIGHT_PER_TZ = 1.0
WEST_WEIGHT_PER_TZ = 0.6
# Resynchronisation: abgebaute „Zeitzonen-Schuld" pro Kalendertag (~1 TZ/Tag).
RECOVERY_TZ_PER_DAY = 1.0
# Konservative Gesamt-Diskontierung (moderne Charter/Ruheregeln). 0..1.
DISCOUNT = 0.25


@dataclass(frozen=True)
class JetLagResult:
    per_team: Dict[str, float]
    gini: float
    weights: dict

    @property
    def total(self) -> float:
        return sum(self.per_team.values())

    @property
    def worst(self) -> List[str]:
        return [t for t, _ in sorted(self.per_team.items(), key=lambda kv: -kv[1])[:5]]


def _gini(values: List[float]) -> float:
    """Gini-Koeffizient (0 = perfekt gleich, →1 = ungleich). Für Fairness-Reporting."""
    xs = sorted(v for v in values if v >= 0)
    n = len(xs)
    if n == 0 or sum(xs) == 0:
        return 0.0
    cum = 0.0
    for i, x in enumerate(xs, 1):
        cum += i * x
    return (2 * cum) / (n * sum(xs)) - (n + 1) / n


def team_jet_lag_index(
    season: Season, team: str, teams_by_id,
    *, east_w: float = EAST_WEIGHT_PER_TZ, west_w: float = WEST_WEIGHT_PER_TZ,
    recovery: float = RECOVERY_TZ_PER_DAY, discount: float = DISCOUNT,
) -> float:
    """Akkumulierte zirkadiane Fehlanpassung eines Teams über die Saison.

    Modell (konservativ, transparent): eine „zirkadiane Schuld" D wird bei jedem
    Ortswechsel um die (gewichteten) überquerten Zeitzonen erhöht (ostwärts stärker)
    und baut sich täglich um ``recovery`` ab. Der Index ist das Tagesintegral von D
    (Σ der täglichen Restschuld), final mit ``discount`` skaliert. Fair: identisch
    für alle Teams.
    """
    seq = []
    seen = set()
    for g in season.games_for_team(team):
        if g.date not in seen:
            seen.add(g.date)
            seq.append((g.date, g.home))   # Spielstadt = Heim-Team
    if len(seq) < 2:
        return 0.0
    debt = 0.0
    integral = 0.0
    prev_city = seq[0][1]
    prev_date = seq[0][0]
    for date, city in seq[1:]:
        gap_days = max(1, (date - prev_date).days)
        # Erholung über die verstrichenen Tage (vor dem neuen Transfer)
        debt = max(0.0, debt - recovery * gap_days)
        if city != prev_city:
            off0 = tz_offset_hours(teams_by_id[prev_city].timezone, date)
            off1 = tz_offset_hours(teams_by_id[city].timezone, date)
            hops = abs(off1 - off0)
            if hops:
                # America-Offsets sind negativ; weiter östlich = weniger negativ
                # (z. B. LA -8 → NY -5) → off1 > off0 bedeutet Ostwärts-Reise.
                eastward = off1 > off0
                debt += hops * (east_w if eastward else west_w)
        integral += debt * gap_days
        prev_city, prev_date = city, date
    return integral * discount


def season_jet_lag(
    season: Season, teams: List, teams_by_id=None,
    *, east_w: float = EAST_WEIGHT_PER_TZ, west_w: float = WEST_WEIGHT_PER_TZ,
    recovery: float = RECOVERY_TZ_PER_DAY, discount: float = DISCOUNT,
) -> JetLagResult:
    """Jet-Lag-Index je Team + Gini (Fairness). Reine Analyse, kein Plan-Eingriff."""
    if teams_by_id is None:
        teams_by_id = {t.id: t for t in teams}
    ids = [t.id for t in teams]
    per = {t: team_jet_lag_index(season, t, teams_by_id, east_w=east_w, west_w=west_w,
                                 recovery=recovery, discount=discount) for t in ids}
    return JetLagResult(per_team=per, gini=_gini(list(per.values())),
                        weights={"east_w": east_w, "west_w": west_w,
                                 "recovery": recovery, "discount": discount})
