"""Travel-Optimization-Layer fuer den from-Scratch-Generator.

Der CP-SAT-Generator (siehe `generator.py`) liefert einen *feasiblen* Plan,
ohne Travel-Optimum zu beruecksichtigen. Diese Stufe nimmt diesen Plan und
verbessert ihn mit lokaler Suche (Simulated Annealing auf Serien-Start-Daten).

Moves (alle erhalten Constraint-Invarianz):
- SHIFT: Eine Serie um +-k Tage verschieben
- SWAP: Zwei Serien tauschen Start-Daten (gleiche Laenge erforderlich)

Akzeptiert wird ein Move, wenn:
- die Saison-Window-Grenze nicht verletzt wird
- der All-Star-Break unberuehrt bleibt
- kein Team zwei Serien gleichzeitig hat (NoOverlap)

Ziel: Total-km minimieren (optimize_travel) ODER
      Multi-Objective ParetoBundle (optimize_pareto, Sprint 2.3b).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from .data_loader import Team
from .distance import haversine_km
from .timezones import tz_offset_hours
from .feasibility import FeasibilityThresholds, DEFAULT_THRESHOLDS, _classify
from .generator import GeneratorConfig
from .season import Game, Season
# Audit A18 (Sprint A-4): zuvor lokale Imports in optimize_pareto auf
# Modulebene hochgezogen — sie liegen weder im Hot-Path noch in einer
# zirkulären Abhängigkeit (pareto_types/revenue importieren generator_optimizer
# nicht). Bringt Klarheit und vermeidet Mikro-Overhead pro Aufruf.
from .pareto_types import compute_pareto_bundle, _compute_off_day_variance
from .revenue import expected_revenue_raw, build_division_rivals
from .two_phase_pacing import AC_2_1_8_MAX_AWAY_STREAK, AC_2_1_9_MAX_GAMES

if TYPE_CHECKING:
    from .event_conflicts import LocalEvent
    from .pareto_types import ParetoBundle
    from .phases import PhasePlan
    from .profiles import ParetoProfile
    from .tv_slots import TvSlotConfig


@dataclass
class SeriesEntry:
    """Eine zu plazierende Serie mit aktuellem Start-Datum-Index."""
    idx: int
    home: str
    away: str
    length: int
    start_day: int                       # 0..(season_days - length)
    # Spiele pro Tag der Serie (len == length). Normal alle 1; ein Doubleheader-
    # Tag hat 2. Leer -> wie [1]*length behandelt. Wird beim Roundtrip
    # (entries->season) gebraucht, damit Doubleheader nicht verloren gehen
    # (Sprint 3 FIX fuer Warm-Start auf realen Plaenen mit DH).
    day_game_counts: Tuple[int, ...] = ()
    # Nacht-Härtung 2026-06-11 (P2): dh_type je Serientag (""=kein DH, "S"/"Y")
    # — reine Metadaten-Durchreichung, damit der Roundtrip entries->season den
    # MLB-doubleHeader-Typ ERHAELT und V(C)(14) Satz 2 (max. 1 Home-Split-DH)
    # auf SA-Output messbar ist (vorher vakuos, weil der Typ verloren ging).
    day_dh_types: Tuple[str, ...] = ()

    def days_occupied(self) -> Set[int]:
        return set(range(self.start_day, self.start_day + self.length))


@dataclass
class OptimizerConfig:
    iterations: int = 5000
    start_temperature: float = 1500.0
    end_temperature: float = 1.0
    shift_max_days: int = 7              # SHIFT-Move: +-N Tage
    move_mix_shift: float = 0.6          # Anteil SHIFT-Moves (vom Nicht-GEO-Rest)
    # ---- Sprint 3: geo-bewusster Struktur-Move ----
    # Anteil GEO-Moves: loest eine Auswaerts-Serie heraus und setzt sie direkt
    # neben den geografisch naechsten Auswaerts-Gegner desselben Teams (Ejection/
    # Insertion-Nachbarschaft aus der TTP-Heuristik-Literatur). Das aendert die
    # Road-Trip-KOMPOSITION (welche Gegner zu einer Reise gehoeren) — anders als
    # SHIFT/SWAP, die nur Termine verschieben. Schliesst den Reise-Gap zum realen
    # MLB-Plan. Diagnose: docs/SPRINT_3_DIAGNOSIS_TRAVEL.md. Feasibility wird ueber
    # alle betroffenen Teams geprueft; Akzeptanz via SA-Energie (deterministisch).
    move_mix_geo: float = 0.35
    # P2-5: Breite der Geo-Nachbarschaft (Anzahl nächster Auswärts-Partner, die
    # als Einfüge-Anker in Frage kommen). Default 2 = bisheriges Verhalten
    # (bit-identisch). Höher = stärkere Struktur-Nachbarschaft (TTP-Richtung).
    geo_topk: int = 2
    # ---- Sprint 4: OR-opt / Best-Insertion-Geo-Move (TTP-Nachbarschaft) ----
    # Anteil OROPT-Moves. Wie der GEO-Move loest OROPT eine Auswaerts-Serie heraus
    # und setzt sie neben einen geografisch nahen Auswaerts-Gegner — ABER statt
    # eines zufaelligen Partners + erstem zulaessigen Slot scannt OROPT
    # DETERMINISTISCH alle geo_topk-Partner x {davor, danach} und waehlt den Slot
    # mit der GERINGSTEN resultierenden Reise des bewegten Teams (Best-
    # Insertion/Steepest-Descent — die in der TTP-Literatur ueblichere, staerkere
    # OR-opt-Nachbarschaft). Die eigentliche Annahme bleibt SA-Energie-basiert
    # (deterministisch). Nutzt dieselbe Single-Entry-Buchhaltung wie GEO/SHIFT.
    # DEFAULT 0.0 → Move-Band leer, rng-Sequenz + Verzweigung bit-identisch zum
    # bisherigen Verhalten. Empfohlen mit hoeherem geo_topk (4–8).
    move_mix_oropt: float = 0.0
    seed: int = 42
    log_every: int = 500
    # ---- Sprint 2.3 Task #15: Fatigue-Penalty ----
    # Energy = total_km + fatigue_lambda * fatigue_penalty
    # Fatigue-Penalty = Sum ueber Teams: (max_consec_away - 13)+^2
    #                                  + (max_games_no_off - 20)+^2
    # Mit Lambda=100000 ist ein einzelner AC-Bruch (z.B. 14 statt 13
    # consec-away => 1^2 = 1) "100000 km wert" — dominiert die km-Loss.
    fatigue_lambda: float = 100000.0
    max_consec_away_limit: int = 13      # AC-2.1.8
    max_games_no_off_limit: int = 20     # AC-2.1.9
    # ---- Sprint 3 P1-3: Getaway-Feasibility-Penalty (optional, weich) ----
    # Energy += feas_lambda * feasibility_penalty. Bestraft unrealistische
    # Back-to-Backs (siehe src/feasibility.py). DEFAULT 0.0 → komplett aus, kein
    # Zusatz-Compute, Produktionsverhalten bit-identisch. Empfohlener Aktiv-Wert:
    # ~50_000 (deutlich unter fatigue_lambda, damit AC-2.1.8/9 Vorrang behalten,
    # aber spuerbar gegenueber km). w_exceeds >> w_tight: echte Envelope-
    # Verstoesse hart, harte-aber-konforme Turnarounds nur leicht bestraft.
    feas_lambda: float = 0.0
    feas_w_exceeds: float = 1.0
    feas_w_tight: float = 0.1
    # ---- Sprint 5.2: harte CBA V(C)(11) PT→ET-Off-Day als SA-Penalty (gegated) ----
    # Verhindert, dass ein Move einen konsekutiven Spieltag Pacific-Stadt → Eastern-
    # Stadt OHNE Off-Day erzeugt (stille CBA-PTET-Verletzung). Reitet auf der
    # Feasibility-Penalty-Maschinerie (greift nur bei feas_lambda>0). DEFAULT 0.0 →
    # bit-identisch. Empfohlener Aktiv-Wert: ~100 (× feas_lambda dominiert km klar).
    feas_w_ptet: float = 0.0
    # ---- Sprint 3 P1-3: Feiertags-Incentive (optional, weich) ----
    # Energy += holiday_lambda * holiday_penalty. Penalty = fehlende Slate-
    # Abdeckung an league_wide-Feiertagen + fehlende Marquee-Spiele an
    # marquee-Feiertagen. DEFAULT 0.0 → aus, bit-identisch. Aktiv-Wert ~5_000
    # (Feiertage sind ein weicher Wunsch, kein Constraint).
    holiday_lambda: float = 0.0
    holiday_w_slate: float = 1.0         # je fehlendem Team-Slot an league_wide-Tagen
    holiday_w_marquee: float = 5.0       # je fehlendem Marquee-Spiel an marquee-Tagen
    # ---- Q10: optionaler gefensterter CP-SAT-LNS-Repair fuer AC-2.1.8 ----
    # Nach der SA laeuft optional ein Large-Neighborhood-Search-Repair: pro zu
    # langem Road-Trip wird ein kleines Zeitfenster (inkl. Gegner-Serien) plus
    # alle Serien des verletzenden Teams freigegeben und mit dem strukturellen
    # AC-2.1.8-Constraint (nur fuer dieses Team) + Stay-Close-Ziel exakt geloest.
    # Global-monotone Akzeptanz: ein Move wird nur uebernommen, wenn die Zahl der
    # Teams ueber dem Limit sinkt (oder bei Gleichstand der globale worst). Senkt
    # die realen AC-2.1.8-Verletzungen weiter, deterministisch (1-Worker) und
    # matchup-erhaltend — aber OHNE ≤13-Garantie (Kopplung kaskadiert ueber
    # Fenstergrenzen; siehe docs/Q10_ANALYSE_UND_RECHERCHE.md). Default aus
    # (Laufzeit-Aufschlag ~15-25 s).
    enable_lns_ac218_repair: bool = False
    lns_pad: int = 8
    lns_solve_time_s: float = 2.5
    lns_budget_s: float = 30.0
    lns_max_passes: int = 60
    # ---- Sprint 3 P1-2: optionale Doubleheader-Verdichtung (Post-SA) ----
    # Verdichtet nach der SA verbliebene zu lange Road-Trips per Day-Night-DH
    # (letzte Auswaerts-Serie des Trips → DH, Spanne −1). Matchup-erhaltend,
    # deterministisch, occupancy-schrumpfend (kein neuer Overlap). Default aus →
    # Verhalten unveraendert. Siehe src/doubleheaders.py.
    enable_dh_compression: bool = False
    # ---- Review-Fix 2026-06-10 (P0-2): V(C)(13)-Off-Day-Verteilungs-Penalty ----
    # Energy += sched13_lambda * Σ_Team max(0, m − m0), wobei m die V(C)(13)-
    # Meldungszahl des Teams in Checker-Granularitaet ist (Fenster-Flag +
    # Minima-Flags, m ∈ 0..3; exakt schedule_rules.check_offday_distribution)
    # und m0 der Startwert (Warm-Start auf as-played-Daten traegt Artefakte,
    # die der SA nicht beheben muss — Gate-Kriterium ist "keine NEUEN
    # Verstoesse"). Zusaetzlich wird die Best-Loesung nur aus Zustaenden mit
    # Penalty 0 uebernommen (Best-Filter). Mit ~1e6 wirkt der Term wie ein
    # harter Guard (analog fatigue_lambda).
    #
    # WICHTIG — KEINE Garantie "per Konstruktion": Der Penalty *senkt* die
    # Verstoss-Wahrscheinlichkeit drastisch, garantiert Konformitaet aber NICHT
    # aus sich heraus. Er misst V(C)(13) relativ zu ``_s13_asb`` (dem All-Star-
    # Break); bei FALSCHEM oder fehlendem ASB optimiert der SA gegen das falsche
    # Modell und erzeugt sehr wohl neue Verstoesse (gemessen: ~29 auf dem
    # 2026-Original bei ASB=None, scheinbar besser mit -2,31 %% statt -1,7 %%,
    # weil Verstoesse km sparen). Die EINZIGE harte Garantie ist die Ablehnung
    # durch das Publish-Gate (publish_gate.publishable_report, baseline=Input)
    # PLUS ausreichend Iterationen. Korrekte Formel also: "Konformitaet durch
    # Gate-Ablehnung + ausreichende Iterationen", nicht "per Konstruktion".
    # Gegen die ASB-Fehlbedienung schuetzt zusaetzlich der Guard in
    # production_optimizer_config() (Finalisierung Punkt 3).
    # DEFAULT 0.0 → kein Zusatz-Compute, bit-identisch (Dataclass-Kontrakt).
    # Produktionspfade nutzen production_optimizer_config().
    sched13_lambda: float = 0.0
    # ---- Finalisierung Punkt 3: ASB-Fehlbedienungs-Guard ----
    # Der V(C)(13)-Penalty misst relativ zum All-Star-Break. Fehlt/falsch der
    # ASB, optimiert er gegen das falsche Modell und laesst still neue Verstoesse
    # durch (gemessen ~29 auf 2026-Original bei ASB=None — scheinbar besser, weil
    # Verstoesse km sparen). Ist dieser Schalter True (Produktions-Default), bricht
    # optimize_travel FRUEH ab, wenn sched13_lambda>0 aber kein plausibler ASB im
    # Saisonfenster liegt — statt den Fehler erst dem Gate zu ueberlassen.
    # DEFAULT False → Verhalten/Bit-Identitaet unveraendert.
    require_all_star_break: bool = False


# ====================================================================
# Produktions-Default (Review-Fix 2026-06-10, P0-1/P0-2)
# ====================================================================
# Der nackte OptimizerConfig()-Default bleibt aus Bit-Identitaets-Gruenden
# "alle Schutzterme aus" (zahlreiche Determinismus-Tests und Alt-Messungen
# haengen daran). Die PRODUKTIONSPFADE (tools/backtest --warm-start, src/main)
# duerfen damit aber NICHT mehr laufen: gemessen erzeugt der ungeschuetzte
# Default harte CBA-Verstoesse (V(C)(11): 18x/2024, 28x/2025; Review-Report
# docs/REVIEW_2026-06-10_INDEPENDENT_AI.md). Produktion = diese Funktion;
# der alte Zustand ist nur noch explizit per --legacy-bitident erreichbar.

PRODUCTION_FATIGUE_LAMBDA = 1_000_000.0
PRODUCTION_FEAS_LAMBDA = 50_000.0      # Reise-Envelope (FEAS-GETA, hart)
PRODUCTION_FEAS_W_PTET = 100.0         # CBA V(C)(11) PT→ET (hart)
# V(C)(13) als Guard (1e6, wie fatigue_lambda). Messreihe 2026-06-10 (3M Iter,
# Seed 42, real 2024): lambda=2e3 → SA kehrt nie in einen verstoßfreien Zustand
# zurueck (km-Gewinn 0); lambda=2e4 → −1,86 %; lambda=1e5 und 1e6 → −2,39 %,
# Gate PASS. Die Korrektheit haengt dabei NICHT allein an Lambda: die Best-
# Loesung wird grundsaetzlich nur aus Zustaenden OHNE neue V(C)(13)-Verstoesse
# uebernommen (Best-Filter in optimize_travel), und das Publish-Gate misst
# jeden Output. EHRLICHER TRADE-OFF: volle Regel-Konformitaet kostet km
# (−2,4 % statt −4,9 % bei 3M) — die alte, hoehere Zahl entstand durch
# Regelverstoesse und war nicht publizierbar.
PRODUCTION_SCHED13_LAMBDA = 1_000_000.0  # CBA V(C)(13) Off-Day-Verteilung


def production_optimizer_config(**overrides) -> "OptimizerConfig":
    """OptimizerConfig mit AKTIVEN Regel-Schutztermen (Produktions-Default).

    Gemessen (2026-06-10, real 2024, 3–6 M Iter, Seed 42): kostet keine km
    (−4,94 % mit Gates vs. −4,88 % ohne) und senkt die Verstoesse drastisch.
    WICHTIG: Diese Terme machen den Output NICHT "konform per Konstruktion" —
    bei falschem/fehlendem All-Star-Break optimiert der V(C)(13)-Term gegen das
    falsche Modell und laesst neue Verstoesse durch (gemessen ~29 auf dem
    2026-Original mit ASB=None). Die harte Garantie ist erst das Publish-Gate
    (publishable_report) PLUS ausreichend Iterationen; der ASB-Guard unten faengt
    die Fehlbedienung frueh ab. Siehe docs/REVIEW_2026-06-10_INDEPENDENT_AI.md
    (P0-1) und docs/FINALIZATION.md (Punkte 2+3).
    """
    base = dict(
        fatigue_lambda=PRODUCTION_FATIGUE_LAMBDA,
        feas_lambda=PRODUCTION_FEAS_LAMBDA,
        feas_w_ptet=PRODUCTION_FEAS_W_PTET,
        sched13_lambda=PRODUCTION_SCHED13_LAMBDA,
        require_all_star_break=True,  # Punkt-3-Guard: ASB-Fehlbedienung früh kippen
    )
    base.update(overrides)
    return OptimizerConfig(**base)


@dataclass
class OptimizationLog:
    initial_km: float
    final_km: float
    iterations: int
    accepted: int
    rejected_constraint: int
    rejected_temperature: int
    history: List[float] = field(default_factory=list)


def _season_to_entries(season: Season, cfg: GeneratorConfig) -> List[SeriesEntry]:
    """Zerlegt eine Season in Serien-Eintraege mit Start-Day-Index."""
    # Gruppiere Spiele zu Serien (gleiches home/away/aufeinanderfolgende Tage)
    games = sorted(season.games, key=lambda g: (g.home, g.away, g.date))
    entries: List[SeriesEntry] = []
    idx = 0
    cur: List[Game] = []
    for g in games:
        if not cur:
            cur = [g]
            continue
        prev = cur[-1]
        same = (prev.home == g.home and prev.away == g.away)
        consec = (g.date - prev.date).days <= 1
        if same and consec:
            cur.append(g)
        else:
            entries.append(_entry_from_games(idx, cur, cfg))
            idx += 1
            cur = [g]
    if cur:
        entries.append(_entry_from_games(idx, cur, cfg))
    return entries


def _entry_from_games(idx: int, games: List[Game], cfg: GeneratorConfig) -> SeriesEntry:
    start_day = (games[0].date - cfg.season_start).days
    # length = Anzahl TAGE der Serie (nicht Spiele), damit days_occupied() korrekt ist.
    # Bei Doubleheadern (2 Spiele am selben Tag): length=1, nicht 2 — sonst wird
    # ein Folgetag als belegt markiert, was NoOverlap-Checks korrumpiert.
    num_days = (games[-1].date - games[0].date).days + 1
    # Spiele pro Tag erfassen (Doubleheader = 2 am selben Tag), damit der
    # Roundtrip entries->season die DH erhaelt.
    per_day: Dict[int, int] = {}
    dh_per_day: Dict[int, str] = {}
    for g in games:
        off = (g.date - games[0].date).days
        per_day[off] = per_day.get(off, 0) + 1
        if g.doubleheader_seq > 0 and g.dh_type:
            dh_per_day[off] = g.dh_type
    day_game_counts = tuple(per_day.get(off, 1) for off in range(num_days))
    day_dh_types = tuple(dh_per_day.get(off, "") for off in range(num_days))
    return SeriesEntry(
        idx=idx,
        home=games[0].home,
        away=games[0].away,
        length=num_days,
        start_day=start_day,
        day_game_counts=day_game_counts,
        day_dh_types=day_dh_types,
    )


def _entries_to_season(entries: List[SeriesEntry], cfg: GeneratorConfig,
                        all_star_dates: tuple) -> Season:
    games: List[Game] = []
    pk = 2_000_000
    for e in entries:
        counts = e.day_game_counts or tuple([1] * e.length)
        dh_types = e.day_dh_types or tuple([""] * e.length)
        for off in range(e.length):
            d = cfg.season_start + timedelta(days=e.start_day + off)
            c = counts[off] if off < len(counts) else 1
            dht = dh_types[off] if off < len(dh_types) else ""
            for seq in range(c):
                # Doubleheader (c>1): doubleheader_seq = 1,2; sonst 0.
                # dh_type wird durchgereicht (P2: V(C)(14)-Satz-2 messbar).
                games.append(Game(game_pk=pk, date=d, home=e.home, away=e.away,
                                  venue=e.home,
                                  doubleheader_seq=(seq + 1 if c > 1 else 0),
                                  game_type="R",
                                  dh_type=(dht if c > 1 else "")))
                pk += 1
    games.sort(key=lambda g: (g.date, g.game_pk))
    return Season(season=cfg.season, games=games,
                   season_start=cfg.season_start, season_end=cfg.season_end,
                   all_star_dates=all_star_dates)


def _build_team_index(entries: List[SeriesEntry]) -> Dict[str, List[int]]:
    """Pro Team: Liste der Indizes seiner Serien-Eintraege."""
    out: Dict[str, List[int]] = {}
    for i, e in enumerate(entries):
        out.setdefault(e.home, []).append(i)
        out.setdefault(e.away, []).append(i)
    return out


def _team_total_km(team_id: str, entries: List[SeriesEntry],
                    team_idx: Dict[str, List[int]],
                    teams_by_id: Dict[str, Team]) -> float:
    """Reisedistanz fuer ein Team gegeben die aktuelle Belegung."""
    my_entries = sorted((entries[i] for i in team_idx[team_id]),
                         key=lambda e: e.start_day)
    if not my_entries:
        return 0.0
    home = teams_by_id[team_id]
    # Start daheim
    loc = team_id
    km = 0.0
    for e in my_entries:
        venue = e.home   # Wo gespielt wird
        if venue != loc:
            a = teams_by_id[loc]
            b = teams_by_id[venue]
            km += haversine_km(a.lat, a.lon, b.lat, b.lon)
        loc = venue
    # Zurueck nach Hause
    if loc != team_id:
        a = teams_by_id[loc]
        km += haversine_km(a.lat, a.lon, home.lat, home.lon)
    return km


def _total_km(entries: List[SeriesEntry], team_idx: Dict[str, List[int]],
              teams_by_id: Dict[str, Team]) -> float:
    return sum(_team_total_km(tid, entries, team_idx, teams_by_id)
               for tid in team_idx)


def _valid_start_for_length(length: int, total_days: int,
                              break_days: Set[int]) -> Set[int]:
    out: Set[int] = set()
    for start in range(0, total_days - length + 1):
        occupied = set(range(start, start + length))
        if not occupied.intersection(break_days):
            out.add(start)
    return out


def _no_team_overlap(entries: List[SeriesEntry], team_idx: Dict[str, List[int]],
                     changed_idx: int) -> bool:
    """Prueft, ob die neue Belegung der Serie `changed_idx` mit Mitspielern
    desselben Teams nicht kollidiert.

    M8 (Sprint 2.11): Statt pro Paar zwei Tages-Mengen zu allokieren und zu
    schneiden (O(Laenge) je Paar), wird der Ueberlappungstest als reiner
    Intervall-Vergleich gefuehrt — zwei Serien [s1,e1] und [s2,e2] ueberlappen
    genau dann, wenn ``s1 <= e2 and s2 <= e1``. Das ist O(1) je Paar (keine
    Set-Allokation) und damit deutlich schneller in der heissen SA-Schleife.
    """
    moved = entries[changed_idx]
    # Audit A10 (Sprint A-4): defensive Behandlung degenerierter Serien.
    if moved.length <= 0:
        return True
    m_start = moved.start_day
    m_end = moved.start_day + moved.length - 1
    for team in (moved.home, moved.away):
        for other_idx in team_idx[team]:
            if other_idx == changed_idx:
                continue
            other = entries[other_idx]
            o_start = other.start_day
            o_end = other.start_day + other.length - 1
            if m_start <= o_end and o_start <= m_end:
                return False
    return True


# ---------------------- Fatigue-Score-Helfer (Task #15) ----------------------

def _team_max_streaks(team_id: str, entries: List[SeriesEntry],
                       team_idx: Dict[str, List[int]]) -> Tuple[int, int]:
    """Berechnet (max_days_away_from_home, max_games_no_off) fuer ein Team.

    - max_days_away_from_home (AC-2.1.8): laengste Road-Trip in "days away from
      home" gemaess CBA-Definition (siehe docs/CBA_DEFINITIONS.md). Eine
      Road-Trip beginnt mit dem ersten Auswaertsspiel und endet mit dem
      letzten Auswaertsspiel vor dem naechsten Heimspiel; **Off-Days mitten in
      der Reise zaehlen mit**. Nur ein Heimspiel beendet die Road-Trip.
      Gemessen als Spanne in Kalendertagen (last_away - first_away + 1).
    - max_games_no_off (AC-2.1.9): laengste Folge konsekutiver Tage, an denen
      das Team ueberhaupt spielt (Off-Day unterbricht).

    Konsistent mit `player_fatigue.max_consecutive_away_days`.

    Audit A7 (Sprint A-4): Diese Funktion allokiert pro Aufruf ein
    day_is_away-Dict und eine sortierte Liste — bei ~700k SA-Moves × wenigen
    Aufrufen pro Move ist das spuerbar, aber unkritisch fuer die aktuelle
    Workload. Eine echte Optimierung (per-Team-State, der inkrementell durch
    SHIFT/SWAP gepflegt wird) ist als Folgearbeit dokumentiert; vor MLB-
    Skalierung sollte das angegangen werden.
    """
    my = [entries[i] for i in team_idx[team_id]]
    if not my:
        return 0, 0

    # Pro Tag: spielt das Team an diesem Tag auswaerts oder zu Hause?
    # (Ein Tag kann fuer dasselbe Team nicht zugleich Heim- und Auswaerts sein.)
    day_is_away: Dict[int, bool] = {}
    for e in my:
        is_away = (e.away == team_id)
        for off in range(e.length):
            d = e.start_day + off
            day_is_away[d] = is_away
    play_days = sorted(day_is_away)

    # --- AC-2.1.8: Road-Trip-Spanne (Off-Days zaehlen mit, Heimspiel bricht) ---
    max_away = 0
    trip_start: Optional[int] = None
    trip_end: Optional[int] = None
    for d in play_days:
        if day_is_away[d]:
            if trip_start is None:
                trip_start = d
            trip_end = d
        else:
            if trip_start is not None:
                max_away = max(max_away, trip_end - trip_start + 1)
                trip_start = None
                trip_end = None
    if trip_start is not None:
        max_away = max(max_away, trip_end - trip_start + 1)

    # --- AC-2.1.9: konsekutive Spieltage ohne Off-Day ---
    # N8 (Sprint 2.11): `play_days` ist bereits eine sortierte Liste DISTINKTER
    # Tage (Keys von day_is_away), daher entfällt die frühere Doubleheader-
    # Sonderbehandlung — ein einfacher Lauf-Zähler genügt.
    def _max_run(days: List[int]) -> int:
        max_run = 0
        cur = 0
        prev: Optional[int] = None
        for d in days:
            cur = cur + 1 if (prev is not None and d == prev + 1) else 1
            if cur > max_run:
                max_run = cur
            prev = d
        return max_run

    return max_away, _max_run(play_days)


def _team_fatigue_penalty(max_consec_away: int, max_games_no_off: int,
                           away_limit: int = 13, off_limit: int = 20) -> float:
    """Quadratische Penalty fuer AC-2.1.8/9-Verletzungen."""
    p = 0.0
    if max_consec_away > away_limit:
        diff = max_consec_away - away_limit
        p += diff * diff
    if max_games_no_off > off_limit:
        diff = max_games_no_off - off_limit
        p += diff * diff
    return p


def _initial_team_fatigue(entries: List[SeriesEntry],
                           team_idx: Dict[str, List[int]],
                           away_limit: int, off_limit: int) -> Tuple[Dict[str, Tuple[int, int]], float]:
    """Initiale Berechnung der Fatigue-Werte fuer alle Teams.

    Returns:
        (team_fatigue_dict, total_penalty) — pro Team (consec_away, no_off)
        plus die Summe der Per-Team-Penalties.
    """
    team_fatigue: Dict[str, Tuple[int, int]] = {}
    total = 0.0
    for tid in team_idx:
        ca, no = _team_max_streaks(tid, entries, team_idx)
        team_fatigue[tid] = (ca, no)
        total += _team_fatigue_penalty(ca, no, away_limit, off_limit)
    return team_fatigue, total


# ------------------ Getaway-Feasibility-Penalty (Sprint 3 P1-3) ------------------
# Optionaler weicher SA-Term, der unrealistische Back-to-Backs bestraft: ein Team,
# das an Tag d in Stadt A und an Tag d+1 in Stadt B (ohne Off-Day) spielt. Bewertet
# wie src/feasibility.py: `exceeds_real_envelope` (jenseits des real beobachteten
# MLB-Maximums, ~4200 km / 3 TZ-Hops) stark, `tight` (ostwaerts, >=2 Hops, lange
# Distanz) leicht. Per-Team zerlegbar wie die Fatigue-Penalty → inkrementell
# pflegbar. Standardmaessig deaktiviert (feas_lambda=0) → Produktionsverhalten
# bit-identisch.

# CBA V(C)(11): Pacific→Eastern erzwingt Off-Day. Zonen konsistent mit
# compliance._PT_ZONES / _ET_ZONES.
_PT_ZONES_SA = {"America/Los_Angeles"}
_ET_ZONES_SA = {"America/New_York", "America/Toronto"}


def _team_feasibility_penalty(team_id: str, entries: List[SeriesEntry],
                               team_idx: Dict[str, List[int]],
                               teams_by_id: Dict[str, Team],
                               season_start,
                               thresholds: FeasibilityThresholds,
                               w_exceeds: float, w_tight: float,
                               w_ptet: float = 0.0) -> float:
    """Feasibility-Penalty eines Teams gegeben die aktuelle Belegung.

    Konsistent mit ``feasibility.team_transitions``: nur konsekutive
    Intercity-Transfers (gap = 1 Tag) werden bewertet. ``w_ptet`` (Sprint 5.2,
    Default 0.0 → bit-identisch) addiert eine Strafe je konsekutivem Spieltag
    Pacific-Stadt → Eastern-Stadt ohne Off-Day (harte CBA-Regel V(C)(11)).
    """
    my = [entries[i] for i in team_idx.get(team_id, [])]
    if not my:
        return 0.0
    day_city: Dict[int, str] = {}
    for e in my:
        for off in range(e.length):
            d = e.start_day + off
            if d not in day_city:        # erster Belegende setzt die Stadt (kein Overlap)
                day_city[d] = e.home
    days = sorted(day_city)
    pen = 0.0
    for d0, d1 in zip(days, days[1:]):
        if d1 - d0 != 1:
            continue                     # Off-Day-Puffer → kein Back-to-Back
        c0, c1 = day_city[d0], day_city[d1]
        if c0 == c1:
            continue
        ta, tb = teams_by_id[c0], teams_by_id[c1]
        if w_ptet and ta.timezone in _PT_ZONES_SA and tb.timezone in _ET_ZONES_SA:
            pen += w_ptet                # CBA V(C)(11): PT→ET ohne Off-Day
        km = haversine_km(ta.lat, ta.lon, tb.lat, tb.lon)
        arrive_date = season_start + timedelta(days=d1)
        off0 = tz_offset_hours(ta.timezone, arrive_date)
        off1 = tz_offset_hours(tb.timezone, arrive_date)
        hops = abs(off1 - off0)
        eastward = off1 > off0
        sev = _classify(km, hops, eastward, thresholds)
        if sev == "exceeds_real_envelope":
            pen += w_exceeds
        elif sev == "tight":
            pen += w_tight
    return pen


def _initial_team_feasibility(entries: List[SeriesEntry],
                               team_idx: Dict[str, List[int]],
                               teams_by_id: Dict[str, Team],
                               season_start,
                               thresholds: FeasibilityThresholds,
                               w_exceeds: float, w_tight: float,
                               w_ptet: float = 0.0) -> Tuple[Dict[str, float], float]:
    """Initiale Feasibility-Penalty je Team plus Summe."""
    team_feas: Dict[str, float] = {}
    total = 0.0
    for tid in team_idx:
        p = _team_feasibility_penalty(tid, entries, team_idx, teams_by_id,
                                      season_start, thresholds, w_exceeds, w_tight,
                                      w_ptet)
        team_feas[tid] = p
        total += p
    return team_feas, total


# ---------------------- AC-2.1.8 Pre-Repair (Sprint 2.7) ----------------------

def _team_road_trips(team_id: str, entries: List[SeriesEntry],
                      team_idx: Dict[str, List[int]]) -> List[Tuple[int, int]]:
    """Liste der Road-Trips eines Teams als (first_away_day, last_away_day).

    Konsistent mit `_team_max_streaks` (CBA-Definition, Off-Days zaehlen mit,
    Heimspiel beendet die Trip). Spanne in Tagen = end - start + 1.
    """
    my = [entries[i] for i in team_idx.get(team_id, [])]
    day_is_away: Dict[int, bool] = {}
    for e in my:
        is_away = (e.away == team_id)
        for off in range(e.length):
            day_is_away[e.start_day + off] = is_away
    trips: List[Tuple[int, int]] = []
    start: Optional[int] = None
    end: Optional[int] = None
    for d in sorted(day_is_away):
        if day_is_away[d]:
            if start is None:
                start = d
            end = d
        else:
            if start is not None:
                trips.append((start, end))
                start = end = None
    if start is not None:
        trips.append((start, end))
    return trips


def _team_worst_trip(team_id: str, entries: List[SeriesEntry],
                      team_idx: Dict[str, List[int]]) -> int:
    trips = _team_road_trips(team_id, entries, team_idx)
    return max((b - a + 1 for a, b in trips), default=0)


def _bo_ok(blackout: Optional[Dict[str, "frozenset"]], home: str,
           start: int, length: int) -> bool:
    """True, wenn die Heimserie (home, [start, start+length)) keinen
    home_blackout_days-Tag belegt. Ohne Blackout-Daten immer True."""
    if not blackout:
        return True
    bl = blackout.get(home)
    if not bl:
        return True
    return all((start + k) not in bl for k in range(length))


def _greedy_fatigue_repair(entries: List[SeriesEntry],
                            team_idx: Dict[str, List[int]],
                            valid_starts: Optional[Dict[int, Set[int]]] = None,
                            away_limit: int = 13,
                            off_limit: int = 20,
                            max_passes: int = 80,
                            blackout: Optional[Dict[str, "frozenset"]] = None) -> int:
    """Deterministischer Pre-Repair fuer AC-2.1.8 (Road-Trip <= away_limit).

    Hintergrund (Sprint 2.7 / Review C1): Nachdem die AC-2.1.8-Definition auf
    "days away from home" korrigiert wurde, kann der CP-SAT-Plan Road-Trips
    > 13 Tage enthalten, die die reine Travel-SA nicht zuverlaessig aufbricht.
    Dieser Schritt bricht zu lange Road-Trips gezielt auf, indem er eine
    Heimserie (ausserhalb der Trip) mit einer Auswaertsserie gleicher Laenge
    (innerhalb der Trip) tauscht. Da beide Serien dieselbe Laenge und zuvor
    gueltige Start-Tage hatten, bleibt die All-Star-/Break-Day-Gueltigkeit
    erhalten; geprueft wird nur die NoOverlap-Invariante.

    Akzeptiert wird ein Swap nur, wenn er die laengste Road-Trip des
    betrachteten Teams verkuerzt UND bei keinem der beiden Tausch-Partner eine
    *neue* Verletzung erzeugt. Liefert die Anzahl angewandter Swaps zurueck.
    """
    applied = 0
    for _pass in range(max_passes):
        violators: List[Tuple[int, str]] = []
        for tid in team_idx:
            w = _team_worst_trip(tid, entries, team_idx)
            if w > away_limit:
                violators.append((w, tid))
        if not violators:
            break
        violators.sort(reverse=True)
        improved = False
        for worst, tid in violators:
            trips = _team_road_trips(tid, entries, team_idx)
            viol = [(a, b) for a, b in trips if b - a + 1 > away_limit]
            if not viol:
                continue
            a, b = max(viol, key=lambda ab: ab[1] - ab[0])
            my = team_idx[tid]
            away_in = [i for i in my
                       if entries[i].away == tid
                       and not (entries[i].start_day > b
                                or entries[i].start_day + entries[i].length - 1 < a)]
            home_out = [i for i in my
                        if entries[i].home == tid
                        and (entries[i].start_day > b
                             or entries[i].start_day + entries[i].length - 1 < a)]
            done = False
            # --- Strategie 1: Swap away-in <-> home-out (gleiche Laenge) ---
            for ai in away_in:
                for hi in home_out:
                    if entries[ai].length != entries[hi].length:
                        continue
                    # Partner-Teams und deren Vor-Swap-Worst merken
                    partners = {entries[ai].home, entries[hi].away}
                    partners.discard(tid)
                    pre = {p: _team_worst_trip(p, entries, team_idx) for p in partners}
                    sa, sh = entries[ai].start_day, entries[hi].start_day
                    entries[ai].start_day, entries[hi].start_day = sh, sa
                    ok_overlap = (_no_team_overlap(entries, team_idx, ai)
                                  and _no_team_overlap(entries, team_idx, hi))
                    new_self = _team_worst_trip(tid, entries, team_idx)
                    # keine neue Partner-Verletzung erzeugen
                    ok_partners = all(
                        _team_worst_trip(p, entries, team_idx) <= max(away_limit, pre[p])
                        for p in partners
                    )
                    ok_bo = (_bo_ok(blackout, entries[ai].home, sh, entries[ai].length)
                             and _bo_ok(blackout, entries[hi].home, sa, entries[hi].length))
                    if ok_overlap and ok_bo and new_self < worst and ok_partners:
                        applied += 1
                        improved = True
                        done = True
                        break
                    # sonst zuruecknehmen
                    entries[ai].start_day, entries[hi].start_day = sa, sh
                if done:
                    break
            if done:
                continue
            # --- Strategie 2: Relocate einer Heimserie in eine Luecke des Trips ---
            # Nur 2 Teams (tid + Gegner) muessen frei sein -> hoehere Trefferquote
            # als der 4-Team-Swap. Bricht den Trip durch einen Heimtag in der Mitte.
            home_all = [i for i in my if entries[i].home == tid]
            for hi in home_all:
                L = entries[hi].length
                cand = valid_starts.get(L) if valid_starts else None
                # Zielfenster: vollstaendig innerhalb [a, b]
                lo, hi_day = a, b - L + 1
                if cand is not None:
                    targets = sorted(d for d in cand if lo <= d <= hi_day)
                else:
                    targets = list(range(lo, hi_day + 1))
                # Heim-Blackout (home_blackout_days) respektieren.
                targets = [d for d in targets
                           if _bo_ok(blackout, entries[hi].home, d, L)]
                old = entries[hi].start_day
                placed = False
                partners = {entries[hi].away}
                pre = {p: _team_worst_trip(p, entries, team_idx) for p in partners}
                # AC-2.1.9-Wert (no_off) der betroffenen Teams VOR dem Move,
                # damit das Relocate nicht ein Constraint gegen das andere tauscht.
                pre_off = {p: _team_max_streaks(p, entries, team_idx)[1]
                           for p in (partners | {tid})}
                for sd in targets:
                    if sd == old:
                        continue
                    entries[hi].start_day = sd
                    self_away, self_off = _team_max_streaks(tid, entries, team_idx)
                    if (_no_team_overlap(entries, team_idx, hi)
                            and self_away < worst
                            and self_off <= max(off_limit, pre_off[tid])
                            and all(_team_worst_trip(p, entries, team_idx)
                                    <= max(away_limit, pre[p]) for p in partners)
                            and all(_team_max_streaks(p, entries, team_idx)[1]
                                    <= max(off_limit, pre_off[p]) for p in partners)):
                        applied += 1
                        improved = True
                        placed = True
                        break
                    entries[hi].start_day = old
                if placed:
                    done = True
                    break
        if not improved:
            break
    return applied


def _lns_window_repair(entries: List[SeriesEntry],
                       team_idx: Dict[str, List[int]],
                       valid_starts: Dict[int, Set[int]],
                       total_days: int,
                       away_limit: int = 13,
                       off_limit: int = 20,
                       pad: int = 8,
                       solve_time_s: float = 2.5,
                       budget_s: float = 30.0,
                       max_passes: int = 60) -> int:
    """Gefensterter CP-SAT-LNS-Repair fuer AC-2.1.8 (Q10).

    Staerker als `_greedy_fatigue_repair`: statt eines Einzelzugs loest er pro zu
    langem Road-Trip ein kleines CP-SAT-Teilproblem. Vorgehen je verletzendem
    Team `tid` und dessen laengster Verletzer-Trip [a, b]:

    1. Freigeben: alle Serien im Zeitfenster [a-pad, b+pad] (jedes Teams) PLUS
       *alle* Serien von `tid` (auch ausserhalb — sonst ist das Teilproblem oft
       ueber-constrained und infeasible). Alle uebrigen Serien bleiben fix.
    2. NoOverlap pro Team ueber dessen komplette Serienmenge (frei = Variable,
       sonst Konstante) — haelt die globale Feasibility.
    3. Struktureller AC-2.1.8-Gap-Constraint NUR fuer `tid` (dessen Heim-Serien
       ausserhalb des Fensters gehen als Konstanten ein und verankern automatisch
       Opening/Closing). Nur EIN Team zu constrainen bleibt tractable, wo alle 30
       gleichzeitig intraktabel sind.
    4. Stay-Close-Ziel: minimiere die Gesamt-Verschiebung gegenueber dem aktuellen
       (sonst guten) Plan -> minimaler Kollateralschaden bei anderen Teams.

    Akzeptanz ist **global monoton**: ein Fenster-Resultat wird nur uebernommen,
    wenn die Zahl der Teams ueber `away_limit` sinkt (oder bei Gleichstand der
    globale worst), und kein Team `off_limit` (AC-2.1.9) verletzt. Damit
    terminiert das Verfahren und verschlechtert den Plan nie. Serien werden nur
    verschoben (kein Hinzufuegen/Entfernen) -> Matchup-Quoten bleiben exakt.

    WICHTIG: liefert KEINE ≤away_limit-Garantie. Die team-uebergreifende Kopplung
    kann dazu fuehren, dass ein Team nicht ohne Regression eines anderen reparabel
    ist; solche Faelle bleiben offen (siehe docs/Q10_ANALYSE_UND_RECHERCHE.md).
    Deterministisch bei 1-Worker + festem Seed. Gibt die Anzahl uebernommener
    Fenster-Reparaturen zurueck.
    """
    from ortools.sat.python import cp_model
    from .generator import _add_ac_2_1_8_gap_constraints
    import time as _time

    def _global_state() -> Tuple[int, int]:
        worsts = [_team_worst_trip(t, entries, team_idx) for t in team_idx]
        return sum(1 for w in worsts if w > away_limit), (max(worsts) if worsts else 0)

    applied = 0
    tried: Set[Tuple[str, int, int]] = set()
    t_start = _time.perf_counter()
    for _pass in range(max_passes):
        if _time.perf_counter() - t_start > budget_s:
            break
        violators = sorted(
            ((_team_worst_trip(t, entries, team_idx), t) for t in team_idx
             if _team_worst_trip(t, entries, team_idx) > away_limit),
            reverse=True,
        )
        if not violators:
            break
        progressed = False
        for worst, tid in violators:
            if _time.perf_counter() - t_start > budget_s:
                break
            trips = _team_road_trips(tid, entries, team_idx)
            viol = [(a, b) for a, b in trips if b - a + 1 > away_limit]
            if not viol:
                continue
            a, b = max(viol, key=lambda ab: ab[1] - ab[0])
            if (tid, a, b) in tried:
                continue
            tried.add((tid, a, b))

            W0 = max(0, a - pad)
            W1 = min(total_days - 1, b + pad)
            tid_set = set(team_idx[tid])
            free = [i for i, e in enumerate(entries)
                    if (e.start_day >= W0 and e.start_day + e.length - 1 <= W1)
                    or i in tid_set]
            free_set = set(free)
            if not free:
                continue

            m = cp_model.CpModel()
            svar: Dict[int, cp_model.IntVar] = {}
            evar: Dict[int, cp_model.IntVar] = {}
            for i in free:
                e = entries[i]
                in_window = (e.start_day >= W0 and e.start_day + e.length - 1 <= W1)
                if i in tid_set and not in_window:
                    dom = sorted(valid_starts[e.length])
                else:
                    dom = [d for d in valid_starts[e.length] if W0 <= d <= W1 - e.length + 1]
                if not dom:
                    dom = [e.start_day]
                svar[i] = m.NewIntVarFromDomain(cp_model.Domain.FromValues(dom), f"s{i}")
                evar[i] = m.NewIntVar(0, total_days, f"e{i}")
                m.Add(evar[i] == svar[i] + e.length)

            for t, idxs in team_idx.items():
                ivs = []
                for i in idxs:
                    e = entries[i]
                    if i in free_set:
                        ivs.append(m.NewIntervalVar(svar[i], e.length, evar[i], f"iv{i}_{t}"))
                    else:
                        ivs.append(m.NewFixedSizeIntervalVar(e.start_day, e.length, f"fi{i}_{t}"))
                if len(ivs) >= 2:
                    m.AddNoOverlap(ivs)

            home_series: List[Tuple] = []
            for i in team_idx[tid]:
                e = entries[i]
                if e.home != tid:
                    continue
                if i in free_set:
                    home_series.append((svar[i], evar[i], e.length))
                else:
                    home_series.append((m.NewConstant(e.start_day),
                                        m.NewConstant(e.start_day + e.length), e.length))
            _add_ac_2_1_8_gap_constraints(m, {tid: home_series}, total_days,
                                          limit=away_limit)

            devs = []
            for i in free:
                dv = m.NewIntVar(0, total_days, f"dev{i}")
                m.Add(dv >= svar[i] - entries[i].start_day)
                m.Add(dv >= entries[i].start_day - svar[i])
                devs.append(dv)
            m.Minimize(sum(devs))

            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = solve_time_s
            solver.parameters.num_search_workers = 1
            solver.parameters.random_seed = 42
            st = solver.Solve(m)
            if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                continue

            pre_cnt, pre_worst = _global_state()
            pre_off = max(_team_max_streaks(t, entries, team_idx)[1] for t in team_idx)
            saved = {i: entries[i].start_day for i in free}
            for i in free:
                entries[i].start_day = solver.Value(svar[i])
            post_cnt, post_worst = _global_state()
            post_off = max(_team_max_streaks(t, entries, team_idx)[1] for t in team_idx)
            better = (post_cnt < pre_cnt) or (post_cnt == pre_cnt and post_worst < pre_worst)
            if better and post_off <= max(off_limit, pre_off):
                applied += 1
                progressed = True
                break
            for i in free:
                entries[i].start_day = saved[i]
        if not progressed:
            break
    return applied


# ---------------------- Haupt-Optimierer ----------------------

def _team_sched13_violations(team_id: str, entries: List[SeriesEntry],
                             team_idx: Dict[str, List[int]],
                             asb_days: Set[int],
                             max_per_7: int = 2,
                             min_last_67: int = 7,
                             min_last_32: int = 3) -> int:
    """V(C)(13)-Verstoss-Zaehler eines Teams auf Entry-Ebene (Review-Fix P0-2).

    Zaehlung EXAKT in der Granularitaet von schedule_rules.check_offday_
    distribution (eine Meldung je Kategorie und Team, m ∈ {0..3}): (a) 1, wenn
    IRGENDEIN rollierendes 7-Tage-Fenster > ``max_per_7`` Open Days hat (ASB-
    Tage ausgenommen); (b) je 1, wenn ein Spaetsaison-Minimum verfehlt wird
    (≥7 Open Days in den letzten 67 Tagen, ≥3 in den letzten 32 — bezogen auf
    den letzten Spieltag des Teams). Damit gilt: max(0, m − m0) == 0 je Team
    ⇔ das Publish-Gate sieht fuer dieses Team keine NEUE V(C)(13)-Meldung
    (kein Kategorien-Tausch moeglich; frueher zaehlte diese Funktion jedes
    Fenster einzeln und Defizit-HOEHEN — das erlaubte stille Trades zwischen
    Kategorien und brach die Gate-Aequivalenz). Deterministisch, kein RNG."""
    occ: Set[int] = set()
    for ei in team_idx[team_id]:
        e = entries[ei]
        occ.update(range(e.start_day, e.start_day + e.length))
    if not occ:
        return 0
    first, last = min(occ), max(occ)
    span = last - first + 1
    open_flags = [0] * span
    for d in range(first, last + 1):
        if d not in occ and d not in asb_days:
            open_flags[d - first] = 1
    viol = 0
    if span >= 7:
        wsum = sum(open_flags[:7])
        window_bad = wsum > max_per_7
        if not window_bad:
            for s in range(1, span - 6):
                wsum += open_flags[s + 6] - open_flags[s - 1]
                if wsum > max_per_7:
                    window_bad = True
                    break
        if window_bad:
            viol += 1
    n67 = sum(open_flags[max(0, span - 67):])
    n32 = sum(open_flags[max(0, span - 32):])
    if n67 < min_last_67:
        viol += 1
    if n32 < min_last_32:
        viol += 1
    return viol


def optimize_travel(season: Season, teams: List[Team], cfg: GeneratorConfig,
                      opt_cfg: Optional[OptimizerConfig] = None) -> Tuple[Season, OptimizationLog]:
    """SA-Optimierer: minimiert Total-km auf einem bereits feasiblen Plan."""
    # Kein mutables Default-Objekt im Funktionskopf (geteilte Instanz über Aufrufe).
    if opt_cfg is None:
        opt_cfg = OptimizerConfig()
    rng = random.Random(opt_cfg.seed)
    teams_by_id = {t.id: t for t in teams}

    entries = _season_to_entries(season, cfg)
    team_idx = _build_team_index(entries)

    # Edge-Cases: leerer oder trivialer Plan -> nichts zu optimieren.
    if len(entries) == 0:
        return season, OptimizationLog(initial_km=0.0, final_km=0.0,
                                        iterations=0, accepted=0,
                                        rejected_constraint=0,
                                        rejected_temperature=0)
    if len(entries) < 2:
        km = _total_km(entries, team_idx, teams_by_id)
        return season, OptimizationLog(initial_km=km, final_km=km,
                                        iterations=0, accepted=0,
                                        rejected_constraint=0,
                                        rejected_temperature=0)

    # Vorberechnung: zulaessige Start-Tage pro Serien-Laenge
    total_days = (cfg.season_end - cfg.season_start).days + 1
    break_days: Set[int] = set()
    if cfg.all_star_break:
        d = cfg.all_star_break[0]
        while d <= cfg.all_star_break[1]:
            break_days.add((d - cfg.season_start).days)
            d += timedelta(days=1)
    # Sprint A-6 FIX: Wenn enforce_fatigue_constraints=True, hat CP-SAT
    # (Stufe 1) auch die periodischen Break-Days erzwungen — die SA muss sie
    # ebenfalls respektieren, sonst kann sie Serien auf diese Tage schieben und
    # die strukturelle AC-2.1.9-Garantie aushebeln. Frueher uebersehen; siehe
    # test_AC_2_1_9_realer_generator_haelt_off_day_frequenz.
    if cfg.enforce_fatigue_constraints:
        from .generator import _periodic_break_days
        break_days |= _periodic_break_days(total_days, max_gap=21)
    valid_starts: Dict[int, Set[int]] = {}
    for length in {e.length for e in entries}:
        valid_starts[length] = _valid_start_for_length(length, total_days, break_days)

    # Sprint 3 FIX: Die SA-Moves muessen home_blackout_days respektieren (Sprint
    # 2.2 Disruption-Constraint: pro Heim-Team gesperrte Tag-Indizes). valid_starts
    # kodiert nur die Break-Days (laengen-abhaengig), nicht die team-spezifischen
    # Blackouts. Ohne diesen Check kann ein Move ein HEIMSPIEL in ein gesperrtes
    # Fenster schieben (vom Geo-Move ausgeloest; latent auch in SHIFT/SWAP).
    _blackout = cfg.home_blackout_days or {}

    def _start_ok(entry: SeriesEntry, start: int) -> bool:
        """Start zulaessig: Break-Days (valid_starts) UND kein Heim-Blackout."""
        if start not in valid_starts[entry.length]:
            return False
        bl = _blackout.get(entry.home)
        if bl:
            for k in range(entry.length):
                if (start + k) in bl:
                    return False
        return True

    # ---- AC-2.1.8 Pre-Repair (Sprint 2.7) ----
    # Bricht nach der Definitionskorrektur (Review C1) verbliebene zu lange
    # Road-Trips aus dem CP-SAT-Plan auf, bevor die Travel-SA startet. Die SA
    # haelt die Feasibility danach via fatigue_lambda (>= 1e6) aufrecht.
    if cfg.enforce_fatigue_constraints:
        _greedy_fatigue_repair(entries, team_idx, valid_starts,
                               away_limit=opt_cfg.max_consec_away_limit,
                               blackout=_blackout)

    # QA Q3: km inkrementell pflegen (wie optimize_pareto), statt _total_km in
    # jedem SA-Schritt voll ueber alle 30 Teams neu zu rechnen. team_km_state
    # haelt die exakte Per-Team-km; current_km = sum(values()) ist bit-identisch
    # zu _total_km (gleiche Operanden, gleiche dict-Reihenfolge), sodass die
    # SA-Entscheidungen und damit das Ergebnis unveraendert deterministisch
    # bleiben (Bit-Identitaet bei gleichem Seed).
    team_km_state: Dict[str, float] = {
        tid: _team_total_km(tid, entries, team_idx, teams_by_id) for tid in team_idx
    }
    initial_km = sum(team_km_state.values())
    # Initiale Fatigue-Werte fuer alle Teams (Task #15)
    team_fatigue, fatigue_penalty = _initial_team_fatigue(
        entries, team_idx,
        opt_cfg.max_consec_away_limit, opt_cfg.max_games_no_off_limit,
    )
    LAMBDA = opt_cfg.fatigue_lambda

    # ---- Sprint 3 P1-3: optionaler Feasibility-Term (per-Team, inkrementell) ----
    FEAS_LAMBDA = opt_cfg.feas_lambda
    _feas_th = DEFAULT_THRESHOLDS
    if FEAS_LAMBDA > 0.0:
        team_feas, feas_penalty = _initial_team_feasibility(
            entries, team_idx, teams_by_id, cfg.season_start, _feas_th,
            opt_cfg.feas_w_exceeds, opt_cfg.feas_w_tight, opt_cfg.feas_w_ptet,
        )
    else:
        team_feas, feas_penalty = {}, 0.0

    HOLIDAY_LAMBDA = opt_cfg.holiday_lambda

    # ---- Review-Fix P0-2 (2026-06-10): V(C)(13)-Off-Day-Verteilungs-Term ----
    # Per-Team-Verstoss-Zaehler (7-Tage-Fenster + Spaetsaison-Minima), inkrementell
    # wie team_feas gepflegt. Bei sched13_lambda == 0 kein Zusatz-Compute und
    # Zusatzterm exakt 0.0 → bit-identisch zum bisherigen Verhalten.
    SCHED13_LAMBDA = opt_cfg.sched13_lambda
    _s13_asb: Set[int] = set()
    if SCHED13_LAMBDA > 0.0:
        if cfg.all_star_break:
            _d = cfg.all_star_break[0]
            while _d <= cfg.all_star_break[1]:
                _s13_asb.add((_d - cfg.season_start).days)
                _d += timedelta(days=1)
        # ---- Finalisierung Punkt 3: ASB-Fehlbedienungs-Guard ----
        # Wenn der Produktions-Default das verlangt (require_all_star_break),
        # FRUEH abbrechen statt still gegen das falsche V(C)(13)-Modell zu
        # optimieren. Geprueft: ASB gesetzt UND mindestens ein ASB-Tag faellt
        # plausibel ins Saisonfenster (sonst mappt _s13_asb auf nichts).
        if opt_cfg.require_all_star_break:
            _season_len = (cfg.season_end - cfg.season_start).days
            _asb_in_window = any(0 <= d <= _season_len for d in _s13_asb)
            if not cfg.all_star_break or not _asb_in_window:
                raise ValueError(
                    "ASB-Guard (Finalisierung Punkt 3): sched13_lambda>0 mit "
                    "Produktions-Config, aber kein plausibler All-Star-Break im "
                    f"Saisonfenster (all_star_break={cfg.all_star_break!r}, "
                    f"season {cfg.season_start}..{cfg.season_end}). Der "
                    "V(C)(13)-Penalty wuerde gegen ein falsches Modell optimieren "
                    "und still neue Verstoesse erzeugen. Korrekten ASB setzen "
                    "(z. B. src.season.detect_all_star_break) oder den Guard "
                    "bewusst per OptimizerConfig(require_all_star_break=False) "
                    "deaktivieren.")
        team_s13: Dict[str, int] = {
            tid: _team_sched13_violations(tid, entries, team_idx, _s13_asb)
            for tid in team_idx
        }
        # BASELINE-RELATIV: Bestraft wird nur der Anteil UEBER dem Startwert
        # (max(0, m - m0) je Team). Der Warm-Start beginnt auf as-played-Daten,
        # die Artefakt-Verstoesse tragen, die der Optimierer nicht beheben MUSS
        # (Gate-Kriterium = "keine NEUEN Verstoesse", publish_gate). Ein
        # absoluter Penalty wuerde das SA-Budget in Artefakt-Reparatur statt km
        # stecken (gemessen: -1,9 % statt -4,9 % km bei 3M Iter). Auf sauberen
        # Plaenen ist m0 = 0 → identisch zum absoluten Penalty (strikt).
        _s13_base: Dict[str, int] = dict(team_s13)
        s13_penalty = float(sum(max(0, v - _s13_base[t])
                                for t, v in team_s13.items()))
    else:
        team_s13, s13_penalty = {}, 0.0
        _s13_base = {}

    def _energy(km: float, pen: float, feas: float = 0.0, holiday: float = 0.0,
                s13: float = 0.0) -> float:
        # Bei FEAS_LAMBDA/HOLIDAY_LAMBDA/SCHED13_LAMBDA == 0 sind die Zusatzterme
        # 0.0 → fuer positive endliche Energien bit-identisch zur frueheren Formel
        # (x + 0.0 == x), d.h. Default-Verhalten unveraendert deterministisch.
        return (km + LAMBDA * pen + FEAS_LAMBDA * feas + HOLIDAY_LAMBDA * holiday
                + SCHED13_LAMBDA * s13)

    def _recompute_team_s13(team_ids: Tuple[str, ...]) -> float:
        """Aktualisiert team_s13 fuer die betroffenen Teams; gibt NEUE Total-
        V(C)(13)-Penalty (baseline-relativ) zurueck (analog _recompute_team_feas)."""
        nonlocal s13_penalty
        for tid in team_ids:
            base = _s13_base[tid]
            old_p = max(0, team_s13[tid] - base)
            new_m = _team_sched13_violations(tid, entries, team_idx, _s13_asb)
            team_s13[tid] = new_m
            s13_penalty = s13_penalty - old_p + max(0, new_m - base)
        return s13_penalty

    def _restore_team_s13(snapshot: Dict[str, int], old_penalty: float) -> None:
        nonlocal s13_penalty
        for tid, val in snapshot.items():
            team_s13[tid] = val
        s13_penalty = old_penalty

    def _recompute_team_feas(team_ids: Tuple[str, ...]) -> float:
        """Aktualisiert team_feas fuer die betroffenen Teams; gibt NEUE Total-
        Feasibility-Penalty zurueck (analog _recompute_team_fatigue)."""
        nonlocal feas_penalty
        for tid in team_ids:
            old_p = team_feas[tid]
            new_p = _team_feasibility_penalty(
                tid, entries, team_idx, teams_by_id, cfg.season_start, _feas_th,
                opt_cfg.feas_w_exceeds, opt_cfg.feas_w_tight, opt_cfg.feas_w_ptet,
            )
            team_feas[tid] = new_p
            feas_penalty = feas_penalty - old_p + new_p
        return feas_penalty

    def _restore_team_feas(snapshot: Dict[str, float], old_penalty: float) -> None:
        nonlocal feas_penalty
        for tid, val in snapshot.items():
            team_feas[tid] = val
        feas_penalty = old_penalty

    # ---- Sprint 3 P1-3: optionaler Feiertags-Incentive (global, inkrementell) ----
    # Belegungszaehler auf den (wenigen) Feiertagstagen. slate-Tage (league_wide)
    # wollen einen vollen Slate (30 Teams = 2*15 Serien); marquee-Tage wollen ein
    # Marquee-Spiel. Penalty = fehlende Abdeckung. Pro Move werden nur die Zaehler
    # der verschobenen Serie(n) auf den Feiertagstagen aktualisiert (O(#Feiertage)).
    holiday_slate_days: List[int] = []
    holiday_marquee_days: List[int] = []
    series_on_day: Dict[int, int] = {}
    marquee_on_day: Dict[int, int] = {}
    is_marquee_entry: List[bool] = [False] * len(entries)
    holiday_penalty = 0.0
    W_SLATE = opt_cfg.holiday_w_slate
    W_MARQUEE = opt_cfg.holiday_w_marquee

    if HOLIDAY_LAMBDA > 0.0:
        from .holidays import load_holidays
        from .tv_slots import TvSlotConfig
        try:
            _mq = TvSlotConfig.load().marquee_mult
        except Exception:
            def _mq(h, a):  # pragma: no cover - Fallback ohne TV-Slot-Daten
                return 1.0
        for _i, _e in enumerate(entries):
            is_marquee_entry[_i] = _mq(_e.home, _e.away) > 1.0
        for _h in load_holidays(season):
            if _h.on_date is None:
                continue
            di = (_h.on_date - cfg.season_start).days
            if di < 0 or di >= total_days:
                continue
            if _h.kind == "league_wide":
                holiday_slate_days.append(di)
                series_on_day[di] = 0
            elif _h.kind == "marquee_incentive":
                holiday_marquee_days.append(di)
                marquee_on_day[di] = 0
        # Initialbelegung zaehlen
        for _i, _e in enumerate(entries):
            lo, hi = _e.start_day, _e.start_day + _e.length
            for di in holiday_slate_days:
                if lo <= di < hi:
                    series_on_day[di] += 1
            if is_marquee_entry[_i]:
                for di in holiday_marquee_days:
                    if lo <= di < hi:
                        marquee_on_day[di] += 1

    def _holiday_total() -> float:
        p = 0.0
        for di in holiday_slate_days:
            missing = 30 - 2 * series_on_day[di]
            if missing > 0:
                p += W_SLATE * missing
        for di in holiday_marquee_days:
            if marquee_on_day[di] < 1:
                p += W_MARQUEE
        return p

    def _holiday_apply_counters(idx: int, from_start: int, to_start: int) -> None:
        """Aktualisiert die Feiertags-Belegungszaehler, wenn Serie idx von
        from_start nach to_start wandert (nur Feiertagstage betroffen)."""
        e = entries[idx]
        length = e.length
        f_lo, f_hi = from_start, from_start + length
        t_lo, t_hi = to_start, to_start + length
        for di in holiday_slate_days:
            was = f_lo <= di < f_hi
            now = t_lo <= di < t_hi
            if was and not now:
                series_on_day[di] -= 1
            elif now and not was:
                series_on_day[di] += 1
        if is_marquee_entry[idx]:
            for di in holiday_marquee_days:
                was = f_lo <= di < f_hi
                now = t_lo <= di < t_hi
                if was and not now:
                    marquee_on_day[di] -= 1
                elif now and not was:
                    marquee_on_day[di] += 1

    if HOLIDAY_LAMBDA > 0.0:
        holiday_penalty = _holiday_total()

    current_km = initial_km
    current_energy = _energy(current_km, fatigue_penalty, feas_penalty,
                             holiday_penalty, s13_penalty)
    best_km = initial_km
    best_energy = current_energy
    best_starts = [e.start_day for e in entries]

    history: List[float] = [initial_km]
    accepted = rejected_constraint = rejected_temp = 0

    def _affected_teams_for_entry(idx: int) -> Tuple[str, str]:
        """Welche Teams aendern ihre Fatigue, wenn entry idx verschoben wird."""
        e = entries[idx]
        return (e.home, e.away)

    def _recompute_team_fatigue(team_ids: Tuple[str, ...]) -> float:
        """Berechnet die Fatigue-Penalty-Differenz, wenn die genannten Teams
        neu evaluiert werden. Aktualisiert `team_fatigue` und gibt die NEUE
        TOTALE Penalty zurueck.
        """
        nonlocal fatigue_penalty
        for tid in team_ids:
            old_ca, old_no = team_fatigue[tid]
            old_p = _team_fatigue_penalty(
                old_ca, old_no,
                opt_cfg.max_consec_away_limit, opt_cfg.max_games_no_off_limit,
            )
            new_ca, new_no = _team_max_streaks(tid, entries, team_idx)
            new_p = _team_fatigue_penalty(
                new_ca, new_no,
                opt_cfg.max_consec_away_limit, opt_cfg.max_games_no_off_limit,
            )
            team_fatigue[tid] = (new_ca, new_no)
            fatigue_penalty = fatigue_penalty - old_p + new_p
        return fatigue_penalty

    def _restore_team_fatigue(snapshot: Dict[str, Tuple[int, int]],
                                old_penalty: float) -> None:
        """Rollt team_fatigue/fatigue_penalty auf den Snapshot zurueck."""
        nonlocal fatigue_penalty
        for tid, val in snapshot.items():
            team_fatigue[tid] = val
        fatigue_penalty = old_penalty

    def _recompute_team_km(team_ids: Tuple[str, ...]) -> float:
        """Aktualisiert team_km_state fuer die betroffenen Teams und gibt die
        NEUE Total-km zurueck. Die Summe laeuft ueber alle Per-Team-Werte in
        stabiler dict-Reihenfolge — bit-identisch zu `_total_km`.
        """
        for tid in team_ids:
            team_km_state[tid] = _team_total_km(tid, entries, team_idx, teams_by_id)
        return sum(team_km_state.values())

    def _restore_team_km(snapshot: Dict[str, float]) -> None:
        """Rollt team_km_state auf den Snapshot zurueck (nach abgelehntem Move)."""
        for tid, val in snapshot.items():
            team_km_state[tid] = val

    # ---- Sprint 3: Vorberechnung fuer den GEO-Move ----
    # Pro Team die Indizes seiner Auswaerts-Serien (away == team). home/away
    # aendern sich waehrend der SA nicht (nur start_day), daher einmal stabil.
    away_entries_by_team: Dict[str, List[int]] = {
        tid: [i for i in team_idx[tid] if entries[i].away == tid]
        for tid in team_idx
    }
    geo_teams: List[str] = [tid for tid, lst in away_entries_by_team.items()
                            if len(lst) >= 2]

    # Vorberechnung der geografisch naechsten Auswaerts-Partner pro Serie i
    # (Top-K). Gegner/Venues aendern sich nicht waehrend der SA -> einmal statisch.
    # Spart in der heissen Schleife die O(#away)-Distanzsuche je GEO-Move.
    _GEO_TOPK = max(1, opt_cfg.geo_topk)
    nearest_partners: Dict[int, List[int]] = {}
    for _t in geo_teams:
        ae = away_entries_by_team[_t]
        for i in ae:
            ci = teams_by_id[entries[i].home]
            ranked = sorted(
                (j for j in ae if j != i),
                key=lambda j: haversine_km(ci.lat, ci.lon,
                                           teams_by_id[entries[j].home].lat,
                                           teams_by_id[entries[j].home].lon),
            )
            nearest_partners[i] = ranked[:_GEO_TOPK]

    geo_share = opt_cfg.move_mix_geo if geo_teams else 0.0
    # Sprint 4: OROPT-Band liegt zwischen GEO und SHIFT. Bei move_mix_oropt == 0
    # (oder ohne geo_teams) ist oropt_cut == geo_share → das Band ist leer und
    # shift_cut faellt exakt auf die alte Formel zurueck (bit-identische
    # rng-Sequenz und Verzweigung; Default-Determinismus unveraendert).
    oropt_share = opt_cfg.move_mix_oropt if geo_teams else 0.0
    oropt_cut = geo_share + oropt_share
    shift_cut = oropt_cut + (1.0 - oropt_cut) * opt_cfg.move_mix_shift

    def _best_oropt_start(i: int, partners: List[int], old_start: int) -> Optional[int]:
        """Best-Insertion: scannt alle Partner x {davor, danach} und liefert den
        zulaessigen Slot mit der GERINGSTEN Reise des bewegten Teams (entries[i].away).
        Rein lesend bis auf temporaeres Setzen/Zuruecksetzen von start_day; keine
        rng-Nutzung → voll deterministisch. None, wenn kein Slot zulaessig ist."""
        mover = entries[i].away
        best_start: Optional[int] = None
        best_km = float("inf")
        for j in partners:
            for new_start in (entries[j].start_day + entries[j].length,
                              entries[j].start_day - entries[i].length):
                if new_start == old_start:
                    continue
                if not _start_ok(entries[i], new_start):
                    continue
                entries[i].start_day = new_start
                ok = _no_team_overlap(entries, team_idx, i)
                if ok:
                    cand_km = _team_total_km(mover, entries, team_idx, teams_by_id)
                    # Deterministischer Tie-Break: kleinerer Start gewinnt.
                    if cand_km < best_km or (cand_km == best_km
                                             and (best_start is None or new_start < best_start)):
                        best_km = cand_km
                        best_start = new_start
                entries[i].start_day = old_start
        return best_start

    for it in range(opt_cfg.iterations):
        # Temperatur
        progress = it / max(1, opt_cfg.iterations - 1)
        T = opt_cfg.start_temperature * (
            opt_cfg.end_temperature / opt_cfg.start_temperature
        ) ** progress

        # Move waehlen: GEO (Struktur) / SHIFT / SWAP
        move_r = rng.random()
        if move_r < geo_share:
            # GEO: Auswaerts-Serie neben den naechsten Auswaerts-Gegner desselben
            # Teams setzen -> aendert die Road-Trip-Komposition (Geografie-Cluster).
            t = rng.choice(geo_teams)
            i = rng.choice(away_entries_by_team[t])
            partners = nearest_partners.get(i)
            if not partners:
                continue
            j = partners[0] if len(partners) == 1 else rng.choice(partners)
            old_start = entries[i].start_day
            placed = False
            for new_start in (entries[j].start_day + entries[j].length,
                              entries[j].start_day - entries[i].length):
                if new_start == old_start:
                    continue
                if not _start_ok(entries[i], new_start):
                    continue
                entries[i].start_day = new_start
                if _no_team_overlap(entries, team_idx, i):
                    placed = True
                    break
                entries[i].start_day = old_start
            if not placed:
                rejected_constraint += 1
                continue
            # Akzeptanz rein ueber die SA-Energie (km + fatigue_lambda * penalty).
            # Mit fatigue_lambda=1e6 werden Moves, die AC-2.1.8/9 verschlechtern,
            # praktisch nie akzeptiert (dE ~ 1e6, exp(-dE/T) ~ 0); verbessernde
            # Moves bleiben erlaubt. Ein separater harter Guard ist daher unnoetig
            # und wuerde sogar trip-verkuerzende Moves blockieren.
            affected = _affected_teams_for_entry(i)
            _moved = [(i, old_start, entries[i].start_day)]
            old_penalty = fatigue_penalty
            fat_snapshot = {tid: team_fatigue[tid] for tid in affected}
            km_snapshot = {tid: team_km_state[tid] for tid in affected}
            new_penalty = _recompute_team_fatigue(affected)
            new_km = _recompute_team_km(affected)
            if FEAS_LAMBDA > 0.0:
                old_feas = feas_penalty
                feas_snapshot = {tid: team_feas[tid] for tid in affected}
                new_feas = _recompute_team_feas(affected)
            else:
                new_feas = 0.0
            if HOLIDAY_LAMBDA > 0.0:
                for _mi, _ms, _mt in _moved:
                    _holiday_apply_counters(_mi, _ms, _mt)
                new_holiday = _holiday_total()
            else:
                new_holiday = holiday_penalty
            if SCHED13_LAMBDA > 0.0:
                old_s13 = s13_penalty
                s13_snapshot = {tid: team_s13[tid] for tid in affected}
                new_s13 = _recompute_team_s13(affected)
            else:
                new_s13 = 0.0
            new_energy = _energy(new_km, new_penalty, new_feas, new_holiday, new_s13)
            dE = new_energy - current_energy
            if dE < 0 or rng.random() < math.exp(-dE / max(1e-9, T)):
                current_km = new_km
                current_energy = new_energy
                holiday_penalty = new_holiday
                accepted += 1
                if current_energy < best_energy and (
                        SCHED13_LAMBDA <= 0.0 or s13_penalty == 0.0):
                    # Review-Fix P0-2: Mit aktivem V(C)(13)-Term wird nur ein
                    # Zustand OHNE neue Off-Day-Verteilungs-Verstoesse je als
                    # Best-Loesung uebernommen (Gate-Konformitaet des SA-Outputs
                    # per Konstruktion; transiente Verstoesse beim Explorieren
                    # bleiben erlaubt). Bei SCHED13_LAMBDA == 0 exakt die alte
                    # Bedingung → bit-identisch.
                    best_energy = current_energy
                    best_km = current_km
                    best_starts = [e.start_day for e in entries]
            else:
                entries[i].start_day = old_start
                _restore_team_fatigue(fat_snapshot, old_penalty)
                _restore_team_km(km_snapshot)
                if FEAS_LAMBDA > 0.0:
                    _restore_team_feas(feas_snapshot, old_feas)
                if HOLIDAY_LAMBDA > 0.0:
                    for _mi, _ms, _mt in _moved:
                        _holiday_apply_counters(_mi, _mt, _ms)
                if SCHED13_LAMBDA > 0.0:
                    _restore_team_s13(s13_snapshot, old_s13)
                rejected_temp += 1
        elif move_r < oropt_cut:
            # OROPT (Best-Insertion-Geo, Sprint 4): wie GEO eine Auswaerts-Serie
            # neben einen nahen Gegner setzen, aber den km-besten Slot unter ALLEN
            # geo_topk-Partnern x {davor,danach} deterministisch waehlen. Annahme
            # weiter SA-energie-basiert. Single-Entry-Buchhaltung == GEO/SHIFT.
            t = rng.choice(geo_teams)
            i = rng.choice(away_entries_by_team[t])
            partners = nearest_partners.get(i)
            if not partners:
                continue
            old_start = entries[i].start_day
            new_start = _best_oropt_start(i, partners, old_start)
            if new_start is None:
                rejected_constraint += 1
                continue
            entries[i].start_day = new_start
            affected = _affected_teams_for_entry(i)
            _moved = [(i, old_start, entries[i].start_day)]
            old_penalty = fatigue_penalty
            fat_snapshot = {tid: team_fatigue[tid] for tid in affected}
            km_snapshot = {tid: team_km_state[tid] for tid in affected}
            new_penalty = _recompute_team_fatigue(affected)
            new_km = _recompute_team_km(affected)
            if FEAS_LAMBDA > 0.0:
                old_feas = feas_penalty
                feas_snapshot = {tid: team_feas[tid] for tid in affected}
                new_feas = _recompute_team_feas(affected)
            else:
                new_feas = 0.0
            if HOLIDAY_LAMBDA > 0.0:
                for _mi, _ms, _mt in _moved:
                    _holiday_apply_counters(_mi, _ms, _mt)
                new_holiday = _holiday_total()
            else:
                new_holiday = holiday_penalty
            if SCHED13_LAMBDA > 0.0:
                old_s13 = s13_penalty
                s13_snapshot = {tid: team_s13[tid] for tid in affected}
                new_s13 = _recompute_team_s13(affected)
            else:
                new_s13 = 0.0
            new_energy = _energy(new_km, new_penalty, new_feas, new_holiday, new_s13)
            dE = new_energy - current_energy
            if dE < 0 or rng.random() < math.exp(-dE / max(1e-9, T)):
                current_km = new_km
                current_energy = new_energy
                holiday_penalty = new_holiday
                accepted += 1
                if current_energy < best_energy and (
                        SCHED13_LAMBDA <= 0.0 or s13_penalty == 0.0):
                    # Review-Fix P0-2: Mit aktivem V(C)(13)-Term wird nur ein
                    # Zustand OHNE neue Off-Day-Verteilungs-Verstoesse je als
                    # Best-Loesung uebernommen (Gate-Konformitaet des SA-Outputs
                    # per Konstruktion; transiente Verstoesse beim Explorieren
                    # bleiben erlaubt). Bei SCHED13_LAMBDA == 0 exakt die alte
                    # Bedingung → bit-identisch.
                    best_energy = current_energy
                    best_km = current_km
                    best_starts = [e.start_day for e in entries]
            else:
                entries[i].start_day = old_start
                _restore_team_fatigue(fat_snapshot, old_penalty)
                _restore_team_km(km_snapshot)
                if FEAS_LAMBDA > 0.0:
                    _restore_team_feas(feas_snapshot, old_feas)
                if HOLIDAY_LAMBDA > 0.0:
                    for _mi, _ms, _mt in _moved:
                        _holiday_apply_counters(_mi, _mt, _ms)
                if SCHED13_LAMBDA > 0.0:
                    _restore_team_s13(s13_snapshot, old_s13)
                rejected_temp += 1
        elif move_r < shift_cut:
            # SHIFT
            i = rng.randrange(len(entries))
            entry = entries[i]
            old_start = entry.start_day
            delta = rng.randint(-opt_cfg.shift_max_days, opt_cfg.shift_max_days)
            if delta == 0:
                continue
            new_start = old_start + delta
            if not _start_ok(entry, new_start):
                rejected_constraint += 1
                continue
            entry.start_day = new_start
            if not _no_team_overlap(entries, team_idx, i):
                entry.start_day = old_start
                rejected_constraint += 1
                continue
            # Energy = km + Lambda * fatigue
            affected = _affected_teams_for_entry(i)
            _moved = [(i, old_start, entries[i].start_day)]
            old_penalty = fatigue_penalty
            fat_snapshot = {tid: team_fatigue[tid] for tid in affected}
            km_snapshot = {tid: team_km_state[tid] for tid in affected}
            new_penalty = _recompute_team_fatigue(affected)
            new_km = _recompute_team_km(affected)
            if FEAS_LAMBDA > 0.0:
                old_feas = feas_penalty
                feas_snapshot = {tid: team_feas[tid] for tid in affected}
                new_feas = _recompute_team_feas(affected)
            else:
                new_feas = 0.0
            if HOLIDAY_LAMBDA > 0.0:
                for _mi, _ms, _mt in _moved:
                    _holiday_apply_counters(_mi, _ms, _mt)
                new_holiday = _holiday_total()
            else:
                new_holiday = holiday_penalty
            if SCHED13_LAMBDA > 0.0:
                old_s13 = s13_penalty
                s13_snapshot = {tid: team_s13[tid] for tid in affected}
                new_s13 = _recompute_team_s13(affected)
            else:
                new_s13 = 0.0
            new_energy = _energy(new_km, new_penalty, new_feas, new_holiday, new_s13)
            dE = new_energy - current_energy
            if dE < 0 or rng.random() < math.exp(-dE / max(1e-9, T)):
                current_km = new_km
                current_energy = new_energy
                holiday_penalty = new_holiday
                accepted += 1
                if current_energy < best_energy and (
                        SCHED13_LAMBDA <= 0.0 or s13_penalty == 0.0):
                    # Review-Fix P0-2: Mit aktivem V(C)(13)-Term wird nur ein
                    # Zustand OHNE neue Off-Day-Verteilungs-Verstoesse je als
                    # Best-Loesung uebernommen (Gate-Konformitaet des SA-Outputs
                    # per Konstruktion; transiente Verstoesse beim Explorieren
                    # bleiben erlaubt). Bei SCHED13_LAMBDA == 0 exakt die alte
                    # Bedingung → bit-identisch.
                    best_energy = current_energy
                    best_km = current_km
                    best_starts = [e.start_day for e in entries]
            else:
                entry.start_day = old_start
                _restore_team_fatigue(fat_snapshot, old_penalty)
                _restore_team_km(km_snapshot)
                if FEAS_LAMBDA > 0.0:
                    _restore_team_feas(feas_snapshot, old_feas)
                if HOLIDAY_LAMBDA > 0.0:
                    for _mi, _ms, _mt in _moved:
                        _holiday_apply_counters(_mi, _mt, _ms)
                if SCHED13_LAMBDA > 0.0:
                    _restore_team_s13(s13_snapshot, old_s13)
                rejected_temp += 1
        else:
            # SWAP zweier Serien gleicher Laenge
            i, j = rng.sample(range(len(entries)), 2)
            if entries[i].length != entries[j].length:
                continue
            old_i = entries[i].start_day
            old_j = entries[j].start_day
            # Blackout-Check fuer die getauschten Positionen (gleiche Laenge ->
            # Break-Days ok, aber team-spezifische Heim-Blackouts koennen brechen).
            if not (_start_ok(entries[i], old_j) and _start_ok(entries[j], old_i)):
                rejected_constraint += 1
                continue
            entries[i].start_day = old_j
            entries[j].start_day = old_i
            if not (_no_team_overlap(entries, team_idx, i)
                     and _no_team_overlap(entries, team_idx, j)):
                entries[i].start_day = old_i
                entries[j].start_day = old_j
                rejected_constraint += 1
                continue
            affected = tuple(set(_affected_teams_for_entry(i) + _affected_teams_for_entry(j)))
            _moved = [(i, old_i, entries[i].start_day), (j, old_j, entries[j].start_day)]
            old_penalty = fatigue_penalty
            fat_snapshot = {tid: team_fatigue[tid] for tid in affected}
            km_snapshot = {tid: team_km_state[tid] for tid in affected}
            new_penalty = _recompute_team_fatigue(affected)
            new_km = _recompute_team_km(affected)
            if FEAS_LAMBDA > 0.0:
                old_feas = feas_penalty
                feas_snapshot = {tid: team_feas[tid] for tid in affected}
                new_feas = _recompute_team_feas(affected)
            else:
                new_feas = 0.0
            if HOLIDAY_LAMBDA > 0.0:
                for _mi, _ms, _mt in _moved:
                    _holiday_apply_counters(_mi, _ms, _mt)
                new_holiday = _holiday_total()
            else:
                new_holiday = holiday_penalty
            if SCHED13_LAMBDA > 0.0:
                old_s13 = s13_penalty
                s13_snapshot = {tid: team_s13[tid] for tid in affected}
                new_s13 = _recompute_team_s13(affected)
            else:
                new_s13 = 0.0
            new_energy = _energy(new_km, new_penalty, new_feas, new_holiday, new_s13)
            dE = new_energy - current_energy
            if dE < 0 or rng.random() < math.exp(-dE / max(1e-9, T)):
                current_km = new_km
                current_energy = new_energy
                holiday_penalty = new_holiday
                accepted += 1
                if current_energy < best_energy and (
                        SCHED13_LAMBDA <= 0.0 or s13_penalty == 0.0):
                    # Review-Fix P0-2: Mit aktivem V(C)(13)-Term wird nur ein
                    # Zustand OHNE neue Off-Day-Verteilungs-Verstoesse je als
                    # Best-Loesung uebernommen (Gate-Konformitaet des SA-Outputs
                    # per Konstruktion; transiente Verstoesse beim Explorieren
                    # bleiben erlaubt). Bei SCHED13_LAMBDA == 0 exakt die alte
                    # Bedingung → bit-identisch.
                    best_energy = current_energy
                    best_km = current_km
                    best_starts = [e.start_day for e in entries]
            else:
                entries[i].start_day = old_i
                entries[j].start_day = old_j
                _restore_team_fatigue(fat_snapshot, old_penalty)
                _restore_team_km(km_snapshot)
                if FEAS_LAMBDA > 0.0:
                    _restore_team_feas(feas_snapshot, old_feas)
                if HOLIDAY_LAMBDA > 0.0:
                    for _mi, _ms, _mt in _moved:
                        _holiday_apply_counters(_mi, _mt, _ms)
                if SCHED13_LAMBDA > 0.0:
                    _restore_team_s13(s13_snapshot, old_s13)
                rejected_temp += 1

        if it % opt_cfg.log_every == 0:
            history.append(current_km)

    # Beste Lösung anwenden
    for i, e in enumerate(entries):
        e.start_day = best_starts[i]
    # ---- AC-2.1.8 Post-Repair (Sprint 2.7) ----
    # Nach dem SA noch verbliebene zu lange Road-Trips final aufbrechen. Der SA
    # kann durch seine Umordnungen Slots freigemacht haben, die der Pre-Repair
    # noch nicht hatte. Reduziert die Penalty weiter (energie-konsistent, da
    # fatigue_lambda die km-Aenderung dominiert).
    if cfg.enforce_fatigue_constraints:
        _greedy_fatigue_repair(entries, team_idx, valid_starts,
                               away_limit=opt_cfg.max_consec_away_limit,
                               off_limit=opt_cfg.max_games_no_off_limit,
                               blackout=_blackout)
        # ---- Q10: optionaler gefensterter CP-SAT-LNS-Repair ----
        # Geht ueber den Greedy-Repair hinaus (loest pro Trip ein kleines
        # CP-SAT-Teilproblem). Default aus; siehe OptimizerConfig.
        if opt_cfg.enable_lns_ac218_repair:
            _lns_window_repair(entries, team_idx, valid_starts, total_days,
                               away_limit=opt_cfg.max_consec_away_limit,
                               off_limit=opt_cfg.max_games_no_off_limit,
                               pad=opt_cfg.lns_pad,
                               solve_time_s=opt_cfg.lns_solve_time_s,
                               budget_s=opt_cfg.lns_budget_s,
                               max_passes=opt_cfg.lns_max_passes)
        # ---- Sprint 3 P1-2: optionale Day-Night-DH-Verdichtung ----
        # Verdichtet verbliebene zu lange Road-Trips per DH (Spanne −1 je DH).
        # Default aus; matchup-erhaltend, occupancy-schrumpfend → kein Overlap.
        if opt_cfg.enable_dh_compression:
            from .doubleheaders import plan_doubleheaders_for_fatigue
            plan_doubleheaders_for_fatigue(
                entries, team_idx,
                away_limit=opt_cfg.max_consec_away_limit)
        best_km = _total_km(entries, team_idx, teams_by_id)
    optimized = _entries_to_season(entries, cfg, season.all_star_dates)
    log = OptimizationLog(
        initial_km=initial_km,
        final_km=best_km,
        iterations=opt_cfg.iterations,
        accepted=accepted,
        rejected_constraint=rejected_constraint,
        rejected_temperature=rejected_temp,
        history=history,
    )
    return optimized, log


# ============================================================
# Multi-Objective SA (Sprint 2.3b) — optimize_pareto
# ============================================================

@dataclass
class ParetoOptLog:
    """Laufzeit-Log für optimize_pareto."""
    initial_energy: float
    final_energy: float
    initial_bundle_km: float
    final_bundle_km: float
    iterations: int
    accepted: int
    rejected_constraint: int
    rejected_temperature: int
    profile_name: str
    history: List[float] = field(default_factory=list)  # Energie-Verlauf


def optimize_pareto(
    season: Season,
    teams: List[Team],
    cfg: GeneratorConfig,
    profile: "ParetoProfile",
    iterations: int = 3000,
    start_temperature: float = 3_000_000.0,
    end_temperature: float = 100.0,
    shift_max_days: int = 7,
    move_mix_shift: float = 0.6,
    seed: int = 42,
    log_every: int = 500,
    events: Optional[List["LocalEvent"]] = None,
    tv_cfg: Optional["TvSlotConfig"] = None,
    revenue_model=None,
    phase_plan: "Optional[PhasePlan]" = None,
    # ---- Sprint 3 P1-5: Geo-Move + Feasibility/Holiday-Terme (gespiegelt aus
    # optimize_travel). Alle Defaults aus → rng-Sequenz und Energie bit-identisch
    # zum bisherigen Pareto-SA (68 Determinismus-Tests bleiben gruen). ----
    move_mix_geo: float = 0.0,
    geo_topk: int = 2,
    feas_lambda: float = 0.0,
    feas_w_exceeds: float = 1.0,
    feas_w_tight: float = 0.1,
    feas_w_ptet: float = 0.0,
    holiday_lambda: float = 0.0,
    holiday_w_slate: float = 1.0,
    holiday_w_marquee: float = 5.0,
) -> Tuple[Season, "ParetoBundle", ParetoOptLog]:
    """Multi-Objective SA: minimiert ParetoProfile.compute_energy(bundle).

    Inkrementelles State-Management (Sprint 2.3b):
    - Travel (km): per-Team-Update über `_team_total_km()` (~0.3ms/move)
    - Fatigue: per-Team-Update über `_team_max_streaks()` (~0.3ms/move)
    - Revenue: per-Entry-Update via `expected_revenue()` (O(series_length))
    - TV-Score: per-Entry-Update via Slot-Wert-Delta (O(series_length))
    - Event-Friction: per-Entry-Update via Event-Lookup (O(series_length))
    - Off-Day-Variance: einmalig am Anfang und Ende berechnet (ändert sich
      bei SHIFT/SWAP kaum — Spielanzahl pro Team bleibt konstant)

    Gesamt: ~1ms/akzeptierter Move (vs. 44ms ohne Inkrementalität).
    3000 Iter × 30% Accept × 1ms = ~1s pro SA-Lauf, 8 Profile = ~10s.

    Args:
        season:            Startplan (z.B. aus optimize_travel).
        teams:             Alle 30 Teams.
        cfg:               GeneratorConfig (Saison-Fenster etc.).
        profile:           ParetoProfile mit Gewichten für alle 8 Dimensionen.
        iterations:        SA-Iterationen (3000 = production, 1000 = fast test).
        start_temperature: Start-Temperatur in km-Äquivalent-Einheiten.
        end_temperature:   End-Temperatur.
        shift_max_days:    Max. Verschiebung für SHIFT-Moves.
        move_mix_shift:    Anteil SHIFT-Moves (Rest: SWAP).
        seed:              Deterministischer Seed.
        log_every:         Energie-Log-Intervall.
        events:            Lokale Events; None → aus data/local_events.json.
        tv_cfg:            TV-Slot-Config; None → aus data/tv_slots.json.
        revenue_model:     Revenue-Modell; None → aus data/revenue_model.json.

    Returns:
        (optimized_season, final_pareto_bundle, log)
    """
    # `compute_pareto_bundle`, `expected_revenue_raw`, `build_division_rivals`
    # sind seit Sprint A-4 (Audit A18) modulweit importiert.

    rng = random.Random(seed)
    teams_by_id = {t.id: t for t in teams}
    season_start = cfg.season_start

    # ── Lazy-Loading externer Ressourcen (einmalig) ───────────────────
    if events is None:
        from .event_conflicts import load_local_events
        events = load_local_events()
    if tv_cfg is None:
        from .tv_slots import TvSlotConfig
        tv_cfg = TvSlotConfig.load()
    if revenue_model is None:
        from .revenue import RevenueModel
        revenue_model = RevenueModel.load()

    division_rivals = build_division_rivals(teams)

    # Events-Index: pro Team nur relevante (nicht-Stadium-Booking) Events
    events_by_team: Dict[str, list] = {}
    for ev in events:
        if ev.is_stadium_booking():
            continue
        for tid in ev.team_ids:
            events_by_team.setdefault(tid, []).append(ev)

    # ── Entries aufbauen ──────────────────────────────────────────────
    entries = _season_to_entries(season, cfg)
    team_idx = _build_team_index(entries)

    if len(entries) < 2:
        bundle = compute_pareto_bundle(season, teams, events, tv_cfg, revenue_model,
                                        validate_hard_constraints=False)
        e_val = profile.compute_energy(bundle)
        log = ParetoOptLog(initial_energy=e_val, final_energy=e_val,
                           initial_bundle_km=bundle.travel_km,
                           final_bundle_km=bundle.travel_km,
                           iterations=0, accepted=0,
                           rejected_constraint=0, rejected_temperature=0,
                           profile_name=profile.name)
        return season, bundle, log

    # ── Gültige Start-Tage pro Serien-Länge ──────────────────────────
    total_days = (cfg.season_end - cfg.season_start).days + 1
    break_days: Set[int] = set()
    if cfg.all_star_break:
        d = cfg.all_star_break[0]
        while d <= cfg.all_star_break[1]:
            break_days.add((d - cfg.season_start).days)
            d += timedelta(days=1)
    # Sprint A-6 FIX (analog zu optimize_travel): periodische Break-Days aus
    # CP-SAT auch in der Pareto-SA respektieren, sonst kann die SA Serien auf
    # die strukturellen Off-Days verschieben und AC-2.1.9 aushebeln.
    if cfg.enforce_fatigue_constraints:
        from .generator import _periodic_break_days
        break_days |= _periodic_break_days(total_days, max_gap=21)
    valid_starts: Dict[int, Set[int]] = {}
    for length in {e.length for e in entries}:
        valid_starts[length] = _valid_start_for_length(length, total_days, break_days)

    # AC-2.1.8 Pre-Repair (Sprint 2.7) — konsistent mit optimize_travel: bricht
    # zu lange Road-Trips vor dem SA auf, sodass die Pareto-Läufe mit deutlich
    # höherer Wahrscheinlichkeit constraint-freie (is_valid) Pläne liefern.
    # QA Q6: an enforce_fatigue_constraints koppeln (wie optimize_travel) und
    # Limits aus den zentralen AC-Konstanten statt hartkodiert beziehen.
    if cfg.enforce_fatigue_constraints:
        _greedy_fatigue_repair(entries, team_idx, valid_starts,
                               away_limit=AC_2_1_8_MAX_AWAY_STREAK,
                               off_limit=AC_2_1_9_MAX_GAMES)

    # ── Inkrementelle Hilfsfunktionen ─────────────────────────────────
    # Sprint 3: optionale Phasen-Gewichtung. _pm(d, key) liefert den
    # Multiplikator der aktiven Phase(n) am Datum d (1.0 ohne Phasen-Plan).
    # Da die per-Serie-Werte ohnehin pro Tag nach Datum gerechnet werden,
    # bleibt die SA-Inkrementalitaet automatisch konsistent.
    def _pm(d, key: str) -> float:
        return phase_plan.multiplier(d, key) if phase_plan is not None else 1.0

    def _entry_revenue_val(e: SeriesEntry) -> float:
        """Revenue-Summe für eine Serie (Audit A6: ohne Game-Allokation)."""
        total = 0.0
        for off in range(e.length):
            d = season_start + timedelta(days=e.start_day + off)
            total += expected_revenue_raw(
                d, e.home, e.away, 0, revenue_model, division_rivals,
            ) * _pm(d, "revenue")
        return total

    def _entry_tv_val(e: SeriesEntry) -> float:
        """TV-Score-Summe für eine Serie."""
        mult = tv_cfg.marquee_mult(e.home, e.away)
        pp   = tv_cfg.team_pick_prob(e.home)
        total = 0.0
        for off in range(e.length):
            d = season_start + timedelta(days=e.start_day + off)
            wd = d.weekday()
            # Erwartungswert-Modell (C2-Fix, Sprint 2.9): konsistent mit
            # tv_slots.compute_tv_slot_score / expected_slot_value.
            total += tv_cfg.expected_slot_value(wd) * mult * pp * _pm(d, "tv")
        return total

    def _entry_friction_val(e: SeriesEntry) -> float:
        """Event-Friction-Summe für eine Serie (nur Heimspiele)."""
        team_evs = events_by_team.get(e.home, [])
        if not team_evs:
            return 0.0
        total = 0.0
        for off in range(e.length):
            d = season_start + timedelta(days=e.start_day + off)
            for ev in team_evs:
                if ev.covers_date(d):
                    total += ev.severity * _pm(d, "friction")
        return total

    # ── Initialen inkrementellen State aufbauen ───────────────────────
    # Travel
    team_km_state: Dict[str, float] = {
        tid: _team_total_km(tid, entries, team_idx, teams_by_id) for tid in team_idx
    }
    current_km = sum(team_km_state.values())

    # Fatigue (passt direkt zur player_fatigue-Formel)
    team_fat: Dict[str, Tuple[int, int]] = {}
    for tid in team_idx:
        ca, no = _team_max_streaks(tid, entries, team_idx)
        team_fat[tid] = (ca, no)

    # Hard-constraint limits (AC-2.1.8/9) — used for incremental violation count
    _AWAY_LIMIT = AC_2_1_8_MAX_AWAY_STREAK
    _OFF_LIMIT  = AC_2_1_9_MAX_GAMES

    def _fatigue_score_from_state() -> float:
        return (sum(ca * ca for ca, no in team_fat.values())
                + 0.5 * sum(no * no for ca, no in team_fat.values()))

    def _max_away_from_state() -> int:
        return max((ca for ca, no in team_fat.values()), default=0)

    def _cv_from_state() -> int:
        """Zählt Hard-Constraint-Verletzungen (AC-2.1.8/9) aus dem inkrementellen State.

        O(num_teams) — team_fat ist immer aktuell, kein Full-Recompute nötig.
        """
        cv = 0
        for ca, no in team_fat.values():
            if ca > _AWAY_LIMIT:
                cv += 1
            if no > _OFF_LIMIT:
                cv += 1
        return cv

    current_fatigue = _fatigue_score_from_state()
    current_max_away = _max_away_from_state()

    # Revenue / TV / Friction per Entry
    entry_rev  = [_entry_revenue_val(e) for e in entries]
    entry_tv   = [_entry_tv_val(e) for e in entries]
    entry_fric = [_entry_friction_val(e) for e in entries]
    current_revenue  = sum(entry_rev)
    current_tv       = sum(entry_tv)
    current_friction = sum(entry_fric)

    # Off-Day-Varianz (M1, Sprint 2.11): jetzt im SA-Energiefunktional enthalten,
    # damit SA-Energie ≡ profile.compute_energy(bundle).
    # Hinweis: Die Varianz misst die Spieltag-Dichte (Spieltage/Saisonspanne) pro
    # Team. Da SHIFT/SWAP weder Spiele hinzufügen/entfernen noch Doubleheader
    # erzeugen (jede Serie belegt feste, nicht überlappende Tage), ist die
    # Dichte je Team — und damit die Varianz — unter den Moves invariant. Wir
    # berechnen sie daher einmal aus dem Startplan; sie wird zusätzlich alle
    # `_OFF_VAR_REFRESH` Iterationen sicherheitshalber neu berechnet.
    # Audit A18 (Sprint A-4): _compute_off_day_variance ist modulweit importiert.
    _off_var_fn = _compute_off_day_variance
    _team_id_list = [t.id for t in teams]
    current_off_var = _off_var_fn(season, _team_id_list)
    _OFF_VAR_REFRESH = 500

    # ── Sprint 3 P1-5: optionale Feasibility-Penalty (per-Team, wie optimize_travel) ──
    FEAS_LAMBDA = feas_lambda
    _feas_th = DEFAULT_THRESHOLDS
    team_feas: Dict[str, float] = {}
    current_feas = 0.0
    if FEAS_LAMBDA > 0.0:
        for tid in team_idx:
            p = _team_feasibility_penalty(tid, entries, team_idx, teams_by_id,
                                          season_start, _feas_th,
                                          feas_w_exceeds, feas_w_tight, feas_w_ptet)
            team_feas[tid] = p
            current_feas += p

    # ── Sprint 3 P1-5: optionaler Feiertags-Incentive (global, wie optimize_travel) ──
    HOLIDAY_LAMBDA = holiday_lambda
    holiday_slate_days: List[int] = []
    holiday_marquee_days: List[int] = []
    series_on_day: Dict[int, int] = {}
    marquee_on_day: Dict[int, int] = {}
    is_marquee_entry: List[bool] = [False] * len(entries)
    W_SLATE = holiday_w_slate
    W_MARQUEE = holiday_w_marquee
    current_holiday = 0.0
    if HOLIDAY_LAMBDA > 0.0:
        from .holidays import load_holidays
        _mq = tv_cfg.marquee_mult
        for _i, _e in enumerate(entries):
            is_marquee_entry[_i] = _mq(_e.home, _e.away) > 1.0
        for _h in load_holidays(season):
            if _h.on_date is None:
                continue
            di = (_h.on_date - season_start).days
            if di < 0 or di >= total_days:
                continue
            if _h.kind == "league_wide":
                holiday_slate_days.append(di)
                series_on_day[di] = 0
            elif _h.kind == "marquee_incentive":
                holiday_marquee_days.append(di)
                marquee_on_day[di] = 0
        for _i, _e in enumerate(entries):
            lo, hi = _e.start_day, _e.start_day + _e.length
            for di in holiday_slate_days:
                if lo <= di < hi:
                    series_on_day[di] += 1
            if is_marquee_entry[_i]:
                for di in holiday_marquee_days:
                    if lo <= di < hi:
                        marquee_on_day[di] += 1

    def _holiday_total() -> float:
        p = 0.0
        for di in holiday_slate_days:
            missing = 30 - 2 * series_on_day[di]
            if missing > 0:
                p += W_SLATE * missing
        for di in holiday_marquee_days:
            if marquee_on_day[di] < 1:
                p += W_MARQUEE
        return p

    def _holiday_apply_counters(idx: int, from_start: int, to_start: int) -> None:
        e = entries[idx]
        length = e.length
        f_lo, f_hi = from_start, from_start + length
        t_lo, t_hi = to_start, to_start + length
        for di in holiday_slate_days:
            was = f_lo <= di < f_hi
            now = t_lo <= di < t_hi
            if was and not now:
                series_on_day[di] -= 1
            elif now and not was:
                series_on_day[di] += 1
        if is_marquee_entry[idx]:
            for di in holiday_marquee_days:
                was = f_lo <= di < f_hi
                now = t_lo <= di < t_hi
                if was and not now:
                    marquee_on_day[di] -= 1
                elif now and not was:
                    marquee_on_day[di] += 1

    if HOLIDAY_LAMBDA > 0.0:
        current_holiday = _holiday_total()

    # ── Sprint 3 P1-5: optionaler Geo-Move (Struktur-Nachbarschaft) ──
    away_entries_by_team: Dict[str, List[int]] = {}
    geo_teams: List[str] = []
    nearest_partners: Dict[int, List[int]] = {}
    geo_share = 0.0
    if move_mix_geo > 0.0:
        away_entries_by_team = {
            tid: [i for i in team_idx[tid] if entries[i].away == tid]
            for tid in team_idx
        }
        geo_teams = [tid for tid, lst in away_entries_by_team.items() if len(lst) >= 2]
        _GEO_TOPK = max(1, geo_topk)
        for _t in geo_teams:
            ae = away_entries_by_team[_t]
            for i in ae:
                ci = teams_by_id[entries[i].home]
                ranked = sorted(
                    (j for j in ae if j != i),
                    key=lambda j: haversine_km(ci.lat, ci.lon,
                                               teams_by_id[entries[j].home].lat,
                                               teams_by_id[entries[j].home].lon),
                )
                nearest_partners[i] = ranked[:_GEO_TOPK]
        geo_share = move_mix_geo if geo_teams else 0.0
    shift_cut = geo_share + (1.0 - geo_share) * move_mix_shift

    def _energy_from_state() -> float:
        """Berechnet Energie aus inkrementellem State (inkl. off_day_variance).

        Beinhaltet violations_penalty * cv für Hard-Constraint-Verletzungen,
        damit SA valid bleibt (violations_penalty = 1e9 km → faktisch unendlich).
        """
        # P1-5: FEAS_/HOLIDAY_LAMBDA == 0 → Zusatzterme 0.0 → bit-identisch zur
        # bisherigen Energie (x + 0.0 == x).
        return (
            profile.w_travel       * current_km
            + profile.w_revenue    * current_revenue
            + profile.w_fatigue    * current_fatigue
            + profile.w_away_streak * current_max_away
            + profile.w_off_day    * current_off_var
            + profile.w_tv         * current_tv
            + profile.w_friction   * current_friction
            + profile.violations_penalty * _cv_from_state()
            + FEAS_LAMBDA          * current_feas
            + HOLIDAY_LAMBDA       * current_holiday
        )

    current_energy = _energy_from_state()
    best_energy    = current_energy
    best_starts    = [e.start_day for e in entries]
    initial_energy = current_energy
    initial_km     = current_km

    history: List[float] = [current_energy]
    accepted = rejected_constraint = rejected_temp = 0

    # ── SA-Hauptschleife ──────────────────────────────────────────────

    def _apply_shift_update(idx: int, old_s: int) -> None:
        """Inkrementelles Update nach SHIFT/SWAP/GEO von entries[idx].

        P1-5: pflegt zusaetzlich (gegated) die Feasibility-Penalty (per-Team,
        wie Fatigue) und die Feiertags-Belegungszaehler (global). ``old_s`` ist
        die Vor-Move-Position — fuer die Feiertags-Delta-Buchung (von old_s nach
        entries[idx].start_day).
        """
        nonlocal current_km, current_fatigue, current_max_away
        nonlocal current_revenue, current_tv, current_friction
        nonlocal current_feas, current_holiday
        e = entries[idx]
        # Travel
        for tid in (e.home, e.away):
            new_km = _team_total_km(tid, entries, team_idx, teams_by_id)
            current_km += new_km - team_km_state[tid]
            team_km_state[tid] = new_km
        # Fatigue
        new_fat = 0.0
        old_fat = 0.0
        for tid in (e.home, e.away):
            old_ca, old_no = team_fat[tid]
            old_fat += old_ca * old_ca + 0.5 * old_no * old_no
            new_ca, new_no = _team_max_streaks(tid, entries, team_idx)
            team_fat[tid] = (new_ca, new_no)
            new_fat += new_ca * new_ca + 0.5 * new_no * new_no
        current_fatigue += new_fat - old_fat
        current_max_away = _max_away_from_state()
        # Revenue / TV / Friction (N7: je einmal berechnen statt zweimal)
        new_rev, new_tv, new_fric = (_entry_revenue_val(e),
                                     _entry_tv_val(e), _entry_friction_val(e))
        current_revenue  += new_rev  - entry_rev[idx]
        current_tv       += new_tv   - entry_tv[idx]
        current_friction += new_fric - entry_fric[idx]
        entry_rev[idx]  = new_rev
        entry_tv[idx]   = new_tv
        entry_fric[idx] = new_fric
        # P1-5: Feasibility (per-Team) + Feiertage (global), nur wenn aktiv.
        if FEAS_LAMBDA > 0.0:
            for tid in (e.home, e.away):
                old_fp = team_feas[tid]
                new_fp = _team_feasibility_penalty(
                    tid, entries, team_idx, teams_by_id, season_start, _feas_th,
                    feas_w_exceeds, feas_w_tight, feas_w_ptet)
                team_feas[tid] = new_fp
                current_feas += new_fp - old_fp
        if HOLIDAY_LAMBDA > 0.0:
            _holiday_apply_counters(idx, old_s, e.start_day)
            current_holiday = _holiday_total()

    def _revert_shift(idx: int, old_s: int) -> None:
        """Revert-Update nach abgelehntem SHIFT/SWAP/GEO."""
        nonlocal current_km, current_fatigue, current_max_away
        nonlocal current_revenue, current_tv, current_friction
        nonlocal current_feas, current_holiday
        e = entries[idx]
        # P1-5: Feiertags-Zaehler zuruecksetzen, BEVOR start_day zurueckgesetzt
        # wird (von der abgelehnten Position e.start_day zurueck nach old_s).
        if HOLIDAY_LAMBDA > 0.0:
            _holiday_apply_counters(idx, e.start_day, old_s)
        e.start_day = old_s
        for tid in (e.home, e.away):
            new_km = _team_total_km(tid, entries, team_idx, teams_by_id)
            current_km += new_km - team_km_state[tid]
            team_km_state[tid] = new_km
        new_fat = old_fat = 0.0
        for tid in (e.home, e.away):
            old_ca, old_no = team_fat[tid]
            old_fat += old_ca * old_ca + 0.5 * old_no * old_no
            new_ca, new_no = _team_max_streaks(tid, entries, team_idx)
            team_fat[tid] = (new_ca, new_no)
            new_fat += new_ca * new_ca + 0.5 * new_no * new_no
        current_fatigue += new_fat - old_fat
        current_max_away = _max_away_from_state()
        # N7: je einmal berechnen statt zweimal
        new_rev, new_tv, new_fric = (_entry_revenue_val(e),
                                     _entry_tv_val(e), _entry_friction_val(e))
        current_revenue  += new_rev  - entry_rev[idx]
        current_tv       += new_tv   - entry_tv[idx]
        current_friction += new_fric - entry_fric[idx]
        entry_rev[idx]  = new_rev
        entry_tv[idx]   = new_tv
        entry_fric[idx] = new_fric
        # P1-5: Feasibility neu (entries nun wieder auf old_s); Feiertags-Total
        # neu aus den oben zurueckgesetzten Zaehlern.
        if FEAS_LAMBDA > 0.0:
            for tid in (e.home, e.away):
                old_fp = team_feas[tid]
                new_fp = _team_feasibility_penalty(
                    tid, entries, team_idx, teams_by_id, season_start, _feas_th,
                    feas_w_exceeds, feas_w_tight, feas_w_ptet)
                team_feas[tid] = new_fp
                current_feas += new_fp - old_fp
        if HOLIDAY_LAMBDA > 0.0:
            current_holiday = _holiday_total()

    for it in range(iterations):
        progress = it / max(1, iterations - 1)
        T = start_temperature * (end_temperature / start_temperature) ** progress

        # M1-Sicherheitsnetz: Off-Day-Varianz periodisch exakt nachziehen
        # (in der Praxis invariant; falls Doubleheader o.ä. doch auftreten,
        # bleibt die Energie damit konsistent zum finalen Bundle).
        if it > 0 and it % _OFF_VAR_REFRESH == 0:
            _season_now = _entries_to_season(entries, cfg, season.all_star_dates)
            current_off_var = _off_var_fn(_season_now, _team_id_list)
            current_energy = _energy_from_state()

        # P1-5: Ein rng.random() entscheidet GEO/SHIFT/SWAP. Bei geo_share == 0
        # ist shift_cut == move_mix_shift → exakt dieselbe Verzweigung und
        # rng-Sequenz wie zuvor (`if rng.random() < move_mix_shift`).
        move_r = rng.random()
        if move_r < geo_share:
            # ── GEO (Struktur-Move, gespiegelt aus optimize_travel) ──
            t = rng.choice(geo_teams)
            i = rng.choice(away_entries_by_team[t])
            partners = nearest_partners.get(i)
            if not partners:
                continue
            j = partners[0] if len(partners) == 1 else rng.choice(partners)
            old_s = entries[i].start_day
            placed = False
            for new_s in (entries[j].start_day + entries[j].length,
                          entries[j].start_day - entries[i].length):
                if new_s == old_s:
                    continue
                if new_s not in valid_starts[entries[i].length]:
                    continue
                entries[i].start_day = new_s
                if _no_team_overlap(entries, team_idx, i):
                    placed = True
                    break
                entries[i].start_day = old_s
            if not placed:
                rejected_constraint += 1
                continue
            _apply_shift_update(i, old_s)
            new_energy = _energy_from_state()
            dE = new_energy - current_energy
            if dE < 0 or rng.random() < math.exp(-dE / max(1e-9, T)):
                current_energy = new_energy
                accepted += 1
                if current_energy < best_energy:
                    best_energy = current_energy
                    best_starts = [en.start_day for en in entries]
            else:
                _revert_shift(i, old_s)
                rejected_temp += 1
        elif move_r < shift_cut:
            # ── SHIFT ──
            i = rng.randrange(len(entries))
            e = entries[i]
            old_s = e.start_day
            delta = rng.randint(-shift_max_days, shift_max_days)
            if delta == 0:
                continue
            new_s = old_s + delta
            if new_s not in valid_starts[e.length]:
                rejected_constraint += 1
                continue
            e.start_day = new_s
            if not _no_team_overlap(entries, team_idx, i):
                e.start_day = old_s
                rejected_constraint += 1
                continue
            # Inkrementelles Update
            _apply_shift_update(i, old_s)
            new_energy = _energy_from_state()
            dE = new_energy - current_energy
            if dE < 0 or rng.random() < math.exp(-dE / max(1e-9, T)):
                current_energy = new_energy
                accepted += 1
                if current_energy < best_energy:
                    best_energy = current_energy
                    best_starts = [en.start_day for en in entries]
            else:
                _revert_shift(i, old_s)
                rejected_temp += 1

        else:
            # ── SWAP ──
            i, j = rng.sample(range(len(entries)), 2)
            if entries[i].length != entries[j].length:
                continue
            old_i, old_j = entries[i].start_day, entries[j].start_day
            entries[i].start_day = old_j
            entries[j].start_day = old_i
            if not (_no_team_overlap(entries, team_idx, i)
                     and _no_team_overlap(entries, team_idx, j)):
                entries[i].start_day = old_i
                entries[j].start_day = old_j
                rejected_constraint += 1
                continue
            _apply_shift_update(i, old_i)
            _apply_shift_update(j, old_j)
            new_energy = _energy_from_state()
            dE = new_energy - current_energy
            if dE < 0 or rng.random() < math.exp(-dE / max(1e-9, T)):
                current_energy = new_energy
                accepted += 1
                if current_energy < best_energy:
                    best_energy = current_energy
                    best_starts = [en.start_day for en in entries]
            else:
                _revert_shift(i, old_i)
                _revert_shift(j, old_j)
                rejected_temp += 1

        if it % log_every == 0:
            history.append(current_energy)

    # ── Beste Lösung anwenden + finales Bundle berechnen ─────────────
    for i, e in enumerate(entries):
        e.start_day = best_starts[i]
    optimized = _entries_to_season(entries, cfg, season.all_star_dates)
    final_bundle = compute_pareto_bundle(
        optimized, teams, events, tv_cfg, revenue_model,
        validate_hard_constraints=True,
    )

    log = ParetoOptLog(
        initial_energy=initial_energy,
        final_energy=best_energy,
        initial_bundle_km=initial_km,
        final_bundle_km=final_bundle.travel_km,
        iterations=iterations,
        accepted=accepted,
        rejected_constraint=rejected_constraint,
        rejected_temperature=rejected_temp,
        profile_name=profile.name,
        history=history,
    )
    return optimized, final_bundle, log
