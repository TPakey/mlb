"""Tests für tools/whatif_demo.py (Sprint 2.6).

Abdeckung:
  - Argument-Parser: alle Flags vorhanden, Defaults korrekt
  - _build_cfg: GeneratorConfig korrekt initialisiert
  - _fmt_time: Formatierung ms / s
  - _result_to_json_entry: JSON-Struktur korrekt
  - _export_json: Datei wird geschrieben, JSON valide
  - run_demo: Smoke-Test mit --no-json --scenario force (gepatchter Generator)
  - Szenario-Routing: nur das gewünschte Szenario wird ausgeführt

Nicht abgedeckt (benötigen echte Saison-Generierung ~20s):
  - Voller E2E-Durchlauf run_demo() mit allen 3 Szenarien
  - Szenario 3 (Pareto) mit realem SA

Sprint-Referenz: docs/SPRINT_2_6_REVIEW.md
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.whatif_demo import (
    _build_cfg,
    _export_json,
    _fmt_time,
    _parse_args,
    _result_to_json_entry,
)
from src.generator import GeneratorConfig
from src.pareto_types import ParetoBundle
from src.season import Game, Season
from src.whatif import WhatIfResult, DimensionDelta


# ====================================================================
# Hilfsfunktionen
# ====================================================================

def _mk_bundle(**kwargs) -> ParetoBundle:
    defaults = dict(
        travel_km=1_900_000.0,
        revenue_usd=8_000_000_000.0,
        fatigue_score=450.0,
        max_away_streak=11.0,
        off_day_variance=2.5,
        tv_slot_score=280.0,
        event_friction=90.0,
        constraint_violations=0.0,
    )
    defaults.update(kwargs)
    return ParetoBundle(**defaults)


def _mk_delta(name: str, orig: float, mod: float, direction: str = "neutral") -> DimensionDelta:
    return DimensionDelta(
        name=name, label=name, unit="",
        original=orig, modified=mod,
        delta=mod - orig, delta_pct=0.0,
        direction=direction, minimize=True,
    )


def _mk_season() -> Season:
    games = [
        Game(game_pk=i, date=date(2026, 4, 1) + timedelta(days=i),
             home="NYY", away="BOS", venue="NYY")
        for i in range(5)
    ]
    return Season(season=2026, games=games,
                  season_start=date(2026, 3, 26), season_end=date(2026, 9, 27))


def _mk_whatif_result(n_better: int = 3, feasible: bool = True) -> WhatIfResult:
    bundle = _mk_bundle()
    mod_bundle = _mk_bundle(travel_km=1_880_000.0)
    deltas = [
        _mk_delta("travel_km", 1_900_000, 1_880_000, "better"),
        _mk_delta("revenue_usd", 8e9, 8e9, "neutral"),
        _mk_delta("fatigue_score", 450, 460, "worse"),
    ]
    return WhatIfResult(
        scenario_name="Test",
        description="Test-Szenario",
        original_bundle=bundle,
        modified_bundle=mod_bundle,
        deltas=deltas,
        modified_season=_mk_season(),
        feasible=feasible,
        warnings=[],
    )


# ====================================================================
# Argument-Parser
# ====================================================================

class TestParseArgs:
    def test_defaults(self):
        with patch("sys.argv", ["whatif_demo.py"]):
            args = _parse_args()
        assert args.seed == 42
        assert args.sa_iter == 3000
        assert args.scenario == "all"
        assert args.no_json is False
        assert args.verbose is False
        assert args.json_out == ""

    def test_seed_override(self):
        with patch("sys.argv", ["whatif_demo.py", "--seed", "7"]):
            args = _parse_args()
        assert args.seed == 7

    def test_scenario_force(self):
        with patch("sys.argv", ["whatif_demo.py", "--scenario", "force"]):
            args = _parse_args()
        assert args.scenario == "force"

    def test_scenario_blackout(self):
        with patch("sys.argv", ["whatif_demo.py", "--scenario", "blackout"]):
            args = _parse_args()
        assert args.scenario == "blackout"

    def test_scenario_compare(self):
        with patch("sys.argv", ["whatif_demo.py", "--scenario", "compare"]):
            args = _parse_args()
        assert args.scenario == "compare"

    def test_no_json_flag(self):
        with patch("sys.argv", ["whatif_demo.py", "--no-json"]):
            args = _parse_args()
        assert args.no_json is True

    def test_json_out(self):
        with patch("sys.argv", ["whatif_demo.py", "--json-out", "/tmp/test.json"]):
            args = _parse_args()
        assert args.json_out == "/tmp/test.json"

    def test_verbose(self):
        with patch("sys.argv", ["whatif_demo.py", "--verbose"]):
            args = _parse_args()
        assert args.verbose is True

    def test_invalid_scenario(self):
        with patch("sys.argv", ["whatif_demo.py", "--scenario", "invalid"]):
            with pytest.raises(SystemExit):
                _parse_args()


# ====================================================================
# _build_cfg
# ====================================================================

class TestBuildCfg:
    def test_returns_generator_config(self):
        cfg = _build_cfg(seed=42)
        assert isinstance(cfg, GeneratorConfig)

    def test_seed_propagated(self):
        cfg = _build_cfg(seed=99)
        assert cfg.random_seed == 99

    def test_season_2026(self):
        cfg = _build_cfg(seed=42)
        assert cfg.season == 2026
        assert cfg.season_start == date(2026, 3, 26)
        assert cfg.season_end == date(2026, 9, 27)

    def test_enforce_fatigue_true(self):
        cfg = _build_cfg(seed=42)
        assert cfg.enforce_fatigue_constraints is True

    def test_reproducibility_workers(self):
        cfg = _build_cfg(seed=42)
        assert cfg.num_search_workers == 1

    def test_all_star_break_set(self):
        cfg = _build_cfg(seed=42)
        assert cfg.all_star_break is not None
        start, end = cfg.all_star_break
        assert start == date(2026, 7, 13)
        assert end == date(2026, 7, 16)


# ====================================================================
# _fmt_time
# ====================================================================

class TestFmtTime:
    def test_under_one_second(self):
        result = _fmt_time(0.056)
        assert "ms" in result
        assert "56" in result

    def test_exactly_one_second(self):
        result = _fmt_time(1.0)
        assert "s" in result
        assert "1.0" in result

    def test_larger_value(self):
        result = _fmt_time(17.3)
        assert "17.3s" == result

    def test_sub_millisecond(self):
        result = _fmt_time(0.0001)
        assert "ms" in result

    def test_zero(self):
        result = _fmt_time(0.0)
        assert "0ms" == result


# ====================================================================
# _result_to_json_entry
# ====================================================================

class TestResultToJsonEntry:
    def test_none_result_returns_skipped(self):
        entry = _result_to_json_entry("test_label", None, 0.0)
        assert entry["scenario"] == "test_label"
        assert entry["status"] == "skipped"

    def test_valid_result_has_scenario_name(self):
        result = _mk_whatif_result()
        entry = _result_to_json_entry("force_nyyatbos", result, 1.5)
        assert entry["scenario"] == "force_nyyatbos"

    def test_valid_result_has_elapsed(self):
        result = _mk_whatif_result()
        entry = _result_to_json_entry("force_nyyatbos", result, 1.23)
        assert abs(entry["elapsed_s"] - 1.23) < 1e-3

    def test_valid_result_has_feasible(self):
        result = _mk_whatif_result(feasible=True)
        entry = _result_to_json_entry("test", result, 0.5)
        assert entry["feasible"] is True

    def test_valid_result_has_deltas(self):
        result = _mk_whatif_result()
        entry = _result_to_json_entry("test", result, 0.5)
        assert "deltas" in entry
        assert isinstance(entry["deltas"], list)
        assert len(entry["deltas"]) > 0

    def test_valid_result_has_n_better_worse(self):
        result = _mk_whatif_result()
        entry = _result_to_json_entry("test", result, 0.5)
        assert "n_better" in entry
        assert "n_worse" in entry

    def test_json_serializable(self):
        result = _mk_whatif_result()
        entry = _result_to_json_entry("test", result, 0.5)
        # Muss fehlerfrei JSON-serialisierbar sein
        serialized = json.dumps(entry)
        assert len(serialized) > 0

    def test_infeasible_result(self):
        result = _mk_whatif_result(feasible=False)
        entry = _result_to_json_entry("test", result, 0.1)
        assert entry["feasible"] is False


# ====================================================================
# _export_json
# ====================================================================

class TestExportJson:
    def _get_cfg(self) -> GeneratorConfig:
        return _build_cfg(42)

    def test_creates_file(self, tmp_path):
        out = tmp_path / "output" / "test.json"
        cfg = self._get_cfg()
        _export_json(out, cfg, gen_time=15.0, n_games=2432, scenarios=[])
        assert out.exists()

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "test.json"
        cfg = self._get_cfg()
        _export_json(out, cfg, gen_time=15.0, n_games=2432, scenarios=[])
        assert out.exists()

    def test_valid_json(self, tmp_path):
        out = tmp_path / "test.json"
        cfg = self._get_cfg()
        _export_json(out, cfg, gen_time=15.0, n_games=2432, scenarios=[])
        data = json.loads(out.read_text())
        assert "meta" in data
        assert "scenarios" in data

    def test_meta_fields(self, tmp_path):
        out = tmp_path / "test.json"
        cfg = self._get_cfg()
        _export_json(out, cfg, gen_time=15.0, n_games=2432, scenarios=[])
        meta = json.loads(out.read_text())["meta"]
        assert meta["season"] == 2026
        assert meta["seed"] == 42
        assert meta["n_games"] == 2432
        assert meta["generator_time_s"] == 15.0
        assert "sprint" in meta

    def test_scenarios_list(self, tmp_path):
        out = tmp_path / "test.json"
        cfg = self._get_cfg()
        scenarios = [{"scenario": "test", "feasible": True}]
        _export_json(out, cfg, gen_time=5.0, n_games=100, scenarios=scenarios)
        data = json.loads(out.read_text())
        assert len(data["scenarios"]) == 1
        assert data["scenarios"][0]["scenario"] == "test"

    def test_generated_at_is_iso(self, tmp_path):
        out = tmp_path / "test.json"
        cfg = self._get_cfg()
        _export_json(out, cfg, gen_time=1.0, n_games=10, scenarios=[])
        meta = json.loads(out.read_text())["meta"]
        # ISO-Format: kein ValueError
        datetime.fromisoformat(meta["generated_at"])

    def test_unicode_in_scenarios(self, tmp_path):
        out = tmp_path / "test.json"
        cfg = self._get_cfg()
        scenarios = [{"scenario": "Konzert — Münich", "feasible": True}]
        _export_json(out, cfg, gen_time=1.0, n_games=10, scenarios=scenarios)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "Münich" in data["scenarios"][0]["scenario"]


# ====================================================================
# run_demo Smoke-Test (gepatchter Generator)
# ====================================================================

class TestRunDemoSmoke:
    """Smoke-Tests: run_demo() mit --no-json und --scenario force.

    Der Generator (generate) und whatif_force_series werden gepacht,
    damit die Tests in < 1s laufen.
    """

    def _make_args(
        self,
        scenario: str = "force",
        no_json: bool = True,
        seed: int = 42,
    ) -> argparse.Namespace:
        return argparse.Namespace(
            seed=seed,
            sa_iter=3000,
            scenario=scenario,
            json_out="",
            no_json=no_json,
            verbose=False,
        )

    def _make_mock_season(self) -> Season:
        return _mk_season()

    def _make_mock_result(self) -> MagicMock:
        """Simuliert GeneratorResult."""
        r = MagicMock()
        r.season = self._make_mock_season()
        r.status = "OPTIMAL"
        r.final_km = 1_900_000.0
        return r

    @patch("tools.whatif_demo.whatif_force_series")
    @patch("tools.whatif_demo.load_teams")
    @patch("tools.whatif_demo.generate")
    @patch("tools.whatif_demo.extract_matchup_quotas")
    @patch("tools.whatif_demo.LocalFileAdapter")
    def test_force_scenario_runs(
        self, mock_adapter, mock_quotas, mock_generate,
        mock_load_teams, mock_force, capsys
    ):
        """Szenario 'force' läuft ohne Exception durch (gepatch)."""
        mock_generate.return_value = self._make_mock_result()
        mock_load_teams.return_value = []
        mock_adapter.return_value.fetch_season_schedule.return_value = MagicMock()
        mock_quotas.return_value = MagicMock()

        # whatif_force_series gibt ein valides WhatIfResult zurück
        mock_force.return_value = _mk_whatif_result()

        from tools.whatif_demo import run_demo
        args = self._make_args(scenario="force", no_json=True)

        # Kein Exception = Smoke-Test bestanden
        run_demo(args)

        mock_force.assert_called_once()

    @patch("tools.whatif_demo.whatif_blackout")
    @patch("tools.whatif_demo.load_teams")
    @patch("tools.whatif_demo.generate")
    @patch("tools.whatif_demo.extract_matchup_quotas")
    @patch("tools.whatif_demo.LocalFileAdapter")
    def test_blackout_scenario_runs(
        self, mock_adapter, mock_quotas, mock_generate,
        mock_load_teams, mock_blackout, capsys
    ):
        """Szenario 'blackout' läuft ohne Exception durch."""
        mock_generate.return_value = self._make_mock_result()
        mock_load_teams.return_value = []
        mock_adapter.return_value.fetch_season_schedule.return_value = MagicMock()
        mock_quotas.return_value = MagicMock()
        mock_blackout.return_value = _mk_whatif_result()

        from tools.whatif_demo import run_demo
        args = self._make_args(scenario="blackout", no_json=True)
        run_demo(args)
        mock_blackout.assert_called_once()

    @patch("tools.whatif_demo.whatif_force_series")
    @patch("tools.whatif_demo.whatif_blackout")
    @patch("tools.whatif_demo.sample_pareto_frontier")
    @patch("tools.whatif_demo.load_teams")
    @patch("tools.whatif_demo.generate")
    @patch("tools.whatif_demo.extract_matchup_quotas")
    @patch("tools.whatif_demo.LocalFileAdapter")
    def test_all_scenarios_no_exception(
        self, mock_adapter, mock_quotas, mock_generate,
        mock_load_teams, mock_pareto, mock_blackout, mock_force, capsys
    ):
        """Alle Szenarien (--scenario all) laufen ohne Exception."""
        mock_generate.return_value = self._make_mock_result()
        mock_load_teams.return_value = []
        mock_adapter.return_value.fetch_season_schedule.return_value = MagicMock()
        mock_quotas.return_value = MagicMock()
        mock_force.return_value = _mk_whatif_result()
        mock_blackout.return_value = _mk_whatif_result()

        # Frontier-Mock: mindestens 2 Punkte (balanced + travel_min)
        frontier = MagicMock()
        p1 = MagicMock()
        p1.label = "balanced"
        p1.bundle = _mk_bundle()
        p1.season = _mk_season()
        p2 = MagicMock()
        p2.label = "travel_min"
        p2.bundle = _mk_bundle(travel_km=1_800_000.0)
        p2.season = _mk_season()
        frontier.points = [p1, p2]
        frontier.all_evaluated = [p1, p2]
        frontier.n_non_dominated = 2
        frontier.anchor_labels = {"balanced", "travel_min"}
        frontier.best_by = MagicMock(return_value=p1)
        mock_pareto.return_value = frontier

        with patch("tools.whatif_demo.whatif_compare") as mock_cmp:
            mock_cmp.return_value = _mk_whatif_result()
            from tools.whatif_demo import run_demo
            args = self._make_args(scenario="all", no_json=True)
            run_demo(args)

        mock_force.assert_called_once()
        mock_blackout.assert_called_once()
        mock_cmp.assert_called_once()

    @patch("tools.whatif_demo.whatif_force_series")
    @patch("tools.whatif_demo.load_teams")
    @patch("tools.whatif_demo.generate")
    @patch("tools.whatif_demo.extract_matchup_quotas")
    @patch("tools.whatif_demo.LocalFileAdapter")
    def test_json_export_written(
        self, mock_adapter, mock_quotas, mock_generate,
        mock_load_teams, mock_force, tmp_path, capsys
    ):
        """Mit --json-out wird eine Datei geschrieben."""
        mock_generate.return_value = self._make_mock_result()
        mock_load_teams.return_value = []
        mock_adapter.return_value.fetch_season_schedule.return_value = MagicMock()
        mock_quotas.return_value = MagicMock()
        mock_force.return_value = _mk_whatif_result()

        out_path = str(tmp_path / "test_output.json")

        from tools.whatif_demo import run_demo
        args = argparse.Namespace(
            seed=42,
            sa_iter=3000,
            scenario="force",
            json_out=out_path,
            no_json=False,
            verbose=False,
        )
        run_demo(args)

        assert Path(out_path).exists()
        data = json.loads(Path(out_path).read_text())
        assert "meta" in data
        assert "scenarios" in data
        assert len(data["scenarios"]) == 1

    @patch("tools.whatif_demo.whatif_force_series")
    @patch("tools.whatif_demo.load_teams")
    @patch("tools.whatif_demo.generate")
    @patch("tools.whatif_demo.extract_matchup_quotas")
    @patch("tools.whatif_demo.LocalFileAdapter")
    def test_blackout_only_skipped_with_force_scenario(
        self, mock_adapter, mock_quotas, mock_generate,
        mock_load_teams, mock_force, capsys
    ):
        """Mit --scenario force wird whatif_blackout NICHT aufgerufen."""
        mock_generate.return_value = self._make_mock_result()
        mock_load_teams.return_value = []
        mock_adapter.return_value.fetch_season_schedule.return_value = MagicMock()
        mock_quotas.return_value = MagicMock()
        mock_force.return_value = _mk_whatif_result()

        with patch("tools.whatif_demo.whatif_blackout") as mock_blackout:
            from tools.whatif_demo import run_demo
            args = self._make_args(scenario="force", no_json=True)
            run_demo(args)
            mock_blackout.assert_not_called()
