"""Sprint 5.1 — Startzeit-Schicht (gegated, deterministisch).

Führt **Startzeiten** als nachgelagerte Modell-Dimension ein, damit die CBA-
Startzeit-Regeln V(C)(6)–(9) hart prüfbar werden und TV-Fenster an Slots
gebunden werden können — **ohne** den deterministischen Reise-Optimierpfad zu
berühren (Design: ``docs/SPRINT_5_1_STARTTIME_DESIGN.md``).

Architektur: reine, deterministische Funktion von (fixierter Plan + Appendix C +
Zeitzonen [+ TV-Pins]). **Kein RNG.** Das Modul wird nur aufgerufen, wenn explizit
gewünscht (Gating) — der Default-Optimierpfad bleibt bit-identisch.

Alle Zeiten sind **Lokalzeit der Spielstadt** als „Minuten nach Mitternacht"
(z. B. 19:00 = 1140). In-Flight-Zeiten kommen ausschließlich aus
``data/appendix_c_travel_times.json`` (Appendix C, Rating A1) — niemals aus dem
Haversine-/Charter-Schätzer (so verlangt es V(C)(8): „All references to
'in-flight time' in this Article V shall be as set forth in Appendix C.").

CBA-Verbatim: ``regulations/CBA_2022-2026_Article_V_Scheduling.md``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .season import Season

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# --- CBA-Konstanten (Lokalzeit-Minuten) ---
NIGHT_START_MIN = 19 * 60          # 7 P.M. — Default-Nachtspiel & V(C)(8)-Basis
DAY_MIN_START_MIN = 13 * 60        # 1 P.M. — V(C)(6) frühestes Tag-Spiel (Noon nur m. Ausnahme)
NOON_MIN = 12 * 60                 # 12 P.M. — Untergrenze der V(C)(6)-Ausnahme
GETAWAY_INFLIGHT_THRESHOLD_MIN = 150   # 2 1/2 h — V(C)(8)-Schwelle
NIGHTDAY_FLOOR_MIN = 17 * 60       # 5 P.M. — V(C)(9)-Untergrenze
NIGHTDAY_PRIOR_NIGHT_MIN = 19 * 60  # 7 P.M. — V(C)(9) „prior evening start ≥ 7 P.M."
SHORT_INFLIGHT_MIN = 90            # 1 1/2 h — V(C)(9)-Ausnahme-Schwelle
# Empirische per-Club First-Pitch-Konvention: nominale 7-PM-Anker, reale
# Erstwuerfe bis ~19:40 (z. B. Braves 19:20, Rays 19:35). Einheitliche Quelle
# fuer V(C)(8)- und TV-Pin-Checks (compliance.py nutzt dieselbe Konstante).
GETAWAY_CONVENTION_TOL_MIN = 40
# --- V(C)(5) (Review-Runde 2, Punkt 3) ---
VC5_LATEST_PRIOR_MIN = 17 * 60     # 5 P.M. — späteste Startzeit vor Day-DH-Folgetag
DAY_DH_FIRST_MAX_MIN = 16 * 60     # erstes DH-Spiel < 16:00 = "day doubleheader"
#   (konsistent mit twi_night_first_min in schedule_rules: Twi-Night ≥ 16:00)

# Internationale / neutrale Spielorte: dort gilt die Heim-Team-Zeitzone NICHT,
# und V(C)(8) (Reisezeit zwischen MLB-Städten) ist nicht anwendbar. Diese Spiele
# werden aus der Startzeit-Analyse ausgeschlossen (Reproduktions-Ehrlichkeit).
NEUTRAL_VENUE_HINTS = (
    "Seoul", "London", "Tokyo", "Mexico", "Monterrey", "San Juan",
    "Williamsport", "Dyersville", "Field of Dreams", "Rickwood", "Bristol",
    "Gocheok", "Sky Dome", "Estadio", "Sydney", "Tokyo Dome", "Centro",
    "Muncy Bank", "BB&T", "Historic",
)


class GameSlot(str, Enum):
    """Startzeit-Slot eines Spiels."""
    DAY = "DAY"            # ~13:00 (Tag-Spiel)
    NIGHT = "NIGHT"        # ~19:00 (Abend-Spiel)
    GETAWAY = "GETAWAY"    # V(C)(8)-begrenzte Abreise-Startzeit
    TV_FIXED = "TV_FIXED"  # netzwerk-gepinnt (ESPN/Apple/FOX)


# ====================================================================
# Appendix-C-Lookup
# ====================================================================

@dataclass(frozen=True)
class AppendixC:
    """In-Flight-Zeiten (Minuten) zwischen MLB-Städten, symmetrisch, Diagonale 0."""
    minutes: Dict[str, Dict[str, int]]
    source: str = "Appendix C (CBA 2022-2026)"

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AppendixC":
        path = path or (DATA_DIR / "appendix_c_travel_times.json")
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        mins = raw["travel_minutes"]
        return cls(minutes={a: dict(row) for a, row in mins.items()},
                   source=raw.get("__meta__", {}).get("source", "Appendix C"))

    def inflight_minutes(self, team_a: str, team_b: str) -> int:
        """In-Flight-Zeit (Minuten) zwischen den Heimstädten zweier Teams."""
        try:
            return self.minutes[team_a][team_b]
        except KeyError as exc:
            raise KeyError(
                f"Appendix C: kein Eintrag für {team_a}<->{team_b}. "
                f"Team-IDs müssen Projekt-IDs sein (z. B. CHC, KCR, SDP, SFG, TBR, WSN)."
            ) from exc


# ====================================================================
# V(C)(8) — Getaway-Formel
# ====================================================================

def getaway_latest_start_min(inflight_min: int) -> int:
    """V(C)(8): späteste Startzeit eines Getaway-Spiels (Lokalzeit-Minuten).

    „… determined by taking the portion of the in-flight time that exceeds
    2 1/2 hours, and subtracting that amount of time from 7 P.M."

    latest = 19:00 − max(0, inflight − 2:30).
    Für Inflight ≤ 2:30 ist die Grenze schlicht 19:00 (keine Verschiebung).
    """
    excess = max(0, inflight_min - GETAWAY_INFLIGHT_THRESHOLD_MIN)
    return NIGHT_START_MIN - excess


def fmt_min(m: Optional[int]) -> str:
    """Minuten-nach-Mitternacht → 'H:MM' (24h)."""
    if m is None:
        return "—"
    h, mm = divmod(int(m) % (24 * 60), 60)
    return f"{h}:{mm:02d}"


# ====================================================================
# Travel-Kontext aus dem (date-level) Plan ableiten
# ====================================================================

@dataclass(frozen=True)
class _DayVenue:
    day: date
    venue_team: str   # Heim-Team-ID = Spielstadt
    is_neutral: bool


def _team_day_sequence(season: Season, team_id: str) -> List[_DayVenue]:
    """Distinkte Spieltage eines Teams mit Spielstadt (Heim-Team-ID)."""
    out: List[_DayVenue] = []
    seen = set()
    for g in season.games_for_team(team_id):
        if g.date in seen:
            continue
        seen.add(g.date)
        neutral = any(h.lower() in (g.venue or "").lower() for h in NEUTRAL_VENUE_HINTS)
        out.append(_DayVenue(day=g.date, venue_team=g.home, is_neutral=neutral))
    return out


@dataclass(frozen=True)
class GetawayContext:
    """Ein Getaway-Spieltag: ein oder beide Clubs reisen zum Folgetag-Spiel weiter.

    ``binding_inflight_min`` = größte erforderliche In-Flight-Zeit der reisenden
    Clubs (bindet die früheste „späteste Startzeit").
    """
    game_date: date
    venue_team: str
    traveling: Tuple[str, ...]          # Clubs, die am Folgetag woanders spielen
    binding_inflight_min: int
    latest_start_min: int


def find_getaway_contexts(
    season: Season,
    appendix_c: AppendixC,
    team_ids: Optional[List[str]] = None,
) -> Dict[Tuple[date, str], GetawayContext]:
    """Identifiziert Getaway-Spieltage (V(C)(8), Bedingung „either Club travels to
    another game the following day").

    Schlüssel: (Spieldatum, Spielstadt=Heim-Team). Pro Tag/Ort kann es 1–2
    reisende Clubs geben; die bindende (längste) In-Flight-Zeit bestimmt
    ``latest_start_min``. Neutrale/internationale Spielorte werden übersprungen.

    Hinweis: Bedingung „visiting Club travels to a home off-day" wird konservativ
    mit erfasst, sofern der Gast am Folgetag an einem anderen Ort (= seinem Heim)
    spielt; reine Off-Day-Reisen ohne Folgetag-Spiel sind selten und werden hier
    bewusst nicht erzwungen (würden die Grenze nur lockern, nie verschärfen).
    """
    if team_ids is None:
        team_ids = sorted({g.home for g in season.games} | {g.away for g in season.games})

    # Pro Team: Spielstadt je Tag, um „reist am Folgetag woanders hin" zu erkennen.
    seqs = {t: _team_day_sequence(season, t) for t in team_ids}

    contexts: Dict[Tuple[date, str], GetawayContext] = {}
    for g in season.games:
        key = (g.date, g.home)
        if key in contexts:
            continue
        if any(h.lower() in (g.venue or "").lower() for h in NEUTRAL_VENUE_HINTS):
            continue
        city = g.home  # Spielstadt
        traveling: Dict[str, int] = {}   # club -> inflight_min
        for club in (g.home, g.away):
            seq = seqs.get(club, [])
            # finde diesen Spieltag in der Team-Sequenz
            idx = next((i for i, dv in enumerate(seq) if dv.day == g.date), None)
            if idx is None:
                continue
            nxt = seq[idx + 1] if idx + 1 < len(seq) else None
            if nxt is not None and nxt.day == g.date + timedelta(days=1):
                # Bedingung „either Club travels to another game the following day"
                if nxt.is_neutral or nxt.venue_team == city:
                    continue  # bleibt am selben Ort → keine Reise
                try:
                    inflight = appendix_c.inflight_minutes(city, nxt.venue_team)
                except KeyError:
                    continue
                traveling[club] = inflight
                continue
            # Review-Runde 2 (Punkt 4): Bedingung „the visiting Club travels to
            # a home off-day". Vorher NICHT erfasst, wenn der Gast am Folgetag
            # gar nicht spielt — der alte Kommentar behauptete, das „lockere
            # nur"; das war VERKEHRT herum: jeder zusätzliche reisende Club
            # kann die bindende Inflight-Zeit nur ERHÖHEN, die späteste
            # Startzeit also nur verschärfen → echte Verstöße blieben
            # unentdeckt. Erfasst: Gast (away), Folgetag offen, nächstes Spiel
            # zu Hause (oder Saisonende) → Rückflug in die Heimstadt.
            if club != g.away or club == city:
                continue
            next_day_open = (nxt is None or nxt.day > g.date + timedelta(days=1))
            goes_home_next = (nxt is None or nxt.venue_team == club)
            if next_day_open and goes_home_next and club != city:
                try:
                    traveling[club] = appendix_c.inflight_minutes(city, club)
                except KeyError:
                    continue
        if not traveling:
            continue
        binding = max(traveling.values())
        contexts[key] = GetawayContext(
            game_date=g.date,
            venue_team=city,
            traveling=tuple(sorted(traveling)),
            binding_inflight_min=binding,
            latest_start_min=getaway_latest_start_min(binding),
        )
    return contexts


# ====================================================================
# Zuweisung (deterministisch, gegated)
# ====================================================================

@dataclass(frozen=True)
class StartTimeAssignment:
    game_pk: int
    game_date: date
    home: str
    away: str
    slot: GameSlot
    local_start_min: int
    reason: str


def assign_start_times(
    season: Season,
    appendix_c: AppendixC,
    *,
    team_ids: Optional[List[str]] = None,
    tv_pins: Optional[Dict[int, int]] = None,
    default_day_pks: Optional[set] = None,
) -> Dict[int, StartTimeAssignment]:
    """Deterministische Slot-/Startzeit-Zuweisung über den (fixierten) Plan.

    Regeln (deterministisch, kein RNG):
      1. TV-Pin vorhanden  → ``TV_FIXED`` mit gepinnter Zeit (hart, FORK 1).
      2. Getaway-Spieltag  → ``GETAWAY`` mit der V(C)(8)-spätesten Startzeit
         (= maximal zulässig; der Optimierer darf nur früher ansetzen).
      3. in ``default_day_pks`` → ``DAY`` (13:00).
      4. sonst             → ``NIGHT`` (19:00).

    Die Zuweisung ändert **nichts** am Plan und wird nur auf Anforderung erzeugt
    (Gating). ``tv_pins``/``default_day_pks`` sind optional (Daten aus 5.3/C2).
    """
    tv_pins = tv_pins or {}
    default_day_pks = default_day_pks or set()
    contexts = find_getaway_contexts(season, appendix_c, team_ids)

    # Review-Runde 2 (Punkt 3): Doubleheader-Politik des Zuweisers — erstes
    # DH-Spiel = DAY (13:00), zweites = NIGHT (19:00) (Day-Night-DH, der
    # MLB-übliche Makeup-Modus). Damit ist jeder zugewiesene DH ein DAY-DH im
    # Sinne von V(C)(5) (erstes Spiel < 16:00) → V(C)(5) wird unten als Cap
    # auf die Vortags-Spiele beider Clubs durchgesetzt.
    dh_clubs_by_day: Dict[date, set] = {}
    for g in season.games:
        if g.doubleheader_seq > 0:
            dh_clubs_by_day.setdefault(g.date, set()).update((g.home, g.away))

    out: Dict[int, StartTimeAssignment] = {}
    for g in sorted(season.games, key=lambda x: (x.date, x.home, x.game_pk)):
        if g.game_pk in tv_pins:
            out[g.game_pk] = StartTimeAssignment(
                g.game_pk, g.date, g.home, g.away, GameSlot.TV_FIXED,
                tv_pins[g.game_pk], "TV-Pin (Netzwerk-Fenster, hart)")
            continue
        if g.doubleheader_seq == 1:
            ctx = contexts.get((g.date, g.home))
            start = DAY_MIN_START_MIN
            note = "Day-Night-DH: Spiel 1 (13:00)"
            if ctx is not None and ctx.latest_start_min < start:
                start = ctx.latest_start_min
                note += f" | V(C)(8)-Cap {fmt_min(start)}"
            out[g.game_pk] = StartTimeAssignment(
                g.game_pk, g.date, g.home, g.away, GameSlot.DAY, start, note)
            continue
        if g.doubleheader_seq == 2:
            # V(C)(8) gilt auch fuer das zweite DH-Spiel eines Getaway-Tags:
            # Start = min(19:00, spaeteste zulaessige Getaway-Zeit).
            ctx = contexts.get((g.date, g.home))
            start = NIGHT_START_MIN
            note = "Day-Night-DH: Spiel 2 (19:00)"
            if ctx is not None and ctx.latest_start_min < start:
                start = ctx.latest_start_min
                note += f" | V(C)(8)-Cap {fmt_min(start)}"
            out[g.game_pk] = StartTimeAssignment(
                g.game_pk, g.date, g.home, g.away, GameSlot.NIGHT, start, note)
            continue
        ctx = contexts.get((g.date, g.home))
        if ctx is not None:
            out[g.game_pk] = StartTimeAssignment(
                g.game_pk, g.date, g.home, g.away, GameSlot.GETAWAY,
                ctx.latest_start_min,
                f"Getaway V(C)(8): inflight {fmt_min(ctx.binding_inflight_min)} "
                f"→ latest {fmt_min(ctx.latest_start_min)} "
                f"(reist: {','.join(ctx.traveling)})")
            continue
        if g.game_pk in default_day_pks:
            out[g.game_pk] = StartTimeAssignment(
                g.game_pk, g.date, g.home, g.away, GameSlot.DAY,
                DAY_MIN_START_MIN, "Tag-Spiel (Default 13:00)")
            continue
        out[g.game_pk] = StartTimeAssignment(
            g.game_pk, g.date, g.home, g.away, GameSlot.NIGHT,
            NIGHT_START_MIN, "Nacht-Spiel (Default 19:00)")

    # ---- V(C)(5)-Durchsetzung (Review-Runde 2, Punkt 3): "a game will not be
    # scheduled to start after 5 P.M. if either Club is scheduled to play a day
    # doubleheader the next day". Cap auf 17:00 für alle Nicht-TV-Spiele am
    # Vortag eines Day-DHs (DH-Spiel-1 ist per Politik oben immer DAY).
    # TV-Pins werden NICHT überschrieben (harte Netzwerk-Fenster) — ein
    # V(C)(5)-Konflikt mit einem Pin bleibt sichtbar (Validator flaggt ihn).
    for g in season.games:
        nxt_clubs = dh_clubs_by_day.get(g.date + timedelta(days=1))
        if not nxt_clubs or (g.home not in nxt_clubs and g.away not in nxt_clubs):
            continue
        asg = out.get(g.game_pk)
        if asg is None or asg.slot is GameSlot.TV_FIXED:
            continue
        if asg.local_start_min > VC5_LATEST_PRIOR_MIN:
            out[g.game_pk] = StartTimeAssignment(
                g.game_pk, g.date, g.home, g.away, asg.slot,
                VC5_LATEST_PRIOR_MIN,
                asg.reason + " | V(C)(5)-Cap 17:00 (Day-DH am Folgetag)")
    return out


# ====================================================================
# Validierung gegen zugewiesene/echte Startzeiten
# ====================================================================

@dataclass(frozen=True)
class StartTimeViolation:
    rule: str          # "V(C)(8)" | "V(C)(9)" | "V(C)(6)"
    game_pk: int
    game_date: date
    venue_team: str
    detail: str


def validate_getaway_times(
    season: Season,
    start_min: Dict[int, int],
    appendix_c: AppendixC,
    *,
    team_ids: Optional[List[str]] = None,
    espn_snb_pks: Optional[set] = None,
    rescheduled_pks: Optional[set] = None,
    tolerance_min: int = 0,
) -> List[StartTimeViolation]:
    """V(C)(8): kein Getaway-Spiel startet nach der spätesten zulässigen Zeit.

    ``start_min``: game_pk → Lokal-Startminute (echt oder zugewiesen). Spiele ohne
    Startzeit werden übersprungen (skip/inherit). ESPN-Sunday-Night- und
    Reschedule-Spiele sind laut V(C)(8) ausgenommen.
    """
    espn_snb_pks = espn_snb_pks or set()
    rescheduled_pks = rescheduled_pks or set()
    contexts = find_getaway_contexts(season, appendix_c, team_ids)
    by_key_games: Dict[Tuple[date, str], List] = {}
    for g in season.games:
        by_key_games.setdefault((g.date, g.home), []).append(g)

    viols: List[StartTimeViolation] = []
    for key, ctx in contexts.items():
        for g in by_key_games.get(key, []):
            if g.game_pk in espn_snb_pks or g.game_pk in rescheduled_pks:
                continue
            s = start_min.get(g.game_pk)
            if s is None:
                continue
            if s > ctx.latest_start_min + tolerance_min:
                viols.append(StartTimeViolation(
                    rule="V(C)(8)", game_pk=g.game_pk, game_date=g.date,
                    venue_team=g.home,
                    detail=(f"Start {fmt_min(s)} > latest {fmt_min(ctx.latest_start_min)} "
                            f"(inflight {fmt_min(ctx.binding_inflight_min)}, "
                            f"reist: {','.join(ctx.traveling)})")))
    return viols


def detect_home_openers(season: Season) -> set:
    """game_pk des ersten Heimspiels jedes Teams (Home-Opener, V(C)(9)-Ausnahme)."""
    first: Dict[str, Tuple[date, int]] = {}
    for g in season.games:
        key = (g.date, g.game_pk)
        cur = first.get(g.home)
        if cur is None or key < cur:
            first[g.home] = key
    return {pk for (_, pk) in first.values()}


def holiday_dates_for(season: Season) -> set:
    """Konkrete Feiertagsdaten der Saison (für V(C)(9)-Ausnahme) aus
    ``data/holiday_pins.json`` via ``src.holidays.load_holidays``."""
    from .holidays import load_holidays
    return {h.on_date for h in load_holidays(season) if h.on_date is not None}


def validate_nightday_times(
    season: Season,
    start_min: Dict[int, int],
    appendix_c: AppendixC,
    teams_by_id,
    *,
    team_ids: Optional[List[str]] = None,
    holiday_dates: Optional[set] = None,
    home_opener_pks: Optional[set] = None,
    rescheduled_pks: Optional[set] = None,
    convention_tol_min: int = 0,
) -> List[StartTimeViolation]:
    """V(C)(9): kein Start vor 17:00, wenn ein Club am Vorabend in einer ANDEREN
    Stadt ein Spiel mit Start ≥ 19:00 hatte.

    Ausnahmen (CBA): (a) inflight ≤ 1:30 und Tag-Spiel ist Feiertag/Home-Opener;
    (b) bis zu 6×/Saison Reise nach Chicago zu den Cubs; (c) Reschedule mit
    inflight ≤ 1:30. (b)/(c) werden konservativ als Ausnahme akzeptiert, wenn die
    Bedingung (Ziel CHC bzw. reschedule+short) zutrifft.
    """
    holiday_dates = holiday_dates or set()
    home_opener_pks = home_opener_pks or set()
    rescheduled_pks = rescheduled_pks or set()
    if team_ids is None:
        team_ids = sorted({g.home for g in season.games} | {g.away for g in season.games})

    # Pro Team: Datum -> (Spielstadt, früheste Startminute des Vorabends)
    prev_by_team: Dict[str, Dict[date, Tuple[str, Optional[int]]]] = {}
    for t in team_ids:
        seq = season.games_for_team(t)
        day_city: Dict[date, str] = {}
        day_latest: Dict[date, Optional[int]] = {}
        for g in seq:
            day_city.setdefault(g.date, g.home)
            s = start_min.get(g.game_pk)
            if s is not None:
                cur = day_latest.get(g.date)
                day_latest[g.date] = s if cur is None else max(cur, s)
        prev_by_team[t] = {d: (day_city[d], day_latest.get(d)) for d in day_city}

    viols: List[StartTimeViolation] = []
    cubs_exception_used = 0
    for g in season.games:
        s = start_min.get(g.game_pk)
        if s is None or s >= NIGHTDAY_FLOOR_MIN:
            continue  # nur Tag-Spiele vor 17:00 betroffen
        yest = g.date - timedelta(days=1)
        for club in (g.home, g.away):
            info = prev_by_team.get(club, {}).get(yest)
            if not info:
                continue
            prev_city, prev_start = info
            if prev_start is None or prev_start < NIGHTDAY_PRIOR_NIGHT_MIN:
                continue  # Vorabend kein ≥19:00-Spiel
            if prev_city == g.home:
                continue  # selbe Stadt → keine Reise
            try:
                inflight = appendix_c.inflight_minutes(prev_city, g.home)
            except KeyError:
                continue
            # Ausnahmen
            is_holiday = g.date in holiday_dates
            is_opener = g.game_pk in home_opener_pks
            if inflight <= SHORT_INFLIGHT_MIN and (is_holiday or is_opener):
                continue
            if g.game_pk in rescheduled_pks and inflight <= SHORT_INFLIGHT_MIN:
                continue
            if g.home == "CHC" and club == g.away and cubs_exception_used < 6:
                cubs_exception_used += 1
                continue
            if s + convention_tol_min < NIGHTDAY_FLOOR_MIN:
                viols.append(StartTimeViolation(
                    rule="V(C)(9)", game_pk=g.game_pk, game_date=g.date,
                    venue_team=g.home,
                    detail=(f"Start {fmt_min(s)} < 17:00; {club} spielte {yest} in "
                            f"{prev_city} um {fmt_min(prev_start)} (≥19:00); "
                            f"inflight {fmt_min(inflight)}")))
                break
    return viols


def validate_day_min_times(
    season: Season,
    start_min: Dict[int, int],
    *,
    day_threshold_min: int = NIGHTDAY_FLOOR_MIN,
) -> List[StartTimeViolation]:
    """V(C)(6): Tag-Spiele nicht vor 13:00; 12:00–13:00 nur mit Ausnahme
    (Off-Day am Vortag ODER Spiel in derselben Stadt in den letzten 24 h).

    Ein „Tag-Spiel" wird operativ als Start < ``day_threshold_min`` (17:00)
    klassifiziert. Verstoß = Start < 12:00 (immer) ODER 12:00–13:00 ohne erfüllte
    Ausnahme.
    """
    viols: List[StartTimeViolation] = []
    # je Team: Spieltage (für Off-Day-/Same-City-Ausnahme)
    teams = sorted({g.home for g in season.games} | {g.away for g in season.games})
    seqs = {t: _team_day_sequence(season, t) for t in teams}
    for g in season.games:
        s = start_min.get(g.game_pk)
        if s is None or s >= day_threshold_min:
            continue
        if s < NOON_MIN:
            viols.append(StartTimeViolation(
                rule="V(C)(6)", game_pk=g.game_pk, game_date=g.date,
                venue_team=g.home, detail=f"Tag-Spiel-Start {fmt_min(s)} < 12:00"))
            continue
        if s < DAY_MIN_START_MIN:
            # 12:00–13:00 → braucht Ausnahme für BEIDE Clubs
            ok = True
            for club in (g.home, g.away):
                seq = seqs.get(club, [])
                idx = next((i for i, dv in enumerate(seq) if dv.day == g.date), None)
                if idx is None:
                    ok = False
                    break
                prev = seq[idx - 1] if idx > 0 else None
                off_day_prev = (prev is None) or (g.date - prev.day).days >= 2
                same_city_24h = (prev is not None and prev.day == g.date - timedelta(days=1)
                                 and prev.venue_team == g.home)
                if not (off_day_prev or same_city_24h):
                    ok = False
                    break
            if not ok:
                viols.append(StartTimeViolation(
                    rule="V(C)(6)", game_pk=g.game_pk, game_date=g.date,
                    venue_team=g.home,
                    detail=f"Start {fmt_min(s)} in 12:00–13:00 ohne Off-Day/Same-City-Ausnahme"))
    return viols


# ====================================================================
# Echte Startzeiten aus dem MLB-Stats-API-JSON extrahieren (für Messung)
# ====================================================================

def build_tv_pins(season: Season, broadcasts_path: Path,
                  real_start_min: Dict[int, int]) -> Dict[int, int]:
    """TV-Pins (game_pk → Startminute) für Spiele mit NATIONALEM TV
    (Nacht-Härtung 2026-06-11, P1-7: von Validierung zu Constraint).

    Quelle: ``data/mlb_broadcasts_<jahr>.json`` (Fakten, Rating A) × reale
    Startzeiten — d. h. die vertraglich gesendeten nationalen Fenster werden
    als HARTE Pins in ``assign_start_times(tv_pins=…)`` gereicht. Für künftige
    Saisons ersetzen Broadcaster-Vertragsfenster die realen Zeiten (C2-Ausbau).
    Deterministisch; leeres Dict, wenn keine Fakten-Datei existiert."""
    p = Path(broadcasts_path)
    if not p.exists():
        return {}
    payload = json.loads(p.read_text(encoding="utf-8"))
    national = {int(k) for k in payload.get("national_tv_by_game_pk", {})}
    return {g.game_pk: real_start_min[g.game_pk]
            for g in season.games
            if g.game_pk in national and g.game_pk in real_start_min}


def validate_tv_pins(season: Season, start_min: Dict[int, int],
                     tv_pins: Dict[int, int], appendix_c: "AppendixC",
                     *, espn_snb_pks: Optional[set] = None,
                     rescheduled_pks: Optional[set] = None) -> List[StartTimeViolation]:
    """Erzwingungs-Check für TV-Pins (P1-7):

    1. **Pin-Treue:** jede zugewiesene Zeit eines gepinnten Spiels muss EXAKT
       der Pin-Zeit entsprechen (Netzwerk-Fenster sind vertraglich hart).
    2. **Pin-CBA-Konflikte:** ein Pin, der V(C)(8) (Getaway-Grenze; SNB/
       Reschedules ausgenommen) oder V(C)(5) (Spätstart vor Day-DH) bricht,
       wird als Konflikt gemeldet — das ist die Planungs-Information, die ein
       Scheduler VOR der Vertragsfixierung braucht."""
    espn_snb_pks = espn_snb_pks or set()
    rescheduled_pks = rescheduled_pks or set()
    viols: List[StartTimeViolation] = []
    by_pk = {g.game_pk: g for g in season.games}
    # 1) Pin-Treue
    for pk, pinned in sorted(tv_pins.items()):
        got = start_min.get(pk)
        g = by_pk.get(pk)
        if g is None:
            continue
        if got != pinned:
            viols.append(StartTimeViolation(
                rule="TV-PIN", game_pk=pk, game_date=g.date, venue_team=g.home,
                detail=f"Pin {fmt_min(pinned)} nicht übernommen "
                       f"(zugewiesen: {fmt_min(got)})"))
    # 2) Pin vs. V(C)(8)-Getaway-Grenze — mit derselben ±40-min-First-Pitch-
    # Konvention wie STARTTIME-GETAWAY (nominale 7-PM-Anker, reale Erstwuerfe
    # 19:05-19:40; ohne Toleranz waeren 19:05-Pins falsch-positive Konflikte).
    contexts = find_getaway_contexts(season, appendix_c)
    for pk, pinned in sorted(tv_pins.items()):
        g = by_pk.get(pk)
        if g is None or pk in espn_snb_pks or pk in rescheduled_pks:
            continue
        ctx = contexts.get((g.date, g.home))
        if ctx is not None and pinned > ctx.latest_start_min + GETAWAY_CONVENTION_TOL_MIN:
            viols.append(StartTimeViolation(
                rule="TV-PIN/V(C)(8)", game_pk=pk, game_date=g.date,
                venue_team=g.home,
                detail=f"Pin {fmt_min(pinned)} > Getaway-Grenze "
                       f"{fmt_min(ctx.latest_start_min)} — Netzwerk-Fenster "
                       f"kollidiert mit CBA (vor Vertragsfixierung klären)"))
    # 3) Pin vs. V(C)(5) (Spätstart vor Day-DH des Folgetags)
    pinned_min = {pk: m for pk, m in tv_pins.items()}
    merged = dict(start_min); merged.update(pinned_min)
    for v in validate_day_dh_prior_times(season, merged,
                                         rescheduled_pks=rescheduled_pks):
        if v.game_pk in tv_pins:
            viols.append(StartTimeViolation(
                rule="TV-PIN/V(C)(5)", game_pk=v.game_pk, game_date=v.game_date,
                venue_team=v.venue_team, detail="Pin: " + v.detail))
    return viols


def find_day_dh_days(season: Season, start_min: Dict[int, int]) -> Dict[str, set]:
    """Club → Tage, an denen der Club ein DAY-Doubleheader spielt (erstes
    DH-Spiel < 16:00; konsistent mit der Twi-Night-Grenze). V(C)(5)-Hilfe."""
    out: Dict[str, set] = {}
    for g in season.games:
        if g.doubleheader_seq != 1:
            continue
        s = start_min.get(g.game_pk)
        if s is None or s >= DAY_DH_FIRST_MAX_MIN:
            continue
        out.setdefault(g.home, set()).add(g.date)
        out.setdefault(g.away, set()).add(g.date)
    return out


def validate_day_dh_prior_times(
    season: Season,
    start_min: Dict[int, int],
    *,
    rescheduled_pks: Optional[set] = None,
) -> List[StartTimeViolation]:
    """V(C)(5) (Review-Runde 2, Punkt 3): „a game will not be scheduled to
    start after 5 P.M. if either Club is scheduled to play a day doubleheader
    the next day". Day-DH = erstes DH-Spiel < 16:00. Auf as-played-Daten sind
    Folgetag-Day-DHs überwiegend Rainout-Makeups (das VORTAGS-Spiel war beim
    Original-Scheduling regelkonform) → ``rescheduled_pks`` nimmt die
    Makeup-DHs aus der Day-DH-Menge aus; ohne dieses Set ist die Messung
    informativ (as-played-Artefakte), auf zugewiesenen Startzeiten hart."""
    rescheduled_pks = rescheduled_pks or set()
    # Day-DH-Tage, optional ohne Makeup-DHs (Reschedules)
    filtered = {pk: s for pk, s in start_min.items()}
    dh_days_raw = find_day_dh_days(season, filtered)
    if rescheduled_pks:
        resched_dh_keys = set()
        for g in season.games:
            if g.doubleheader_seq > 0 and g.game_pk in rescheduled_pks:
                resched_dh_keys.add((g.date, g.home, g.away))
        dh_days: Dict[str, set] = {}
        for g in season.games:
            if g.doubleheader_seq != 1:
                continue
            if (g.date, g.home, g.away) in resched_dh_keys:
                continue
            s = start_min.get(g.game_pk)
            if s is None or s >= DAY_DH_FIRST_MAX_MIN:
                continue
            dh_days.setdefault(g.home, set()).add(g.date)
            dh_days.setdefault(g.away, set()).add(g.date)
    else:
        dh_days = dh_days_raw
    viols: List[StartTimeViolation] = []
    for g in season.games:
        s = start_min.get(g.game_pk)
        if s is None or s <= VC5_LATEST_PRIOR_MIN:
            continue
        nxt = g.date + timedelta(days=1)
        offenders = [c for c in (g.home, g.away) if nxt in dh_days.get(c, set())]
        if offenders:
            viols.append(StartTimeViolation(
                rule="V(C)(5)", game_pk=g.game_pk, game_date=g.date,
                venue_team=g.home,
                detail=(f"Start {fmt_min(s)} > 17:00, aber {','.join(offenders)} "
                        f"spielt am {nxt} ein Day-Doubleheader")))
    return viols


def load_real_start_times(
    path: Path,
    teams_by_id,
    *,
    game_type: str = "R",
) -> Dict[int, int]:
    """game_pk → Lokal-Startminute aus einem MLB-Stats-API-Schedule-JSON.

    Liest ``gameDate`` (UTC) und konvertiert DST-korrekt in die Lokalzeit der
    **Spielstadt** (Heim-Team). Berührt den Season-Loader nicht (der die Uhrzeit
    verwirft) — eigenständige, schlanke Extraktion für die Reproduktions-Messung.
    Internationale/neutrale Spielorte werden übersprungen (Heim-TZ nicht gültig).
    """
    from zoneinfo import ZoneInfo
    from .loaders import _resolve_team_code

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    PLAYED = {"Final", "Completed Early", "Game Over"}
    out: Dict[int, int] = {}
    for day_entry in raw.get("dates", []):
        for gr in day_entry.get("games", []):
            if gr.get("gameType") != game_type:
                continue
            if (gr.get("status") or {}).get("detailedState", "") not in PLAYED:
                continue
            if gr.get("startTimeTBD"):
                continue
            venue_name = (gr.get("venue") or {}).get("name") or ""
            if any(h.lower() in venue_name.lower() for h in NEUTRAL_VENUE_HINTS):
                continue
            home = _resolve_team_code(gr["teams"]["home"]["team"])
            if not home or home not in teams_by_id:
                continue
            gd = gr.get("gameDate")
            if not gd:
                continue
            try:
                dt_utc = datetime.fromisoformat(gd.replace("Z", "+00:00"))
                local = dt_utc.astimezone(ZoneInfo(teams_by_id[home].timezone))
            except Exception:
                continue
            out[int(gr.get("gamePk", 0))] = local.hour * 60 + local.minute
    return out


def load_exempt_pks(path: Path, teams_by_id, *, game_type: str = "R"):
    """(rescheduled_pks, snb_pks) aus einem MLB-Stats-API-Schedule-JSON.

    Review-Runde 2 (Punkt 4): Mit der vollständigen V(C)(8)-Abdeckung
    (inkl. „visiting Club travels to a home off-day") braucht eine ehrliche
    Messung die im CBA explizit ausgenommenen Spiele:
    - **Reschedules:** ``rescheduledFrom`` gesetzt oder „Makeup"-Description
      (V(C)(8): „… shall not apply to … rescheduled games"). Faktenfeld, exakt.
    - **ESPN Sunday Night Baseball**, dreistufig (C2-Schließung, Runde 3):
      1. ``data/mlb_broadcasts_<jahr>.json`` (volle Saison-Fakten aus
         ``tools/fetch_broadcasts.py``): Sonntag + nationales TV mit
         ESPN-CallSign → FAKT (Rating A).
      2. ``data/mlb_national_tv.json`` (punktuell verifizierte Fakten für
         urteils-relevante Spiele) → FAKT je gelistetem Spiel.
      3. Fallback-HEURISTIK: Sonntag + dayNight=='night' + Start ≥ 18:30 —
         kann Nicht-ESPN-Sonntag-Nachtspiele mit-ausnehmen; nur aktiv, wenn
         keine Fakten-Quelle existiert, und als Heuristik dokumentiert.
    Deterministisch, kein RNG.
    """
    from zoneinfo import ZoneInfo
    from .loaders import _resolve_team_code

    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))

    # --- Fakten-Quellen für nationale TV-Broadcasts (Stufen 1+2) ---
    season_digits = "".join(ch for ch in path.stem if ch.isdigit())
    facts_tv: Dict[int, List[str]] = {}
    facts_complete = False     # True = volle Saison-Fakten (Stufe 1)
    full = path.parent / f"mlb_broadcasts_{season_digits}.json"
    if season_digits and full.exists():
        payload = json.loads(full.read_text(encoding="utf-8"))
        facts_tv = {int(k): v for k, v in
                    payload.get("national_tv_by_game_pk", {}).items()}
        facts_complete = True
    else:
        spot = path.parent / "mlb_national_tv.json"
        if spot.exists():
            payload = json.loads(spot.read_text(encoding="utf-8"))
            facts_tv = {int(k): v.get("national_tv", []) for k, v in
                        payload.get("national_tv_by_game_pk", {}).items()}

    def _is_espn(pk: int) -> Optional[bool]:
        """True/False = Fakt; None = kein Fakt für dieses Spiel vorhanden."""
        if pk in facts_tv:
            return any("ESPN" in str(c).upper() for c in facts_tv[pk])
        if facts_complete:
            return False   # volle Fakten: nicht gelistet ⇒ kein nationales TV
        return None

    resched: set = set()
    snb: set = set()
    for day_entry in raw.get("dates", []):
        for gr in day_entry.get("games", []):
            if gr.get("gameType") != game_type:
                continue
            pk = int(gr.get("gamePk", 0))
            desc = (gr.get("description") or "").lower()
            if gr.get("rescheduledFrom") or "makeup" in desc:
                resched.add(pk)
            home = _resolve_team_code(gr["teams"]["home"]["team"])
            gd = gr.get("gameDate")
            if not home or home not in teams_by_id or not gd:
                continue
            try:
                dt_utc = datetime.fromisoformat(gd.replace("Z", "+00:00"))
                local = dt_utc.astimezone(ZoneInfo(teams_by_id[home].timezone))
            except Exception:
                continue
            if local.weekday() != 6:
                continue   # SNB gibt es nur sonntags
            espn = _is_espn(pk)
            if espn is True:
                snb.add(pk)
            elif espn is None and (gr.get("dayNight") == "night"
                                   and local.hour * 60 + local.minute >= 18 * 60 + 30):
                snb.add(pk)   # Fallback-Heuristik (keine Fakten-Quelle)
    return resched, snb
