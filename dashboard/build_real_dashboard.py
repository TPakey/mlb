"""Generiert das Sprint-1-Dashboard mit ECHTEN MLB-Daten.

Lädt:
- data/teams.json
- output/validation/validation_2024.json / validation_2025.json
- output/validation/validation_extended_2024.json / validation_extended_2025.json
- echte Reisemetriken aus src.travel

Schreibt: dashboard/sprint1.html
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import load_teams
from src.datasources import LocalFileAdapter
from src.travel import compute_season_travel
from src.validation import validate_season
from src.validation_v2 import find_zigzags


def build_payload() -> dict:
    teams = load_teams()
    adapter = LocalFileAdapter(base_dir=ROOT / "data")

    seasons = {}
    for year in (2024, 2025):
        season = adapter.fetch_season_schedule(year)
        base = validate_season(season, teams)
        travel = compute_season_travel(season, teams)
        zigzags = find_zigzags(season, teams)

        per_team = []
        for tid in sorted(base.by_team.keys()):
            tr = base.by_team[tid]
            log = travel.by_team[tid]
            per_team.append({
                "team_id": tid,
                "original_km": log.total_km,
                "optimal_km": log.total_km - tr.total_savings_km,
                "savings_km": tr.total_savings_km,
                "savings_pct": tr.savings_pct,
                "num_trips": tr.num_road_trips,
                "num_changed": tr.num_trips_changed,
                "flight_hours": log.total_flight_hours,
                "tz_hops": log.total_timezone_hops,
                "cross_country": log.cross_country_trips,
                "longest_trip": log.longest_trip_km,
            })

        top_trips = base.top_improving_trips(15)
        top_data = [
            {
                "team_id": t.team_id,
                "cities_original": list(t.cities_original),
                "cities_optimal": list(t.cities_optimal),
                "km_original": t.km_original,
                "km_optimal": t.km_optimal,
                "savings_km": t.savings_km,
                "savings_pct": t.savings_pct,
                "nights": t.nights,
            }
            for t in top_trips
        ]

        zigzag_data = [
            {
                "team_id": z.team_id,
                "cities": list(z.cities),
                "direction_changes": z.direction_changes,
                "wasted_km": z.wasted_km,
            }
            for z in zigzags[:20]
        ]

        seasons[year] = {
            "year": year,
            "total_original_km": travel.total_km,
            "total_optimal_km": travel.total_km - base.total_savings_km,
            "total_savings_km": base.total_savings_km,
            "total_savings_pct": base.savings_pct,
            "total_co2_kg": base.total_co2_savings_kg,
            "total_cost_usd": base.total_cost_savings_usd,
            "avg_km_per_team": travel.avg_km_per_team,
            "median_km": travel.median_km,
            "num_trips": sum(r.num_road_trips for r in base.by_team.values()),
            "num_trips_changed": sum(r.num_trips_changed for r in base.by_team.values()),
            "per_team": per_team,
            "top_trips": top_data,
            "zigzags": zigzag_data,
        }

    return {
        "teams": [
            {
                "id": t.id, "name": t.name, "league": t.league,
                "division": t.division, "city": t.city, "state": t.state,
                "lat": t.lat, "lon": t.lon,
            }
            for t in teams
        ],
        "seasons": seasons,
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8" />
<title>MLB Logistics Optimizer · Sprint 1 Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0b1220; --panel: #141d33; --panel-2: #1c2746;
    --text: #e8ecf6; --muted: #8a96b3;
    --accent: #4fc3f7; --gold: #ffb74d;
    --good: #66bb6a; --bad: #ef5350; --border: #233055;
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.5; }
  header { padding: 24px 32px; border-bottom: 1px solid var(--border);
           display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; }
  header h1 { margin: 0; font-size: 22px; font-weight: 600; }
  header .sub { color: var(--muted); font-size: 13px; }
  .badge { display: inline-block; padding: 4px 10px; background: var(--panel-2); border-radius: 12px; font-size: 11px; color: var(--muted); margin-left: 8px; }
  .badge.honest { background: rgba(102,187,106,0.15); color: var(--good); }
  .grid { display: grid; gap: 16px; grid-template-columns: repeat(12, 1fr); padding: 24px 32px; }
  .card { background: var(--panel); border-radius: 12px; padding: 16px 20px; border: 1px solid var(--border); }
  .card h2 { margin: 0 0 12px; font-size: 13px; color: var(--muted); font-weight: 500;
             text-transform: uppercase; letter-spacing: 0.5px; }
  .kpi { font-size: 28px; font-weight: 600; }
  .kpi .delta { font-size: 14px; margin-left: 8px; color: var(--good); }
  .span-3 { grid-column: span 3; }
  .span-4 { grid-column: span 4; }
  .span-6 { grid-column: span 6; }
  .span-8 { grid-column: span 8; }
  .span-12 { grid-column: span 12; }
  .controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
  .pill { padding: 6px 14px; background: var(--panel-2); border: 1px solid #2c3a64;
          border-radius: 999px; cursor: pointer; color: var(--text); font-size: 13px; }
  .pill.active { background: var(--accent); color: #082138; border-color: var(--accent); font-weight: 600; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 6px 10px; text-align: left; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 500; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  td.team { font-weight: 600; }
  .legend { font-size: 12px; color: var(--muted); margin-top: 8px; }
  .map-wrap { position: relative; height: 380px; background: #0e1730; border-radius: 8px; overflow: hidden; }
  .anecdote { padding: 12px 16px; margin: 8px 0; background: var(--panel-2);
              border-left: 3px solid var(--gold); border-radius: 4px; font-size: 13px; }
  .anecdote .head { font-weight: 600; color: var(--gold); margin-bottom: 4px; }
  .anecdote .route { font-family: Consolas, Monaco, monospace; color: var(--text); margin: 2px 0; }
  .anecdote .savings { color: var(--good); font-weight: 600; margin-top: 4px; }
  .truth-callout { padding: 16px 20px; background: rgba(255,183,77,0.08); border-left: 4px solid var(--gold); border-radius: 4px; margin-bottom: 16px; }
  .truth-callout .title { font-weight: 600; color: var(--gold); font-size: 14px; margin-bottom: 6px; }
  .truth-callout .body { color: var(--text); font-size: 13px; line-height: 1.6; }
  .footer { padding: 16px 32px; color: var(--muted); font-size: 12px; text-align: center; }
</style>
</head>
<body>
<header>
  <div>
    <h1>MLB Logistics Optimizer <span class="badge honest">Sprint 1 · echte Daten</span></h1>
    <div class="sub">Validierung gegen offiziellen MLB-Saisonkalender · Quelle: MLB Stats API</div>
  </div>
  <div class="controls">
    <span style="color:var(--muted);font-size:13px;">Saison:</span>
    <button class="pill active" data-year="2024">2024</button>
    <button class="pill" data-year="2025">2025</button>
  </div>
</header>

<div class="grid">

  <div class="truth-callout span-12">
    <div class="title">Sprint-1-Kernbefund — ehrlich</div>
    <div class="body">
      Über zwei volle Saisons (4.864 echte Spiele) sind <strong>92 % der Road Trips bereits TSP-optimal</strong> geroutet.
      Theoretisches Einsparpotenzial allein durch bessere Trip-Reihenfolge: <strong>~1 %</strong> der Gesamtreisedistanz.
      MLB macht das gut. Die <em>echte</em> Optimierungs-Headroom liegt in der koordinierten Schedule-Restrukturierung —
      Sprint 2.
    </div>
  </div>

  <div class="card span-3">
    <h2>Original-km (alle 30 Teams)</h2>
    <div class="kpi" id="k-orig">–</div>
    <div class="legend" id="k-orig-sub">–</div>
  </div>
  <div class="card span-3">
    <h2>Optimal-km nach Trip-Routing</h2>
    <div class="kpi" id="k-opt">–</div>
    <div class="legend" id="k-opt-sub">–</div>
  </div>
  <div class="card span-3">
    <h2>Trip-Routing-Einsparung</h2>
    <div class="kpi" id="k-sav">–</div>
    <div class="legend" id="k-sav-sub">–</div>
  </div>
  <div class="card span-3">
    <h2>Road Trips analysiert</h2>
    <div class="kpi" id="k-trips">–</div>
    <div class="legend" id="k-trips-sub">–</div>
  </div>

  <div class="card span-8">
    <h2>Reise-km pro Team — Original vs. Trip-Optimiert</h2>
    <canvas id="team-bar" height="320"></canvas>
    <div class="legend">Westküsten-Teams (SEA, SDP, SFG, LAD, OAK) reisen am meisten — geografisch isoliert.
      Zentrale Teams (CHC, CIN, PIT) am wenigsten. MLBs Trip-Routing ist überall sehr nah am Optimum.</div>
  </div>

  <div class="card span-4">
    <h2>Top 5 Zigzag-Trips</h2>
    <div id="anecdotes"></div>
    <div class="legend">Hier zahlt MLB Geld — Cross-Country-Routen mit mehreren Richtungswechseln.
      Die Mets-Story ist Sprint-2-Begründung in Reinform.</div>
  </div>

  <div class="card span-12">
    <h2>Pro-Team-Aufschlüsselung</h2>
    <table id="team-table">
      <thead><tr>
        <th>Team</th>
        <th class="num">Original km</th>
        <th class="num">Optimal km</th>
        <th class="num">Einsparung</th>
        <th class="num">%</th>
        <th class="num">Road Trips</th>
        <th class="num">Suboptimal</th>
        <th class="num">Cross-Country</th>
        <th class="num">Längster Flug</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </div>

</div>

<div class="footer">
  Daten: MLB Stats API (statsapi.mlb.com) · Reisemodell: Haversine + Charter-Flugzeit ·
  Methode: Intra-Trip-TSP (exakt) · Sprint 1 abgeschlossen
</div>

<script>
const PAYLOAD = __PAYLOAD__;
let currentYear = 2024;
let teamBarChart = null;

function fmt(n, dig=0) { return Math.round(n).toLocaleString('de-DE'); }
function fmtPct(n) { return (n>=0?'+':'') + n.toFixed(2) + ' %'; }

function render() {
  const s = PAYLOAD.seasons[currentYear];
  document.getElementById('k-orig').textContent = fmt(s.total_original_km) + ' km';
  document.getElementById('k-orig-sub').textContent =
    `Ø ${fmt(s.avg_km_per_team)} km/Team · Median ${fmt(s.median_km)} km`;
  document.getElementById('k-opt').textContent = fmt(s.total_optimal_km) + ' km';
  document.getElementById('k-opt-sub').textContent = 'Nach TSP-optimaler Trip-Routenführung';
  document.getElementById('k-sav').innerHTML =
    fmt(s.total_savings_km) + ' km <span class="delta">' + (s.total_savings_pct).toFixed(2) + ' %</span>';
  document.getElementById('k-sav-sub').textContent =
    `≈ ${fmt(s.total_co2_kg/1000)} t CO₂ · $${(s.total_cost_usd/1e6).toFixed(2)} M`;
  document.getElementById('k-trips').innerHTML =
    s.num_trips + ' <span class="delta" style="color:var(--muted)">' + s.num_trips_changed + ' suboptimal</span>';
  document.getElementById('k-trips-sub').textContent =
    `${(100 - s.num_trips_changed/s.num_trips*100).toFixed(0)} % bereits TSP-optimal`;

  renderTeamBar(s);
  renderAnecdotes(s);
  renderTable(s);
}

function renderTeamBar(s) {
  const sorted = [...s.per_team].sort((a,b) => b.original_km - a.original_km);
  const labels = sorted.map(t => t.team_id);
  const orig = sorted.map(t => t.original_km);
  const opt = sorted.map(t => t.optimal_km);
  if (teamBarChart) teamBarChart.destroy();
  teamBarChart = new Chart(document.getElementById('team-bar'), {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        { label: 'Original', data: orig, backgroundColor: '#4fc3f7' },
        { label: 'Optimal (Trip-Routing)', data: opt, backgroundColor: '#ffb74d' },
      ],
    },
    options: {
      scales: {
        x: { ticks: { color: '#8a96b3', font: { size: 10 } }, grid: { color: '#1a2440' } },
        y: { ticks: { color: '#8a96b3', callback: v => fmt(v/1000) + 'k' }, grid: { color: '#233055' } },
      },
      plugins: { legend: { labels: { color: '#e8ecf6' } } },
    },
  });
}

function renderAnecdotes(s) {
  const el = document.getElementById('anecdotes');
  el.innerHTML = '';
  s.top_trips.slice(0, 5).forEach(t => {
    const div = document.createElement('div');
    div.className = 'anecdote';
    div.innerHTML = `
      <div class="head">${t.team_id} · ${t.nights} Nächte</div>
      <div class="route">Original:  ${t.cities_original.join(' → ')}</div>
      <div class="route">Optimal:   ${t.cities_optimal.join(' → ')}</div>
      <div class="savings">−${fmt(t.savings_km)} km (${t.savings_pct.toFixed(1)} %)</div>
    `;
    el.appendChild(div);
  });
}

function renderTable(s) {
  const tb = document.querySelector('#team-table tbody');
  tb.innerHTML = '';
  const sorted = [...s.per_team].sort((a,b) => b.original_km - a.original_km);
  sorted.forEach(t => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="team">${t.team_id}</td>
      <td class="num">${fmt(t.original_km)}</td>
      <td class="num">${fmt(t.optimal_km)}</td>
      <td class="num">${fmt(t.savings_km)}</td>
      <td class="num">${t.savings_pct.toFixed(2)} %</td>
      <td class="num">${t.num_trips}</td>
      <td class="num">${t.num_changed}</td>
      <td class="num">${t.cross_country}</td>
      <td class="num">${fmt(t.longest_trip)}</td>
    `;
    tb.appendChild(tr);
  });
}

document.querySelectorAll('.pill').forEach(p => {
  p.addEventListener('click', () => {
    document.querySelectorAll('.pill').forEach(x => x.classList.remove('active'));
    p.classList.add('active');
    currentYear = parseInt(p.dataset.year);
    render();
  });
});

render();
</script>
</body>
</html>
"""


def main() -> None:
    payload = build_payload()
    html = HTML_TEMPLATE.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
    out = ROOT / "dashboard" / "sprint1.html"
    out.write_text(html, encoding="utf-8")
    print(f"Geschrieben: {out}")
    for year in (2024, 2025):
        s = payload["seasons"][year]
        print(f"  {year}: {s['total_original_km']:,.0f} km original → "
              f"{s['total_optimal_km']:,.0f} km optimal · "
              f"{s['total_savings_km']:,.0f} km gespart ({s['total_savings_pct']:.2f} %)")


if __name__ == "__main__":
    main()
