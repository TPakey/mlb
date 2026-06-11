"""Tests für Sprint 3 P1-3/P1-4: feasibility, holidays, compliance, explain.

Schnell (keine CP-SAT-Läufe). Mischung aus Unit-Tests auf Mini-Seasons und
Integrations-Checks gegen den realen 2024-Plan (lädt JSON, < 1 s).
"""
from __future__ import annotations

from datetime import date

import pytest

from src.season import Season
from src.datasources import LocalFileAdapter
from src.feasibility import (
    feasibility_report, team_transitions, FeasibilityThresholds,
    _classify, DEFAULT_THRESHOLDS,
)
from src.holidays import (
    nth_weekday, resolve_holiday_date, load_holidays, holiday_report,
    evaluate_holiday, Holiday,
)
from src.compliance import compliance_report, RULES
from src.explain import explain_plan

from conftest import make_game, make_mini_season


# Bequemer Marquee-Stub für Holiday-Tests
def _marquee_nyy_bos(home, away):
    return 1.5 if {home, away} == {"NYY", "BOS"} else 1.0


@pytest.fixture(scope="module")
def real_2024(data_dir):
    return LocalFileAdapter(base_dir=str(data_dir)).fetch_season_schedule(2024)


# ====================================================================
# feasibility.py
# ====================================================================

class TestFeasibility:
    def test_back_to_back_beyond_envelope_is_violation(self, teams_by_id_map):
        # NYY reist von Seattle (Tag 0) nach Miami (Tag 1): SEA-MIA ~4392 km > 4200.
        games = [
            make_game(1, 0, "SEA", "NYY"),   # NYY auswärts in Seattle
            make_game(2, 1, "MIA", "NYY"),   # NYY auswärts in Miami, Folgetag
        ]
        s = make_mini_season(games)
        rep = feasibility_report(s, ["NYY"], teams_by_id_map)
        assert len(rep.violations) == 1
        v = rep.violations[0]
        assert v.from_city == "SEA" and v.to_city == "MIA"
        assert v.severity == "exceeds_real_envelope"
        assert not rep.ok

    def test_off_day_buffer_not_flagged(self, teams_by_id_map):
        # Gleicher weiter Sprung, aber mit Off-Day dazwischen (gap=2) → kein B2B.
        games = [
            make_game(1, 0, "SEA", "NYY"),
            make_game(2, 2, "MIA", "NYY"),
        ]
        s = make_mini_season(games)
        rep = feasibility_report(s, ["NYY"], teams_by_id_map)
        assert rep.violations == []
        assert rep.ok

    def test_short_close_transfer_ok(self, teams_by_id_map):
        # NYY → BOS (~300 km, gleiche TZ) am Folgetag: unauffällig.
        games = [
            make_game(1, 0, "NYY", "TOR"),
            make_game(2, 1, "BOS", "NYY"),
        ]
        s = make_mini_season(games)
        rep = feasibility_report(s, ["NYY"], teams_by_id_map)
        assert rep.violations == []
        ts = team_transitions(s, "NYY", teams_by_id_map)
        assert ts and ts[0].severity == "ok"

    def test_eastward_long_haul_is_tight(self, teams_by_id_map):
        # SEA → HOU: ~3040 km, 2 TZ-Hops ostwärts → tight (Review-Hinweis).
        games = [
            make_game(1, 0, "SEA", "HOU"),
            make_game(2, 1, "HOU", "SEA"),
        ]
        s = make_mini_season(games)
        ts = team_transitions(s, "SEA", teams_by_id_map)
        assert ts and ts[0].severity == "tight"
        assert ts[0].eastward is True and ts[0].tz_hops >= 2

    def test_classify_thresholds(self):
        th = DEFAULT_THRESHOLDS
        assert _classify(4500, 3, True, th) == "exceeds_real_envelope"   # km
        assert _classify(2000, 4, False, th) == "exceeds_real_envelope"  # hops
        assert _classify(3200, 2, True, th) == "tight"
        assert _classify(3200, 2, False, th) == "ok"   # westwärts → kein tight
        assert _classify(1000, 1, True, th) == "ok"

    def test_deterministic(self, teams_by_id_map):
        games = [make_game(1, 0, "SEA", "NYY"), make_game(2, 1, "MIA", "NYY")]
        s = make_mini_season(games)
        a = feasibility_report(s, ["NYY"], teams_by_id_map)
        b = feasibility_report(s, ["NYY"], teams_by_id_map)
        assert a.summary() == b.summary()
        assert [t.severity for t in a.all_transitions] == [t.severity for t in b.all_transitions]

    def test_real_plan_passes_envelope(self, real_2024, teams_by_id_map):
        tids = sorted({g.home for g in real_2024.games})
        rep = feasibility_report(real_2024, tids, teams_by_id_map)
        # Reale Pläne überschreiten das (aus ihnen abgeleitete) Envelope nie.
        assert rep.ok
        assert rep.max_consecutive_km <= DEFAULT_THRESHOLDS.max_real_consecutive_km


# ====================================================================
# holidays.py
# ====================================================================

class TestHolidays:
    def test_nth_weekday(self):
        # Memorial Day = letzter Montag im Mai; Labor Day = erster Montag im Sep.
        assert nth_weekday(2024, 5, 0, -1) == date(2024, 5, 27)
        assert nth_weekday(2025, 5, 0, -1) == date(2025, 5, 26)
        assert nth_weekday(2024, 9, 0, 1) == date(2024, 9, 2)
        assert nth_weekday(2025, 9, 0, 1) == date(2025, 9, 1)

    def test_resolve_dates(self):
        s = make_mini_season([make_game(1, 0, "NYY", "BOS", base=date(2024, 3, 28))],
                             season=2024, season_start=date(2024, 3, 28))
        assert resolve_holiday_date({"type": "fixed", "month": 7, "day": 4}, s) == date(2024, 7, 4)
        assert resolve_holiday_date({"type": "opening_day"}, s) == date(2024, 3, 28)

    def test_league_wide_full_slate(self, teams):
        tids = [t.id for t in teams]
        # 15 Spiele am 15. April 2024 → alle 30 Teams aktiv = voller Slate.
        games = []
        base = date(2024, 4, 15)
        for i in range(0, 30, 2):
            games.append(make_game(100 + i, 0, tids[i], tids[i + 1], base=base))
        # Bracketing-Spiele, damit Apr 15 in der Saison liegt.
        games.append(make_game(1, 0, tids[0], tids[1], base=date(2024, 3, 28)))
        games.append(make_game(2, 0, tids[0], tids[1], base=date(2024, 9, 1)))
        s = Season(season=2024, games=games,
                   season_start=date(2024, 3, 28), season_end=date(2024, 9, 30))
        jr = Holiday("jackie_robinson_day", "Jackie Robinson Day", date(2024, 4, 15),
                     "league_wide", 1.5, "")
        ev = evaluate_holiday(s, jr, _marquee_nyy_bos)
        assert ev.in_season and ev.is_full_slate
        assert ev.teams_active == 30
        assert ev.score == pytest.approx(1.5)

    def test_marquee_incentive_scoring(self, teams):
        base = date(2024, 3, 28)
        games = [
            make_game(1, 0, "NYY", "BOS", base=base),   # Marquee
            make_game(2, 0, "LAD", "SDP", base=base),   # kein Marquee (Stub)
        ]
        s = Season(season=2024, games=games, season_start=base,
                   season_end=date(2024, 9, 30))
        od = Holiday("opening_day", "Opening Day", base, "marquee_incentive", 2.0, "")
        ev = evaluate_holiday(s, od, _marquee_nyy_bos)
        assert ev.n_marquee == 1
        assert ev.score == pytest.approx(2.0)

    def test_load_holidays_resolves_all(self, real_2024):
        hs = load_holidays(real_2024)
        keys = {h.key for h in hs}
        assert {"opening_day", "jackie_robinson_day", "independence_day",
                "memorial_day", "labor_day"} <= keys
        assert all(h.on_date is not None for h in hs)

    def test_real_plan_holiday_report(self, real_2024):
        rep = holiday_report(real_2024, marquee_fn=_marquee_nyy_bos)
        jr = next(e for e in rep.evaluations if e.holiday.key == "jackie_robinson_day")
        assert jr.is_full_slate          # real: 30/30 am 15. April
        assert rep.total_score > 0


# ====================================================================
# compliance.py
# ====================================================================

class TestCompliance:
    def test_real_2024_is_compliant(self, real_2024, teams_by_id_map):
        tids = sorted({g.home for g in real_2024.games})
        rep = compliance_report(real_2024, tids, teams_by_id_map)
        assert rep.is_compliant            # alle harten Regeln bestehen
        assert rep.hard_failures == []
        # AC-Checks vorhanden + bestanden
        assert rep.get("AC-2.1.8").passed
        assert rep.get("AC-2.1.9").passed

    def test_provenance_in_machine_readable(self, real_2024, teams_by_id_map):
        tids = sorted({g.home for g in real_2024.games})
        d = compliance_report(real_2024, tids, teams_by_id_map).to_dict()
        assert set(d) >= {"season_year", "is_compliant", "checks"}
        first = d["checks"][0]["rule"]
        assert {"rule_id", "authority", "reference", "definition_doc",
                "mechanism", "severity"} <= set(first)
        # JSON serialisierbar
        import json
        json.loads(compliance_report(real_2024, tids, teams_by_id_map).to_json())

    def test_feasibility_violation_breaks_compliance(self, teams_by_id_map):
        # Konstruierter Plan mit Envelope-Verstoß (SEA→MIA B2B).
        games = [make_game(1, 0, "SEA", "NYY"), make_game(2, 1, "MIA", "NYY")]
        s = make_mini_season(games)
        rep = compliance_report(s, ["NYY", "SEA", "MIA"], teams_by_id_map)
        feas = rep.get("FEAS-GETA")
        assert not feas.passed
        assert not rep.is_compliant

    def test_reference_counts_exact(self, teams_by_id_map):
        # 1 Spiel NYY vs BOS → counts NYY=1, BOS=1. Referenz erwartet exakt das.
        s = make_mini_season([make_game(1, 0, "NYY", "BOS")])
        rep = compliance_report(s, ["NYY", "BOS"], teams_by_id_map,
                                reference_counts={"NYY": 1, "BOS": 1})
        assert rep.get("SCHED-162").passed
        rep2 = compliance_report(s, ["NYY", "BOS"], teams_by_id_map,
                                 reference_counts={"NYY": 2, "BOS": 1})
        assert not rep2.get("SCHED-162").passed

    def test_rules_registry_complete(self):
        for rid in ("AC-2.1.8", "AC-2.1.9", "CBA-PTET", "SCHED-162", "SCHED-HA",
                    "FEAS-GETA", "PIN-LEAGUE"):
            assert rid in RULES
            assert RULES[rid].severity in ("hard", "soft")
            assert RULES[rid].definition_doc

    def test_ptet_offday_violation(self, teams_by_id_map):
        # CBA V(C)(11): NYY spielt Tag 0 auswärts in LAD (Pacific), Tag 1 zu Hause
        # in NYY (Eastern) — konsekutiv, kein Off-Day → Verstoß.
        games = [make_game(1, 0, "LAD", "NYY"), make_game(2, 1, "NYY", "BOS")]
        s = make_mini_season(games)
        rep = compliance_report(s, ["NYY", "LAD", "BOS"], teams_by_id_map)
        ptet = rep.get("CBA-PTET")
        assert ptet is not None and not ptet.passed
        assert not rep.is_compliant            # harte Regel → bricht Compliance

    def test_ptet_offday_ok_with_gap(self, teams_by_id_map):
        # Gleiches Routing, aber ein Off-Day dazwischen (Tag 0 → Tag 2) → konform.
        games = [make_game(1, 0, "LAD", "NYY"), make_game(2, 2, "NYY", "BOS")]
        s = make_mini_season(games)
        rep = compliance_report(s, ["NYY", "LAD", "BOS"], teams_by_id_map)
        assert rep.get("CBA-PTET").passed

    def test_ptet_real_2024_compliant(self, real_2024, teams_by_id_map):
        # Realer 2024-Plan: 0 PT→ET-Folgen ohne Off-Day (gemessen).
        tids = sorted({g.home for g in real_2024.games} | {g.away for g in real_2024.games})
        assert compliance_report(real_2024, tids, teams_by_id_map).get("CBA-PTET").passed


# ====================================================================
# explain.py
# ====================================================================

class TestExplain:
    def test_explain_contains_sections(self, real_2024, teams):
        md = explain_plan(real_2024, teams).to_markdown()
        for header in ("Überblick", "Reise", "Regel-Compliance",
                       "Reise-Feasibility", "Härteste Road-Trips",
                       "Nachhaltigkeit & Fairness", "Feiertags-Highlights"):
            assert header in md
        assert "Saison 2024" in md

    def test_explain_sustainability_values(self, real_2024, teams):
        # P2-3: CO₂ + Fairness verdrahtet (Gini + CO₂-Tonnen erscheinen).
        md = explain_plan(real_2024, teams).to_markdown()
        assert "CO₂ gesamt" in md and "Gini" in md
        assert "kg/km" in md

    def test_explain_baseline_delta(self, real_2024, teams):
        # Baseline = derselbe Plan → Delta 0,0 %.
        md = explain_plan(real_2024, teams, baseline=real_2024).to_markdown()
        assert "Baseline" in md
        assert "+0.0 %" in md
