"""Geteilte pytest-Fixtures und Test-Helfer.

Audit A22 (Sprint A-5): Helper-Funktionen wie `_mk_game`/`_g` /`_mini_season`
waren in mehreren Test-Dateien dupliziert. Hier liegen jetzt gemeinsame
Helfer als pytest-Fixtures, sodass neue Tests sie ohne Copy-Paste nutzen
koennen. Bestehende Tests behalten ihre lokalen Helfer als Backward-Compat.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

# src/ ins sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from src.data_loader import load_teams, teams_by_id
from src.season import Game, Season


# ── Daten-Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def teams():
    return load_teams()


@pytest.fixture(scope="session")
def teams_by_id_map(teams):
    return teams_by_id(teams)


@pytest.fixture(scope="session")
def data_dir():
    return ROOT / "data"


@pytest.fixture(scope="session")
def output_dir():
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    return out


# ── Gemeinsame Test-Helfer (A22) ─────────────────────────────────────────────

DEFAULT_BASE_DATE = date(2026, 4, 1)


def make_game(
    pk: int,
    day_offset: int,
    home: str,
    away: str,
    *,
    base: date = DEFAULT_BASE_DATE,
    venue: Optional[str] = None,
    dh_seq: int = 0,
    game_type: str = "R",
) -> Game:
    """Kanonischer Game-Builder fuer Tests (A22, Sprint A-5).

    Vermeidet die in mehreren Test-Dateien duplizierten `_mk_game`/`_g`-
    Helper. Wer noch lokale Varianten nutzt, kann nach und nach hierauf
    umsteigen.
    """
    return Game(
        game_pk=pk,
        date=base + timedelta(days=day_offset),
        home=home,
        away=away,
        venue=venue or home,
        doubleheader_seq=dh_seq,
        game_type=game_type,
    )


def make_mini_season(
    games: List[Game],
    *,
    season: int = 2026,
    season_start: date = DEFAULT_BASE_DATE,
    season_length_days: int = 180,
) -> Season:
    """Kanonischer Season-Builder fuer Tests (A22, Sprint A-5)."""
    return Season(
        season=season,
        games=list(games),
        season_start=season_start,
        season_end=season_start + timedelta(days=season_length_days),
    )


@pytest.fixture
def make_game_fixture():
    """pytest-Fixture-Variante von `make_game` (per dependency injection)."""
    return make_game


@pytest.fixture
def make_mini_season_fixture():
    """pytest-Fixture-Variante von `make_mini_season`."""
    return make_mini_season
