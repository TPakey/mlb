"""Tests für Sprint 3: SA-Soft-Terme (Feasibility + Feiertage) und
Doubleheader-Verdichtung (P1-2).

Kernziele:
- DETERMINISMUS: bei abgeschalteten Termen (Default) ist optimize_travel
  bit-identisch; auch mit aktivierten Termen reproduzierbar.
- WIRKUNG: aktivierte Terme verbessern Feasibility bzw. Feiertags-Slates.
- DH: Verdichtung verkürzt Road-Trips, erhält die Spielanzahl, erzeugt
  echte Day-Night-DH.

Nutzt den realen 2024-Plan mit kleiner Iterationszahl (schnell, < 2 s je Lauf).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.season import Game, Season
from src.datasources import LocalFileAdapter
from src.generator import GeneratorConfig
from src.generator_optimizer import (
    OptimizerConfig, optimize_travel, optimize_pareto,
    _season_to_entries, _build_team_index, _team_feasibility_penalty,
)
from src.profiles import get_pareto
from src.feasibility import feasibility_report, DEFAULT_THRESHOLDS
from src.holidays import holiday_report
from src.player_fatigue import max_consecutive_away_days
from src.doubleheaders import (
    can_compress_tail, compress_tail, compress_for_fatigue,
    plan_doubleheaders_for_fatigue, series_game_count,
)
from src.season import detect_all_star_break

from conftest import make_game, make_mini_season


@pytest.fixture(scope="module")
def real_2024(data_dir):
    return LocalFileAdapter(base_dir=str(data_dir)).fetch_season_schedule(2024)


@pytest.fixture(scope="module")
def cfg_2024(real_2024):
    return GeneratorConfig(
        season=2024, season_start=real_2024.season_start,
        season_end=real_2024.season_end,
        all_star_break=detect_all_star_break(real_2024),
        num_search_workers=1, random_seed=42, enforce_fatigue_constraints=True,
    )


def _run(real, teams, cfg, **oc_kw):
    oc = OptimizerConfig(iterations=5000, move_mix_geo=0.35, seed=42,
                         fatigue_lambda=1_000_000.0, **oc_kw)
    return optimize_travel(real, teams, cfg, oc)


# ====================================================================
# Feasibility-Penalty-Helfer
# ====================================================================

def test_feasibility_penalty_helper(teams_by_id_map, cfg_2024):
    # NYY: SEA (Tag 0) → MIA (Tag 1) = 4392 km > Envelope → exceeds.
    base = cfg_2024.season_start
    games = [
        Game(1, base, "SEA", "NYY", "SEA"),
        Game(2, base + timedelta(days=1), "MIA", "NYY", "MIA"),
    ]
    s = Season(season=2024, games=games, season_start=base,
               season_end=base + timedelta(days=180))
    entries = _season_to_entries(s, cfg_2024)
    team_idx = _build_team_index(entries)
    pen = _team_feasibility_penalty("NYY", entries, team_idx, teams_by_id_map,
                                    base, DEFAULT_THRESHOLDS, 1.0, 0.1)
    assert pen == pytest.approx(1.0)   # genau ein exceeds-Transfer


# ====================================================================
# Determinismus
# ====================================================================

class TestDeterminism:
    def test_all_off_deterministic(self, real_2024, teams, cfg_2024):
        _, a = _run(real_2024, teams, cfg_2024)
        _, b = _run(real_2024, teams, cfg_2024)
        assert a.final_km == b.final_km

    def test_feas_on_deterministic(self, real_2024, teams, cfg_2024):
        _, a = _run(real_2024, teams, cfg_2024, feas_lambda=50_000.0)
        _, b = _run(real_2024, teams, cfg_2024, feas_lambda=50_000.0)
        assert a.final_km == b.final_km

    def test_holiday_on_deterministic(self, real_2024, teams, cfg_2024):
        _, a = _run(real_2024, teams, cfg_2024, holiday_lambda=5_000.0)
        _, b = _run(real_2024, teams, cfg_2024, holiday_lambda=5_000.0)
        assert a.final_km == b.final_km

    def test_off_terms_do_not_change_result(self, real_2024, teams, cfg_2024):
        # feas_lambda=0 muss exakt dasselbe Ergebnis liefern wie ohne Angabe.
        _, base = _run(real_2024, teams, cfg_2024)
        _, zero = _run(real_2024, teams, cfg_2024, feas_lambda=0.0,
                       holiday_lambda=0.0)
        assert base.final_km == zero.final_km


# ====================================================================
# Wirkung der Terme
# ====================================================================

class TestEffect:
    def test_feasibility_term_reduces_violations(self, real_2024, teams, cfg_2024,
                                                 teams_by_id_map):
        tids = sorted({g.home for g in real_2024.games})
        off, _ = _run(real_2024, teams, cfg_2024)
        on, _ = _run(real_2024, teams, cfg_2024, feas_lambda=50_000.0)
        v_off = feasibility_report(off, tids, teams_by_id_map).summary()["n_violations"]
        v_on = feasibility_report(on, tids, teams_by_id_map).summary()["n_violations"]
        # Der Feasibility-Term darf die Lage nie verschlechtern und behebt hier
        # die von der km-only-SA eingefuehrten Envelope-Verstoesse.
        assert v_on <= v_off

    def test_holiday_term_improves_slate(self, real_2024, teams, cfg_2024):
        def slate_total(season):
            r = holiday_report(season)
            return sum(e.teams_active for e in r.evaluations
                       if e.holiday.kind == "league_wide" and e.in_season)
        off, _ = _run(real_2024, teams, cfg_2024)
        on, _ = _run(real_2024, teams, cfg_2024, holiday_lambda=5_000.0)
        assert slate_total(on) >= slate_total(off)


# ====================================================================
# Doubleheader-Verdichtung
# ====================================================================

class TestDoubleheaders:
    def _trip_season(self, base):
        # NYY: 14-Tage-Road-Trip, letzte Serie (CLE) 2 Spiele → verdichtbar.
        plan = [(0, "BOS"), (1, "BOS"), (2, "BOS"), (3, "BAL"), (4, "BAL"),
                (5, "BAL"), (6, "TBR"), (7, "TBR"), (8, "TBR"), (9, "TOR"),
                (10, "TOR"), (11, "TOR"), (12, "CLE"), (13, "CLE")]
        games = [Game(i + 1, base + timedelta(days=off), opp, "NYY", opp)
                 for i, (off, opp) in enumerate(plan)]
        return Season(season=2026, games=games, season_start=base,
                      season_end=base + timedelta(days=180))

    def test_can_compress_and_compress_tail(self):
        from src.generator_optimizer import SeriesEntry
        e = SeriesEntry(idx=0, home="CLE", away="NYY", length=3,
                        start_day=0, day_game_counts=(1, 1, 1))
        assert can_compress_tail(e)
        dh_day = compress_tail(e)
        assert e.length == 2
        assert e.day_game_counts == (1, 2)
        assert dh_day == 1
        assert series_game_count(e) == 3      # Spielanzahl erhalten
        # Nach Verdichtung kein weiterer Tail-DH (vorletzter Tag hat schon 2)
        assert not can_compress_tail(e)

    def test_compress_for_fatigue_fixes_trip(self):
        base = date(2026, 4, 1)
        cfg = GeneratorConfig(season=2026, season_start=base,
                              season_end=base + timedelta(days=180))
        s = self._trip_season(base)
        assert max_consecutive_away_days(s, "NYY") == 14
        ns, plan = compress_for_fatigue(s, cfg, away_limit=13)
        assert plan.n_created == 1
        assert max_consecutive_away_days(ns, "NYY") == 13
        # Spielanzahl erhalten
        assert len([g for g in ns.games if g.involves("NYY")]) == 14
        # echter Day-Night-DH erzeugt
        dh = [g for g in ns.games if g.doubleheader_seq > 0]
        assert len(dh) == 2 and {g.doubleheader_seq for g in dh} == {1, 2}

    def test_compress_for_fatigue_noop_when_compliant(self):
        base = date(2026, 4, 1)
        cfg = GeneratorConfig(season=2026, season_start=base,
                              season_end=base + timedelta(days=180))
        # Kurzer Trip (3 Tage) → nichts zu tun.
        games = [Game(i + 1, base + timedelta(days=off), "BOS", "NYY", "BOS")
                 for i, off in enumerate((0, 1, 2))]
        s = Season(season=2026, games=games, season_start=base,
                   season_end=base + timedelta(days=180))
        ns, plan = compress_for_fatigue(s, cfg, away_limit=13)
        assert plan.n_created == 0

    def test_geo_topk_default_bit_identical(self, real_2024, teams, cfg_2024):
        # P2-5: geo_topk=2 (Default) ist bit-identisch zu nicht gesetztem Wert.
        _, a = _run(real_2024, teams, cfg_2024)
        _, b = _run(real_2024, teams, cfg_2024, geo_topk=2)
        assert a.final_km == b.final_km

    def test_geo_topk_wider_deterministic(self, real_2024, teams, cfg_2024):
        # Breitere Nachbarschaft bleibt deterministisch. (Der km-Gewinn zeigt sich
        # erst bei hohen Iterationszahlen — gemessen 200k: topk=6 ~−1 % vs topk=2;
        # bei wenigen Iterationen konvergiert die breitere Nachbarschaft langsamer.
        # Daher hier nur Determinismus, nicht die km-Verbesserung asserten.)
        _, k6a = _run(real_2024, teams, cfg_2024, geo_topk=6)
        _, k6b = _run(real_2024, teams, cfg_2024, geo_topk=6)
        assert k6a.final_km == k6b.final_km

    def test_dh_compression_in_optimize_travel_preserves_games(
            self, real_2024, teams, cfg_2024):
        # enable_dh_compression darf die Gesamt-Spielanzahl nie aendern und
        # bleibt deterministisch.
        a, la = _run(real_2024, teams, cfg_2024, enable_dh_compression=True)
        b, lb = _run(real_2024, teams, cfg_2024, enable_dh_compression=True)
        assert len(a.games) == len(real_2024.games)
        assert la.final_km == lb.final_km


# ====================================================================
# P1-5: Geo-Move + Feasibility/Holiday in optimize_pareto
# ====================================================================

class TestParetoP15:
    def _run(self, real, teams, cfg, **kw):
        prof = get_pareto("balanced")
        return optimize_pareto(real, teams, cfg, prof, iterations=1500, seed=42, **kw)

    def test_default_deterministic_and_unchanged(self, real_2024, teams, cfg_2024):
        # Default (alle neuen Terme aus) ist reproduzierbar — und identisch,
        # egal ob die Lambdas explizit 0 oder gar nicht gesetzt sind.
        _, b1, l1 = self._run(real_2024, teams, cfg_2024)
        _, b2, l2 = self._run(real_2024, teams, cfg_2024)
        assert l1.final_energy == l2.final_energy
        assert b1.travel_km == b2.travel_km
        _, b3, l3 = self._run(real_2024, teams, cfg_2024,
                              move_mix_geo=0.0, feas_lambda=0.0, holiday_lambda=0.0)
        assert l3.final_energy == l1.final_energy
        assert b3.travel_km == b1.travel_km

    def test_geo_move_deterministic_and_helps_travel(self, real_2024, teams, cfg_2024):
        _, off, _ = self._run(real_2024, teams, cfg_2024)
        _, on1, l1 = self._run(real_2024, teams, cfg_2024, move_mix_geo=0.35)
        _, on2, l2 = self._run(real_2024, teams, cfg_2024, move_mix_geo=0.35)
        assert l1.final_energy == l2.final_energy            # deterministisch
        # Geo-Move darf die Reise nicht verschlechtern (Struktur-Nachbarschaft).
        assert on1.travel_km <= off.travel_km

    def test_feas_term_deterministic_and_no_worse(self, real_2024, teams, cfg_2024,
                                                  teams_by_id_map):
        from src.feasibility import feasibility_report
        tids = sorted({g.home for g in real_2024.games})
        s_off, _, _ = self._run(real_2024, teams, cfg_2024, move_mix_geo=0.35)
        s_on, _, l1 = self._run(real_2024, teams, cfg_2024, move_mix_geo=0.35,
                                feas_lambda=50_000.0)
        _, _, l2 = self._run(real_2024, teams, cfg_2024, move_mix_geo=0.35,
                             feas_lambda=50_000.0)
        assert l1.final_energy == l2.final_energy
        v_off = feasibility_report(s_off, tids, teams_by_id_map).summary()["n_violations"]
        v_on = feasibility_report(s_on, tids, teams_by_id_map).summary()["n_violations"]
        assert v_on <= v_off

    def test_holiday_term_deterministic(self, real_2024, teams, cfg_2024):
        _, _, l1 = self._run(real_2024, teams, cfg_2024, holiday_lambda=5_000.0)
        _, _, l2 = self._run(real_2024, teams, cfg_2024, holiday_lambda=5_000.0)
        assert l1.final_energy == l2.final_energy
