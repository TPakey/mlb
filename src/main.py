"""CLI-Einstiegspunkt für den MLB Logistics Optimizer (Hauptpfad).

Seit Sprint 2.8 (M10) ruft dieser CLI die **aktuelle** Pipeline auf:
CP-SAT-Generator (`generator.generate`) + Travel-/Fatigue-SA, optional die
Pareto-Front über 8 Dimensionen (`pareto.sample_pareto_frontier`).

Der alte Sprint-0/1-Prototyp-Pfad (schedule_generator/optimizer/scoring/...)
liegt jetzt unter `src/legacy/` und wird nicht mehr aufgerufen. Siehe
docs/ARCHITECTURE_DECISION.md.

Beispiele:
    python -m src.main --season 2026
    python -m src.main --season 2026 --pareto
    python -m src.main --season 2026 --seed 7 --json-out output/season_2026.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

# Audit A17 (Sprint A-3): zentrale Logging-Konfiguration statt `print`.
# Log-Level über die Umgebungsvariable MLB_LOG_LEVEL (Default INFO).
import os as _os
logging.basicConfig(
    level=_os.environ.get("MLB_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mlb.main")

from .data_loader import load_teams
from .datasources import LocalFileAdapter
from .generator import GeneratorConfig, generate
from .matchup_extractor import extract_matchup_quotas
from .player_fatigue import (
    all_teams_pass_fatigue_constraints,
    max_consecutive_away_days,
    max_games_without_off_day,
)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

# MLB-typisches Saisonfenster (Late-March bis Late-September).
DEFAULT_SEASON_START = date(2026, 3, 26)
DEFAULT_SEASON_END = date(2026, 9, 27)
DEFAULT_ALL_STAR_BREAK = (date(2026, 7, 13), date(2026, 7, 16))


def _season_to_dict(season) -> dict:
    return {
        "season": season.season,
        "season_start": season.season_start.isoformat() if season.season_start else None,
        "season_end": season.season_end.isoformat() if season.season_end else None,
        "games": [
            {
                "game_pk": g.game_pk,
                "date": g.date.isoformat(),
                "home": g.home,
                "away": g.away,
                "venue": g.venue,
                "doubleheader_seq": g.doubleheader_seq,
            }
            for g in sorted(season.games, key=lambda g: (g.date, g.game_pk))
        ],
    }


def _print_fatigue_summary(season, team_ids) -> None:
    ok, viols = all_teams_pass_fatigue_constraints(season, team_ids)
    worst_away = max((max_consecutive_away_days(season, t) for t in team_ids), default=0)
    worst_off = max((max_games_without_off_day(season, t) for t in team_ids), default=0)
    logger.info(f"  AC-2.1.8 worst days-away-from-home : {worst_away}  (Limit 13)")
    logger.info(f"  AC-2.1.9 worst games-without-off   : {worst_off}  (Limit 20)")
    if ok:
        logger.info("  Fatigue-Constraints: ALLE eingehalten ✓")
    else:
        logger.info(f"  Fatigue-Constraints: {len(viols)} Verletzung(en):")
        for v in viols[:10]:
            logger.info(f"    - {v}")
        if len(viols) > 10:
            logger.info(f"    ... (+{len(viols) - 10} weitere)")


def _validate_args(args) -> None:
    """Härtung (Sprint 4): CLI-Eingaben früh und mit klarer Meldung prüfen,
    statt sie still in undefiniertes SA-Verhalten laufen zu lassen."""
    errs: list = []
    if args.travel_iterations < 0:
        errs.append("--travel-iterations darf nicht negativ sein")
    if args.sa_iterations < 0:
        errs.append("--sa-iterations darf nicht negativ sein")
    if args.interior < 0:
        errs.append("--interior darf nicht negativ sein")
    if args.solver_time <= 0:
        errs.append("--solver-time muss > 0 sein")
    if args.geo_topk < 1:
        errs.append("--geo-topk muss >= 1 sein")
    if args.feas_lambda < 0:
        errs.append("--feas-lambda darf nicht negativ sein")
    if getattr(args, "feas_ptet", 0.0) < 0:
        errs.append("--feas-ptet darf nicht negativ sein")
    if getattr(args, "sched13_lambda", 0.0) < 0:
        errs.append("--sched13-lambda darf nicht negativ sein")
    if args.holiday_lambda < 0:
        errs.append("--holiday-lambda darf nicht negativ sein")
    if not (0.0 <= args.oropt_share <= 1.0):
        errs.append("--oropt-share muss im Bereich [0, 1] liegen")
    if errs:
        raise SystemExit("Ungültige Argumente:\n  - " + "\n  - ".join(errs))


def run_generate(args) -> int:
    _validate_args(args)
    # Betriebsmodus (Punkt 6): 'forschung' = Gate misst + markiert, kein Abbruch.
    if getattr(args, "mode", "publizierbar") == "forschung":
        args.allow_unpublishable = True
        logger.warning("Betriebsmodus FORSCHUNG: Gate-Verstöße brechen nicht ab, "
                       "Output wird markiert (kein Auslieferungsmodus).")
    teams = load_teams()
    team_ids = [t.id for t in teams]

    adapter = LocalFileAdapter(base_dir="data")
    source_season = adapter.fetch_season_schedule(args.source_season)
    quotas = extract_matchup_quotas(source_season)

    # P0 (2026-06-07): Warm-Start ist der EINZIGE Produktionspfad (CBA-konform,
    # schlägt den realen Plan). From-Scratch ist nur noch Algorithmus-Validierung
    # und über --from-scratch explizit anzufordern. Begründung:
    # docs/DECISION_P0_PRODUCTION_PATH.md.
    use_warm_start = not args.from_scratch
    if args.from_scratch:
        logger.warning(
            "⚠️ --from-scratch: Kalt-Generierung ist NUR Algorithmus-Validierung, "
            "KEIN Produktionspfad. AC-2.1.8 (≤13 Tage) ist hier nicht garantiert. "
            "Für einen MLB-tauglichen Plan ohne --from-scratch laufen lassen "
            "(Warm-Start). Siehe docs/DECISION_P0_PRODUCTION_PATH.md."
        )

    if use_warm_start:
        # WARM-START (empfohlen): den realen Plan der Quell-Saison als Startpunkt
        # nehmen und mit dem SA-Optimizer (Geo-Move) verbessern. Da der Start
        # bereits ein sehr guter, CBA-konformer Plan ist, SCHLAGEN wir ihn auf
        # Reise und bleiben konform — statt ihn reise-blind from-scratch zu
        # unterbieten. Realistischer Produktionsfall (Vorjahresplan anpassen).
        # Begruendung + Messreihe: docs/SPRINT_3_DIAGNOSIS_TRAVEL.md.
        from .generator_optimizer import OptimizerConfig, optimize_travel
        from .season import detect_all_star_break
        if args.legacy_bitident:
            logger.warning(
                "⚠️ --legacy-bitident: Regel-Schutzterme AUS (Alt-Verhalten vor "
                "2026-06-10). Output kann harte CBA-Verstoesse enthalten und wird "
                "nur markiert. Kein Produktionsmodus.")
            args.feas_lambda = 0.0
            args.feas_ptet = 0.0
            args.sched13_lambda = 0.0
        # Review-Runde 2 (Punkt 2): VENUE-AVAIL aktiv — Stadion-Belegungen als
        # harte Blackout-Tage (SA) + Gate-Check. Legacy: leer (Bit-Identitaet).
        from .event_conflicts import (load_local_events,
                                      stadium_bookings_to_blackout_days)
        events = load_local_events()
        blackouts = ({} if args.legacy_bitident else
                     stadium_bookings_to_blackout_days(
                         events, source_season.season_start,
                         source_season.season_end))
        cfg = GeneratorConfig(
            season=args.source_season,
            season_start=source_season.season_start,
            season_end=source_season.season_end,
            all_star_break=detect_all_star_break(source_season),
            max_solver_time_seconds=args.solver_time,
            num_search_workers=1,
            random_seed=args.seed,
            enforce_fatigue_constraints=True,
            travel_optimizer_iterations=args.travel_iterations,
            home_blackout_days=blackouts,
        )
        oc = OptimizerConfig(
            iterations=args.travel_iterations,
            shift_max_days=cfg.travel_optimizer_shift_max_days,
            move_mix_geo=0.35,
            geo_topk=args.geo_topk,
            seed=args.seed,
            fatigue_lambda=1_000_000.0,
            # Review-Fix P0-1 (2026-06-10): Regel-Schutzterme sind jetzt
            # PRODUKTIONS-DEFAULT (CLI-Defaults = production_optimizer_config);
            # das Alt-Verhalten gibt es nur noch explizit per --legacy-bitident.
            feas_lambda=args.feas_lambda,
            feas_w_ptet=args.feas_ptet,
            sched13_lambda=args.sched13_lambda,
            holiday_lambda=args.holiday_lambda,
            enable_dh_compression=args.dh_compression,
            move_mix_oropt=args.oropt_share,
        )
        logger.info(
            "→ Warm-Start: optimiere realen Plan %s (Seed %s, %d Iter) ...",
            args.source_season, args.seed, args.travel_iterations,
        )
        season, opt_log = optimize_travel(source_season, teams, cfg, oc)
        result = None
        logger.info("  Start-km: %s → Final-km: %s",
                    f"{opt_log.initial_km:,.0f}", f"{opt_log.final_km:,.0f}")
        # ---- Publish-Gate (Review-Fix P0-1): Output MESSEN vor Ausweisung.
        from .publish_gate import publishable_report
        from .data_loader import teams_by_id as _tbi
        gate = publishable_report(season, _tbi(teams), baseline=source_season, events=events)
        logger.info("  Publish-Gate: %s", gate.summary())
        if not gate.is_publishable:
            if args.legacy_bitident or args.allow_unpublishable:
                logger.error("⛔ %s — Plan wird als NICHT PUBLIZIERBAR markiert.",
                             gate.summary())
            else:
                logger.error("⛔ %s — Abbruch (Exit 1). Mit --allow-unpublishable "
                             "laesst sich der Plan trotzdem inspizieren.",
                             gate.summary())
                return 1
    else:
        cfg = GeneratorConfig(
            season=args.season,
            season_start=DEFAULT_SEASON_START,
            season_end=DEFAULT_SEASON_END,
            all_star_break=DEFAULT_ALL_STAR_BREAK,
            max_solver_time_seconds=args.solver_time,
            num_search_workers=1,
            random_seed=args.seed,
            # Offizielle Saison-Generierung: hohes Travel-Budget fuer den
            # bestmoeglichen Plan (GeneratorConfig-Default ist bewusst moderat fuer
            # interaktive Pfade). Per --travel-iterations ueberschreibbar.
            travel_optimizer_iterations=args.travel_iterations,
        )

        logger.info(
            "→ Generiere Saison %s (Quoten aus %s, Seed %s) ...",
            args.season, args.source_season, args.seed,
        )
        result = generate(quotas, cfg)
        logger.info(f"  Status: {result.status}")
        if result.season is None:
            logger.info("  Kein feasibler Plan gefunden.")
            return 1
        season = result.season
        # Publish-Gate (strikt) auch fuer den Validierungs-Pfad — nur Messung/
        # Markierung, kein Abbruch (--from-scratch ist kein Produktionspfad).
        from .publish_gate import publishable_report
        from .data_loader import teams_by_id as _tbi
        from .event_conflicts import load_local_events
        gate = publishable_report(season, _tbi(teams), events=load_local_events())
        logger.info("  Publish-Gate (strikt): %s", gate.summary())
    logger.info(f"  Spiele: {len(season.games)}")
    if result is not None and result.final_km is not None:
        logger.info(f"  Reise-km (nach SA): {result.final_km:,.0f}")
    _print_fatigue_summary(season, team_ids)

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = Path(args.json_out) if args.json_out else (
        OUTPUT_DIR / f"season_{args.season}_seed{args.seed}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    season_dict = _season_to_dict(season)

    # ---- Review-Runde 2 (Punkt 3): Startzeiten sind Teil des OUTPUTS, nicht
    # nur Validierung. Deterministische Zuweisung (V(C)(5)-Cap + V(C)(8)-
    # Getaway-Grenzen erzwungen), dann Selbst-Messung der Startzeit-Regeln.
    from .start_times import assign_start_times, AppendixC, fmt_min
    _amin = None
    try:
        _asg = assign_start_times(season, AppendixC.load())
        for gd in season_dict["games"]:
            a = _asg.get(gd["game_pk"])
            if a is not None:
                gd["start_local"] = fmt_min(a.local_start_min)
                gd["slot"] = a.slot.value
        _amin = {pk: a.local_start_min for pk, a in _asg.items()}
        from .compliance import compliance_report as _crep
        _rep = _crep(season, teams_by_id=_tbi(teams), start_min=_amin)
        _st = [c for c in _rep.checks if c.rule_id.startswith("STARTTIME")]
        logger.info("  Startzeiten zugewiesen (%d Spiele); Regel-Check: %s",
                    len(_asg),
                    "; ".join(f"{c.rule_id}={'OK' if c.passed else 'FAIL'}" for c in _st))
        season_dict["start_time_rules"] = {
            c.rule_id: {"passed": c.passed, "measured": c.measured} for c in _st}
    except Exception as exc:
        logger.warning("  Startzeit-Zuweisung fehlgeschlagen: %s", exc)
    # Review-Fix P0-1: Gate-Ergebnis gehoert in den Export — ein Plan ohne
    # bestandenes Gate darf nie unmarkiert weitergereicht werden.
    season_dict["publish_gate"] = {
        "is_publishable": gate.is_publishable,
        "summary": gate.summary(),
        "mode": gate.mode,
    }
    out_path.write_text(json.dumps(season_dict, indent=2), encoding="utf-8")
    logger.info(f"  Plan gespeichert: {out_path}")

    # ---- Review-Runde 2 (Punkt 6): Output-Compliance-Report (JSON+MD) als
    # Pflicht-Artefakt neben dem Plan — messen statt behaupten, pro Lauf.
    try:
        from .run_report import write_run_artifacts
        _base = source_season if use_warm_start else None
        paths = write_run_artifacts(
            season, out_path.parent, out_path.stem, _tbi(teams),
            baseline=_base, start_min=_amin,
            events=(events if use_warm_start else None),
            mode=getattr(args, "mode", "publizierbar"))
        logger.info("  Compliance-Artefakte: %s / %s", paths["json"], paths["md"])
    except Exception as exc:
        logger.warning("  Compliance-Artefakte fehlgeschlagen: %s", exc)

    if args.pareto:
        from .pareto import sample_pareto_frontier
        logger.info(f"\n→ Pareto-Front (Profil-Anker + {args.interior} Interior-Punkte) ...")
        frontier = sample_pareto_frontier(
            season, teams, cfg,
            master_seed=args.seed,
            sa_iterations=args.sa_iterations,
            n_interior_points=args.interior,
            # Sprint 3 P1-5: dieselben optionalen Terme auch im Pareto-Pfad.
            sa_move_mix_geo=(0.35 if args.pareto_geo else 0.0),
            sa_geo_topk=args.geo_topk,
            sa_feas_lambda=args.feas_lambda,
            sa_holiday_lambda=args.holiday_lambda,
            # P1-5: Auslieferungsmodus liefert nur publizierbare Punkte.
            publishable_only=(getattr(args, "mode", "publizierbar") == "publizierbar"),
        )
        logger.info(f"  Nicht-dominierte Pläne: {len(frontier.points)}")
        for p in frontier.points:
            b = p.bundle
            logger.info(
                "    [%16s] km=%10.0f rev=$%7.1fM away=%3s tv=%7.1f viol=%s",
                p.label, b.travel_km, b.revenue_usd / 1e6,
                b.max_away_streak, b.tv_slot_score, b.constraint_violations,
            )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="MLB Logistics Optimizer (Hauptpfad)")
    parser.add_argument("--season", type=int, default=2026,
                        help="Zu generierendes Saisonjahr (Default 2026)")
    parser.add_argument("--source-season", type=int, default=2024,
                        help="Saison, aus der die Matchup-Quoten extrahiert werden")
    parser.add_argument("--seed", type=int, default=42, help="Master-Seed (deterministisch)")
    parser.add_argument("--solver-time", type=float, default=60.0,
                        help="Max. CP-SAT-Solver-Zeit in Sekunden")
    parser.add_argument("--travel-iterations", type=int, default=6_000_000,
                        help="SA-Iterationen fuer die Travel-Optimierung (offizieller "
                             "Saisonplan: hoch fuer beste Qualitaet; Default 6 Mio)")
    parser.add_argument("--warm-start", action="store_true",
                        help="(DEPRECATED — jetzt Default) Warm-Start ist seit P0 der "
                             "einzige Produktionspfad; dieses Flag bleibt nur aus "
                             "Rückwärtskompatibilität und ist ein No-Op.")
    parser.add_argument("--from-scratch", action="store_true",
                        help="NUR Algorithmus-Validierung: Kalt-Generierung from-scratch "
                             "(CP-SAT+SA) statt Warm-Start. NICHT MLB-tauglich — AC-2.1.8 "
                             "ist hier nicht garantiert. Siehe "
                             "docs/DECISION_P0_PRODUCTION_PATH.md.")
    from .generator_optimizer import (PRODUCTION_FEAS_LAMBDA,
                                      PRODUCTION_FEAS_W_PTET,
                                      PRODUCTION_SCHED13_LAMBDA)
    parser.add_argument("--feas-lambda", type=float, default=PRODUCTION_FEAS_LAMBDA,
                        help="Gewicht des Getaway-Feasibility-Terms in der SA-Energie. "
                             "Review-Fix P0-1 (2026-06-10): Default AKTIV (50000) — "
                             "verhindert unrealistische Back-to-Backs jenseits des "
                             "realen MLB-Envelopes (FEAS-GETA, hart). 0 nur noch via "
                             "--legacy-bitident.")
    parser.add_argument("--feas-ptet", type=float, default=PRODUCTION_FEAS_W_PTET,
                        help="Gewicht des CBA-PTET-Penaltys (V(C)(11) Pacific→Eastern "
                             "erzwingt Off-Day; wirkt nur mit --feas-lambda>0). "
                             "Review-Fix P0-1: Default AKTIV (100) — der alte Default 0 "
                             "erzeugte gemessen 18 (2024) / 28 (2025) harte Verstoesse.")
    parser.add_argument("--sched13-lambda", type=float, default=PRODUCTION_SCHED13_LAMBDA,
                        help="Review-Fix P0-2: Gewicht des V(C)(13)-Off-Day-Verteilungs-"
                             "Terms (>2 Open Days/7-Tage-Fenster, Spaetsaison-Minima). "
                             "Default AKTIV (1e6, wirkt wie harter Guard).")
    parser.add_argument("--mode", choices=("publizierbar", "forschung"),
                        default="publizierbar",
                        help="Review-Runde 2 (Punkt 6): Betriebsmodus. "
                             "'publizierbar' (Default) bricht bei Gate-Verstoß ab; "
                             "'forschung' misst + markiert laut, bricht nicht ab. "
                             "Beide Modi schreiben den Output-Compliance-Report "
                             "(JSON+MD) neben den Plan-Export.")
    parser.add_argument("--legacy-bitident", action="store_true",
                        help="Alt-Verhalten OHNE Regel-Schutzterme (bit-identisch zu "
                             "Messungen vor 2026-06-10; setzt --feas-lambda/--feas-ptet/"
                             "--sched13-lambda auf 0). ACHTUNG: Output kann harte "
                             "CBA-Verstoesse enthalten. Kein Produktionsmodus.")
    parser.add_argument("--allow-unpublishable", action="store_true",
                        help="Publish-Gate-Verstoesse nicht als Fehler (Exit 1) werten, "
                             "sondern den Plan markiert exportieren (nur Inspektion).")
    parser.add_argument("--holiday-lambda", type=float, default=0.0,
                        help="Sprint 3 P1-3: Gewicht des Feiertags-Incentives (0 = aus). "
                             "Empfohlen aktiv ~5000 — bevorzugt volle Feiertags-Slates + "
                             "Marquee-Spiele an Feiertagen.")
    parser.add_argument("--geo-topk", type=int, default=2,
                        help="Sprint 3 P2-5: Breite der Geo-Nachbarschaft (Anzahl "
                             "nächster Auswärts-Partner als Einfüge-Anker). Default 2; "
                             "4–6 verbessern die Reise messbar (~−1 %% bei 200k Iter).")
    parser.add_argument("--oropt-share", type=float, default=0.0,
                        help="Sprint 4 (EXPERIMENTELL): Anteil OR-opt/Best-Insertion-"
                             "Geo-Moves (0 = aus, Default). Messung zeigt: konvergiert "
                             "früh minimal besser, ist aber bei Produktions-Iterationen "
                             "schlechter als der stochastische GEO-Move → für offizielle "
                             "Pläne AUS lassen. Siehe docs/SPRINT_4_REVIEW.md.")
    parser.add_argument("--dh-compression", action="store_true",
                        help="Sprint 3 P1-2: verbliebene zu lange Road-Trips per "
                             "Day-Night-Doubleheader verdichten (matchup-erhaltend).")
    parser.add_argument("--pareto", action="store_true",
                        help="Zusätzlich die Pareto-Front berechnen")
    parser.add_argument("--pareto-geo", action="store_true",
                        help="Sprint 3 P1-5: Geo-Move auch in der Pareto-SA aktivieren "
                             "(stärkt den multi-objektiven Pfad auf der Reise-Achse). "
                             "--feas-lambda/--holiday-lambda gelten dort ebenfalls.")
    parser.add_argument("--interior", type=int, default=4,
                        help="Anzahl Interior-Punkte für die Pareto-Front")
    parser.add_argument("--sa-iterations", type=int, default=3000,
                        help="SA-Iterationen pro Pareto-Lauf")
    parser.add_argument("--json-out", default=None, help="Zielpfad für den Saison-Export")
    args = parser.parse_args()

    raise SystemExit(run_generate(args))


if __name__ == "__main__":
    main()
