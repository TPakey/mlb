"""Tests für die Scheduler-Operations-Suite (Routing, Security, Hotels, Dossier)."""
from __future__ import annotations

from datetime import date

import pytest

from src.datasources import LocalFileAdapter
from src.ops_routing import estimate_route, city_routing, Coord
from src.ops_security import (
    _parse_months, build_security_briefing, load_ops_profiles, briefing_to_markdown,
)
from src.ops_hotels import (
    HotelCandidate, score_hotel, recommend_hotels, load_team_hotels,
)
from src.ops_dossier import team_trip_dossiers, dossier_to_markdown


# ---------------- Routing ----------------

class TestRouting:
    def test_estimate_route_basics(self):
        leg = estimate_route("A", "B", 40.0, -74.0, 40.5, -74.0,
                             detour=1.35, congestion=1.0)
        assert leg.road_km > leg.crow_km                 # Umweg > Luftlinie
        assert leg.drive_min > 0
        assert 0.15 <= leg.reliability <= 0.99

    def test_congestion_lowers_reliability_and_raises_time(self):
        free = estimate_route("A", "B", 40.0, -74.0, 40.3, -74.0, congestion=1.0)
        jam = estimate_route("A", "B", 40.0, -74.0, 40.3, -74.0, congestion=2.2)
        assert jam.drive_min > free.drive_min
        assert jam.reliability < free.reliability

    def test_city_routing_has_airport_to_ballpark(self):
        r = city_routing("NYY", hotel=Coord("H", 40.75, -73.99))
        assert r.airport_to_ballpark.road_km > 0
        assert r.airport_to_hotel is not None
        assert r.hotel_to_ballpark is not None


# ---------------- Security ----------------

class TestSecurity:
    def test_parse_months(self):
        assert _parse_months("Jun–Nov") == {6, 7, 8, 9, 10, 11}
        assert _parse_months("ganzjährig") == set(range(1, 13))
        assert _parse_months("Apr–Mai, Sep") == {4, 5, 9}

    def test_profiles_cover_all_teams(self):
        from src.data_loader import load_teams
        profiles = load_ops_profiles()
        assert {t.id for t in load_teams()} <= set(profiles)

    def test_miami_july_high_risk_hurricane(self):
        b = build_security_briefing("MIA", month=7)
        assert b.overall_severity >= 4                   # Hurrikan-Saison aktiv
        assert any("Hurrikan" in h["hazard"] for h in b.active_hazards)
        assert b.trauma_center                           # benannt

    def test_seasonal_awareness(self):
        # Miami im März (außerhalb Hurrikan-Saison) < Miami im Juli.
        march = build_security_briefing("MIA", month=3).overall_severity
        july = build_security_briefing("MIA", month=7).overall_severity
        assert march < july

    def test_briefing_markdown_has_all_sections(self):
        md = briefing_to_markdown(build_security_briefing("DET", month=5))
        for s in ("Wetter & Naturgefahren", "Medizinische Bereitschaft",
                  "Boden-Transport-Risiko", "Venue- & Crowd-Security",
                  "Notfall-Framework"):
            assert s in md


# ---------------- Hotels ----------------

class TestHotels:
    def test_score_prefers_quality_security_history_over_pure_proximity(self):
        # Nahes, schwaches Haus vs. etwas weiter, top + bewährt.
        bp_lat, bp_lon = 42.346, -71.097          # Fenway
        near_weak = HotelCandidate("Near/Weak", 42.346, -71.098, tier=2,
                                   security_tier=2, past_stays=0)
        far_strong = HotelCandidate("Far/Strong", 42.36, -71.08, tier=5,
                                    security_tier=5, past_stays=12, past_rating=4.7)
        s_near = score_hotel(near_weak, bp_lat, bp_lon)
        s_far = score_hotel(far_strong, bp_lat, bp_lon)
        assert s_far.score > s_near.score
        assert s_far.is_vetted and not s_near.is_vetted

    def test_recommend_ranks_seed_city(self):
        scores = recommend_hotels("BOS")
        assert scores and scores[0].score >= scores[-1].score
        assert scores[0].hotel.past_stays >= 3           # bewährtes Haus oben

    def test_new_property_flagged_for_audit(self):
        h = HotelCandidate("New", 42.35, -71.10, tier=4, security_tier=4, past_stays=0)
        s = score_hotel(h, 42.346, -71.097)
        assert "Audit" in s.history_note


# ---------------- Dossier ----------------

class TestDossier:
    @pytest.fixture(scope="class")
    def season(self, data_dir):
        return LocalFileAdapter(base_dir=str(data_dir)).fetch_season_schedule(2024)

    def test_team_trip_dossiers_only_away(self, season):
        d = team_trip_dossiers(season, "NYY", limit=6)
        assert d
        for x in d:
            assert x.visiting_team == "NYY"
            assert x.host_team != "NYY"                   # nur Auswärts

    def test_rivalry_flag_for_nyy_at_bos(self, season):
        d = team_trip_dossiers(season, "NYY")
        bos = [x for x in d if x.host_team == "BOS"]
        assert bos and any(b.high_profile for b in bos)   # Marquee geflaggt

    def test_dossier_markdown_complete(self, season):
        d = team_trip_dossiers(season, "NYY")
        bos = [x for x in d if x.host_team == "BOS"][0]
        md = dossier_to_markdown(bos)
        assert "Boden-Routing" in md and "Hotel-Empfehlung" in md
        assert "Security- & Risiko-Briefing" in md
