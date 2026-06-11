"""Acceptance-Tests fuer Sprint 2.1 - Schedule-from-Scratch Generator.

Jeder Test entspricht einem AC aus dem SPRINT_2_CHARTER.md.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

from src.datasources import LocalFileAdapter
from src.generator import GeneratorConfig, generate
from src.matchup_extractor import extract_matchup_quotas, MatchupQuotas, SeriesTemplate


# ---------------------- Fixtures ----------------------

@pytest.fixture(scope="module")
def quotas_2024(data_dir):
    adapter = LocalFileAdapter(base_dir=data_dir)
    season = adapter.fetch_season_schedule(2024)
    return extract_matchup_quotas(season)


@pytest.fixture(scope="module")
def default_cfg():
    # num_search_workers=1: CP-SAT mit >1 Worker ist nicht-deterministisch
    # (Thread-Race). Reproduzierbare Tests verlangen Single-Thread.
    return GeneratorConfig(
        season=2026,
        season_start=date(2026, 3, 26),
        season_end=date(2026, 9, 27),
        all_star_break=(date(2026, 7, 13), date(2026, 7, 16)),
        max_solver_time_seconds=60,
        num_search_workers=1,
    )


@pytest.fixture(scope="module")
def generated_result(quotas_2024, default_cfg):
    """Einmaliger Generator-Lauf, in allen Tests des Moduls geteilt."""
    return generate(quotas_2024, default_cfg)


# ---------------------- AC 2.1.1: Performance ----------------------

def test_AC_2_1_1_solver_under_30_minutes(generated_result):
    """AC-2.1.1: Generierung in <=30 Minuten (1800s)."""
    assert generated_result.solve_time_seconds <= 1800
    # Praxis-Wert: viel kleiner
    assert generated_result.solve_time_seconds <= 60


# ---------------------- AC 2.1.2-3: Spiele-/Heim-/Auswaertsbalance ----------------------

def test_AC_2_1_2_games_per_team(generated_result, quotas_2024):
    """AC-2.1.2: Spiele pro Team entsprechen der Quoten-Vorgabe.

    Da unsere Eingabe-Quoten aus der echten MLB-2024 stammen, akzeptieren wir
    deren reale Asymmetrie (161..163). Bei rein konstruierten Quoten (162/Team
    by construction) muss diese Range exakt 162 sein.
    """
    assert generated_result.season is not None
    games_per_team = {}
    for g in generated_result.season.games:
        games_per_team[g.home] = games_per_team.get(g.home, 0) + 1
        games_per_team[g.away] = games_per_team.get(g.away, 0) + 1
    # Erwartung pro Team = quotas.games_per_team[team]
    expected = quotas_2024.games_per_team()
    for tid, n in expected.items():
        assert games_per_team[tid] == n, \
            f"Team {tid}: erzeugt {games_per_team[tid]} Spiele, erwartet {n}"


def test_AC_2_1_3_home_away_balance(generated_result, quotas_2024):
    """AC-2.1.3: Heim/Auswaertsverteilung entspricht Quoten-Vorgabe."""
    home_counts = {}
    away_counts = {}
    for g in generated_result.season.games:
        home_counts[g.home] = home_counts.get(g.home, 0) + 1
        away_counts[g.away] = away_counts.get(g.away, 0) + 1
    for tid in home_counts:
        expected_home = quotas_2024.home_count(tid)
        expected_away = quotas_2024.away_count(tid)
        assert home_counts[tid] == expected_home, \
            f"Team {tid}: erzeugt {home_counts[tid]} Heimspiele, erwartet {expected_home}"
        assert away_counts.get(tid, 0) == expected_away


# ---------------------- AC 2.1.4: Matchup-Quoten ----------------------

def test_AC_2_1_4_matchup_quotas_preserved(generated_result, quotas_2024):
    """AC-2.1.4: Matchup-Quoten je Paarung sind exakt erhalten."""
    erzeugt = {}
    for g in generated_result.season.games:
        key = (g.home, g.away)
        erzeugt[key] = erzeugt.get(key, 0) + 1
    soll = quotas_2024.matchup_counts()
    for key, n in soll.items():
        assert erzeugt.get(key, 0) == n, \
            f"Matchup {key}: erzeugt {erzeugt.get(key, 0)}, erwartet {n}"


# ---------------------- AC 2.1.5: All-Star-Break ----------------------

def test_AC_2_1_5_all_star_break_respected(generated_result, default_cfg):
    """AC-2.1.5: keine Spiele im All-Star-Break-Fenster."""
    break_start, break_end = default_cfg.all_star_break
    for g in generated_result.season.games:
        assert not (break_start <= g.date <= break_end), \
            f"Spiel {g.game_pk} am {g.date} liegt im All-Star-Break"


# ---------------------- AC 2.1.6: Saisonfenster ----------------------

def test_AC_2_1_6_within_season_window(generated_result, default_cfg):
    """AC-2.1.6: alle Spiele liegen im Saisonfenster."""
    for g in generated_result.season.games:
        assert default_cfg.season_start <= g.date <= default_cfg.season_end


# ---------------------- AC 2.1.7: Keine Doppelbuchungen ----------------------

def test_AC_2_1_7_no_double_bookings(generated_result):
    """AC-2.1.7: kein Team hat zwei Spiele am gleichen Tag (ohne Doubleheader)."""
    per_team_per_date = {}
    for g in generated_result.season.games:
        for tid in (g.home, g.away):
            key = (tid, g.date)
            per_team_per_date[key] = per_team_per_date.get(key, 0) + 1
    duplicates = [(k, v) for k, v in per_team_per_date.items() if v > 1]
    assert not duplicates, f"Doppelbuchungen gefunden: {duplicates[:5]}"


# ---------------------- AC 2.1.10: Plausibilitaet Total-km ----------------------

@pytest.mark.integration
def test_AC_2_1_10_total_km_in_range(generated_result, teams):
    """AC-2.1.10: Total-km in plausibler MLB-Range.

    Baseline neu festgeschrieben (Sprint 2.7/2.11, Risiko A): Seit der
    Korrektur der AC-2.1.8-Definition (Review C1) bricht der Fatigue-Repair
    zu lange Road-Trips gezielt auf und tauscht dafür Reise-km ein — die
    frühere ~1,96M-Benchmark verschiebt sich nach oben (~2,1M). Die Obergrenze
    wurde entsprechend auf 2,3M angehoben. Travel-km ist haversine-basiert,
    daher von der DST-Korrektur (M2) unberührt.
    """
    from src.travel import compute_season_travel
    report = compute_season_travel(generated_result.season, teams)
    assert 1_500_000 <= report.total_km <= 2_300_000, \
        f"Total km {report.total_km:,.0f} ausserhalb 1.5-2.3M"


# ---------------------- AC 2.1.11: Reproduzierbarkeit ----------------------

def test_AC_2_1_11_reproducible_with_same_seed(quotas_2024):
    """AC-2.1.11: gleicher Seed -> identische Loesung.

    Reproduzierbarkeit ist orthogonal zur km-Qualitaet: wir testen Determinismus
    der gesamten Pipeline (CP-SAT + SA) mit reduzierter Iter-Zahl, um zwei volle
    Generator-Laeufe schnell durchzuwringen. Das aendert nichts am Verhalten
    (Bit-Identitaet bei gleichem Seed), nur an der Test-Laufzeit.
    """
    fast_cfg = GeneratorConfig(
        season=2026,
        season_start=date(2026, 3, 26),
        season_end=date(2026, 9, 27),
        all_star_break=(date(2026, 7, 13), date(2026, 7, 16)),
        max_solver_time_seconds=60,
        num_search_workers=1,                # erzwingt CP-SAT-Determinismus
        travel_optimizer_iterations=50_000,  # SA ist seed-deterministisch unabhaengig von Iter-Zahl
    )
    r1 = generate(quotas_2024, fast_cfg)
    r2 = generate(quotas_2024, fast_cfg)
    assert r1.season is not None and r2.season is not None
    games_1 = [(g.date, g.home, g.away) for g in r1.season.games]
    games_2 = [(g.date, g.home, g.away) for g in r2.season.games]
    assert games_1 == games_2, "Generator nicht deterministisch mit gleichem Seed"


# ---------------------- Smoke-Test: Mini-Szenario ----------------------

def test_smoke_minimal_quotas():
    """Mini-Smoke: 2 Teams, 1 Serie, 3 Spiele - muss feasible sein."""
    quotas = MatchupQuotas(
        season=2026,
        series_templates=[SeriesTemplate(home="NYY", away="BOS", length=3)],
    )
    cfg = GeneratorConfig(
        season=2026,
        season_start=date(2026, 4, 1),
        season_end=date(2026, 4, 5),
        max_solver_time_seconds=5,
    )
    result = generate(quotas, cfg)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.season is not None
    assert len(result.season.games) == 3
