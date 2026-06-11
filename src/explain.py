"""Menschenlesbare Plan-Begründung (P1-4).

Officials müssen einen Plan nicht nur prüfen, sondern auch **erklären** können:
Warum ist er gut? Wo wurden Trade-offs gemacht? Hält er die Regeln ein — und
woran sieht man das? Dieses Modul erzeugt eine kompakte, deutschsprachige
Begründung (Markdown) aus den bereits berechneten Fakten (Reise, Compliance,
Feasibility, Feiertage). Optional gegen eine Baseline (z. B. den realen Plan).

Bewusst **faktenbasiert und nüchtern** — keine Marketing-Sprache, jede Aussage
ist aus dem Plan messbar. Komplementär zum maschinenlesbaren
``compliance.ComplianceReport``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .season import Season
from .data_loader import Team, teams_by_id as _teams_by_id
from .travel import compute_season_travel, SeasonTravelReport
from .sustainability import compute_co2_report
from .fairness import compute_fairness_report
from .player_fatigue import max_consecutive_away_days
from .compliance import compliance_report, ComplianceReport
from .feasibility import feasibility_report, FeasibilityReport
from .holidays import holiday_report, HolidayReport


@dataclass(frozen=True)
class PlanExplanation:
    season_year: int
    sections: List[tuple]   # (Überschrift, Markdown-Text)

    def to_markdown(self) -> str:
        parts = [f"# Plan-Begründung — Saison {self.season_year}\n"]
        for title, body in self.sections:
            parts.append(f"## {title}\n\n{body}\n")
        return "\n".join(parts)


def _fmt_km(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def _section_overview(season: Season, team_ids: List[str]) -> tuple:
    stats = season.stats()
    body = (
        f"Die Saison umfasst **{_fmt_km(stats['games_total'])} Spiele** über "
        f"**{len(team_ids)} Teams**, vom {stats['first_date']} bis {stats['last_date']}. "
        f"Doubleheader: {stats['doubleheaders']}."
    )
    return ("Überblick", body)


def _section_travel(travel: SeasonTravelReport,
                    baseline: Optional[SeasonTravelReport]) -> tuple:
    total = travel.total_km
    lines = [
        f"Gesamt-Reisedistanz: **{_fmt_km(total)} km** "
        f"(Ø {_fmt_km(travel.avg_km_per_team)} km/Team, Median "
        f"{_fmt_km(travel.median_km)} km)."
    ]
    if baseline is not None:
        delta = total - baseline.total_km
        pct = 100.0 * delta / baseline.total_km if baseline.total_km else 0.0
        rel = "weniger" if delta < 0 else "mehr"
        lines.append(
            f"Gegenüber der Baseline ({_fmt_km(baseline.total_km)} km): "
            f"**{_fmt_km(abs(delta))} km {rel}** ({pct:+.1f} %)."
        )
    # Top-3 reise-intensivste Teams (dort liegen die größten Lasten / Trade-offs).
    top = sorted(travel.by_team.items(), key=lambda kv: -kv[1].total_km)[:3]
    top_txt = "; ".join(
        f"{tid} {_fmt_km(log.total_km)} km (längster Flug {_fmt_km(log.longest_trip_km)} km)"
        for tid, log in top
    )
    lines.append(f"Reise-intensivste Teams: {top_txt}.")
    return ("Reise", "\n\n".join(lines))


def _section_compliance(report: ComplianceReport) -> tuple:
    head = ("✅ **Alle harten Regeln eingehalten.**"
            if report.is_compliant
            else f"⚠️ **{len(report.hard_failures)} harte Regel(n) verletzt.**")
    rows = []
    for c in report.checks:
        mark = "✅" if c.passed else ("⚠️" if c.rule.severity == "soft" else "❌")
        rows.append(f"- {mark} **{c.rule_id}** ({c.rule.name}): {c.measured}. {c.detail}")
    return ("Regel-Compliance", head + "\n\n" + "\n".join(rows))


def _section_feasibility(feas: FeasibilityReport) -> tuple:
    s = feas.summary()
    lines = [
        f"Konsekutive Intercity-Transfers (Back-to-Back, kein Off-Day): "
        f"**{s['n_back_to_back']}**, längster **{_fmt_km(feas.max_consecutive_km)} km**."
    ]
    if feas.violations:
        lines.append(
            f"❌ **{len(feas.violations)} Transfer(s) jenseits des realen MLB-Envelopes** — "
            "diese sind härter als alles, was reale Planer je gelegt haben:"
        )
        for v in feas.violations[:5]:
            lines.append(
                f"  - {v.team}: {v.from_city}→{v.to_city} "
                f"{_fmt_km(v.km)} km / {v.tz_hops} TZ-Hops ({v.depart_date}→{v.arrive_date})"
            )
    else:
        lines.append("✅ Kein Transfer jenseits des realen MLB-Envelopes.")
    if feas.tight:
        lines.append(
            f"ℹ️ {len(feas.tight)} harte, aber real-konforme Turnarounds (ostwärts, "
            "≥2 TZ-Hops, lange Distanz) — Review-Hinweis, kein Verstoß."
        )
    return ("Reise-Feasibility (Getaway-Days)", "\n\n".join(lines))


def _section_roadtrips(season: Season, team_ids: List[str]) -> tuple:
    trips = sorted(
        ((t, max_consecutive_away_days(season, t)) for t in team_ids),
        key=lambda kv: -kv[1],
    )[:5]
    txt = ", ".join(f"{t} ({d} Tage)" for t, d in trips)
    body = (
        f"Längste Road-Trips (Tage am Stück auswärts, Limit 13): {txt}. "
        "Diese Teams tragen die größte Reiselast — hier wurden die schärfsten "
        "Trade-offs zwischen Reise-Minimierung und Fatigue-Limit gemacht."
    )
    return ("Härteste Road-Trips", body)


def _section_sustainability(travel: SeasonTravelReport,
                            base_travel: Optional[SeasonTravelReport]) -> tuple:
    co2 = compute_co2_report(travel)
    fair = compute_fairness_report(travel)
    lines = [
        f"CO₂ gesamt: **{_fmt_km(co2.total_tonnes)} t** "
        f"(Ø {_fmt_km(co2.avg_tonnes_per_team)} t/Team; Faktor "
        f"{co2.kg_per_km_factor:.2f} kg/km, ICAO Jet-A × 737-800)."
    ]
    if base_travel is not None:
        base_co2 = compute_co2_report(base_travel)
        d = co2.total_tonnes - base_co2.total_tonnes
        pct = 100.0 * d / base_co2.total_tonnes if base_co2.total_tonnes else 0.0
        rel = "weniger" if d < 0 else "mehr"
        lines.append(
            f"Gegenüber der Baseline ({_fmt_km(base_co2.total_tonnes)} t): "
            f"**{_fmt_km(abs(d))} t {rel}** ({pct:+.1f} %)."
        )
    lines.append(
        f"Fairness der Reiselast: Gini **{fair.gini:.3f}** "
        f"(0 = perfekt gleich), Disparität {fair.disparity_ratio:.2f}× "
        f"(intensivstes {fair.max_team} vs. ärmstes {fair.min_team})."
    )
    return ("Nachhaltigkeit & Fairness", "\n\n".join(lines))


def _section_holidays(hol: HolidayReport) -> tuple:
    lines = []
    for e in hol.evaluations:
        if not e.in_season:
            continue
        lines.append(f"- **{e.holiday.name}** ({e.holiday.on_date}): {e.note}")
    gaps = hol.league_wide_gaps
    head = (f"Feiertags-Incentive-Score **{hol.total_score:.2f}**. "
            + ("Alle league_wide-Feiertage mit vollem Slate."
               if not gaps else
               f"{len(gaps)} Feiertag(e) ohne vollen Slate (soft, kein Blocker)."))
    return ("Feiertags-Highlights", head + "\n\n" + "\n".join(lines))


def explain_plan(
    season: Season,
    teams: Optional[List[Team]] = None,
    *,
    baseline: Optional[Season] = None,
    compliance: Optional[ComplianceReport] = None,
) -> PlanExplanation:
    """Erzeugt eine deutschsprachige Plan-Begründung.

    ``teams`` optional (sonst aus ``data_loader.load_teams``). ``baseline``
    optional — ein Vergleichsplan (z. B. der reale Plan) für die Reise-Delta.
    ``compliance`` optional — ein vorab berechneter Report (sonst neu berechnet).
    """
    if teams is None:
        from .data_loader import load_teams
        teams = load_teams()
    tbi = _teams_by_id(teams)
    team_ids = sorted({g.home for g in season.games} | {g.away for g in season.games})

    travel = compute_season_travel(season, teams)
    base_travel = compute_season_travel(baseline, teams) if baseline is not None else None
    rep = compliance if compliance is not None else compliance_report(season, team_ids, tbi)
    feas = feasibility_report(season, team_ids, tbi)
    hol = holiday_report(season)

    sections = [
        _section_overview(season, team_ids),
        _section_travel(travel, base_travel),
        _section_compliance(rep),
        _section_feasibility(feas),
        _section_roadtrips(season, team_ids),
        _section_sustainability(travel, base_travel),
        _section_holidays(hol),
    ]
    return PlanExplanation(season_year=season.season, sections=sections)
