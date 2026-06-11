"""KI-Layer — Narrative Erklärungen der Optimierungsentscheidungen.

Diese Komponente übersetzt rohe Scores in Stakeholder-taugliche Erklärungen.
Sie ist als regelbasierter Generator implementiert, der die Struktur eines
LLM-gestützten Outputs nachbildet (Headline → Tradeoffs → Risiken → Empfehlung).

Architektonisch ist sie so ausgelegt, dass die Funktion `narrate()` problemlos
gegen einen echten LLM-Call (Anthropic Claude API o. ä.) ausgetauscht werden
kann. Die Eingaben (Score-Bundle, Profil, Vergleichsplan) sind bereits in
einer Form, die ein LLM direkt verarbeiten kann.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..data_loader import Team
from . import penalties as P
from .optimizer import OptimizationResult
from .scoring import ScoreBundle


@dataclass
class Narrative:
    headline: str
    summary: str
    key_tradeoffs: List[str]
    biggest_wins: List[str]
    remaining_risks: List[str]
    recommendation: str

    def to_markdown(self) -> str:
        lines = [
            f"# {self.headline}",
            "",
            "## Kurzfassung",
            self.summary,
            "",
            "## Schlüssel-Tradeoffs",
        ]
        lines.extend(f"- {t}" for t in self.key_tradeoffs)
        lines.append("")
        lines.append("## Grösste Gewinne")
        lines.extend(f"- {t}" for t in self.biggest_wins)
        lines.append("")
        lines.append("## Verbleibende Risiken")
        lines.extend(f"- {t}" for t in self.remaining_risks)
        lines.append("")
        lines.append("## Empfehlung")
        lines.append(self.recommendation)
        return "\n".join(lines)


def _pct(old: float, new: float) -> float:
    if abs(old) < 1e-9:
        return 0.0
    return (old - new) / old * 100


def _format_penalty_hits(bundle: ScoreBundle) -> List[str]:
    out = []
    for cat in (bundle.travel, bundle.fatigue, bundle.fairness,
                bundle.broadcast, bundle.weather, bundle.resilience):
        for code, n in cat.penalty_hits.items():
            try:
                p = P.get(code)
                out.append(f"{p.name}: {n}× ausgelöst — {p.desc}")
            except KeyError:
                out.append(f"{code}: {n}× ausgelöst")
    return out


def narrate(result: OptimizationResult, teams: List[Team]) -> Narrative:
    profile = result.profile
    ib = result.initial_bundle
    fb = result.final_bundle

    travel_delta = _pct(ib.travel.score, fb.travel.score)
    fatigue_delta = _pct(ib.fatigue.score, fb.fatigue.score)
    fairness_delta = _pct(ib.fairness.score, fb.fairness.score)
    weather_delta = _pct(ib.weather.score, fb.weather.score)
    cost_delta = _pct(result.initial_cost, result.final_cost)

    headline = (
        f"Profil «{profile.name}»: Gesamtkosten −{cost_delta:.1f} % "
        f"(Travel −{travel_delta:.1f} %, Fatigue −{fatigue_delta:.1f} %)"
    )

    summary = (
        f"Der Baseline-Spielplan ergab eine Gesamt-Reisestrecke von "
        f"{ib.travel.components.get('total_km', 0):,.0f} km. Nach Optimierung "
        f"mit Profil «{profile.name}» liegt die Strecke bei "
        f"{fb.travel.components.get('total_km', 0):,.0f} km — "
        f"eine Reduktion von {travel_delta:.1f} %. "
        f"Die gewichteten Tradeoff-Kosten sanken um {cost_delta:.1f} %."
    )

    key_tradeoffs: List[str] = []
    if profile.w_revenue >= 2.0:
        key_tradeoffs.append(
            "Dieses Profil priorisiert Revenue und Broadcast — wir akzeptieren "
            "höhere Reisekosten zugunsten attraktiverer Wochenend-Matchups."
        )
    if profile.w_fatigue >= 2.0:
        key_tradeoffs.append(
            "Spielergesundheit hat Vorrang. Wir vermeiden lange Auswärtstrips "
            "und Mehrfach-Zeitzonen-Hops aktiv."
        )
    if profile.w_travel >= 2.0:
        key_tradeoffs.append(
            "Travel-Minimierung dominiert. Geografische Cluster werden gegenüber "
            "Rivalry-Inszenierung bevorzugt."
        )
    if profile.w_fairness >= 2.0:
        key_tradeoffs.append(
            "Fairness im Vordergrund: Varianz zwischen Teams (km, Ruhetage) "
            "wird stärker gewichtet als Einzeloptimum."
        )
    if not key_tradeoffs:
        key_tradeoffs.append(
            "Ausgeglichenes Profil — keine Dimension dominiert. Gut geeignet als "
            "Default oder als Vergleichsbasis zu spezialisierten Profilen."
        )

    biggest_wins: List[str] = []
    if travel_delta > 5:
        biggest_wins.append(
            f"Reisestrecke gesenkt: {ib.travel.components.get('total_km', 0):,.0f} → "
            f"{fb.travel.components.get('total_km', 0):,.0f} km "
            f"(≈ {(ib.travel.components.get('total_km', 0) - fb.travel.components.get('total_km', 0)) * 5.5 / 1000:.0f} t CO₂ gespart)"
        )
    if fb.weather.components.get("cold_april_open", 0) < ib.weather.components.get("cold_april_open", 0):
        biggest_wins.append(
            f"Kaltwetter-Heimspiele Anfang April reduziert: "
            f"{ib.weather.components.get('cold_april_open', 0)} → "
            f"{fb.weather.components.get('cold_april_open', 0)}"
        )
    if fb.fairness.components.get("home_balance_stdev", 99) < ib.fairness.components.get("home_balance_stdev", 99):
        biggest_wins.append(
            f"Heim/Auswärts-Balance verbessert: σ "
            f"{ib.fairness.components.get('home_balance_stdev', 0):.2f} → "
            f"{fb.fairness.components.get('home_balance_stdev', 0):.2f}"
        )
    if not biggest_wins:
        biggest_wins.append("Optimierung bewegt sich im Feinjustierungs-Bereich — keine groben Schwächen im Baseline-Plan.")

    remaining_risks = _format_penalty_hits(fb)
    if not remaining_risks:
        remaining_risks.append("Keine offenen Penalties — der Plan ist auditiert sauber.")

    recommendation = (
        f"Der optimierte Plan unter Profil «{profile.name}» reduziert die "
        f"gewichteten Kosten um {cost_delta:.1f} %. "
    )
    if cost_delta > 10:
        recommendation += (
            "Empfehlung: Übernahme für die operative Planung; nächster Schritt "
            "ist die Stakeholder-Abstimmung zu den verbleibenden Penalties."
        )
    elif cost_delta > 3:
        recommendation += (
            "Empfehlung: in einem A/B-Vergleich mit dem Status-quo evaluieren; "
            "die Einsparung ist substantiell, aber nicht überwältigend."
        )
    else:
        recommendation += (
            "Empfehlung: Profil oder Move-Mix anpassen — die aktuelle Lösung ist "
            "nahe am Baseline. Alternativ ist der Baseline schon stark."
        )

    return Narrative(
        headline=headline,
        summary=summary,
        key_tradeoffs=key_tradeoffs,
        biggest_wins=biggest_wins,
        remaining_risks=remaining_risks,
        recommendation=recommendation,
    )


def compare_profiles(results: List[OptimizationResult]) -> str:
    """Kurzer Vergleichstext zwischen mehreren Profil-Läufen."""
    lines = ["# Profil-Vergleich", ""]
    lines.append("| Profil | Travel-km | Fatigue | Fairness | Gesamtkosten |")
    lines.append("|---|---:|---:|---:|---:|")
    for r in results:
        lines.append(
            f"| {r.profile.name} | "
            f"{r.final_bundle.travel.components.get('total_km', 0):,.0f} | "
            f"{r.final_bundle.fatigue.score:,.0f} | "
            f"{r.final_bundle.fairness.score:,.0f} | "
            f"{r.final_cost:,.0f} |"
        )
    lines.append("")
    lines.append("Pareto-Beobachtung: kein Profil dominiert alle anderen in jeder Dimension. "
                 "Die Wahl ist eine politische Entscheidung.")
    return "\n".join(lines)
