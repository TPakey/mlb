"""Tests für Sprint 4 — neue, gegatete Erweiterungen.

OROPT-Move (Best-Insertion-Geo / TTP-Nachbarschaft):
- DETERMINISMUS: Default (move_mix_oropt=0) bit-identisch zur GEO-Baseline,
  und auch mit aktivem OROPT reproduzierbar (bit-identisch über Läufe).
- INVARIANZ: der Move erhält Spielanzahl/Matchups und bricht keine
  Constraints (AC-2.1.8/9 bleiben ≤ Limit auf dem realen Plan).

Begründung/Messung der NICHT-Aufnahme als Default: docs/SPRINT_4_REVIEW.md
(OROPT konvergiert früh minimal besser, ist aber bei Produktions-Iterationen
schlechter als der stochastische GEO-Move → bleibt gegatet/off).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.datasources import LocalFileAdapter
from src.generator import GeneratorConfig
from src.generator_optimizer import OptimizerConfig, optimize_travel
from src.player_fatigue import (
    max_consecutive_away_days, max_games_without_off_day,
)
from src.season import Game, Season, detect_all_star_break
from src.doubleheaders import compress_for_fatigue
from src.event_conflicts import LocalEvent, venue_conflicts
from src.compliance import compliance_report, RULES

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


def _run(real, teams, cfg, iterations=4000, **oc_kw):
    oc = OptimizerConfig(iterations=iterations, move_mix_geo=0.35, geo_topk=6,
                         seed=42, fatigue_lambda=1_000_000.0, **oc_kw)
    return optimize_travel(real, teams, cfg, oc)


class TestOroptDeterminism:
    def test_default_off_is_geo_baseline(self, real_2024, teams, cfg_2024):
        # move_mix_oropt=0 (Default) → leeres OROPT-Band → bit-identisch zur
        # reinen GEO-Baseline (Default-Determinismus bleibt unverändert).
        _, base = _run(real_2024, teams, cfg_2024)
        _, zero = _run(real_2024, teams, cfg_2024, move_mix_oropt=0.0)
        assert base.final_km == zero.final_km

    def test_oropt_on_reproducible(self, real_2024, teams, cfg_2024):
        _, a = _run(real_2024, teams, cfg_2024, move_mix_oropt=0.3)
        _, b = _run(real_2024, teams, cfg_2024, move_mix_oropt=0.3)
        assert a.final_km == b.final_km

    def test_oropt_changes_search(self, real_2024, teams, cfg_2024):
        # Mit aktivem OROPT nimmt die Suche einen anderen Pfad → i.d.R. anderes
        # Ergebnis als die reine GEO-Baseline (beweist, dass der Branch wirkt).
        _, base = _run(real_2024, teams, cfg_2024)
        _, oropt = _run(real_2024, teams, cfg_2024, move_mix_oropt=0.5)
        assert base.final_km != oropt.final_km


class TestOroptInvariants:
    def test_game_count_preserved(self, real_2024, teams, cfg_2024):
        season, _ = _run(real_2024, teams, cfg_2024, move_mix_oropt=0.4)
        assert len(season.games) == len(real_2024.games)

    def test_no_constraint_violation(self, real_2024, teams, cfg_2024):
        season, _ = _run(real_2024, teams, cfg_2024, move_mix_oropt=0.4)
        team_ids = [t.id for t in teams]
        worst_away = max(max_consecutive_away_days(season, t) for t in team_ids)
        worst_off = max(max_games_without_off_day(season, t) for t in team_ids)
        assert worst_away <= 13
        assert worst_off <= 20

    def test_oropt_not_worse_than_start(self, real_2024, teams, cfg_2024):
        _, log = _run(real_2024, teams, cfg_2024, move_mix_oropt=0.4)
        # Der Optimierer darf den Startplan nie verschlechtern.
        assert log.final_km <= log.initial_km


# ====================================================================
# DH-Compression v2 (Compression + Pull-in)
# ====================================================================

class TestDoubleheaderV2:
    def _trip_last_single(self, base):
        """NYY: 14-Tage-Trip, dessen LETZTE Serie nur 1 Spiel hat (nicht
        tail-verdichtbar) → v1 ist no-op, v2 (Pull-in) muss greifen.
        BOS 0-2, BAL 3-5, TBR 6-8, TOR 9-11, CLE 12 (1), DET 13 (1)."""
        plan = [(0, "BOS"), (1, "BOS"), (2, "BOS"), (3, "BAL"), (4, "BAL"),
                (5, "BAL"), (6, "TBR"), (7, "TBR"), (8, "TBR"), (9, "TOR"),
                (10, "TOR"), (11, "TOR"), (12, "CLE"), (13, "DET")]
        games = [Game(i + 1, base + timedelta(days=off), opp, "NYY", opp)
                 for i, (off, opp) in enumerate(plan)]
        return Season(season=2026, games=games, season_start=base,
                      season_end=base + timedelta(days=180))

    def test_v1_noop_when_last_series_single(self):
        base = date(2026, 4, 1)
        cfg = GeneratorConfig(season=2026, season_start=base,
                              season_end=base + timedelta(days=180))
        s = self._trip_last_single(base)
        assert max_consecutive_away_days(s, "NYY") == 14
        # v1 (Default): letzte Serie 1 Spiel → kein Tail-DH möglich → no-op.
        _, plan = compress_for_fatigue(s, cfg, away_limit=13)
        assert plan.n_created == 0

    def test_v2_pullin_fixes_trip(self):
        base = date(2026, 4, 1)
        cfg = GeneratorConfig(season=2026, season_start=base,
                              season_end=base + timedelta(days=180))
        s = self._trip_last_single(base)
        ns, plan = compress_for_fatigue(s, cfg, away_limit=13, enable_pullin=True)
        assert plan.n_created == 1
        assert max_consecutive_away_days(ns, "NYY") == 13
        # Spielanzahl exakt erhalten (Matchup-Quoten).
        assert len([g for g in ns.games if g.involves("NYY")]) == 14
        # Echter Day-Night-DH erzeugt.
        dh = [g for g in ns.games if g.doubleheader_seq > 0]
        assert len(dh) == 2 and {g.doubleheader_seq for g in dh} == {1, 2}

    def test_v2_preserves_each_matchup_count(self):
        base = date(2026, 4, 1)
        cfg = GeneratorConfig(season=2026, season_start=base,
                              season_end=base + timedelta(days=180))
        s = self._trip_last_single(base)
        ns, _ = compress_for_fatigue(s, cfg, away_limit=13, enable_pullin=True)

        def counts(season):
            out = {}
            for g in season.games:
                out[(g.home, g.away)] = out.get((g.home, g.away), 0) + 1
            return out
        assert counts(ns) == counts(s)

    def test_v2_still_does_v1_when_possible(self):
        # Endet der Trip auf einer ≥2-Spiel-Serie, liefert v2 dasselbe wie v1
        # (Tail-Compression bevorzugt) — keine Regression.
        base = date(2026, 4, 1)
        cfg = GeneratorConfig(season=2026, season_start=base,
                              season_end=base + timedelta(days=180))
        plan = [(0, "BOS"), (1, "BOS"), (2, "BOS"), (3, "BAL"), (4, "BAL"),
                (5, "BAL"), (6, "TBR"), (7, "TBR"), (8, "TBR"), (9, "TOR"),
                (10, "TOR"), (11, "TOR"), (12, "CLE"), (13, "CLE")]
        games = [Game(i + 1, base + timedelta(days=off), opp, "NYY", opp)
                 for i, (off, opp) in enumerate(plan)]
        s = Season(season=2026, games=games, season_start=base,
                   season_end=base + timedelta(days=180))
        _, p1 = compress_for_fatigue(s, cfg, away_limit=13)
        s2 = Season(season=2026, games=list(games), season_start=base,
                    season_end=base + timedelta(days=180))
        ns2, p2 = compress_for_fatigue(s2, cfg, away_limit=13, enable_pullin=True)
        assert p1.n_created == p2.n_created == 1
        assert max_consecutive_away_days(ns2, "NYY") == 13


# ====================================================================
# Harter Venue-Belegungskalender (VENUE-AVAIL)
# ====================================================================

def _booking(team, city, day_offset, base=date(2026, 4, 1), name="Konzert"):
    d = base + timedelta(days=day_offset)
    return LocalEvent(city=city, team_ids=(team,), name=name,
                      start_date=d, end_date=d, severity=5,
                      category="stadium_booking")


class TestVenueCalendar:
    def test_conflict_detected(self):
        # NYY-Heimspiel an Tag 5; Stadion an Tag 5 belegt → harter Konflikt.
        s = make_mini_season([make_game(1, 5, "NYY", "BOS")])
        events = [_booking("NYY", "New York", 5)]
        conflicts = venue_conflicts(s, events)
        assert len(conflicts) == 1
        assert conflicts[0].team_id == "NYY"

    def test_no_conflict_when_clear(self):
        s = make_mini_season([make_game(1, 5, "NYY", "BOS")])
        events = [_booking("NYY", "New York", 7)]    # anderer Tag
        assert venue_conflicts(s, events) == []

    def test_away_game_not_a_conflict(self):
        # Belegung trifft nur Heimspiele; NYY ist hier auswärts (BOS Heim).
        s = make_mini_season([make_game(1, 5, "BOS", "NYY")])
        events = [_booking("NYY", "New York", 5)]
        assert venue_conflicts(s, events) == []

    def test_compliance_optin_default_unchanged(self, teams_by_id_map):
        # Ohne events/check_venue: weiterhin keine VENUE-AVAIL-Regel im Report
        # (rückwärtskompatibel).
        s = make_mini_season([make_game(1, 0, "NYY", "BOS")])
        rep = compliance_report(s, ["NYY", "BOS"], teams_by_id_map)
        assert rep.get("VENUE-AVAIL") is None

    def test_compliance_venue_fails_on_conflict(self, teams_by_id_map):
        s = make_mini_season([make_game(1, 5, "NYY", "BOS")])
        events = [_booking("NYY", "New York", 5)]
        rep = compliance_report(s, ["NYY", "BOS"], teams_by_id_map, events=events)
        chk = rep.get("VENUE-AVAIL")
        assert chk is not None and not chk.passed
        assert not rep.is_compliant            # hart → bricht Compliance

    def test_compliance_venue_passes_when_clear(self, teams_by_id_map):
        s = make_mini_season([make_game(1, 5, "NYY", "BOS")])
        events = [_booking("NYY", "New York", 7)]
        rep = compliance_report(s, ["NYY", "BOS"], teams_by_id_map, events=events)
        assert rep.get("VENUE-AVAIL").passed

    def test_venue_rule_in_registry(self):
        assert "VENUE-AVAIL" in RULES
        assert RULES["VENUE-AVAIL"].severity == "hard"

    def test_hard_blackout_enforced_in_sa(self, teams, cfg_2024, real_2024):
        # End-to-End: home_blackout_days verbietet der SA, ein Heimspiel auf einen
        # belegten Tag zu SCHIEBEN. (Vorbestehende Platzierungen werden nicht
        # zwangsverschoben — daher sperren wir Tage, die im Startplan für NYY-
        # Heimspiele FREI sind, und prüfen, dass die SA keine darauf legt.)
        import dataclasses
        start = cfg_2024.season_start
        init_nyy_home = {(g.date - start).days
                         for g in real_2024.games if g.home == "NYY"}
        # Wähle verstreute Tage, die im Startplan KEIN NYY-Heimspiel tragen
        # (NYY-Heimspiele sind zu dicht für ein zusammenhängendes Fenster).
        total = (cfg_2024.season_end - start).days
        free = [d for d in range(20, total - 5) if d not in init_nyy_home]
        assert len(free) >= 10
        window = set(free[:10])
        cfg = dataclasses.replace(cfg_2024,
                                  home_blackout_days={"NYY": frozenset(window)})
        oc = OptimizerConfig(iterations=8000, move_mix_geo=0.35, geo_topk=6,
                             seed=42, fatigue_lambda=1_000_000.0)
        season, _ = optimize_travel(real_2024, teams, cfg, oc)
        nyy_home_days = {(g.date - start).days
                         for g in season.games if g.home == "NYY"}
        assert nyy_home_days.isdisjoint(window)


# ====================================================================
# Ops-Dashboard-Builder
# ====================================================================

class TestOpsDashboard:
    def _builder(self):
        import importlib.util
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "build_ops_dashboard", root / "dashboard" / "build_ops_dashboard.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_payload_structure(self):
        mod = self._builder()
        payload = mod.build_payload(2024)
        assert payload["season"] == 2024
        assert len(payload["teams"]) == 30
        nyy = payload["teams"]["NYY"]
        assert nyy["n_cities"] > 0
        city = nyy["cities"][0]
        for key in ("city", "host", "start", "end", "risk_level", "severity",
                    "routing", "trauma_center", "high_profile", "hotel"):
            assert key in city
        # Severity in gültigem Bereich.
        assert 0 <= city["severity"] <= 5

    def test_html_is_self_contained(self, tmp_path):
        import json
        import re
        mod = self._builder()
        out = tmp_path / "ops.html"
        mod.build(2024, out)
        html = out.read_text(encoding="utf-8")
        assert "<html" in html and "Trip-Dossiers" in html
        # Eingebetteter JSON-Payload ist gültig.
        m = re.search(r'type="application/json">(.*?)</script>', html, re.S)
        assert m is not None
        data = json.loads(m.group(1))
        assert len(data["teams"]) == 30


# ====================================================================
# Härtung — Input-Validierung & Fehlerbehandlung
# ====================================================================

class TestHardening:
    def test_corrupt_json_raises_clean_error(self, tmp_path):
        from src.datasources import LocalFileAdapter, DataSourceError
        bad = tmp_path / "mlb_schedule_2099.json"
        bad.write_text("{ this is not valid json ", encoding="utf-8")
        with pytest.raises(DataSourceError, match="kein gültiges JSON"):
            LocalFileAdapter(base_dir=tmp_path).fetch_season_schedule(2099)

    def test_missing_file_raises_clean_error(self, tmp_path):
        from src.datasources import LocalFileAdapter, DataSourceError
        with pytest.raises(DataSourceError, match="Keine Schedule-Datei"):
            LocalFileAdapter(base_dir=tmp_path).fetch_season_schedule(2099)

    def test_unknown_format_raises_clean_error(self, tmp_path):
        from src.datasources import LocalFileAdapter, DataSourceError
        bad = tmp_path / "mlb_schedule_2099.json"
        bad.write_text('{"foo": 1}', encoding="utf-8")   # weder dates noch Liste
        with pytest.raises(DataSourceError, match="Unbekanntes JSON-Format"):
            LocalFileAdapter(base_dir=tmp_path).fetch_season_schedule(2099)

    def _args(self, **over):
        import argparse
        d = dict(travel_iterations=1000, sa_iterations=100, interior=4,
                 solver_time=60.0, geo_topk=2, feas_lambda=0.0,
                 holiday_lambda=0.0, oropt_share=0.0)
        d.update(over)
        return argparse.Namespace(**d)

    def test_cli_rejects_negative_iterations(self):
        from src.main import _validate_args
        with pytest.raises(SystemExit, match="travel-iterations"):
            _validate_args(self._args(travel_iterations=-1))

    def test_cli_rejects_bad_oropt_share(self):
        from src.main import _validate_args
        with pytest.raises(SystemExit, match="oropt-share"):
            _validate_args(self._args(oropt_share=1.5))

    def test_cli_rejects_bad_geo_topk(self):
        from src.main import _validate_args
        with pytest.raises(SystemExit, match="geo-topk"):
            _validate_args(self._args(geo_topk=0))

    def test_cli_accepts_valid_args(self):
        from src.main import _validate_args
        _validate_args(self._args())          # darf nicht werfen
