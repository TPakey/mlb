"""Sprint 5.2 — Strukturelle Article-V-Regeln (V(C)(13), V(C)(14)/(15)) +
Post-Output-Hard-Rule-Validierung.

Ehrlichkeit: V(C)(13)/(14) sind Originalplan-Regeln. Auf den as-played-Realdaten
liefern sie informativ Makeup-Artefakte (kein echter Verstoß) — daher SOFT im Report.
Synthetische Mini-Seasons prüfen die Checker-Logik isoliert; ein langsamer
Property-Test belegt, dass der SA-Optimierer keine NEUEN harten Verstöße einführt.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conftest import make_game, make_mini_season

from src.data_loader import load_teams, teams_by_id as _tbi
from src.datasources.local_file import LocalFileAdapter
from src.compliance import compliance_report, RULES
from src.schedule_rules import (
    check_offday_distribution, check_doubleheader_limits,
    original_schedule_violations,
)
from src.start_times import load_real_start_times

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


@pytest.fixture(scope="module")
def tbi():
    return _tbi(load_teams())


def _season(year):
    return LocalFileAdapter(base_dir=DATA).fetch_season_schedule(year)


# ---------- V(C)(13) Off-Day-Verteilung (synthetisch) ----------

def test_offday_window_flagged():
    # Team BOS: Spiele Tag 0,1, dann 3 Open Days (2,3,4), dann 5,6 → 3 Opens/7-Fenster
    games = [make_game(i, d, "BOS", "NYY") for i, d in enumerate([0, 1, 5, 6])]
    s = make_mini_season(games)
    v = check_offday_distribution(s, ["BOS"], min_last_67=0, min_last_32=0)
    assert any(x.rule == "V(C)(13)" and "7-Tage-Fenster" in x.detail for x in v)


def test_offday_window_clean():
    # tägliche Spiele → kein ≤2/7-Verstoß (min-Checks deaktiviert)
    games = [make_game(i, i, "BOS", "NYY") for i in range(14)]
    s = make_mini_season(games)
    v = check_offday_distribution(s, ["BOS"], min_last_67=0, min_last_32=0)
    assert v == []


# ---------- V(C)(14)/(15) Doubleheader (synthetisch) ----------

def test_dh_consecutive_flagged():
    games = [
        make_game(1, 0, "BOS", "NYY", dh_seq=1),
        make_game(2, 0, "BOS", "NYY", dh_seq=2),
        make_game(3, 1, "BOS", "NYY", dh_seq=1),
        make_game(4, 1, "BOS", "NYY", dh_seq=2),
    ]
    s = make_mini_season(games)
    v = check_doubleheader_limits(s, ["BOS", "NYY"])
    assert any(x.rule == "V(C)(14)" for x in v)


def test_dh_single_clean():
    games = [
        make_game(1, 0, "BOS", "NYY", dh_seq=1),
        make_game(2, 0, "BOS", "NYY", dh_seq=2),
        make_game(3, 2, "BOS", "NYY"),
    ]
    s = make_mini_season(games)
    v = check_doubleheader_limits(s, ["BOS", "NYY"])
    assert [x for x in v if x.rule == "V(C)(14)"] == []


def test_twi_night_on_getaway_flagged():
    # BOS: Twi-Night-DH Tag 0 zuhause (erstes Spiel 16:30), reist Tag 1 nach NYY → Getaway
    games = [
        make_game(101, 0, "BOS", "TBR", dh_seq=1),
        make_game(102, 0, "BOS", "TBR", dh_seq=2),
        make_game(103, 1, "NYY", "BOS"),  # BOS reist nach NYY
    ]
    s = make_mini_season(games)
    start_min = {101: 16 * 60 + 30, 102: 19 * 60 + 30, 103: 19 * 60}
    v = check_doubleheader_limits(s, ["BOS", "NYY", "TBR"], start_min=start_min)
    assert any(x.rule == "V(C)(15)" and "Getaway" in x.detail for x in v)


# ---------- Reale Messung (as-played) ----------

@pytest.mark.parametrize("year", [2024, 2025])
def test_real_twinight_zero(year, tbi):
    s = _season(year)
    real = load_real_start_times(DATA / f"mlb_schedule_{year}.json", tbi)
    v = check_doubleheader_limits(s, start_min=real)
    assert [x for x in v if x.rule == "V(C)(15)"] == [], \
        f"{year}: unerwartete Twi-Night-Verstöße"


def test_real_dh_violations_are_makeup_artifacts():
    # Review-Runde 2 (Punkt 1): V(C)(14) hat jetzt ZWEI Teilchecks —
    # Folgetag-DH (Satz 1) und Home-Split-DH-Limit (Satz 2, via dh_type).
    # As-played-Erwartung (gemessen 2026-06-10): 2024 keine Folgetag-DH,
    # 4 Clubs über dem Split-Limit (Rainout-Makeups); 2025 4 Folgetag-DH +
    # 7 Clubs über dem Split-Limit — alles Makeup-Artefakte, informativ.
    s24 = _season(2024)
    v24 = check_doubleheader_limits(s24)
    assert [x for x in v24 if "Folgetagen" in x.detail] == []
    assert len([x for x in v24 if "Split" in x.detail]) == 4
    s25 = _season(2025)
    v25 = check_doubleheader_limits(s25)
    assert all(x.rule == "V(C)(14)" for x in v25)  # nur Satz-1/2-Artefakte
    assert len([x for x in v25 if "Folgetagen" in x.detail]) == 4
    assert len([x for x in v25 if "Split" in x.detail]) == 7


def test_split_dh_limit_flagged_and_clean():
    # Synthetisch: 2 Home-Split-DHs → Verstoß; 1 → sauber (V(C)(14) Satz 2).
    from datetime import date as _date, timedelta as _td
    from src.season import Game, Season
    base = _date(2026, 5, 1)
    def dh(pk, d, home, away, typ):
        return [Game(pk, d, home, away, home, doubleheader_seq=1, dh_type=typ),
                Game(pk + 1, d, home, away, home, doubleheader_seq=2, dh_type=typ)]
    games = (dh(1, base, "BOS", "NYY", "S") + dh(10, base + _td(days=14), "BOS", "TBR", "S")
             + dh(20, base + _td(days=7), "NYY", "TOR", "S"))
    s = Season(season=2026, games=games, season_start=base, season_end=base + _td(days=30))
    v = check_doubleheader_limits(s)
    split = [x for x in v if "Split" in x.detail]
    assert [x.team for x in split] == ["BOS"]   # 2x BOS → Verstoß; 1x NYY → ok


# ---------- Compliance-Wiring (SOFT, rückwärtskompatibel) ----------

def test_structural_rules_are_soft():
    assert RULES["CBA-OFFDAY"].severity == "soft"
    assert RULES["CBA-DH"].severity == "soft"


def test_compliance_includes_structural_rules_real2024(tbi):
    s = _season(2024)
    rep = compliance_report(s, teams_by_id=tbi)
    assert rep.get("CBA-OFFDAY") is not None
    assert rep.get("CBA-DH") is not None
    # SOFT → beeinflussen is_compliant nicht; 2024 bleibt hart-konform
    assert rep.is_compliant


def test_original_guard_combines_rules():
    games = [
        make_game(1, 0, "BOS", "NYY", dh_seq=1),
        make_game(2, 0, "BOS", "NYY", dh_seq=2),
        make_game(3, 1, "BOS", "NYY", dh_seq=1),
        make_game(4, 1, "BOS", "NYY", dh_seq=2),
    ]
    s = make_mini_season(games)
    v = original_schedule_violations(s, ["BOS", "NYY"])
    assert any(x.rule == "V(C)(14)" for x in v)


# ---------- Post-Output: SA führt keine NEUEN harten Verstöße ein ----------

@pytest.mark.slow
def test_ptet_penalty_deterministic():
    """Der gegatete CBA-PTET-SA-Penalty bleibt deterministisch (zwei Läufe
    bit-identisch)."""
    from src.generator_optimizer import (
        GeneratorConfig, OptimizerConfig, optimize_travel)
    from src.season import detect_all_star_break
    teams = load_teams()
    real = _season(2024)
    cfg = GeneratorConfig(
        season=2024, season_start=real.season_start, season_end=real.season_end,
        all_star_break=detect_all_star_break(real),
        num_search_workers=1, random_seed=42, enforce_fatigue_constraints=True)

    def run():
        oc = OptimizerConfig(iterations=2000, move_mix_geo=0.35, seed=42,
                             fatigue_lambda=1_000_000.0, feas_lambda=50_000.0,
                             feas_w_ptet=100.0)
        return optimize_travel(real, teams, cfg, oc)[1].final_km
    assert run() == run()


@pytest.mark.slow
def test_optimizer_introduces_no_new_hard_violation():
    """Review-Fix P0-1 (2026-06-10): Dieser Test prüfte früher nur eine
    NICHT-Default-Konfiguration (feas_w_ptet manuell gesetzt) und gab damit
    falsche Sicherheit über den Produktionspfad. Jetzt testet er EXAKT den
    Produktions-Default (production_optimizer_config — dieselbe Config, die
    tools/backtest --warm-start und src/main verwenden) und prüft über das
    Publish-Gate zusätzlich die Strukturregeln V(C)(13)/(14)/(15), nicht nur
    die harten Compliance-Regeln."""
    from src.generator_optimizer import (
        GeneratorConfig, optimize_travel, production_optimizer_config)
    from src.publish_gate import publishable_report
    from src.season import detect_all_star_break
    teams = load_teams()
    tbi = _tbi(teams)
    real = _season(2024)
    cfg = GeneratorConfig(
        season=2024, season_start=real.season_start, season_end=real.season_end,
        all_star_break=detect_all_star_break(real),
        num_search_workers=1, random_seed=42, enforce_fatigue_constraints=True)
    # PRODUKTIONS-Default — keine manuell aktivierten Terme.
    oc = production_optimizer_config(iterations=200_000, move_mix_geo=0.35, seed=42)
    optimized, _log = optimize_travel(real, teams, cfg, oc)

    base_fail = {c.rule_id for c in
                 compliance_report(real, teams_by_id=tbi).hard_failures}
    opt_fail = {c.rule_id for c in
                compliance_report(optimized, teams_by_id=tbi).hard_failures}
    # Der Optimierer darf KEINEN neuen harten Verstoß erzeugen
    assert opt_fail <= base_fail, f"neue harte Verstöße: {opt_fail - base_fail}"

    # Publish-Gate (P0-1/P0-2): kein neuer harter UND kein neuer struktureller
    # Verstoß (V(C)(13)/(14)/(15)) gegenüber der Baseline.
    gate = publishable_report(optimized, tbi, baseline=real)
    assert gate.is_publishable, gate.summary()


def test_production_default_is_gated_config():
    """Schutz gegen Regression der P0-1-Ursache: der Produktions-Default
    (production_optimizer_config) MUSS alle Regel-Schutzterme aktiv haben."""
    from src.generator_optimizer import production_optimizer_config
    oc = production_optimizer_config(iterations=1)
    assert oc.feas_lambda > 0.0
    assert oc.feas_w_ptet > 0.0
    assert oc.sched13_lambda > 0.0
    assert oc.fatigue_lambda >= 1_000_000.0


def test_ptet_strict_check_subsumes_vc11_sentence2():
    """Review-Runde 2 (Punkt 5): V(C)(11) Satz 2 ('no Club may be scheduled to
    play more than one game in the ET the day after it has played a game in
    the PT') ist vom strikten CBA-PTET-Check SUBSUMIERT: jeder Satz-2-Fall
    setzt eine PT→ET-Spieltagsfolge ohne Off-Day voraus, und genau die flaggt
    _check_pt_et_offday — auch wenn es nur EIN ET-Spiel ist (strikter Default,
    da die ≤7-Liga-Ausnahme nicht modelliert ist). Gemessen real 2024/2025:
    0 Transitionen, 0 Satz-2-Fälle."""
    from datetime import date as _date, timedelta as _td
    from src.season import Game, Season
    from src.compliance import _check_pt_et_offday
    from src.data_loader import load_teams, teams_by_id as _t
    tb = _t(load_teams())
    base = _date(2026, 6, 1)
    # NYY spielt in LA (PT), am Folgetag DOUBLEHEADER in New York (ET):
    games = [
        Game(1, base, "LAD", "NYY", "LAD"),
        Game(2, base + _td(days=1), "NYY", "BOS", "NYY", doubleheader_seq=1),
        Game(3, base + _td(days=1), "NYY", "BOS", "NYY", doubleheader_seq=2),
    ]
    s = Season(season=2026, games=games, season_start=base,
               season_end=base + _td(days=30))
    chk = _check_pt_et_offday(s, ["NYY", "LAD", "BOS"], tb)
    assert not chk.passed                      # Satz-2-Szenario wird geflaggt
    assert any("NYY" in o for o in chk.offenders)
