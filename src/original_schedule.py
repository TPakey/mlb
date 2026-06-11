"""Originalplan-Quelle (P1-5) — Rekonstruktion + Retrosheet-Goldquelle.

Problem (`finding-as-played-data`): `data/mlb_schedule_*.json` ist **as-played**
(Makeups/Relokationen) — Originalplan-Regeln wie V(C)(13)/(14) waren darauf nie
hart messbar. Dieses Modul liefert den ORIGINALPLAN über zwei Wege:

1. **Rekonstruktion aus statsapi-Feldern (offline, sofort verfügbar):**
   Postponed-Einträge stehen im selben JSON am Originaldatum; Makeup-Spiele
   tragen ``rescheduledFrom``. Jedes Spiel wird auf sein Originaldatum
   zurückgelegt. GRENZEN (ehrlich): (a) Planänderungen VOR Saisonstart sind
   unsichtbar (statsapi zeigt nur den letzten Pre-Season-Stand — z. B. ist die
   Rays-Relokation 2025 nach Steinbrenner Field hier schon "original");
   (b) Suspended/Resumed-Spiele zählen am Startdatum; (c) abgesagte Spiele ohne
   Makeup erscheinen am Originaldatum als geplant. Provenienz-Rating: B
   (faktenbasierte Rekonstruktion, nicht das publizierte Dokument).

2. **Retrosheet-SKED-Dateien (Goldquelle, Rating A):** das publizierte Original
   (retrosheet.org/schedule, frei lizenziert mit Quellenvermerk). Download via
   ``python -m tools.fetch_retrosheet`` (läuft auf dem Entwickler-Rechner;
   die Sandbox kann keine ZIPs transportieren). Liegt die Datei in
   ``data/retrosheet/``, wird sie bevorzugt und gegen die Rekonstruktion
   kreuzvalidiert.

Deterministisch, kein RNG, kein Netz (Loader lesen nur lokale Dateien).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .season import Game, Season

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RETROSHEET_DIR = DATA_DIR / "retrosheet"

# Retrosheet-Team-IDs → Projekt-IDs (Stand 2024/2025; historische Codes nicht
# benötigt). Quelle: retrosheet.org Team-IDs.
RETROSHEET_TO_PROJECT = {
    "ANA": "LAA", "ARI": "ARI", "ATL": "ATL", "BAL": "BAL", "BOS": "BOS",
    "CHA": "CWS", "CHN": "CHC", "CIN": "CIN", "CLE": "CLE", "COL": "COL",
    "DET": "DET", "HOU": "HOU", "KCA": "KCR", "LAN": "LAD", "MIA": "MIA",
    "MIL": "MIL", "MIN": "MIN", "NYA": "NYY", "NYN": "NYM", "OAK": "OAK",
    "PHI": "PHI", "PIT": "PIT", "SDN": "SDP", "SEA": "SEA", "SFN": "SFG",
    "SLN": "STL", "TBA": "TBR", "TEX": "TEX", "TOR": "TOR", "WAS": "WSN",
    # 2025+: Athletics (Sacramento) laufen bei Retrosheet als ATH — gemessen
    # an 2025SKED.TXT (ohne dieses Mapping fehlten alle 162 A's-Spiele).
    "ATH": "OAK",
}

# Retrosheet-Location-Codes (Spalte 11 im 2025+-Format) fuer neutrale/
# internationale Spielorte → Klartext, damit die NEUTRAL_VENUE_HINTS der
# Startzeit-/Getaway-Logik greifen. Nur belegte Codes, bewusst klein.
RETROSHEET_NEUTRAL_PARKS = {
    "TOK01": "Tokyo Dome",
    "LON01": "London Stadium",
    "SEO01": "Gocheok Sky Dome, Seoul",
    "MEX01": "Estadio Alfredo Harp Helu, Mexico City",
    "SJU01": "Hiram Bithorn Stadium, San Juan",
    "WIL01": "Williamsport",
    "BIR01": "Rickwood Field",
    "BRI01": "Bristol",
}


# ====================================================================
# Weg 1 — Rekonstruktion aus dem statsapi-JSON
# ====================================================================

def reconstruct_original_schedule(path: Path, *, season: Optional[int] = None,
                                  game_type: str = "R") -> Season:
    """Originalplan aus einem MLB-Stats-API-Schedule-JSON rekonstruieren.

    Regeln je gamePk:
    - Eintrag mit Status "Postponed"/"Cancelled" am Tag D ⇒ Originaldatum = D.
    - Gespielter Eintrag mit ``rescheduledFrom`` ⇒ Originaldatum = das Datum
      aus ``rescheduledFrom`` (falls kein Postponed-Eintrag existiert).
    - Sonst: Spieldatum = Originaldatum.
    Doppelte gamePk werden auf EINEN Eintrag am Originaldatum dedupliziert
    (Postponed-Eintrag gewinnt, weil er die Original-Metadaten trägt).
    Makeup-Doubleheader sind im Original Einzelspiele → doubleheader_seq aus
    dem ORIGINAL-Eintrag, nicht aus dem Makeup.
    """
    from .loaders import _resolve_team_code

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    POSTPONED = {"Postponed", "Cancelled"}
    # gamePk → (original_date, raw_entry, prio)  prio: 2=Postponed-Eintrag,
    # 1=rescheduledFrom-Rueckrechnung, 0=normal
    chosen: Dict[int, Tuple[date, dict, int]] = {}

    for day_entry in raw.get("dates", []):
        day = date.fromisoformat(day_entry["date"])
        for gr in day_entry.get("games", []):
            if gr.get("gameType") != game_type:
                continue
            pk = int(gr.get("gamePk", 0))
            status = (gr.get("status") or {}).get("detailedState", "")
            if status in POSTPONED:
                orig_day, prio = day, 2
            elif gr.get("rescheduledFrom"):
                try:
                    orig_day = datetime.fromisoformat(
                        gr["rescheduledFrom"].replace("Z", "+00:00")).date()
                except ValueError:
                    orig_day = day
                prio = 1
            else:
                orig_day, prio = day, 0
            prev = chosen.get(pk)
            if prev is None or prio > prev[2]:
                chosen[pk] = (orig_day, gr, prio)

    # DH-Original-Erkennung: Ein Doubleheader ist nur dann ORIGINAL geplant,
    # wenn ALLE Spiele des (Tag, Heim)-Slots prio==0 sind. Sonst ist der DH die
    # FOLGE eines Makeups (das verlegte Spiel traegt rescheduledFrom, aber sein
    # urspruenglich an dem Tag geplanter Partner bekam das doubleHeader-Flag
    # nur dadurch) → im Original waren das Einzelspiele. Ohne diese Korrektur
    # wuerden Makeup-Split-DHs faelschlich als Original-Split-DHs gezaehlt
    # (gemessen: ATL 3x/2024 — real sind das Rainout-Makeups).
    dh_slot_prios: Dict[Tuple[date, str], List[int]] = {}
    for pk, (orig_day, gr, prio) in chosen.items():
        if gr.get("doubleHeader", "N") != "N":
            home = _resolve_team_code(gr["teams"]["home"]["team"])
            if home:
                dh_slot_prios.setdefault((orig_day, home), []).append(prio)

    games: List[Game] = []
    for pk, (orig_day, gr, prio) in chosen.items():
        home = _resolve_team_code(gr["teams"]["home"]["team"])
        away = _resolve_team_code(gr["teams"]["away"]["team"])
        if not home or not away:
            continue
        raw_dh = gr.get("doubleHeader", "N")
        slot_prios = dh_slot_prios.get((orig_day, home), [])
        is_orig_dh = (raw_dh != "N" and prio == 0
                      and len(slot_prios) >= 2
                      and all(p == 0 for p in slot_prios))
        games.append(Game(
            game_pk=pk,
            date=orig_day,
            home=home,
            away=away,
            venue=(gr.get("venue") or {}).get("name") or home,
            doubleheader_seq=int(gr.get("gameNumber", 1)) if is_orig_dh else 0,
            game_type=game_type,
            dh_type=raw_dh if is_orig_dh else "",
        ))

    games.sort(key=lambda g: (g.date, g.doubleheader_seq, g.game_pk))
    yr = season or (games[0].date.year if games else 0)
    return Season(season=yr, games=games,
                  season_start=min(g.date for g in games),
                  season_end=max(g.date for g in games))


# ====================================================================
# Weg 2 — Retrosheet-SKED (Goldquelle, falls vorhanden)
# ====================================================================

def retrosheet_path(year: int) -> Path:
    return RETROSHEET_DIR / f"{year}SKED.TXT"


def has_retrosheet(year: int) -> bool:
    return retrosheet_path(year).exists()


def load_retrosheet_schedule(year: int, *, path: Optional[Path] = None) -> Season:
    """Retrosheet-SKED-Datei → Season (Originalplan, Rating A).

    Format (retrosheet.org/schedule): CSV mit Feldern
    1=yyyymmdd, 2=GameNumber(0/1/2), 3=Wochentag, 4-5=Visitor+Liga,
    6=VisitorGameNr, 7-8=Home+Liga, 9=HomeGameNr, 10=D/N/A/E,
    11=Postponement-Hinweis, 12=Makeup-Datum. Pflicht-Quellenvermerk:
    "The information used here was obtained free of charge from and is
    copyrighted by Retrosheet." (siehe data/retrosheet/README).
    """
    p = path or retrosheet_path(year)
    games: List[Game] = []
    pk = 9_000_000  # synthetische PKs (Retrosheet kennt keine gamePk)
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        fields = [f.strip().strip('"') for f in line.split(",")]
        if len(fields) < 9:
            continue
        try:
            d = datetime.strptime(fields[0], "%Y%m%d").date()
        except ValueError:
            continue  # ueberspringt auch die Header-Zeile des 2025+-Formats
        if d.year != year:
            continue
        dh_num = fields[1]
        away = RETROSHEET_TO_PROJECT.get(fields[3])
        home = RETROSHEET_TO_PROJECT.get(fields[6])
        if not away or not home:
            continue
        # 2025+-Format hat 13 Spalten inkl. Location (Index 10) fuer neutrale
        # Spielorte (z. B. TOK01 = Tokyo-Series); Klassikformat hat 12 ohne.
        venue = home
        if len(fields) >= 13 and fields[10]:
            venue = RETROSHEET_NEUTRAL_PARKS.get(
                fields[10], f"Neutral Site {fields[10]}")
        games.append(Game(
            game_pk=pk, date=d, home=home, away=away, venue=venue,
            doubleheader_seq=int(dh_num) if dh_num in ("1", "2") else 0,
            game_type="R",
        ))
        pk += 1
    if not games:
        raise ValueError(f"Retrosheet-Datei {p} enthielt keine parsebaren Spiele")
    games.sort(key=lambda g: (g.date, g.doubleheader_seq, g.game_pk))
    return Season(season=year, games=games,
                  season_start=min(g.date for g in games),
                  season_end=max(g.date for g in games))


# ====================================================================
# Einheitlicher Einstieg + Kreuzvalidierung
# ====================================================================

def load_original_schedule(year: int) -> Tuple[Season, str]:
    """(Originalplan, Quelle) — Retrosheet (Rating A) falls vorhanden, sonst
    Rekonstruktion (Rating B). Liegt beides vor, wird kreuzvalidiert und bei
    Abweichung laut gewarnt (Doku ≠ stillschweigend)."""
    statsapi = DATA_DIR / f"mlb_schedule_{year}.json"
    recon = (reconstruct_original_schedule(statsapi, season=year)
             if statsapi.exists() else None)
    if has_retrosheet(year):
        retro = load_retrosheet_schedule(year)
        if recon is not None:
            diffs = cross_validate(retro, recon)
            if diffs:
                import logging
                logging.getLogger("mlb.original_schedule").warning(
                    "Retrosheet vs. Rekonstruktion %d: %d Abweichungen "
                    "(erste: %s) — Retrosheet (Rating A) wird verwendet.",
                    year, len(diffs), diffs[0])
        return retro, "retrosheet (Rating A, publiziertes Original)"
    if recon is None:
        raise FileNotFoundError(
            f"Weder data/retrosheet/{year}SKED.TXT noch "
            f"data/mlb_schedule_{year}.json vorhanden.")
    return recon, "rekonstruiert aus statsapi-Feldern (Rating B)"


def cross_validate(a: Season, b: Season) -> List[str]:
    """Vergleicht zwei Originalplan-Quellen auf (Datum, Heim, Gast)-Multimengen.
    Liefert menschenlesbare Abweichungen (leer = identische Struktur)."""
    from collections import Counter
    ca = Counter((g.date, g.home, g.away) for g in a.games)
    cb = Counter((g.date, g.home, g.away) for g in b.games)
    out: List[str] = []
    for k in sorted(set(ca) | set(cb)):
        if ca.get(k, 0) != cb.get(k, 0):
            out.append(f"{k[0]} {k[2]}@{k[1]}: {ca.get(k, 0)} vs {cb.get(k, 0)}")
    return out
