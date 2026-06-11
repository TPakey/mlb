"""Generiert das Scheduler-Operations-Dashboard (`dashboard/ops.html`).

Macht die Trip-Operations-Suite (Routing / Hotel / Security-Briefing pro
Auswärts-Stadt) im Dashboard zugänglich — die im Handover gewünschte
„Ops-Dossier ins Dashboard"-Integration.

Lädt den (realen) Saisonplan, berechnet für **alle 30 Teams** die Trip-Dossiers
und bettet einen kompakten JSON-Payload in eine eigenständige HTML-Seite ein.
Die Seite rendert interaktiv: Team-Auswahl → Risiko-Übersicht aller
Auswärts-Städte + aufklappbares Detail-Dossier je Stadt.

Aufruf:
    python -m dashboard.build_ops_dashboard --season 2024
    python -m dashboard.build_ops_dashboard --season 2024 --out dashboard/ops.html
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import load_teams
from src.datasources import LocalFileAdapter
from src.ops_dossier import team_trip_dossiers


def _leg_dict(leg) -> dict | None:
    if leg is None:
        return None
    return {
        "from": leg.from_name, "to": leg.to_name,
        "road_km": round(leg.road_km, 1), "drive_min": round(leg.drive_min),
        "reliability": round(leg.reliability, 2),
    }


def _city_payload(d) -> dict:
    hotel = d.recommended_hotel
    sec = d.security
    return {
        "city": d.city,
        "host": d.host_team,
        "stadium": d.stadium,
        "start": d.start_date.isoformat(),
        "end": d.end_date.isoformat(),
        "n_games": d.n_games,
        "risk_level": sec.risk_level,
        "severity": sec.overall_severity,
        "roof": sec.roof,
        "posture": sec.recommended_posture,
        "trauma_center": sec.trauma_center,
        "transport_reliability": round(sec.transport_reliability, 2),
        "active_hazards": [
            {"hazard": h["hazard"], "severity": h["severity"],
             "months": h.get("months", ""), "note": h.get("note", "")}
            for h in sorted(sec.active_hazards, key=lambda x: -x["severity"])
        ],
        "high_profile": list(d.high_profile),
        "hotel": (None if hotel is None else {
            "name": hotel.hotel.name,
            "score": round(hotel.score, 1),
            "distance_km": round(hotel.distance_km, 1),
            "vetted": bool(hotel.is_vetted),
            "history_note": hotel.history_note,
        }),
        "routing": {
            "airport_to_ballpark": _leg_dict(d.routing.airport_to_ballpark),
            "airport_to_hotel": _leg_dict(d.routing.airport_to_hotel),
            "hotel_to_ballpark": _leg_dict(d.routing.hotel_to_ballpark),
        },
    }


def build_payload(season_year: int) -> dict:
    season = LocalFileAdapter(base_dir=str(ROOT / "data")).fetch_season_schedule(season_year)
    teams = sorted(t.id for t in load_teams())
    out: dict = {"season": season_year, "teams": {}}
    for tid in teams:
        dossiers = team_trip_dossiers(season, tid)
        cities = [_city_payload(d) for d in dossiers]
        n_high = sum(1 for c in cities if c["high_profile"])
        worst = max((c["severity"] for c in cities), default=0)
        out["teams"][tid] = {
            "n_cities": len(cities),
            "n_high_profile": n_high,
            "worst_severity": worst,
            "cities": cities,
        }
    return out


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>MLB Ops · Trip-Dossiers</title>
<style>
  :root {
    --bg:#0b1220; --panel:#141d33; --panel-2:#1c2746; --text:#e8ecf6;
    --muted:#8a96b3; --accent:#4fc3f7; --accent-2:#ffb74d;
    --s1:#66bb6a; --s2:#9ccc65; --s3:#ffb74d; --s4:#ff8a65; --s5:#ef5350;
  }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:var(--bg); color:var(--text); line-height:1.5; }
  header { padding:24px 32px; border-bottom:1px solid #233055; display:flex;
           align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; }
  header h1 { margin:0; font-size:22px; }
  header .sub { color:var(--muted); font-size:13px; }
  nav a { color:var(--accent); text-decoration:none; margin-right:16px; font-size:13px; }
  .wrap { padding:24px 32px; }
  select { background:var(--panel-2); color:var(--text); border:1px solid #2a3a66;
           border-radius:8px; padding:8px 12px; font-size:14px; }
  .summary { display:flex; gap:16px; margin:16px 0; flex-wrap:wrap; }
  .kpi { background:var(--panel); border:1px solid #233055; border-radius:12px;
         padding:14px 18px; min-width:150px; }
  .kpi .v { font-size:24px; font-weight:700; }
  .kpi .l { color:var(--muted); font-size:12px; }
  table { width:100%; border-collapse:collapse; background:var(--panel);
          border-radius:12px; overflow:hidden; margin-bottom:24px; }
  th,td { text-align:left; padding:10px 12px; border-bottom:1px solid #233055; font-size:13px; }
  th { color:var(--muted); font-weight:600; }
  tr.clickable:hover { background:var(--panel-2); cursor:pointer; }
  .pill { display:inline-block; padding:2px 9px; border-radius:999px; font-size:12px;
          font-weight:600; color:#0b1220; }
  .hp { color:var(--accent-2); font-size:12px; }
  .detail { background:var(--panel-2); border:1px solid #2a3a66; border-radius:12px;
            padding:16px 20px; margin:8px 0 20px; }
  .detail h3 { margin:0 0 8px; }
  .detail .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  .detail h4 { margin:12px 0 4px; color:var(--accent); font-size:13px; }
  .detail .muted { color:var(--muted); }
  .haz { font-size:12px; margin:2px 0; }
  .hidden { display:none; }
  @media (max-width:720px){ .detail .grid2 { grid-template-columns:1fr; } }
</style>
</head>
<body>
<header>
  <div>
    <h1>Scheduler-Operations · Trip-Dossiers</h1>
    <div class="sub">Routing · Hotel · City-Security-Briefing je Auswärts-Stadt · Saison __SEASON__</div>
  </div>
  <nav>
    <a href="index.html">← Haupt-Dashboard</a>
    <a href="pareto.html">Pareto-Explorer</a>
  </nav>
</header>
<div class="wrap">
  <label class="muted" for="team">Team:&nbsp;</label>
  <select id="team"></select>
  <div class="summary" id="summary"></div>
  <table id="overview">
    <thead><tr>
      <th>Stadt</th><th>Gastgeber</th><th>Termin</th><th>Sp.</th>
      <th>Risiko</th><th>Transfer-Planbarkeit</th><th>Hotel</th><th></th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table>
  <div id="detail-host"></div>
</div>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
const DATA = JSON.parse(document.getElementById('payload').textContent);
const SCOLORS = {1:'--s1',2:'--s2',3:'--s3',4:'--s4',5:'--s5'};
function sevColor(s){ return getComputedStyle(document.documentElement).getPropertyValue(SCOLORS[s]||'--s3'); }
function fmtDate(s){ const d=new Date(s+'T00:00:00'); return d.toLocaleDateString('de-DE',{day:'2-digit',month:'short'}); }

const sel = document.getElementById('team');
Object.keys(DATA.teams).sort().forEach(t=>{
  const o=document.createElement('option'); o.value=t; o.textContent=t; sel.appendChild(o);
});

function render(tid){
  const td = DATA.teams[tid];
  document.getElementById('summary').innerHTML =
    `<div class="kpi"><div class="v">${td.n_cities}</div><div class="l">Auswärts-Städte</div></div>`+
    `<div class="kpi"><div class="v">${td.n_high_profile}</div><div class="l">High-Profile-Trips</div></div>`+
    `<div class="kpi"><div class="v" style="color:${sevColor(td.worst_severity)}">${td.worst_severity}/5</div><div class="l">höchste Risikostufe</div></div>`;
  const rows = document.getElementById('rows'); rows.innerHTML='';
  document.getElementById('detail-host').innerHTML='';
  td.cities.forEach((c,i)=>{
    const tr=document.createElement('tr'); tr.className='clickable';
    const hotel = c.hotel ? `${c.hotel.name} (${c.hotel.score})${c.hotel.vetted?' ✓':''}` : '<span class="muted">— (kein Seed)</span>';
    tr.innerHTML =
      `<td>${c.city}${c.high_profile.length?' <span class="hp">★</span>':''}</td>`+
      `<td>${c.host}</td>`+
      `<td>${fmtDate(c.start)}–${fmtDate(c.end)}</td>`+
      `<td>${c.n_games}</td>`+
      `<td><span class="pill" style="background:${sevColor(c.severity)}">${c.risk_level} ${c.severity}/5</span></td>`+
      `<td>${Math.round(c.transport_reliability*100)} %</td>`+
      `<td>${hotel}</td>`+
      `<td>▸</td>`;
    tr.onclick=()=>toggleDetail(tid,i);
    rows.appendChild(tr);
  });
}

function legRow(label,leg){
  if(!leg) return `<div class="haz muted">${label}: —</div>`;
  return `<div class="haz">${label}: ${leg.road_km} km · ${leg.drive_min} min · Planbarkeit ${Math.round(leg.reliability*100)} %</div>`;
}

function toggleDetail(tid,i){
  const host=document.getElementById('detail-host');
  const existing=document.getElementById('detail-'+i);
  if(existing){ existing.remove(); return; }
  host.innerHTML='';
  const c=DATA.teams[tid].cities[i];
  const haz = c.active_hazards.length
    ? c.active_hazards.map(h=>`<div class="haz">[${h.severity}/5] ${h.hazard} <span class="muted">(${h.months})</span> — ${h.note}</div>`).join('')
    : '<div class="haz muted">keine saison-aktiven Klimagefahren</div>';
  const hp = c.high_profile.length ? c.high_profile.map(f=>`<div class="haz">⚑ ${f}</div>`).join('') : '';
  const hotel = c.hotel
    ? `<div class="haz">${c.hotel.name} — Score ${c.hotel.score}, ${c.hotel.distance_km} km${c.hotel.vetted?', vetted ✓':''}</div><div class="haz muted">${c.hotel.history_note}</div>`
    : '<div class="haz muted">Kein Hotel im illustrativen Seed — Club importiert reale Buchungshistorie ins selbe Schema.</div>';
  const div=document.createElement('div'); div.className='detail'; div.id='detail-'+i;
  div.innerHTML =
    `<h3>${c.city} · ${c.stadium} <span class="muted">(${c.host})</span></h3>`+
    `<div class="muted">${fmtDate(c.start)}–${fmtDate(c.end)} · ${c.n_games} Spiele · Dach: ${c.roof}</div>`+
    (hp?`<div style="margin-top:6px">${hp}</div>`:'')+
    `<div class="grid2">`+
      `<div><h4>Boden-Routing</h4>`+
        legRow('Flughafen→Stadion',c.routing.airport_to_ballpark)+
        legRow('Flughafen→Hotel',c.routing.airport_to_hotel)+
        legRow('Hotel→Stadion',c.routing.hotel_to_ballpark)+
        `<h4>Hotel-Empfehlung</h4>${hotel}</div>`+
      `<div><h4>Security-Briefing — ${c.risk_level} (${c.severity}/5)</h4>`+
        `<div class="haz">Posture: ${c.posture}</div>`+
        `<div class="haz">Med. Bereitschaft: ${c.trauma_center||'—'}</div>`+
        `<div class="haz">Transport-Planbarkeit: ${Math.round(c.transport_reliability*100)} %</div>`+
        `<h4>Saison-aktive Gefahren</h4>${haz}</div>`+
    `</div>`+
    `<div class="haz muted" style="margin-top:10px">Spieltag-Lage (aktuelle Bedrohungseinstufung, On-Call-EMS-Routing, VIP-/Protest-Lage) wird am Spieltag vom lokalen Law-Enforcement-/EMS-Liaison bestätigt.</div>`;
  host.appendChild(div);
  div.scrollIntoView({behavior:'smooth',block:'nearest'});
}

sel.onchange=()=>render(sel.value);
render(sel.value);
</script>
</body>
</html>
"""


def build(season_year: int, out_path: Path) -> None:
    payload = build_payload(season_year)
    html = (HTML_TEMPLATE
            .replace("__SEASON__", str(season_year))
            .replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    n_teams = len(payload["teams"])
    n_cities = sum(t["n_cities"] for t in payload["teams"].values())
    print(f"Ops-Dashboard geschrieben: {out_path} ({n_teams} Teams, {n_cities} Stadt-Dossiers)")


def main() -> int:
    ap = argparse.ArgumentParser(description="MLB Scheduler-Operations-Dashboard")
    ap.add_argument("--season", type=int, default=2024)
    ap.add_argument("--out", default=str(ROOT / "dashboard" / "ops.html"))
    args = ap.parse_args()
    build(args.season, Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
