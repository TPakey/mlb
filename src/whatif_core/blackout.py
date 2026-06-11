"""whatif_blackout (A21-Split). Re-exportiert ueber `src.whatif`."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Tuple

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


def whatif_blackout(
    season: Season,
    teams: List[Team],
    cfg: GeneratorConfig,
    team: str,
    blackout_dates: List[date],
    is_home_blackout: bool = True,
    reason: str = "",
    scenario_name: str = "",
    events=None,
    tv_cfg=None,
    revenue_model=None,
) -> WhatIfResult:
    """Was passiert, wenn ein Team ein Venue-Blackout hat (z.B. Konzert im Stadion)?

    Findet alle Heimspiele (oder Auswärtsspiele, je nach Typ) des Teams
    in den Blackout-Tagen und verschiebt jede betroffene Serie auf den
    nächsten freien Slot außerhalb des Blackouts.

    Args:
        season:          Aktueller Saisonplan.
        teams:           Alle 30 Teams.
        cfg:             GeneratorConfig.
        team:            Team-ID (z.B. "HOU" für Houston Astros).
        blackout_dates:  Liste der betroffenen Tage (sortiert oder unsortiert).
        is_home_blackout: True = Heimspiele betroffen; False = Auswärtsspiele.
        reason:          Menschenlesbarer Grund (für Report).
        scenario_name:   Optionaler Name.
        events, tv_cfg, revenue_model: Ressourcen für ParetoBundle.

    Returns:
        WhatIfResult mit Delta in allen 8 Dimensionen.
    """
    blackout_set = set(blackout_dates)
    if not scenario_name:
        label = "Heim" if is_home_blackout else "Auswärts"
        dates_str = f"{min(blackout_set)} – {max(blackout_set)}"
        scenario_name = f"{label}-Blackout {team} ({dates_str})"
        if reason:
            scenario_name += f": {reason}"

    warnings: List[str] = []
    feasible = True

    # ── Betroffene Spiele finden ─────────────────────────────────────────────
    if is_home_blackout:
        affected = [g for g in season.games if g.home == team and g.date in blackout_set]
    else:
        affected = [g for g in season.games if g.away == team and g.date in blackout_set]

    if not affected:
        warnings.append(
            f"Keine {'Heim' if is_home_blackout else 'Auswärts'}-Spiele von "
            f"{team} im Blackout-Fenster gefunden. Plan bleibt unverändert."
        )
        # Trotzdem Bundle berechnen (Vergleich ist dann 0-Delta)
        bundle = compute_pareto_bundle(
            season, teams, events=events, tv_cfg=tv_cfg, revenue_model=revenue_model,
        )
        return WhatIfResult(
            scenario_name=scenario_name,
            description=f"Kein Konflikt gefunden für {team}",
            original_bundle=bundle,
            modified_bundle=bundle,
            deltas=_build_deltas(bundle, bundle),
            modified_season=season,
            feasible=True,
            warnings=warnings,
        )

    # ── Serien aus betroffenen Spielen rekonstruieren ────────────────────────
    def _to_series(game_list: List[Game]) -> List[List[Game]]:
        """Gruppiert Spiele zu zusammenhängenden Serien."""
        if not game_list:
            return []
        by_matchup: Dict[Tuple[str, str], List[Game]] = {}
        for g in game_list:
            key = (g.home, g.away)
            by_matchup.setdefault(key, []).append(g)
        groups = []
        for gs in by_matchup.values():
            gs_sorted = sorted(gs, key=lambda g: g.date)
            # Innerhalb der Matchup-Gruppe: aufeinanderfolgende Serien trennen
            cur = [gs_sorted[0]]
            for g in gs_sorted[1:]:
                if (g.date - cur[-1].date).days <= 1:
                    cur.append(g)
                else:
                    groups.append(cur)
                    cur = [g]
            groups.append(cur)
        return groups

    affected_series = _to_series(affected)

    # Für jede betroffene Serie: gesamte Serie aus der Saison holen
    # (nicht nur die im Blackout — wir müssen die ganze Serie verschieben)
    modified = season
    n_moved = 0

    for partial_series in affected_series:
        # Gesamte Serie ermitteln (kann über den Blackout hinausgehen)
        cs_home = partial_series[0].home
        cs_away = partial_series[0].away
        all_series_groups = _find_series_for_matchup(modified, cs_home, cs_away)
        # Welche Gruppe enthält unsere betroffenen Spiele?
        partial_pks = {g.game_pk for g in partial_series}
        full_series = None
        for sg in all_series_groups:
            sg_pks = {g.game_pk for g in sg}
            if partial_pks & sg_pks:
                full_series = sg
                break

        if full_series is None:
            full_series = partial_series  # Fallback

        cs_length = len(full_series)
        # Preferenz: direkt nach dem Blackout-Ende
        preferred = max(blackout_set) + timedelta(days=1)

        new_slot = _find_free_slot(
            modified,
            teams=[cs_home, cs_away],
            series_length=cs_length,
            preferred_start=preferred,
            blackout=blackout_set,
            season_start=cfg.season_start,
            season_end=cfg.season_end,
        )

        if new_slot is None:
            warnings.append(
                f"Konnte Serie {cs_home}@{cs_away} aus Blackout nicht "
                f"rausverschieben — kein freier Slot. Plan nicht vollständig feasibel."
            )
            feasible = False
            modified = _replace_games(modified, full_series, [])
        else:
            moved = _move_games_to_date(full_series, new_slot)
            modified = _replace_games(modified, full_series, moved)
            n_moved += 1

    # ── Bundles berechnen ────────────────────────────────────────────────────
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
        f"{len(affected_series)} Serie(n) von {team} "
        f"aus {min(blackout_set)}–{max(blackout_set)} verschoben. "
        f"Grund: {reason or 'Venue-Blackout'}"
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
