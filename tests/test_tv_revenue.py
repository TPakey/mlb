"""Tests für TV-Slot- und Revenue-Realismus (Sprint 2.9 / Review C2, M9, N3, N4).

Deckt ab:
- C2: Sunday-Night-Premium wird kreditiert; Saturday day/night unterschieden.
- M9: Division-Rival-Bonus stapelt multiplikativ mit Marquee-/Opponent-Faktor.
- N3: Doubleheader-Typ kann single_admission sein.
- N4: Revenue-Daypart nutzt Erwartungswert-Modell (konsistent mit C2).
"""
from __future__ import annotations

from datetime import date

from src.season import Game
from src.tv_slots import TvSlotConfig
from src.revenue import (
    RevenueModel,
    expected_revenue,
    build_division_rivals,
    _doubleheader_type,
    _expected_daypart_factor,
)
from src.data_loader import load_teams


# ── C2: TV-Slot Erwartungswert ───────────────────────────────────────────────

class TestTvExpectedSlot:
    def test_sunday_night_premium_credited(self):
        cfg = TvSlotConfig.load()
        ev = cfg.expected_slot_value(6)
        assert cfg.slot_value(6, "day") < ev < cfg.slot_value(6, "night")

    def test_saturday_blended(self):
        cfg = TvSlotConfig.load()
        ev = cfg.expected_slot_value(5)
        assert cfg.slot_value(5, "day") < ev < cfg.slot_value(5, "night")

    def test_expected_value_is_probability_weighted(self):
        cfg = TvSlotConfig.load()
        mix = cfg.daypart_mix[6]
        manual = (mix["day"] * cfg.slot_value(6, "day")
                  + mix["night"] * cfg.slot_value(6, "night")) / sum(mix.values())
        assert abs(cfg.expected_slot_value(6) - manual) < 1e-9

    def test_missing_weekday_mix_falls_back_to_night(self):
        cfg = TvSlotConfig(
            slot_values={3: {"day": 0.8, "night": 1.2}},
            marquee_multipliers={},
            pick_prob={},
            daypart_mix={},  # leer → Default-Mix greift in load(), hier explizit leer
        )
        # weekday 3 ist nicht im (leeren) Mix → Fallback Night-Wert
        assert cfg.expected_slot_value(3) == cfg.slot_value(3, "night")


# ── M9: Division-Rival-Bonus stapelt ─────────────────────────────────────────

class TestRivalStacking:
    def test_bos_at_nyy_stacks_marquee_and_rival(self):
        teams = load_teams()
        rivals = build_division_rivals(teams)
        model = RevenueModel.load()
        assert "BOS" in rivals.get("NYY", set()), "BOS/NYY sollten AL-East-Rivalen sein"

        g = Game(game_pk=1, date=date(2026, 6, 6), home="NYY", away="BOS", venue="NYY")
        rev_with = expected_revenue(g, model, rivals)
        rev_without = expected_revenue(g, model, division_rivals=None)
        bonus = model.opponent_draw_factor["division_rival_bonus"]
        # Mit Rival-Stacking ist der Revenue exakt um den Bonus höher.
        assert abs(rev_with - rev_without * bonus) < 1.0
        assert bonus > 1.0 and rev_with > rev_without

    def test_non_rival_known_opponent_not_boosted(self):
        teams = load_teams()
        rivals = build_division_rivals(teams)
        model = RevenueModel.load()
        # LAD@NYY: LAD ist bekannter Marquee-Gegner, aber kein AL-East-Rival von NYY.
        g = Game(game_pk=2, date=date(2026, 6, 6), home="NYY", away="LAD", venue="NYY")
        rev_with = expected_revenue(g, model, rivals)
        rev_without = expected_revenue(g, model, division_rivals=None)
        assert abs(rev_with - rev_without) < 1.0  # kein Rival-Bonus


# ── N3 / N4 ──────────────────────────────────────────────────────────────────

class TestDoubleheaderAndDaypart:
    def test_single_admission_marked(self):
        g = Game(game_pk=42, date=date(2026, 6, 6), home="NYY", away="BOS",
                 venue="NYY", doubleheader_seq=1)
        assert _doubleheader_type(g) == "split_admission"
        assert _doubleheader_type(g, single_admission_pks={42}) == "single_admission"

    def test_no_doubleheader(self):
        g = Game(game_pk=1, date=date(2026, 6, 6), home="NYY", away="BOS", venue="NYY")
        assert _doubleheader_type(g) == "none"

    def test_expected_daypart_factor_blends(self):
        model = RevenueModel.load()
        # Samstag (5): Erwartungswert liegt zwischen day- und night-Faktor.
        f = _expected_daypart_factor(5, is_sunday=False, model=model)
        lo = min(model.daypart_factor["day"], model.daypart_factor["night"])
        hi = max(model.daypart_factor["day"], model.daypart_factor["night"])
        assert lo <= f <= hi
