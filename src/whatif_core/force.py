"""whatif_force_series (A21-Split). Re-exportiert ueber `src.whatif`."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from ..data_loader import Team
from ..generator import GeneratorConfig
from ..pareto_types import compute_pareto_bundle
from ..season import Game, Season
from .types import WhatIfResult
from .helpers import (
    _flag_publish_gate,
    _build_deltas,
    _find_free_slot,
    _find_series_for_matchup,
    _flag_constraint_violations,
    _move_games_to_date,
    _replace_games,
)


def whatif_force_series(
    season: Season,
    teams: List[Team],
    cfg: GeneratorConfig,
    home: str,
    away: str,
    forced_start: date,
    series_length: Optional[int] = None,
    scenario_name: str = "",
    events=None,
    tv_cfg=None,
    revenue_model=None,
) -> WhatIfResult:
    """Was passiert, wenn eine bestimmte Serie zu einem festen Datum gespielt wird?

    Findet die Serie home@away im aktuellen Plan, verschiebt sie auf
    forced_start und repariert Kollisionen durch Verschiebung der verdrängten
    Serie auf den nächsten freien Slot.

    Args:
        season:          Aktueller Saisonplan.
        teams:           Alle 30 Teams (für ParetoBundle-Berechnung).
        cfg:             GeneratorConfig (für Saison-Grenzen).
        home:            Heimteam-ID der erzwungenen Serie (z.B. "NYY").
        away:            Auswärtsteam-ID (z.B. "BOS").
        forced_start:    Gewünschtes Startdatum der Serie.
        series_length:   Länge der Serie; wenn None, wird die Länge der
                         bestehenden Serie verwendet.
        scenario_name:   Optionaler Name für den Report.
        events, tv_cfg, revenue_model: Ressourcen für ParetoBundle-Berechnung;
                         wenn None, werden die Defaults aus den data/-Dateien geladen.

    Returns:
        WhatIfResult mit Original- und modifiziertem Bundle.
    """
    if not scenario_name:
        scenario_name = f"Force {home}@{away} am {forced_start}"

    warnings: List[str] = []
    feasible = True

    # ── Schritt 1: Betroffene Serie finden ──────────────────────────────────
    series_groups = _find_series_for_matchup(season, home, away)

    if not series_groups:
        warnings.append(
            f"Keine Serie {home}@{away} im aktuellen Plan gefunden. "
            f"Eine neue {series_length or 3}-Spiele-Serie wird eingefügt."
        )
        target_games: List[Game] = []
        length = series_length or 3
    else:
        # Nächstgelegene Serie zum forced_start wählen
        series_groups.sort(
            key=lambda g: abs((g[0].date - forced_start).days)
        )
        target_games = series_groups[0]
        length = series_length if series_length is not None else len(target_games)

    # ── Schritt 2: Kollisionen am forced_start identifizieren ───────────────
    forced_days = {forced_start + timedelta(days=i) for i in range(length)}
    colliding_games: List[Game] = [
        g for g in season.games
        if g.date in forced_days
        and g.game_pk not in {tg.game_pk for tg in target_games}
        and (g.home in (home, away) or g.away in (home, away))
    ]

    # Kollisionsfamilien bilden (zusammenhängende Serien)
    colliding_series: Dict[Tuple[str, str], List[Game]] = {}
    for cg in colliding_games:
        key = (cg.home, cg.away)
        colliding_series.setdefault(key, []).append(cg)

    # ── Schritt 3: Kollidierende Serien neu terminieren ─────────────────────
    modified = season
    # Zuerst target_games entfernen (sie werden auf forced_start gelegt)
    if target_games:
        modified = _replace_games(modified, target_games, [])

    for (cs_home, cs_away), cs_games in colliding_series.items():
        # Optimalen freien Slot für die verdrängte Serie finden
        cs_length = len(cs_games)
        new_slot = _find_free_slot(
            modified,
            teams=[cs_home, cs_away],
            series_length=cs_length,
            preferred_start=cs_games[0].date + timedelta(days=cs_length + 1),
            blackout=forced_days,
            season_start=cfg.season_start,
            season_end=cfg.season_end,
        )
        if new_slot is None:
            warnings.append(
                f"Konnte Serie {cs_home}@{cs_away} nicht neu terminieren — "
                f"kein freier Slot gefunden. Plan möglicherweise nicht feasibel."
            )
            feasible = False
            # Spiele trotzdem entfernen (besser als Überlappung)
            modified = _replace_games(modified, cs_games, [])
        else:
            moved = _move_games_to_date(cs_games, new_slot)
            modified = _replace_games(modified, cs_games, moved)

    # ── Schritt 4: Erzwungene Serie auf forced_start legen ───────────────────
    if target_games:
        forced_games = _move_games_to_date(target_games, forced_start)
        # Länge ggf. anpassen
        if series_length is not None and series_length != len(forced_games):
            # Kürzen oder verlängern
            if series_length < len(forced_games):
                forced_games = forced_games[:series_length]
            else:
                last = forced_games[-1]
                for extra in range(series_length - len(forced_games)):
                    new_date = last.date + timedelta(days=extra + 1)
                    forced_games.append(Game(
                        game_pk=last.game_pk + extra + 1,
                        date=new_date,
                        home=last.home, away=last.away,
                        venue=last.venue,
                        doubleheader_seq=0, game_type=last.game_type,
                    ))
        modified = _replace_games(modified, [], forced_games)
    else:
        # Neue Serie einfügen
        base_pk = max((g.game_pk for g in season.games), default=5_000_000) + 1
        new_games = [
            Game(
                game_pk=base_pk + i,
                date=forced_start + timedelta(days=i),
                home=home, away=away, venue=home,
                doubleheader_seq=0, game_type="R",
            )
            for i in range(length)
        ]
        modified = _replace_games(modified, [], new_games)

    # ── Schritt 5: Bundles berechnen ─────────────────────────────────────────
    orig_bundle = compute_pareto_bundle(
        season, teams, events=events, tv_cfg=tv_cfg, revenue_model=revenue_model,
    )
    mod_bundle = compute_pareto_bundle(
        modified, teams, events=events, tv_cfg=tv_cfg, revenue_model=revenue_model,
    )
    # Post-Whatif-Validator (2.10.5): harte Constraint-Verletzungen melden.
    feasible = _flag_constraint_violations(mod_bundle, warnings, feasible)
    _flag_publish_gate(season, modified, warnings)

    description = (
        f"{home}@{away} ({length} Spiele) am {forced_start} "
        f"(vorher: {target_games[0].date if target_games else 'n/a'})"
    )

    return WhatIfResult(
        scenario_name=scenario_name,
        description=description,
        original_bundle=orig_bundle,
        modified_bundle=mod_bundle,
        deltas=_build_deltas(orig_bundle, mod_bundle),
        modified_season=modified,
        feasible=feasible,
        warnings=warnings,
    )
