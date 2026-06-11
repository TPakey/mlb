"""Runde 3 — Originalplan-Quelle, Broadcast-Fakten-Schichtung, Manifest.

Beweist die neuen Datenpfade: (a) Rekonstruktion des Originalplans aus
statsapi-Feldern (P1-5, Rating B), (b) Retrosheet-Parser (Rating A, synthetisch
getestet — echte Dateien kommen via tools/fetch_retrosheet auf dem
Entwickler-Rechner), (c) faktenbasierte SNB-Erkennung mit Heuristik-Fallback.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.data_loader import load_teams, teams_by_id as _tbi
from src.original_schedule import (
    reconstruct_original_schedule, load_retrosheet_schedule, cross_validate,
    RETROSHEET_TO_PROJECT,
)
from src.schedule_rules import check_offday_distribution, check_doubleheader_limits

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


@pytest.fixture(scope="module")
def tbi():
    return _tbi(load_teams())


# ---------- Rekonstruktion (Rating B) ----------

def test_reconstruct_2024_structure():
    orig = reconstruct_original_schedule(DATA / "mlb_schedule_2024.json", season=2024)
    assert len(orig.games) == 2430                     # exakt 30*162/2
    pks = [g.game_pk for g in orig.games]
    assert len(pks) == len(set(pks))                   # dedupliziert
    # Makeup-SPLIT-DHs (Typ S) duerfen NICHT als Original-DH zaehlen
    # (Rekonstruktions-Korrektur — vorher zaehlte z. B. ATL 3x faelschlich).
    assert all(g.dh_type != "S" for g in orig.games if g.doubleheader_seq > 0)
    # Es bleiben genau 2 Traditional-DH-Tage (Typ Y, beide Spiele ohne
    # rescheduledFrom): TEX@OAK 2024-05-08 + COL@SFG 2024-07-27. statsapi
    # fuehrt sie als geplant; ob sie im PUBLIZIERTEN Original standen, kann
    # erst die Retrosheet-Goldquelle entscheiden (Felder 11/12) — ehrliche
    # Grenze der Rating-B-Rekonstruktion. CBA-konform sind sie so oder so
    # (V(C)(14) erlaubt nicht-konsekutive Traditional-DHs).
    dh_days = {(g.date, g.home) for g in orig.games if g.doubleheader_seq > 0}
    assert dh_days == {(date(2024, 5, 8), "OAK"), (date(2024, 7, 27), "SFG")}


def test_original_plans_pass_structural_rules():
    """DIE P1-5-Kernmessung: reale ORIGINALPLAENE bestehen die Originalplan-
    Regeln — 2025 vollstaendig (V(C)(13)=0, V(C)(14/15)=0); 2024 bleiben genau
    5 dokumentierte V(C)(13)-Befunde an Sonderfenstern (Seoul-/London-Series,
    Saisonstart-Rand), KEINE DH-Verstoesse. Vorher war das mangels
    Originalplan-Quelle prinzipiell nicht messbar (finding-as-played-data)."""
    o24 = reconstruct_original_schedule(DATA / "mlb_schedule_2024.json", season=2024)
    off24 = check_offday_distribution(o24)
    assert len(off24) == 5
    assert {v.team for v in off24} == {"LAD", "SDP", "NYM", "PHI", "MIL"}
    assert check_doubleheader_limits(o24) == []

    o25 = reconstruct_original_schedule(DATA / "mlb_schedule_2025.json", season=2025)
    assert check_offday_distribution(o25) == []
    assert check_doubleheader_limits(o25) == []


def test_reconstruction_moves_makeups_back():
    # 2025-07-02 SDP@PHI war Makeup of 7/1 PPD → im Originalplan am 7/1.
    orig = reconstruct_original_schedule(DATA / "mlb_schedule_2025.json", season=2025)
    sdp_phi = [g for g in orig.games if g.home == "PHI" and g.away == "SDP"
               and date(2025, 6, 30) <= g.date <= date(2025, 7, 3)]
    dates = sorted(g.date for g in sdp_phi)
    assert date(2025, 7, 1) in dates                  # zurueckverlegt
    assert dates.count(date(2025, 7, 2)) == 1         # nur das regulaere Spiel


# ---------- Retrosheet-Parser (Rating A, synthetisch) ----------

def test_retrosheet_parser_and_mapping(tmp_path):
    sked = tmp_path / "2024SKED.TXT"
    sked.write_text(
        '"20240328","0","Thu","SDN","NL",1,"LAN","NL",1,"N","",""\n'
        '"20240615","1","Sat","CHA","AL",70,"NYA","AL",71,"D","",""\n'
        '"20240615","2","Sat","CHA","AL",71,"NYA","AL",72,"N","",""\n'
        '"20240820","0","Tue","KCA","AL",125,"TBA","AL",126,"N","Rain","20240821"\n',
        encoding="utf-8")
    s = load_retrosheet_schedule(2024, path=sked)
    assert len(s.games) == 4
    g0 = s.games[0]
    assert (g0.home, g0.away, g0.date) == ("LAD", "SDP", date(2024, 3, 28))
    dh = [g for g in s.games if g.doubleheader_seq > 0]
    assert {g.doubleheader_seq for g in dh} == {1, 2}
    assert dh[0].home == "NYY" and dh[0].away == "CWS"
    # Postponed-Eintrag bleibt am ORIGINALDATUM (das ist der Sinn der Quelle)
    assert any(g.date == date(2024, 8, 20) and g.home == "TBR" for g in s.games)


def test_retrosheet_mapping_complete_for_30_teams():
    assert len(set(RETROSHEET_TO_PROJECT.values())) == 30


def test_cross_validate_detects_shift(tmp_path):
    sked = tmp_path / "2024SKED.TXT"
    sked.write_text('"20240328","0","Thu","SDN","NL",1,"LAN","NL",1,"N","",""\n',
                    encoding="utf-8")
    a = load_retrosheet_schedule(2024, path=sked)
    assert cross_validate(a, a) == []
    sked2 = tmp_path / "b.TXT"
    sked2.write_text('"20240329","0","Fri","SDN","NL",1,"LAN","NL",1,"N","",""\n',
                     encoding="utf-8")
    b = load_retrosheet_schedule(2024, path=sked2)
    assert len(cross_validate(a, b)) == 2   # je Datum eine Abweichung


# ---------- SNB: Fakten vor Heuristik ----------

def test_exempt_pks_uses_spot_facts(tbi):
    """Das urteils-relevante Spiel 745736 (LAD@NYY 2024-06-09) kommt als
    verifizierter ESPN-Fakt aus data/mlb_national_tv.json in die SNB-Menge."""
    from src.start_times import load_exempt_pks
    resched, snb = load_exempt_pks(DATA / "mlb_schedule_2024.json", tbi)
    assert 745736 in snb
    assert len(resched) == 34            # rescheduledFrom/Makeup = Faktenfeld


def test_exempt_pks_full_facts_suppress_heuristic(tbi, tmp_path):
    """Liegt eine VOLLE Broadcast-Fakten-Datei vor, ersetzt sie die Heuristik:
    ein Sonntag-Nachtspiel OHNE nationales TV wird nicht mehr ausgenommen."""
    from src.start_times import load_exempt_pks
    sched = {
        "dates": [{
            "date": "2024-06-09",
            "games": [{
                "gamePk": 111, "gameType": "R",
                "gameDate": "2024-06-09T23:10:00Z",   # 19:10 ET, Sonntag
                "dayNight": "night", "status": {"detailedState": "Final"},
                "teams": {"home": {"team": {"abbreviation": "NYY"}},
                          "away": {"team": {"abbreviation": "LAD"}}},
                "venue": {"name": "Yankee Stadium"},
            }],
        }],
    }
    p = tmp_path / "mlb_schedule_2024.json"
    p.write_text(json.dumps(sched), encoding="utf-8")
    # Ohne Fakten-Datei: Heuristik nimmt das Spiel aus
    _, snb_heur = load_exempt_pks(p, tbi)
    assert 111 in snb_heur
    # Mit voller Fakten-Datei (kein nationales TV gelistet): kein SNB-Exempt
    (tmp_path / "mlb_broadcasts_2024.json").write_text(
        json.dumps({"national_tv_by_game_pk": {}}), encoding="utf-8")
    _, snb_fact = load_exempt_pks(p, tbi)
    assert 111 not in snb_fact
    # Und mit ESPN-Fakt: wieder drin — jetzt als Fakt, nicht als Heuristik
    (tmp_path / "mlb_broadcasts_2024.json").write_text(
        json.dumps({"national_tv_by_game_pk": {"111": ["ESPN"]}}), encoding="utf-8")
    _, snb_fact2 = load_exempt_pks(p, tbi)
    assert 111 in snb_fact2


# ---------- Rating A: echte Retrosheet-Dateien (seit 2026-06-11 im Repo) ----------

def test_retrosheet_gold_files_present_and_complete():
    """Goldquelle liegt vor (via DATEN_UPDATE.command geladen): alle drei
    Saisons vollstaendig mit 2430 Spielen (inkl. ATH→OAK-Mapping 2025+ und
    Tokyo-Series via Location-Spalte)."""
    for y in (2024, 2025, 2026):
        s = load_retrosheet_schedule(y)
        assert len(s.games) == 2430, f"{y}: {len(s.games)}"


def test_retrosheet_crossvalidates_reconstruction():
    """2024: Goldquelle und Rekonstruktion sind IDENTISCH (0 Abweichungen auf
    2430 Spielen) — validiert beide Quellen gegenseitig. 2025: exakt 4
    dokumentierte Abweichungen (2x Tokyo-Series LAD@CHC fehlt im gespeicherten
    statsapi-JSON [Datenluecke der as-played-Datei]; 1 STL@TBR-Verschiebung
    20./21.8., die statsapi nicht als Reschedule markiert)."""
    r24 = load_retrosheet_schedule(2024)
    c24 = reconstruct_original_schedule(DATA / "mlb_schedule_2024.json", season=2024)
    assert cross_validate(r24, c24) == []
    r25 = load_retrosheet_schedule(2025)
    c25 = reconstruct_original_schedule(DATA / "mlb_schedule_2025.json", season=2025)
    diffs = cross_validate(r25, c25)
    assert len(diffs) == 4, diffs
    assert sum("LAD@CHC" in d for d in diffs) == 2     # Tokyo-Luecke
    assert sum("STL@TBR" in d for d in diffs) == 2     # 1 Spiel, 2 Datumszeilen


def test_retrosheet_resolves_open_dh_question():
    """Die zwei in der Rekonstruktion unklaren 2024-DH-Tage (TEX@OAK 05-08,
    COL@SFG 07-27) sind laut Goldquelle ORIGINAL geplante Doubleheader."""
    r24 = load_retrosheet_schedule(2024)
    for d, h in ((date(2024, 5, 8), "OAK"), (date(2024, 7, 27), "SFG")):
        g = [x for x in r24.games if x.date == d and x.home == h]
        assert sorted(x.doubleheader_seq for x in g) == [1, 2], (d, h)


def test_original_plan_rating_a_measurement():
    """Originalplan-Messung auf der GOLDQUELLE: 2026 vollstaendig regelrein
    (V(C)(13)=0, V(C)(14/15)=0); 2024 exakt 5 und 2025 exakt 2 V(C)(13)-
    Befunde, ausnahmslos an internationalen Serien-/Saisonstart-Raendern
    (Seoul/London 2024, Tokyo 2025) — dokumentierte Sonderfenster, keine
    Optimierer-relevanten Verstoesse; DH-Regeln ueberall sauber."""
    expect = {2024: ({"LAD", "SDP", "NYM", "PHI", "MIL"}, 5),
              2025: ({"CHC", "LAD"}, 2),
              2026: (set(), 0)}
    for y, (teams_exp, n) in expect.items():
        s = load_retrosheet_schedule(y)
        off = check_offday_distribution(s)
        assert len(off) == n, (y, [f"{v.team}:{v.detail}" for v in off])
        assert {v.team for v in off} == teams_exp
        assert check_doubleheader_limits(s) == []


def test_broadcast_facts_replace_heuristic(tbi):
    """Volle Broadcast-Fakten liegen vor → SNB ist faktenbasiert: 745736
    (LAD@NYY, verifiziert ESPN) enthalten; Menge weicht von der alten
    Heuristik ab (sie uebersah z. B. westliche Frueh-Starts); V(C)(8) bleibt
    bei 0 Verstoessen."""
    from src.start_times import load_exempt_pks
    resched, snb = load_exempt_pks(DATA / "mlb_schedule_2024.json", tbi)
    assert 745736 in snb
    assert len(snb) == 29          # Fakten (Heuristik fand nur 17)


# ---------- C3: Co-Tenant-Kalender (River Cats / Sutter Health Park) ----------

def test_c3_river_cats_cotenant_blackouts():
    """C3 (2026-06-11): River-Cats-Heimstaende (Rating A, MiLB-statsapi) sind
    harte stadium_bookings fuer OAK — 75 Blackout-Tage je Saison 2025/2026;
    reale Plaene kollisionsfrei (MLB/MiLB koordinieren wirklich); ein
    kuenstliches OAK-Heimspiel auf einem River-Cats-Tag wird geflaggt.
    Tarpons-Befund: 2025 auf 'Yankee Complex Field 2' ausgewichen -> bewusst
    KEINE Steinbrenner-Blackouts (siehe _note_c3 in local_events.json)."""
    from datetime import date as _d
    from src.event_conflicts import (load_local_events,
                                     stadium_bookings_to_blackout_days,
                                     venue_conflicts)
    from src.datasources.local_file import LocalFileAdapter
    from src.original_schedule import load_retrosheet_schedule
    from src.season import Game, Season

    events = load_local_events()
    rc = [e for e in events if "River Cats" in e.name]
    assert len(rc) == 27 and all(e.is_stadium_booking() for e in rc)
    bl26 = stadium_bookings_to_blackout_days(events, _d(2026, 3, 25), _d(2026, 9, 27))
    assert len(bl26["OAK"]) == 75
    # Reale Plaene: keine Konflikte (Validierung der Datenquelle)
    s25 = LocalFileAdapter(base_dir=DATA).fetch_season_schedule(2025)
    assert venue_conflicts(s25, events) == []
    assert venue_conflicts(load_retrosheet_schedule(2026), events) == []
    # Negativ-Probe: Verstoss wird erkannt
    fake = Season(season=2026, games=[Game(1, _d(2026, 4, 8), "OAK", "SEA", "OAK")],
                  season_start=_d(2026, 3, 25), season_end=_d(2026, 9, 27))
    assert len(venue_conflicts(fake, events)) == 1


# ---------- C1: Forbes-Revenue als unabhaengige Validierungsreferenz ----------

def test_c1_forbes_revenue_validates_model_ordering():
    """C1 (2026-06-11): Forbes-2025-Gesamt-Revenue (Saison 2024, alle 30 Teams,
    Wikipedia-Mirror, Rating B) als ZWEITE unabhaengige ordinale Validierung des
    Revenue-Modells: Spearman(base_team-Gate-Kalibrierung, Forbes-Revenue) =
    0.92 (gemessen) — neben Spearman 0.892 vs. ESPN-Attendance. EHRLICH:
    Gesamt-Revenue ≠ Gate-Receipts (TV/Sponsoring drin); echte per-Team-Gate-
    Receipts bleiben paywalled (dokumentiert in der Datei). Kein Kalibrier-Input."""
    import json as _json
    from src.revenue_validation import spearman
    forbes = _json.loads((DATA / "forbes_team_financials_2025.json").read_text())
    rev = forbes["revenue_total_musd_by_team"]
    assert len(rev) == 30
    rm = _json.loads((DATA / "revenue_model.json").read_text())
    teams = sorted(set(rev) & set(rm["base_team"]))
    assert len(teams) == 30
    rho = spearman([rm["base_team"][t] for t in teams], [rev[t] for t in teams])
    assert rho > 0.85, f"Spearman {rho:.3f} zu niedrig"


# ---------- C3/C1 Betriebspfad: Registry, Tool-Konsistenz, Verankerung ----------

def test_cotenant_registry_consistent_with_events():
    """Die Sharing-Registry (cotenant_sharing.json) und der Event-Bestand
    passen zusammen: je Sharing-Eintrag und Saison mit Referenzplan existieren
    note-geschluesselte Events; Registry-Eintraege sind vollstaendig belegt
    (venueId, statsapi-IDs, verified-Vermerk)."""
    reg = json.loads((DATA / "cotenant_sharing.json").read_text(encoding="utf-8"))
    assert reg["sharing"], "Registry leer"
    from src.event_conflicts import load_local_events
    events = load_local_events()
    for entry in reg["sharing"]:
        for feld in ("mlb_team", "mlb_statsapi_id", "venue_id",
                     "cotenant_sport_id", "cotenant_team_id", "seasons", "verified"):
            assert entry.get(feld), f"Registry-Feld fehlt: {feld}"
        for season in entry["seasons"]:
            has_ref = ((DATA / f"mlb_schedule_{season}.json").exists()
                       or (DATA / "retrosheet" / f"{season}SKED.TXT").exists())
            mine = [e for e in events
                    if e.note == f"cotenant:{entry['mlb_team']}:{season}"]
            if has_ref:
                assert mine, f"{entry['mlb_team']}/{season}: Events fehlen"
                assert all(e.is_stadium_booking() for e in mine)
    # Dokumentierte Nicht-Sharing-Befunde (Tarpons 2025, Rays 2026) vorhanden
    assert len(reg.get("resolved_non_sharing", [])) >= 2


def test_cotenant_tool_validate_only_passes():
    """Der Betriebs-Check (offline) muss grün sein — exakt das, was MLB-Ops
    nach jedem Datenupdate laufen lässt."""
    import subprocess, sys as _sys
    rc = subprocess.call(
        [_sys.executable, "-m", "tools.fetch_cotenant_calendars", "--validate-only"],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert rc == 0


def test_forbes_reference_is_wired_into_validator():
    """C1 ist im Validierungs-Tool VERANKERT (kein Chat-Einmal-Messwert):
    beide Referenzen (Forbes-Gesamt-Revenue UND echte Gate-Receipts) gehen
    ins PASS/FAIL-Urteil von tools/validate_revenue_model ein."""
    src = (ROOT / "tools" / "validate_revenue_model.py").read_text(encoding="utf-8")
    assert "forbes_team_financials_2025.json" in src
    assert "gate_receipts_2024.json" in src
    assert "ok_forbes and ok_gate" in src.replace(" \
", " ")  # im all_ok-Urteil


# ---------- C3-Tiefe: Drittnutzungs-Kalender 2026 (Konzerte/Events) ----------

def test_c3_thirdparty_bookings_2026():
    """29 recherchierte Voll-Stadion-Drittnutzungen 2026 (Konzerte, Bananas,
    Comedy) als stadium_bookings, je Eintrag mit Quelle; ALLE kollisionsfrei
    mit dem 2026-Originalplan (Retrosheet) — Konzerte werden um den
    publizierten Plan herum gebucht, 0 Kollisionen validieren die Recherche.
    Watchlist (unbestaetigt/Gallagher-Square) bewusst NICHT als Blackout."""
    from src.event_conflicts import load_local_events, venue_conflicts
    tp = [e for e in load_local_events() if str(e.note).startswith("thirdparty:")]
    assert len(tp) == 29
    assert all(e.is_stadium_booking() and e.source for e in tp)
    teams = {t for e in tp for t in e.team_ids}
    assert {"CHC", "BOS", "NYM", "NYY", "LAD", "SDP", "SEA",
            "KCR", "CIN", "MIN", "COL", "STL", "TEX"} <= teams
    r26 = load_retrosheet_schedule(2026)
    assert venue_conflicts(r26, tp) == []


def test_c1_gate_receipts_reference():
    """Echte per-Team-Gate-Receipts (Forbes via Statista-Teaser, 28 Teams mit
    Jahr >= 2023): Spearman gegen base_team = 0.958 (gemessen) — direkteste
    Referenz. Sportico-Anker (inkl. Premium) dokumentieren die bekannte
    absolute Unterschaetzung der Top-Teams (Kalibrier-Befund, kein stiller
    Eingriff). TEX/CLE-Luecke explizit dokumentiert."""
    import json as _json
    from src.revenue_validation import spearman
    gd = _json.loads((DATA / "gate_receipts_2024.json").read_text(encoding="utf-8"))
    rows = gd["gate_receipts_by_team"]
    assert len(rows) == 30
    recent = {t: r["musd"] for t, r in rows.items() if r["year"] >= 2023}
    assert len(recent) == 28           # TEX/CLE nur Alt-Jahr (dokumentiert)
    rm = _json.loads((DATA / "revenue_model.json").read_text(encoding="utf-8"))
    ts = sorted(set(recent) & set(rm["base_team"]))
    rho = spearman([rm["base_team"][t] for t in ts], [recent[t] for t in ts])
    assert rho > 0.9, f"Spearman {rho:.3f}"
    assert "_sportico_internal_anchors_2024" in gd     # Kalibrier-Anker da


# ---------- Nacht-Härtung P1-5: Pareto-Auslieferung nur publizierbar ----------

def test_pareto_publishable_only_filters_frontier():
    """Auslieferungs-Modus (main --pareto / api): nicht publizierbare Punkte
    werden VERWORFEN (vorher nur markiert — dieselbe Fehlerklasse wie P0-1).
    Gemessen real 2024 @4k Iter: 7 Punkte, nur 2 publizierbar → Filter liefert
    exakt diese 2; Forschungs-Default (False) bleibt unverändert."""
    from src.data_loader import load_teams
    from src.datasources.local_file import LocalFileAdapter
    from src.season import detect_all_star_break
    from src.generator import GeneratorConfig
    from src.pareto import sample_pareto_frontier
    teams = load_teams()
    real = LocalFileAdapter(base_dir=DATA).fetch_season_schedule(2024)
    cfg = GeneratorConfig(season=2024, season_start=real.season_start,
                          season_end=real.season_end,
                          all_star_break=detect_all_star_break(real),
                          num_search_workers=1, random_seed=42)
    kw = dict(master_seed=42, sa_iterations=4000, n_interior_points=0,
              sa_move_mix_geo=0.35)
    a = sample_pareto_frontier(real, teams, cfg, **kw)
    n_pub = sum(1 for p in a.points if p.publishable)
    assert n_pub < len(a.points)            # Fehlerklasse existiert ohne Filter
    b = sample_pareto_frontier(real, teams, cfg, publishable_only=True, **kw)
    assert len(b.points) == n_pub and all(p.publishable for p in b.points)
    assert "verworfen" in b.diagnostic


# ---------- Nacht-Härtung B2/P1-6: per-Team-ASB-Check (V(C)(17)) ----------

def test_asb_check_is_per_team(tbi):
    """Die alte league-wide-ASB-Messung meldete 2026 fälschlich '3 Tage Liga-
    Befund'; per-Team gemessen haben 28/30 Teams die vollen 4 Tage und genau
    NYM/PHI 3 (Einzelspiel 16.07., V(C)(18)-Waiver-Klasse). 2024/2025: 30/30."""
    from src.compliance import compliance_report
    from src.datasources.local_file import LocalFileAdapter
    for y in (2024, 2025):
        s = LocalFileAdapter(base_dir=DATA).fetch_season_schedule(y)
        c = compliance_report(s, teams_by_id=tbi).get("CBA-ASB")
        assert c.passed and "30/30" in c.measured, (y, c.measured)
    c26 = compliance_report(load_retrosheet_schedule(2026),
                            teams_by_id=tbi).get("CBA-ASB")
    assert not c26.passed and "28/30" in c26.measured
    assert {o.split(":")[0] for o in c26.offenders} == {"NYM", "PHI"}


# ---------- Nacht-Härtung P1-6: PTET-≤7-Liga-Ausnahme (V(C)(11)) ----------

def test_ptet_league_exemption_with_start_times(tbi):
    """Mit Startzeiten greift die ≤7-Liga-Ausnahme: PT-Spiel <17:00 + ET-Spiel
    >19:00 + Einzelspiel = entschuldbar; frühes ET-Spiel, ET-Doubleheader und
    der 8. Fall je Liga bleiben Verstöße. Ohne Startzeiten: strikt wie bisher."""
    from datetime import date as _d, timedelta as _td
    from src.season import Game, Season
    from src.compliance import _check_pt_et_offday
    base = _d(2026, 6, 1)
    def mk(pk, day, home, away):
        return Game(pk, base + _td(days=day), home, away, home)
    # NYY: LAD(PT) Tag0 -> NYY(ET) Tag1
    games = [mk(1, 0, "LAD", "NYY"), mk(2, 1, "NYY", "BOS")]
    s = Season(season=2026, games=games, season_start=base, season_end=base + _td(days=30))
    # strikt (ohne start_min): Verstoß
    assert not _check_pt_et_offday(s, ["NYY"], tbi).passed
    # Ausnahme erfüllt: PT 13:05, ET 19:10
    ok = _check_pt_et_offday(s, ["NYY"], tbi, start_min={1: 13*60+5, 2: 19*60+10})
    assert ok.passed and "Liga-Ausnahme" in ok.measured
    # ET zu früh (18:00): Verstoß trotz Startzeiten
    assert not _check_pt_et_offday(s, ["NYY"], tbi, start_min={1: 13*60, 2: 18*60}).passed
    # PT zu spät gestartet (19:00): Verstoß
    assert not _check_pt_et_offday(s, ["NYY"], tbi, start_min={1: 19*60, 2: 19*60+10}).passed
    # Satz 2: Doubleheader am ET-Tag => Verstoß
    g_dh = games + [Game(3, base + _td(days=1), "NYY", "BOS", "NYY", doubleheader_seq=2)]
    s_dh = Season(season=2026, games=g_dh, season_start=base, season_end=base + _td(days=30))
    assert not _check_pt_et_offday(s_dh, ["NYY"], tbi,
                                   start_min={1: 13*60, 2: 19*60+10, 3: 23*60}).passed
    # Liga-Limit: 8 AL-Faelle -> der 8. ist Verstoß
    big = []
    sm = {}
    for i in range(8):
        pk1, pk2 = 100 + 2*i, 101 + 2*i
        big += [Game(pk1, base + _td(days=3*i), "LAA", "NYY", "LAA"),
                Game(pk2, base + _td(days=3*i+1), "NYY", "BOS", "NYY")]
        sm[pk1] = 13*60; sm[pk2] = 19*60+10
    s8 = Season(season=2026, games=big, season_start=base, season_end=base + _td(days=40))
    c8 = _check_pt_et_offday(s8, ["NYY"], tbi, start_min=sm)
    assert not c8.passed and len(c8.offenders) == 1 and ">7 Ausnahmen" in c8.offenders[0]


# ---------- Nacht-Härtung P1-7: TV-Pins als harte Fenster ----------

def test_tv_pins_enforced_and_conflicts_detected(tbi):
    """TV-Pins (aus Broadcast-Fakten) werden im Zuweiser EXAKT übernommen
    (real 2024: 691/691, 2025: 594/594, je 0 CBA-Konflikte — gemessen);
    synthetisch: ein nicht übernommener Pin und ein V(C)(8)-brechender Pin
    werden vom Validator gemeldet."""
    from datetime import date as _d, timedelta as _td
    from pathlib import Path as _P
    from src.season import Game, Season
    from src.start_times import (AppendixC, assign_start_times, build_tv_pins,
                                 validate_tv_pins, load_real_start_times)
    ac = AppendixC.load()
    from src.datasources.local_file import LocalFileAdapter
    s24 = LocalFileAdapter(base_dir=DATA).fetch_season_schedule(2024)
    real = load_real_start_times(DATA / "mlb_schedule_2024.json", tbi)
    pins = build_tv_pins(s24, DATA / "mlb_broadcasts_2024.json", real)
    assert len(pins) > 600
    asg = assign_start_times(s24, ac, tv_pins=pins)
    amin = {pk: a.local_start_min for pk, a in asg.items()}
    assert all(amin[pk] == m for pk, m in pins.items())   # Pin-Treue 100%
    # Synthetik: BOS->SEA-Getaway (inflight >> 2:30) mit 19:00-Pin = Konflikt;
    # plus ein Pin, der nicht uebernommen wurde.
    base = _d(2026, 6, 1)
    g = [Game(1, base, "BOS", "NYY", "BOS"), Game(2, base + _td(days=1), "SEA", "BOS", "SEA")]
    s = Season(season=2026, games=g, season_start=base, season_end=base + _td(days=20))
    v = validate_tv_pins(s, {1: 13 * 60, 2: 19 * 60}, {1: 19 * 60}, ac)
    rules = {x.rule for x in v}
    assert "TV-PIN" in rules               # Pin 19:00, zugewiesen 13:00
    assert "TV-PIN/V(C)(8)" in rules       # 19:00 > Grenze (BOS->SEA ~6h Flug)
