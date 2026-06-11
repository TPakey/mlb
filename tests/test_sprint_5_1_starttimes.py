"""Sprint 5.1 — Startzeit-Schicht: Formel, Reproduktion gegen reale 2024/2025-
Pläne, Compliance-Gating und Determinismus.

Kernaussage (gemessen, nicht behauptet): die V(C)(8)-Getaway-Formel reproduziert
die realen Getaway-Startzeiten — reise-bindende Fälle (inflight > 2:30) exakt,
übrige innerhalb der per-Club First-Pitch-Konvention (±40 min). V(C)(9) ist mit
den dokumentierten Ausnahmen (Feiertag/Home-Opener/Cubs) auf beiden realen
Plänen verstoßfrei.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.data_loader import load_teams, teams_by_id as _tbi
from src.datasources.local_file import LocalFileAdapter
from src.compliance import compliance_report
from src.start_times import (
    AppendixC, GameSlot, getaway_latest_start_min, fmt_min,
    assign_start_times, find_getaway_contexts, load_real_start_times,
    validate_getaway_times, validate_nightday_times, validate_day_min_times,
    detect_home_openers, holiday_dates_for,
    NIGHT_START_MIN, GETAWAY_INFLIGHT_THRESHOLD_MIN,
)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


# ---------- Fixtures ----------

@pytest.fixture(scope="module")
def teams():
    return load_teams()


@pytest.fixture(scope="module")
def tbi(teams):
    return _tbi(teams)


@pytest.fixture(scope="module")
def appendix_c():
    return AppendixC.load()


def _season(year):
    return LocalFileAdapter(base_dir=DATA).fetch_season_schedule(year)


# ---------- Appendix-C-Integrität ----------

def test_appendix_c_symmetric_and_anchored(appendix_c):
    m = appendix_c.minutes
    ids = list(m)
    assert len(ids) == 30
    for a in ids:
        assert m[a][a] == 0
        for b in ids:
            assert m[a][b] == m[b][a], f"asymmetrisch {a}<->{b}"
    # Anker (aus realen 2025-Startzeiten zurückgerechnet)
    assert appendix_c.inflight_minutes("LAD", "ATL") == 3 * 60 + 52
    assert appendix_c.inflight_minutes("LAD", "CIN") == 3 * 60 + 48
    assert appendix_c.inflight_minutes("LAA", "LAD") == 3
    assert appendix_c.inflight_minutes("OAK", "SFG") == 1


def test_appendix_c_uses_project_ids(appendix_c):
    # gemappte IDs müssen existieren, Bild-IDs nicht
    for pid in ("CHC", "KCR", "SDP", "SFG", "TBR", "WSN", "CWS"):
        assert pid in appendix_c.minutes
    for img in ("CHI", "KC", "SD", "SF", "TB", "WSH"):
        assert img not in appendix_c.minutes


# ---------- V(C)(8)-Formel ----------

def test_getaway_formula():
    # inflight ≤ 2:30 → keine Verschiebung (19:00)
    assert getaway_latest_start_min(0) == NIGHT_START_MIN
    assert getaway_latest_start_min(GETAWAY_INFLIGHT_THRESHOLD_MIN) == NIGHT_START_MIN
    # inflight 3:30 → Überschuss 60 min → 18:00
    assert getaway_latest_start_min(3 * 60 + 30) == NIGHT_START_MIN - 60
    # inflight 5:00 → Überschuss 150 → 16:30
    assert getaway_latest_start_min(5 * 60) == NIGHT_START_MIN - 150


def test_fmt_min():
    assert fmt_min(1140) == "19:00"
    assert fmt_min(13 * 60) == "13:00"
    assert fmt_min(None) == "—"


# ---------- Reproduktion gegen reale Pläne ----------

@pytest.mark.parametrize("year", [2024, 2025])
def test_getaway_compliance_real_plan(year, tbi, appendix_c):
    """Reale Getaway-Startzeiten halten die V(C)(8)-Grenze ein (±40 min
    First-Pitch-Konvention). Review-Runde 2 (Punkt 4): Abdeckung umfasst jetzt
    auch 'visiting Club travels to a home off-day' — die Messung MUSS dafür die
    expliziten CBA-Ausnahmen (SNB, Reschedules) ausnehmen; die je 1 Roh-Treffer
    2024/2025 sind exakt diese Ausnahmen (LAD@NYY Sunday Night 2024-06-09;
    SDP@PHI Makeup 2025-07-02)."""
    from src.start_times import load_exempt_pks
    season = _season(year)
    real = load_real_start_times(DATA / f"mlb_schedule_{year}.json", tbi)
    resched, snb = load_exempt_pks(DATA / f"mlb_schedule_{year}.json", tbi)
    viols = validate_getaway_times(season, real, appendix_c, tolerance_min=40,
                                   espn_snb_pks=snb, rescheduled_pks=resched)
    assert viols == [], f"{year}: V(C)(8)-Verstöße: {[v.detail for v in viols[:5]]}"
    # Ohne Ausnahmen flaggt die volle Abdeckung genau die CBA-Ausnahmefälle —
    # Beleg, dass die Erweiterung real bindet (vorher unentdeckbar):
    raw = validate_getaway_times(season, real, appendix_c, tolerance_min=40)
    assert len(raw) == 1


@pytest.mark.parametrize("year", [2024, 2025])
def test_getaway_binding_cases_reproduced(year, tbi, appendix_c):
    """Reise-bindende Getaway-Spiele (inflight > 2:30) werden vom realen Plan
    eingehalten — die travel-abhängige Verschärfung der Formel ist real gedeckt."""
    season = _season(year)
    real = load_real_start_times(DATA / f"mlb_schedule_{year}.json", tbi)
    contexts = find_getaway_contexts(season, appendix_c)
    by_key = {}
    for g in season.games:
        by_key.setdefault((g.date, g.home), []).append(g)
    binding_total = 0
    binding_ok = 0
    for key, ctx in contexts.items():
        if ctx.binding_inflight_min <= GETAWAY_INFLIGHT_THRESHOLD_MIN:
            continue
        for g in by_key.get(key, []):
            s = real.get(g.game_pk)
            if s is None:
                continue
            binding_total += 1
            if s <= ctx.latest_start_min + 40:
                binding_ok += 1
    assert binding_total >= 50, f"{year}: zu wenige bindende Fälle ({binding_total})"
    # ≥99 % der bindenden Fälle innerhalb der Grenze (+Konvention)
    assert binding_ok / binding_total >= 0.99, (
        f"{year}: nur {binding_ok}/{binding_total} bindende Fälle konform")


@pytest.mark.parametrize("year", [2024, 2025])
def test_nightday_compliance_real_plan(year, tbi, appendix_c):
    """V(C)(9): mit Feiertags-/Home-Opener-/Cubs-Ausnahmen ist der reale Plan
    verstoßfrei."""
    season = _season(year)
    real = load_real_start_times(DATA / f"mlb_schedule_{year}.json", tbi)
    viols = validate_nightday_times(
        season, real, appendix_c, tbi,
        holiday_dates=holiday_dates_for(season),
        home_opener_pks=detect_home_openers(season))
    assert viols == [], f"{year}: V(C)(9)-Verstöße: {[v.detail for v in viols[:5]]}"


@pytest.mark.parametrize("year", [2024, 2025])
def test_daymin_only_documented_specials(year, tbi):
    """V(C)(6) ist weich: der reale Plan enthält nur wenige (<20) dokumentierte
    Früh-Start-Specials (Patriots'/Education/Holiday-Morning), alle vor 13:00."""
    season = _season(year)
    real = load_real_start_times(DATA / f"mlb_schedule_{year}.json", tbi)
    viols = validate_day_min_times(season, real)
    assert len(viols) < 20, f"{year}: unerwartet viele Früh-Starts: {len(viols)}"
    assert all(v.rule == "V(C)(6)" for v in viols)


# ---------- Zuweisung & Determinismus ----------

def test_assign_start_times_deterministic(appendix_c):
    season = _season(2024)
    a1 = assign_start_times(season, appendix_c)
    a2 = assign_start_times(season, appendix_c)
    assert a1 == a2
    # eine Zuweisung je distinktem game_pk (reale Daten haben wenige Dubletten-
    # pk aus Seoul-Exhibition/Split-DH — daher gegen distinkte pk prüfen)
    assert len(a1) == len({g.game_pk for g in season.games})
    # Getaway-Zuweisungen liegen nie nach 19:00
    for asg in a1.values():
        if asg.slot is GameSlot.GETAWAY:
            assert asg.local_start_min <= NIGHT_START_MIN


def test_assign_respects_tv_pins(appendix_c):
    season = _season(2024)
    some_pk = season.games[0].game_pk
    asg = assign_start_times(season, appendix_c, tv_pins={some_pk: 19 * 60})
    assert asg[some_pk].slot is GameSlot.TV_FIXED
    assert asg[some_pk].local_start_min == 19 * 60


# ---------- Compliance-Gating ----------

def test_compliance_starttime_gated_off_by_default(tbi):
    """Default-Pfad (kein start_min): STARTTIME-* übersprungen & passed → Report
    bleibt hart-konform wie zuvor."""
    season = _season(2024)
    rep = compliance_report(season, teams_by_id=tbi)
    for rid in ("STARTTIME-GETAWAY", "STARTTIME-NIGHTDAY", "STARTTIME-DAYMIN"):
        chk = rep.get(rid)
        assert chk is not None and chk.passed
        assert "übersprungen" in chk.measured
    assert rep.is_compliant


@pytest.mark.parametrize("year", [2024, 2025])
def test_compliance_starttime_active_with_real_times(year, tbi, appendix_c):
    """Mit echten Startzeiten greifen die harten Startzeit-Regeln, der reale Plan
    besteht sie, und die Startzeit-Schicht fügt KEINEN neuen harten Verstoß hinzu
    (Baseline-Vergleich; 2025 hat vorbestehende as-played-Artefakte SCHED-162/HA)."""
    from src.start_times import load_exempt_pks
    season = _season(year)
    real = load_real_start_times(DATA / f"mlb_schedule_{year}.json", tbi)
    resched, snb = load_exempt_pks(DATA / f"mlb_schedule_{year}.json", tbi)
    base = compliance_report(season, teams_by_id=tbi)
    rep = compliance_report(season, teams_by_id=tbi, start_min=real,
                            appendix_c=appendix_c,
                            espn_snb_pks=snb, rescheduled_pks=resched)
    assert rep.get("STARTTIME-GETAWAY").passed
    assert rep.get("STARTTIME-NIGHTDAY").passed
    assert rep.get("STARTTIME-DAYDH").passed   # V(C)(5), Review-Runde 2
    # keine NEUEN harten Verstöße durch die Startzeit-Schicht
    base_fail = {c.rule_id for c in base.hard_failures}
    new_fail = {c.rule_id for c in rep.hard_failures}
    assert new_fail == base_fail, f"{year}: neue harte Verstöße: {new_fail - base_fail}"
