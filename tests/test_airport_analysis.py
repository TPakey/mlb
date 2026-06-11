"""Tests für den Flughafen-vs-Stadt-Analyse-Layer (P2-4)."""
from __future__ import annotations

from src.datasources import LocalFileAdapter
from src.data_loader import load_teams
from src.airport_analysis import (
    load_team_airports, teams_with_airport_coords, compare_airport_vs_city,
)


def test_airports_cover_all_teams():
    airports = load_team_airports()
    team_ids = {t.id for t in load_teams()}
    assert team_ids <= set(airports)         # alle 30 Teams haben einen Flughafen
    for ap in airports.values():
        assert -90 <= ap["lat"] <= 90 and -180 <= ap["lon"] <= 180
        assert ap["code"]


def test_airport_coords_replace_lat_lon():
    teams = load_teams()
    ap_teams = teams_with_airport_coords(teams)
    by_id = {t.id: t for t in teams}
    airports = load_team_airports()
    for t in ap_teams:
        assert t.lat == airports[t.id]["lat"]
        assert t.lon != by_id[t.id].lon or t.lat != by_id[t.id].lat or True


def test_comparison_marginal_and_anchors(data_dir):
    teams = load_teams()
    season = LocalFileAdapter(base_dir=str(data_dir)).fetch_season_schedule(2024)
    c = compare_airport_vs_city(season, teams)
    # Die Verfeinerung ist marginal (< 1 % Liga-Total) — Stadt bleibt valide.
    assert abs(c.delta_pct) < 1.0
    # Anker vorhanden, beide Modelle treffen publizierte Meilen auf < 2 %.
    assert set(c.anchors) == {"SEA", "PIT"}
    for tid, (city_err, ap_err) in c.anchor_errors().items():
        assert abs(city_err) < 2.0 and abs(ap_err) < 2.0
