"""Compliance-Report — jede harte Regel ↔ Quelle, mit Messwert (P1-4).

Damit ein Plan für League Officials **verteidigbar** ist, reicht "es passt schon"
nicht. Officials müssen pro Regel zeigen können: *welche* Regel, *woher* sie
stammt (CBA-Artikel / MLB-Konvention / Definitions-Doc), *wie* sie durchgesetzt
wird, *welcher Wert* gemessen wurde und ob er besteht. Dieses Modul liefert genau
das — als menschenlesbaren **und** maschinenlesbaren (JSON) Compliance-Report mit
**Provenance-Register**.

Geprüfte Regeln (Tabelle korrigiert 2026-06-10 — Review-Fix P3-9; maßgeblich
ist immer das RULES-Register unten, die Tabelle ist nur Übersicht):

| ID                | Regel                                   | Härte | Quelle                        |
|-------------------|-----------------------------------------|-------|-------------------------------|
| AC-2.1.8          | ≤ 13 Tage am Stück auswärts (Qualität)  | soft  | Operative Heuristik (NICHT CBA; regulations/FINDING_AC-2.1.8_vs_CBA.md) |
| AC-2.1.9          | ≤ 20 Spieltage ohne Off-Day             | hard  | CBA V(C)(12)                  |
| CBA-PTET          | PT→ET erzwingt Off-Day                  | hard  | CBA V(C)(11)                  |
| SCHED-162         | Spielzahl je Team (Vollständigkeit)     | hard  | MLB-Saisonregel               |
| SCHED-HA          | 81 Heim / 81 Auswärts je Team           | hard  | MLB-Saisonregel               |
| FEAS-GETA         | kein Back-to-Back über realem Envelope  | hard  | MLB-Ops + src/feasibility     |
| STARTTIME-GETAWAY | Getaway-Startzeit (gegated)             | hard  | CBA V(C)(8)                   |
| STARTTIME-NIGHTDAY| Tag-nach-Nacht andere Stadt (gegated)   | hard  | CBA V(C)(9)                   |
| STARTTIME-DAYMIN  | Tag-Spiel-Mindeststart (gegated)        | soft  | CBA V(C)(6)/(7)               |
| CBA-OFFDAY        | Off-Day-Verteilung (as-played: inform.) | soft* | CBA V(C)(13)                  |
| CBA-DH            | Doubleheader-Limits (as-played: inform.)| soft* | CBA V(C)(14)/(15)             |
| VENUE-AVAIL       | kein Heimspiel an Belegungstag (opt-in) | hard  | src/event_conflicts           |
| PIN-LEAGUE        | Feiertags-Slates (league_wide voll)     | soft  | data/holiday_pins.json        |

"hard" = Verstoß macht den Plan für die Liga unbrauchbar. "soft" = Qualitäts-/
Incentive-Hinweis, kein Blocker. *CBA-OFFDAY/CBA-DH sind Originalplan-Regeln:
auf as-played-Daten informativ; auf Optimierer-Output werden sie HART über das
Publish-Gate durchgesetzt (src/publish_gate.py, Review-Fix P0-2 2026-06-10).

Reines Reporting — verändert keinen Plan. Konsumiert ``player_fatigue``,
``feasibility``, ``holidays``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .season import Season
from .player_fatigue import max_consecutive_away_days, max_games_without_off_day
from .feasibility import feasibility_report, FeasibilityThresholds, DEFAULT_THRESHOLDS
from .holidays import holiday_report


# ====================================================================
# Provenance-Register (statisch) — woher die Regel kommt
# ====================================================================

@dataclass(frozen=True)
class ComplianceRule:
    rule_id: str
    name: str
    authority: str        # "CBA" | "MLB-Saisonregel" | "MLB-Ops" | "League-Konvention"
    reference: str        # Artikel / Konvention
    definition_doc: str   # Repo-Doc mit der verbindlichen Definition
    mechanism: str        # wie der Plan diese Regel durchsetzt
    severity: str         # "hard" | "soft"
    limit_text: str       # menschenlesbares Limit

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id, "name": self.name,
            "authority": self.authority, "reference": self.reference,
            "definition_doc": self.definition_doc, "mechanism": self.mechanism,
            "severity": self.severity, "limit_text": self.limit_text,
        }


RULES: Dict[str, ComplianceRule] = {
    "AC-2.1.8": ComplianceRule(
        rule_id="AC-2.1.8",
        name="Road-Trip-Länge (operatives Qualitätsziel, KEIN CBA-Erfordernis)",
        authority="Operative Heuristik",
        reference="NICHT im CBA Article V belegbar (verifiziert 2026-06-09, siehe "
                  "regulations/FINDING_AC-2.1.8_vs_CBA.md). 'Days away ≤ 13' ist eine "
                  "Belastungs-Heuristik ('13-Game-Gauntlet'), kein Vertrags-Limit. Das "
                  "harte CBA-Muss ist V(C)(12) = AC-2.1.9 (≤ 20 konsekutiv).",
        definition_doc="docs/CBA_DEFINITIONS.md",
        mechanism="Weiches Ziel: SA-Penalty (λ=1e6) minimiert lange Road-Trips; "
                  "Warm-Start startet von einem realen Plan. KEINE harte ≤13-Garantie.",
        severity="soft",
        limit_text="Ziel ≤ 13 Tage (weich; erstes bis letztes Auswärtsspiel, Off-Days inkl.)",
    ),
    "AC-2.1.9": ComplianceRule(
        rule_id="AC-2.1.9",
        name="Maximale Spieltage ohne Off-Day",
        authority="CBA",
        reference="CBA / MoU — ≥ 1 Off-Day je 21-Tage-Fenster",
        definition_doc="docs/CBA_DEFINITIONS.md",
        mechanism="Strukturell via periodische Break-Days (max_gap=21) im CP-SAT "
                  "generator._periodic_break_days.",
        severity="hard",
        limit_text="≤ 20 Spieltage je rollierendem 21-Tage-Fenster (DH = 1 Spieltag)",
    ),
    "CBA-PTET": ComplianceRule(
        rule_id="CBA-PTET",
        name="Pacific→Eastern erzwingt Off-Day (CBA V(C)(11))",
        authority="CBA",
        reference="CBA 2022–2026 Article V(C)(11): 'An open day shall be scheduled "
                  "where travel from cities in the Pacific Time Zone to cities in the "
                  "Eastern Time Zone is required …'. Verbatim: "
                  "regulations/CBA_2022-2026_Article_V_Scheduling.md.",
        definition_doc="regulations/CBA_2022-2026_Article_V_Scheduling.md",
        mechanism="Detektion: für jedes Team kein konsekutiver Spieltag PT-Stadt → "
                  "ET-Stadt ohne dazwischenliegenden Off-Day. Konservativ: die ≤7 "
                  "Liga-Ausnahmen (späte ET-Startzeit) werden NICHT modelliert (brauchen "
                  "Startzeiten, Sprint 5.1) — wir erzwingen den strikten Default, was nur "
                  "strenger ist. Realer 2024+2025-Plan: 0 solche Transfers (gemessen).",
        severity="hard",
        limit_text="0 PT→ET-Spieltagsfolgen ohne Off-Day (PT=America/Los_Angeles; "
                   "ET=America/New_York, America/Toronto)",
    ),
    "CBA-OFFDAY": ComplianceRule(
        rule_id="CBA-OFFDAY",
        name="Off-Day-Verteilung (CBA V(C)(13))",
        authority="CBA",
        reference="CBA 2022–2026 Article V(C)(13): '… a Club shall not be scheduled for "
                  "more than two open days in any seven-day period. All Clubs will be "
                  "scheduled for at least seven open days over the final 67 days … at "
                  "least three … over the final 32 days …'. Verbatim: "
                  "regulations/CBA_2022-2026_Article_V_Scheduling.md.",
        definition_doc="src/schedule_rules.py (check_offday_distribution)",
        mechanism="src.schedule_rules.check_offday_distribution; All-Star-Break (V(C)(17)) "
                  "aus dem ≤2/7-Fenster ausgenommen. ORIGINALPLAN-Regel → harter Guard auf "
                  "Optimierer-Output (schedule_kind='original'); auf as-played-Daten "
                  "WEICH/informativ, weil Makeups/Rainouts artefakt-Open-Days erzeugen "
                  "(finding-as-played-data). Gemessen real 2024/2025: nur as-played-Artefakte "
                  "(z. B. COL 2025-04-17-Rainout-Cluster), keine echten Verstöße.",
        severity="soft",
        limit_text="≤2 Open Days/7-Tage-Fenster (ohne ASB); ≥7 in letzten 67; ≥3 in letzten 32",
    ),
    "CBA-DH": ComplianceRule(
        rule_id="CBA-DH",
        name="Doubleheader-Limits (CBA V(C)(14)/(15))",
        authority="CBA",
        reference="CBA 2022–2026 Article V(C)(14): 'Doubleheaders shall not be scheduled "
                  "on consecutive dates in the original schedule …'; V(C)(15): 'Twi-night "
                  "doubleheaders will be limited … to three per home Club per season. A "
                  "twi-night doubleheader will not be scheduled on a getaway day.' "
                  "Verbatim: regulations/CBA_2022-2026_Article_V_Scheduling.md.",
        definition_doc="src/schedule_rules.py (check_doubleheader_limits)",
        mechanism="src.schedule_rules.check_doubleheader_limits: keine DH an Folgetagen "
                  "je Club; Twi-Night-DH (erstes Spiel ≥16:00, braucht Startzeiten) ≤3/"
                  "Heimclub und nicht am Getaway-Tag. ORIGINALPLAN-Regel → harter Guard auf "
                  "Optimierer-Output; auf as-played WEICH/informativ (Makeup-DHs an "
                  "Folgetagen = Artefakte). Gemessen: 2024 0, 2025 4 Folgetag-DH = "
                  "Rainout-Makeups (BAL/BOS, CHC/MIL).",
        severity="soft",
        limit_text="keine DH an Folgetagen; Twi-Night-DH ≤3/Heimclub & nicht am Getaway",
    ),
    "STARTTIME-GETAWAY": ComplianceRule(
        rule_id="STARTTIME-GETAWAY",
        name="Getaway-Startzeit (CBA V(C)(8))",
        authority="CBA",
        reference="CBA 2022–2026 Article V(C)(8): 'The latest possible start time for "
                  "getaway games … shall be determined by taking the portion of the "
                  "in-flight time that exceeds 2 1/2 hours, and subtracting that amount "
                  "of time from 7 P.M.' (Ausnahme: ESPN Sunday Night Baseball, "
                  "Reschedules). In-Flight = Appendix C. Verbatim: "
                  "regulations/CBA_2022-2026_Article_V_Scheduling.md.",
        definition_doc="docs/SPRINT_5_1_STARTTIME_DESIGN.md",
        mechanism="src.start_times.validate_getaway_times: latest = 19:00 − max(0, "
                  "inflight−2:30) aus Appendix C; gegated (nur aktiv, wenn Startzeiten "
                  "zugewiesen/vorhanden). Vergleich mit per-Club First-Pitch-Konvention "
                  "(±40 min, empirisch: nominale 7-PM-Anker, reale Erstwürfe 7:05–7:40). "
                  "Gemessen real 2024+2025: 0 Verstöße; reise-bindende Fälle (inflight>2:30) "
                  "exakt reproduziert.",
        severity="hard",
        limit_text="Getaway-Start ≤ 19:00 − max(0, inflight−2:30) (±40 min Konvention; "
                   "SNB/Reschedule ausgenommen)",
    ),
    "STARTTIME-NIGHTDAY": ComplianceRule(
        rule_id="STARTTIME-NIGHTDAY",
        name="Tag-nach-Nacht in anderer Stadt (CBA V(C)(9))",
        authority="CBA",
        reference="CBA 2022–2026 Article V(C)(9): 'No Club shall be scheduled … to "
                  "start a game prior to 5 P.M. when one of the Clubs played a game the "
                  "prior evening in a different city with a start time of 7 P.M. or "
                  "later, except …' (a) inflight ≤1:30 + Feiertag/Home-Opener; (b) ≤6× "
                  "Reise zu den Cubs; (c) Reschedule inflight ≤1:30. Verbatim: "
                  "regulations/CBA_2022-2026_Article_V_Scheduling.md.",
        definition_doc="docs/SPRINT_5_1_STARTTIME_DESIGN.md",
        mechanism="src.start_times.validate_nightday_times mit Feiertags-/Home-Opener-/"
                  "Cubs-Ausnahmen; gegated. Gemessen real 2024+2025: 0 Verstöße "
                  "(die 3 Roh-Treffer 2025 = exakt die CBA-Ausnahmen Home-Opener PIT, "
                  "July 4th, Labor Day).",
        severity="hard",
        limit_text="kein Start < 17:00 nach ≥19:00-Auswärtsspiel am Vortag (Ausnahmen "
                   "V(C)(9)(a)-(c))",
    ),
    "STARTTIME-DAYDH": ComplianceRule(
        rule_id="STARTTIME-DAYDH",
        name="Kein Spätstart vor Day-Doubleheader (CBA V(C)(5))",
        authority="CBA",
        reference="CBA 2022–2026 Article V(C)(5): 'a game will not be scheduled "
                  "to start after 5 P.M. if either Club is scheduled to play a day "
                  "doubleheader the next day'. Verbatim: "
                  "regulations/CBA_2022-2026_Article_V_Scheduling.md.",
        definition_doc="src/start_times.py (validate_day_dh_prior_times)",
        mechanism="src.start_times.validate_day_dh_prior_times (Day-DH = erstes "
                  "DH-Spiel < 16:00); im Zuweiser assign_start_times als 17:00-Cap "
                  "DURCHGESETZT (Review-Runde 2, Punkt 3 — vorher gar nicht "
                  "modelliert, als 'Datengrenze' dokumentiert). Auf as-played-Daten "
                  "sind Folgetag-Day-DHs Rainout-Makeups → rescheduled_pks nimmt "
                  "sie aus (gemessen 2024/2025: roh 5/5, ohne Makeups 0/0; auf "
                  "zugewiesenen Zeiten 0 per Konstruktion).",
        severity="hard",
        limit_text="kein Start > 17:00, wenn ein Club am Folgetag ein "
                   "Day-Doubleheader (erstes Spiel < 16:00) spielt",
    ),
    "STARTTIME-DAYMIN": ComplianceRule(
        rule_id="STARTTIME-DAYMIN",
        name="Tag-Spiel-Mindeststartzeit (CBA V(C)(6)/(7), weich)",
        authority="CBA",
        reference="CBA 2022–2026 Article V(C)(6): 'Day games shall not be scheduled … "
                  "to start before 1 P.M., except … between Noon and 1 P.M., if each "
                  "Club meets … (a) off-day previous day; or (b) game in same city "
                  "within previous 24 hours.' Frühere Starts (Patriots'/Education/"
                  "Holiday-Morning) sind etablierte, waiver-gedeckte Liga-Specials "
                  "(V(C)(18)).",
        definition_doc="docs/SPRINT_5_1_STARTTIME_DESIGN.md",
        mechanism="src.start_times.validate_day_min_times; gegated. WEICH, weil der "
                  "reale Plan ~0,4 % dokumentierte Früh-Specials enthält (Patriots' Day "
                  "Fenway 11:10, Education-Day, Feiertags-Morgenspiele). Der Optimierer "
                  "selbst plant keine Sub-13:00-Spiele ohne Anlass.",
        severity="soft",
        limit_text="Tag-Spiel ≥ 13:00 (12:00–13:00 nur mit Off-Day/Same-City-Ausnahme); "
                   "reale Früh-Specials sind weicher Hinweis",
    ),
    "SCHED-162": ComplianceRule(
        rule_id="SCHED-162",
        name="Spielzahl je Team (Vollständigkeit)",
        authority="MLB-Saisonregel",
        reference="MLB Regular Season (162 Spiele/Team nominal)",
        definition_doc="docs/CONVENTIONS.md",
        mechanism="Matchup-Quoten aus Quell-Saison (matchup_extractor); Warm-Start "
                  "erhält die exakte reale Spielmenge (kein Spiel verloren/dupliziert).",
        severity="hard",
        # Hinweis: gespielte Saisonen variieren real 161–163 (Makeups/Ties/DH);
        # mit Referenz-Counts wird auf exakte Übereinstimmung geprüft.
        limit_text="162 Spiele/Team (nominal); ohne Referenz Toleranz 161–163 (reale "
                   "Makeup-Varianz); mit Referenz exakte Übereinstimmung",
    ),
    "SCHED-HA": ComplianceRule(
        rule_id="SCHED-HA",
        name="Heim-/Auswärts-Balance",
        authority="MLB-Saisonregel",
        reference="MLB Regular Season (81 Heim / 81 Auswärts nominal)",
        definition_doc="docs/CONVENTIONS.md",
        mechanism="Heim-/Auswärts-Zuordnung aus den Matchup-Quoten erhalten; "
                  "SA-Moves verschieben nur Termine, nie Heimrecht.",
        severity="hard",
        limit_text="81 Heim / 81 Auswärts je Team (nominal); ±1 Toleranz für reale "
                   "Makeup-Varianz",
    ),
    "FEAS-GETA": ComplianceRule(
        rule_id="FEAS-GETA",
        name="Getaway-Day-/Reise-Feasibility",
        authority="MLB-Ops",
        reference="Reise-Feasibility — kein Back-to-Back jenseits des real "
                  "beobachteten MLB-Envelopes (≤ 4350 km, ≤ 3 TZ-Hops; Schwelle 2026-06-11 von 4200 angehoben — 2026-Original legt bis 4328)",
        definition_doc="docs/PROJECT_REVIEW_2026-06.md (P1-3) + src/feasibility.py",
        mechanism="Validierung via feasibility.feasibility_report; Schwellen aus "
                  "real 2024/2025 abgeleitet.",
        severity="hard",
        limit_text="kein konsekutiver Intercity-Transfer > 4350 km oder > 3 TZ-Hops",
    ),
    "VENUE-AVAIL": ComplianceRule(
        rule_id="VENUE-AVAIL",
        name="Venue-Verfügbarkeit (harter Belegungskalender)",
        authority="MLB-Ops",
        reference="Stadion-Belegungskalender — kein Heimspiel an einem durch "
                  "Drittnutzung (Konzert/NFL/etc.) belegten Tag",
        definition_doc="src/event_conflicts.py (venue_conflicts) + data/local_events.json",
        mechanism="Durchsetzung via stadium_bookings_to_blackout_days → "
                  "GeneratorConfig.home_blackout_days (CP-SAT + SA respektieren "
                  "die Sperrtage); Verifikation via event_conflicts.venue_conflicts.",
        severity="hard",
        limit_text="0 Heimspiele an Stadion-Belegungstagen",
    ),
    "CBA-ASB": ComplianceRule(
        rule_id="CBA-ASB",
        name="All-Star-Break-Länge (CBA V(C)(17))",
        authority="CBA",
        reference="CBA 2022–2026 Article V(C)(17): 'The All-Star break will "
                  "contain four days, during which time Club championship season "
                  "games shall not be played.' Verbatim: "
                  "regulations/CBA_2022-2026_Article_V_Scheduling.md.",
        definition_doc="src/season.py (detect_all_star_break)",
        mechanism="Heuristische ASB-Erkennung (längste liga-weite Lücke im "
                  "mittleren Saisondrittel) gegen die vertragliche 4-Tage-Länge "
                  "validiert (Review-Runde 2, Punkt 9 — vorher unvalidiert). "
                  "WEICH, weil die Erkennung heuristisch ist (Disruption-Szenarien "
                  "können lange Lücken erzeugen) und V(C)(17) Satz 2 "
                  "(Sunday-Night-Rotation, mehrjährig) nicht prüfbar ist. "
                  "Gemessen real 2024/2025: exakt 4 Tage.",
        severity="soft",
        limit_text="erkannter All-Star-Break = 4 Tage",
    ),
    "PIN-LEAGUE": ComplianceRule(
        rule_id="PIN-LEAGUE",
        name="Feiertags-Slates (league_wide)",
        authority="League-Konvention",
        reference="Feiertags-Programmierung (voller Slate an Schlüsseltagen)",
        definition_doc="data/holiday_pins.json",
        mechanism="Reporting/Incentive via holidays.holiday_report; kein harter "
                  "Constraint (Off-Days an Feiertagen sind erlaubt).",
        severity="soft",
        limit_text="möglichst voller Slate (30/30 Teams) an league_wide-Feiertagen",
    ),
}


# ====================================================================
# Ergebnis-Typen
# ====================================================================

@dataclass(frozen=True)
class ComplianceCheck:
    rule_id: str
    passed: bool
    measured: str          # menschenlesbarer gemessener Wert
    detail: str
    offenders: List[str] = field(default_factory=list)

    @property
    def rule(self) -> ComplianceRule:
        return RULES[self.rule_id]

    def to_dict(self) -> dict:
        return {
            "rule": self.rule.to_dict(),
            "passed": self.passed,
            "measured": self.measured,
            "detail": self.detail,
            "offenders": self.offenders,
        }


@dataclass(frozen=True)
class ComplianceReport:
    season_year: int
    checks: List[ComplianceCheck]
    generated_on: date = field(default_factory=date.today)

    def get(self, rule_id: str) -> Optional[ComplianceCheck]:
        return next((c for c in self.checks if c.rule_id == rule_id), None)

    @property
    def hard_checks(self) -> List[ComplianceCheck]:
        return [c for c in self.checks if c.rule.severity == "hard"]

    @property
    def hard_failures(self) -> List[ComplianceCheck]:
        return [c for c in self.hard_checks if not c.passed]

    @property
    def is_compliant(self) -> bool:
        """True, wenn ALLE harten Regeln bestehen (soft ignoriert)."""
        return not self.hard_failures

    def to_dict(self) -> dict:
        return {
            "season_year": self.season_year,
            "generated_on": self.generated_on.isoformat(),
            "is_compliant": self.is_compliant,
            "n_hard_failures": len(self.hard_failures),
            "checks": [c.to_dict() for c in self.checks],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# ====================================================================
# Einzel-Checks
# ====================================================================

def _check_ac218(season: Season, team_ids: List[str]) -> ComplianceCheck:
    vals = {t: max_consecutive_away_days(season, t) for t in team_ids}
    worst = max(vals.values()) if vals else 0
    offenders = [f"{t} ({v})" for t, v in sorted(vals.items(), key=lambda kv: -kv[1]) if v > 13]
    return ComplianceCheck(
        rule_id="AC-2.1.8", passed=not offenders,
        measured=f"worst = {worst} Tage (Limit 13)",
        detail=("alle Teams ≤ 13 Tage am Stück auswärts"
                if not offenders else f"{len(offenders)} Team(s) über dem Limit"),
        offenders=offenders,
    )


def _check_ac219(season: Season, team_ids: List[str]) -> ComplianceCheck:
    vals = {t: max_games_without_off_day(season, t) for t in team_ids}
    worst = max(vals.values()) if vals else 0
    offenders = [f"{t} ({v})" for t, v in sorted(vals.items(), key=lambda kv: -kv[1]) if v > 20]
    return ComplianceCheck(
        rule_id="AC-2.1.9", passed=not offenders,
        measured=f"worst = {worst} Spieltage (Limit 20)",
        detail=("alle Teams ≤ 20 Spieltage ohne Off-Day"
                if not offenders else f"{len(offenders)} Team(s) über dem Limit"),
        offenders=offenders,
    )


_PT_ZONES = {"America/Los_Angeles"}
_ET_ZONES = {"America/New_York", "America/Toronto"}


def _check_pt_et_offday(season: Season, team_ids: List[str], teams_by_id) -> ComplianceCheck:
    """CBA V(C)(11): Reise Pacific→Eastern erfordert einen Off-Day.

    Konservativ (die ≤7 Liga-Ausnahmen mit später ET-Startzeit sind ohne Startzeit-
    Modell nicht verifizierbar → wir erzwingen den strikten Default): ein Verstoß ist
    jeder konsekutive Spieltag eines Teams von einer PT-Stadt zu einer ET-Stadt OHNE
    dazwischenliegenden Off-Day. Spielort = Heim-Team der Partie.
    """
    offenders: List[str] = []
    for t in team_ids:
        gs = season.games_for_team(t)
        # distinkte Spieltage mit Spielort (ein Team spielt pro Tag an einem Ort)
        dayvenue: List[tuple] = []
        seen = set()
        for g in gs:
            if g.date not in seen:
                seen.add(g.date)
                dayvenue.append((g.date, g.home))
        for (d1, v1), (d2, v2) in zip(dayvenue, dayvenue[1:]):
            if (d2 - d1).days != 1:
                continue  # Off-Day vorhanden → ok
            tz1 = teams_by_id[v1].timezone if v1 in teams_by_id else None
            tz2 = teams_by_id[v2].timezone if v2 in teams_by_id else None
            if tz1 in _PT_ZONES and tz2 in _ET_ZONES:
                offenders.append(f"{t}: {v1}({d1})→{v2}({d2}) ohne Off-Day")
    return ComplianceCheck(
        rule_id="CBA-PTET", passed=not offenders,
        measured=f"{len(offenders)} PT→ET-Spieltagsfolge(n) ohne Off-Day",
        detail=("keine PT→ET-Reise ohne Off-Day"
                if not offenders else f"{len(offenders)} PT→ET-Transfer(s) ohne Off-Day"),
        offenders=offenders,
    )


# --- Sprint 5.1: Startzeit-Checks (gegated — nur aktiv mit zugewiesenen Zeiten) ---

# Empirische per-Club First-Pitch-Konvention: nominale 7-PM-Anker, reale Erstwürfe
# bis ~7:40 (Braves 7:20, Rays 7:35). Gemessen an real 2024/2025 → 0 Verstöße.
_GETAWAY_CONVENTION_TOL_MIN = 40


def _skipped_starttime_check(rule_id: str) -> ComplianceCheck:
    return ComplianceCheck(
        rule_id=rule_id, passed=True,
        measured="übersprungen (keine Startzeiten zugewiesen)",
        detail="Regel inaktiv ohne Startzeit-Schicht (Default-Pfad, gegated)",
        offenders=[],
    )


def _check_starttime_getaway(season, start_min, appendix_c, team_ids,
                             espn_snb_pks, rescheduled_pks) -> ComplianceCheck:
    from .start_times import validate_getaway_times
    viols = validate_getaway_times(
        season, start_min, appendix_c, team_ids=team_ids,
        espn_snb_pks=espn_snb_pks, rescheduled_pks=rescheduled_pks,
        tolerance_min=_GETAWAY_CONVENTION_TOL_MIN)
    offenders = [f"{v.game_date} @{v.venue_team} pk={v.game_pk}: {v.detail}" for v in viols]
    return ComplianceCheck(
        rule_id="STARTTIME-GETAWAY", passed=not viols,
        measured=f"{len(viols)} Getaway-Spiel(e) über der V(C)(8)-Grenze "
                 f"(±{_GETAWAY_CONVENTION_TOL_MIN} min Konvention)",
        detail=("alle Getaway-Startzeiten ≤ V(C)(8)-Grenze"
                if not viols else f"{len(viols)} Verstoß/Verstöße gegen V(C)(8)"),
        offenders=offenders,
    )


def _check_starttime_nightday(season, start_min, appendix_c, teams_by_id, team_ids,
                              rescheduled_pks) -> ComplianceCheck:
    from .start_times import (validate_nightday_times, detect_home_openers,
                              holiday_dates_for)
    viols = validate_nightday_times(
        season, start_min, appendix_c, teams_by_id, team_ids=team_ids,
        holiday_dates=holiday_dates_for(season),
        home_opener_pks=detect_home_openers(season),
        rescheduled_pks=rescheduled_pks)
    offenders = [f"{v.game_date} @{v.venue_team} pk={v.game_pk}: {v.detail}" for v in viols]
    return ComplianceCheck(
        rule_id="STARTTIME-NIGHTDAY", passed=not viols,
        measured=f"{len(viols)} V(C)(9)-Verstoß/Verstöße (Tag<17:00 nach ≥19:00-Auswärts)",
        detail=("keine V(C)(9)-Verletzung (Ausnahmen berücksichtigt)"
                if not viols else f"{len(viols)} Verstoß/Verstöße gegen V(C)(9)"),
        offenders=offenders,
    )


def _check_starttime_daydh(season, start_min, rescheduled_pks) -> ComplianceCheck:
    from .start_times import validate_day_dh_prior_times
    viols = validate_day_dh_prior_times(season, start_min,
                                        rescheduled_pks=rescheduled_pks)
    offenders = [f"{v.game_date} @{v.venue_team} pk={v.game_pk}: {v.detail}" for v in viols]
    return ComplianceCheck(
        rule_id="STARTTIME-DAYDH", passed=not viols,
        measured=f"{len(viols)} V(C)(5)-Verstoß/Verstöße (Start >17:00 vor Day-DH)",
        detail=("kein Spätstart vor einem Day-Doubleheader"
                if not viols else f"{len(viols)} Verstoß/Verstöße gegen V(C)(5)"),
        offenders=offenders,
    )


def _check_starttime_daymin(season, start_min) -> ComplianceCheck:
    from .start_times import validate_day_min_times
    viols = validate_day_min_times(season, start_min)
    offenders = [f"{v.game_date} @{v.venue_team} pk={v.game_pk}: {v.detail}" for v in viols]
    return ComplianceCheck(
        rule_id="STARTTIME-DAYMIN", passed=not viols,
        measured=f"{len(viols)} Tag-Spiel(e) < 13:00 (weich; reale Früh-Specials)",
        detail=("alle Tag-Spiele ≥ 13:00 bzw. mit Ausnahme"
                if not viols else f"{len(viols)} Früh-Start-Special(s) (weicher Hinweis)"),
        offenders=offenders,
    )


def _check_offday_distribution(season, team_ids, schedule_kind) -> ComplianceCheck:
    from .schedule_rules import check_offday_distribution
    viols = check_offday_distribution(season, team_ids)
    offenders = [f"{v.team}: {v.detail}" for v in viols]
    note = "" if schedule_kind == "original" else " [as-played: informativ, Makeup-Artefakte]"
    return ComplianceCheck(
        rule_id="CBA-OFFDAY", passed=not viols,
        measured=f"{len(viols)} Off-Day-Verteilungs-Abweichung(en){note}",
        detail=("Off-Day-Verteilung V(C)(13)-konform" if not viols
                else f"{len(viols)} Abweichung(en){note}"),
        offenders=offenders,
    )


def _check_doubleheader_limits(season, team_ids, start_min, schedule_kind) -> ComplianceCheck:
    from .schedule_rules import check_doubleheader_limits
    viols = check_doubleheader_limits(season, team_ids, start_min=start_min)
    offenders = [f"{v.rule} {v.team}: {v.detail}" for v in viols]
    note = "" if schedule_kind == "original" else " [as-played: informativ, Makeup-DHs]"
    return ComplianceCheck(
        rule_id="CBA-DH", passed=not viols,
        measured=f"{len(viols)} DH-Limit-Abweichung(en){note}",
        detail=("Doubleheader-Limits V(C)(14)/(15)-konform" if not viols
                else f"{len(viols)} Abweichung(en){note}"),
        offenders=offenders,
    )


def _team_game_counts(season: Season, team_ids: List[str]) -> Dict[str, int]:
    counts = {t: 0 for t in team_ids}
    for g in season.games:
        if g.home in counts:
            counts[g.home] += 1
        if g.away in counts:
            counts[g.away] += 1
    return counts


def _check_162(season: Season, team_ids: List[str], expected: int = 162,
               tolerance: int = 1,
               reference_counts: Optional[Dict[str, int]] = None) -> ComplianceCheck:
    """Spielzahl-Vollständigkeit.

    Mit ``reference_counts`` (z. B. die realen Counts der Quell-Saison): es muss
    EXAKT übereinstimmen — fängt verlorene/duplizierte Spiele (z. B. den früheren
    Doubleheader-Roundtrip-Bug 2432→2400). Ohne Referenz: Toleranz ``expected ±
    tolerance``, weil gespielte Saisonen real 161–163 streuen (Makeups/Ties/DH).
    """
    counts = _team_game_counts(season, team_ids)
    lo = min(counts.values()) if counts else 0
    hi = max(counts.values()) if counts else 0
    if reference_counts is not None:
        offenders = [
            f"{t} ({counts.get(t, 0)}≠{reference_counts.get(t)})"
            for t in sorted(team_ids)
            if counts.get(t, 0) != reference_counts.get(t)
        ]
        measured = f"Spiele/Team: {lo}–{hi} (geprüft gegen Referenz-Plan)"
        ok_detail = "Spielmenge exakt wie im Referenz-Plan (kein Spiel verloren/dupliziert)"
    else:
        offenders = [
            f"{t} ({c})" for t, c in sorted(counts.items())
            if abs(c - expected) > tolerance
        ]
        measured = f"Spiele/Team: {lo}–{hi} (Soll {expected} ±{tolerance})"
        ok_detail = f"alle Teams {expected} ±{tolerance} Spiele (reale Makeup-Varianz)"
    return ComplianceCheck(
        rule_id="SCHED-162", passed=not offenders,
        measured=measured,
        detail=(ok_detail if not offenders else f"{len(offenders)} Team(s) abweichend"),
        offenders=offenders,
    )


def _check_home_away(season: Season, team_ids: List[str], expected: int = 81,
                     tolerance: int = 1) -> ComplianceCheck:
    home = {t: 0 for t in team_ids}
    away = {t: 0 for t in team_ids}
    for g in season.games:
        if g.home in home:
            home[g.home] += 1
        if g.away in away:
            away[g.away] += 1
    offenders = [
        f"{t} ({home[t]}H/{away[t]}A)"
        for t in sorted(team_ids)
        if abs(home[t] - expected) > tolerance or abs(away[t] - expected) > tolerance
    ]
    return ComplianceCheck(
        rule_id="SCHED-HA", passed=not offenders,
        measured=f"Soll {expected} Heim / {expected} Auswärts je Team (±{tolerance})",
        detail=("Heim-/Auswärts-Balance bei allen Teams im Rahmen"
                if not offenders else f"{len(offenders)} Team(s) unbalanciert"),
        offenders=offenders,
    )


def _check_feasibility(season: Season, team_ids: List[str], teams_by_id,
                       thresholds: FeasibilityThresholds) -> ComplianceCheck:
    rep = feasibility_report(season, team_ids, teams_by_id, thresholds=thresholds)
    viols = rep.violations
    offenders = [
        f"{v.team}: {v.from_city}→{v.to_city} {v.km:.0f} km / {v.tz_hops} TZ-Hops "
        f"({v.depart_date}→{v.arrive_date})"
        for v in viols
    ]
    return ComplianceCheck(
        rule_id="FEAS-GETA", passed=not viols,
        measured=f"max Back-to-Back = {rep.max_consecutive_km:.0f} km; "
                 f"{len(rep.tight)} harte (aber real-konforme) Turnarounds",
        detail=("kein Transfer jenseits des realen MLB-Envelopes"
                if not viols else f"{len(viols)} Transfer(s) über dem realen Envelope"),
        offenders=offenders,
    )


def _check_venue_availability(season: Season, events) -> ComplianceCheck:
    """Harter Venue-Belegungskalender: kein Heimspiel an einem Stadion-
    Belegungstag (Konzert/NFL/etc.)."""
    from .event_conflicts import venue_conflicts
    conflicts = venue_conflicts(season, events)
    offenders = [f"{c.team_id} {c.date}: {c.event_name}" for c in conflicts]
    n_bookings = sum(1 for e in events if e.is_stadium_booking())
    return ComplianceCheck(
        rule_id="VENUE-AVAIL", passed=not conflicts,
        measured=f"{len(conflicts)} Heimspiel(e) auf Belegungstagen "
                 f"(geprüft gegen {n_bookings} Stadion-Belegung[en])",
        detail=("kein Heimspiel an einem belegten Stadion-Tag"
                if not conflicts else f"{len(conflicts)} harter Venue-Konflikt(e)"),
        offenders=offenders,
    )


def _check_asb_length(season: Season) -> ComplianceCheck:
    """CBA V(C)(17): All-Star-Break = 4 Tage — gemessen PRO TEAM, nicht
    league-wide (Nacht-Härtung 2026-06-11, Assessment-Befund B2: 2026 spielen
    NYM@PHI ein Einzelspiel am Do nach dem ASG, die league-wide-Lücke schrumpft
    dadurch auf 3 Tage, obwohl 28/30 Teams die vollen 4 Tage haben — die alte
    Messung meldete fälschlich einen Liga-Befund statt der 2 Ausnahme-Teams).
    Weich, weil Einzelspiel-Ausnahmen V(C)(18)-Waiver-Klasse sind."""
    from .season import detect_all_star_break
    asb = detect_all_star_break(season)
    if asb is None:
        return ComplianceCheck(
            rule_id="CBA-ASB", passed=False,
            measured="kein All-Star-Break erkannt",
            detail="detect_all_star_break fand keine plausible Liga-Pause "
                   "(V(C)(17) verlangt 4 Tage)",
            offenders=[])
    team_ids = sorted({g.home for g in season.games} | {g.away for g in season.games})
    offenders: List[str] = []
    breaks: List[int] = []
    for t in team_ids:
        days = sorted({g.date for g in season.games if g.involves(t)})
        last_before = max((d for d in days if d < asb[0]), default=None)
        first_after = min((d for d in days if d > asb[1]), default=None)
        if last_before is None or first_after is None:
            continue
        free = (first_after - last_before).days - 1
        breaks.append(free)
        if free < 4:
            offenders.append(f"{t}: nur {free} ASB-Tage frei "
                             f"({last_before}→{first_after})")
    n_ok = sum(1 for b in breaks if b >= 4)
    return ComplianceCheck(
        rule_id="CBA-ASB", passed=not offenders,
        measured=(f"per-Team-ASB um {asb[0]}..{asb[1]}: {n_ok}/{len(breaks)} "
                  f"Teams mit ≥4 freien Tagen"),
        detail=("alle Teams mit vertragskonformem 4-Tage-Break" if not offenders
                else f"{len(offenders)} Team(s) unter 4 Tagen (Einzelspiel-"
                     f"Special? → V(C)(18)-Waiver-Klasse, weich)"),
        offenders=offenders)


def _check_holiday_pins(season: Season) -> ComplianceCheck:
    rep = holiday_report(season)
    gaps = rep.league_wide_gaps
    offenders = [
        f"{e.holiday.name} {e.holiday.on_date}: {e.teams_active}/30 Teams aktiv"
        for e in gaps
    ]
    return ComplianceCheck(
        rule_id="PIN-LEAGUE", passed=not gaps,
        measured=f"Feiertags-Incentive-Score {rep.total_score:.2f}; "
                 f"{rep.summary()['total_marquee_on_holidays']} Marquee-Spiele an Feiertagen",
        detail=("alle league_wide-Feiertage mit vollem Slate"
                if not gaps else f"{len(gaps)} Feiertag(e) ohne vollen Slate (soft)"),
        offenders=offenders,
    )


# ====================================================================
# Gesamt-Report
# ====================================================================

def compliance_report(
    season: Season,
    team_ids: Optional[List[str]] = None,
    teams_by_id=None,
    *,
    thresholds: FeasibilityThresholds = DEFAULT_THRESHOLDS,
    expected_games: int = 162,
    reference_counts: Optional[Dict[str, int]] = None,
    events=None,
    check_venue: bool = False,
    start_min: Optional[Dict[int, int]] = None,
    appendix_c=None,
    espn_snb_pks: Optional[set] = None,
    rescheduled_pks: Optional[set] = None,
    schedule_kind: str = "as_played",
) -> ComplianceReport:
    """Vollständiger Compliance-Report über alle Regeln.

    ``team_ids`` / ``teams_by_id`` sind optional — fehlen sie, werden die Teams
    aus dem Plan bzw. den Stammdaten (``data_loader.load_teams``) abgeleitet.
    ``reference_counts`` (optional): Soll-Spielzahlen je Team aus einem
    Referenz-Plan; aktiviert die exakte Vollständigkeitsprüfung (SCHED-162).

    Venue-Verfügbarkeit (VENUE-AVAIL, hart): wird **opt-in** geprüft — entweder
    durch Übergabe von ``events`` (Liste von LocalEvent) oder ``check_venue=True``
    (lädt dann ``data/local_events.json``). Ohne beides bleibt der Report bei den
    bisherigen sechs Regeln (rückwärtskompatibel, Default unverändert).
    """
    if team_ids is None:
        team_ids = sorted({g.home for g in season.games} | {g.away for g in season.games})
    if teams_by_id is None:
        from .data_loader import load_teams, teams_by_id as _tbi
        teams_by_id = _tbi(load_teams())

    checks = [
        _check_ac218(season, team_ids),
        _check_ac219(season, team_ids),
        _check_pt_et_offday(season, team_ids, teams_by_id),
        _check_162(season, team_ids, expected_games, reference_counts=reference_counts),
        _check_home_away(season, team_ids, expected_games // 2),
        _check_feasibility(season, team_ids, teams_by_id, thresholds),
    ]

    # Sprint 5.1: Startzeit-Regeln — gegated. Ohne ``start_min`` (Default-Pfad)
    # werden sie übersprungen (passed=True, "inherited"), sodass der bestehende
    # Report bit-identisch bleibt. Mit zugewiesenen/echten Startzeiten greifen sie.
    if start_min is None:
        checks += [
            _skipped_starttime_check("STARTTIME-GETAWAY"),
            _skipped_starttime_check("STARTTIME-NIGHTDAY"),
            _skipped_starttime_check("STARTTIME-DAYDH"),
            _skipped_starttime_check("STARTTIME-DAYMIN"),
        ]
    else:
        if appendix_c is None:
            from .start_times import AppendixC
            appendix_c = AppendixC.load()
        checks += [
            _check_starttime_getaway(season, start_min, appendix_c, team_ids,
                                     espn_snb_pks, rescheduled_pks),
            _check_starttime_nightday(season, start_min, appendix_c, teams_by_id,
                                      team_ids, rescheduled_pks),
            _check_starttime_daydh(season, start_min, rescheduled_pks),
            _check_starttime_daymin(season, start_min),
        ]

    # Sprint 5.2: strukturelle Originalplan-Regeln (V(C)(13), V(C)(14)/(15)).
    # Als SOFT geführt → beeinflussen is_compliant nicht (rückwärtskompatibel);
    # auf as-played-Daten informativ. Harte Durchsetzung auf Optimierer-Output:
    # src/publish_gate.py (Review-Fix P0-2, 2026-06-10 — verdrahtet in backtest/
    # main/whatif; vorher wurde original_schedule_violations nirgends aufgerufen).
    checks += [
        _check_offday_distribution(season, team_ids, schedule_kind),
        _check_doubleheader_limits(season, team_ids, start_min, schedule_kind),
    ]

    if events is not None or check_venue:
        if events is None:
            from .event_conflicts import load_local_events
            events = load_local_events()
        checks.append(_check_venue_availability(season, events))
    checks.append(_check_asb_length(season))
    checks.append(_check_holiday_pins(season))
    return ComplianceReport(season_year=season.season, checks=checks)
