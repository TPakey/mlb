"""Generiert das interaktive Dashboard als eigenständige HTML-Datei.

Liest:
- data/teams.json
- data/soft_factors.json
- output/profile_comparison.json
- output/<profile>/baseline_schedule.json
- output/<profile>/optimized_schedule.json
- output/<profile>/baseline_metrics.json
- output/<profile>/optimized_metrics.json
- output/<profile>/scores.json
- output/<profile>/narrative.md

Schreibt: dashboard/index.html
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "output"
DASH = ROOT / "dashboard"


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def build() -> str:
    teams = load(DATA / "teams.json")
    soft = load(DATA / "soft_factors.json")
    compare = load(OUT / "profile_comparison.json")

    profile_data = {}
    for p in compare["profiles"]:
        slug = p["profile"]["name"].lower().replace(" ", "_").replace("-", "_")
        # Profile-Slug bei "Revenue Max" -> "revenue_max", "Player Health" -> "player_health"
        # Im output-Ordner gespeichert als 'revenue_max', etc.
        slug_for_dir = {
            "balanced": "balanced",
            "player_health": "player_health",
            "revenue_max": "revenue_max",
            "fan_first": "fan_first",
            "sustainability": "sustainability",
            "fairness": "fairness",
        }.get(slug, slug)
        d = OUT / slug_for_dir
        if not d.exists():
            continue
        profile_data[slug] = {
            "meta": p,
            "baseline": load(d / "baseline_schedule.json"),
            "optimized": load(d / "optimized_schedule.json"),
            "baseline_metrics": load(d / "baseline_metrics.json"),
            "optimized_metrics": load(d / "optimized_metrics.json"),
            "scores": load(d / "scores.json"),
            "narrative": (d / "narrative.md").read_text(encoding="utf-8"),
        }

    payload = {
        "teams": teams["teams"],
        "soft_factors": soft,
        "profiles": profile_data,
        "comparison": compare["profiles"],
    }

    payload_json = json.dumps(payload, ensure_ascii=False)

    html = HTML_TEMPLATE.replace("__PAYLOAD__", payload_json)
    (DASH / "index.html").write_text(html, encoding="utf-8")
    print(f"Dashboard geschrieben: {DASH / 'index.html'}")
    return str(DASH / "index.html")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>MLB Logistics Optimizer · Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0b1220;
    --panel: #141d33;
    --panel-2: #1c2746;
    --text: #e8ecf6;
    --muted: #8a96b3;
    --accent: #4fc3f7;
    --accent-2: #ffb74d;
    --good: #66bb6a;
    --bad: #ef5350;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
  }
  header {
    padding: 24px 32px;
    border-bottom: 1px solid #233055;
    display: flex; align-items: center; justify-content: space-between;
  }
  header h1 { margin: 0; font-size: 22px; font-weight: 600; }
  header .sub { color: var(--muted); font-size: 13px; }
  .grid {
    display: grid; gap: 16px;
    grid-template-columns: repeat(12, 1fr);
    padding: 24px 32px;
  }
  .card {
    background: var(--panel);
    border-radius: 12px;
    padding: 16px 20px;
    border: 1px solid #233055;
  }
  .card h2 { margin: 0 0 12px; font-size: 14px; color: var(--muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }
  .kpi { font-size: 28px; font-weight: 600; }
  .kpi .delta { font-size: 14px; margin-left: 8px; }
  .delta.good { color: var(--good); }
  .delta.bad { color: var(--bad); }
  .span-3 { grid-column: span 3; }
  .span-4 { grid-column: span 4; }
  .span-6 { grid-column: span 6; }
  .span-8 { grid-column: span 8; }
  .span-12 { grid-column: span 12; }
  .controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
  .profile-btn {
    padding: 8px 14px; background: var(--panel-2); border: 1px solid #2c3a64;
    border-radius: 999px; cursor: pointer; color: var(--text); font-size: 13px;
  }
  .profile-btn.active { background: var(--accent); color: #082138; border-color: var(--accent); font-weight: 600; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid #233055; }
  th { color: var(--muted); font-weight: 500; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  .legend { font-size: 12px; color: var(--muted); margin-top: 6px; }
  .map-wrap { position: relative; height: 420px; background: #0e1730; border-radius: 8px; overflow: hidden; }
  .penalty { padding: 8px 12px; margin: 6px 0; background: var(--panel-2); border-left: 3px solid var(--bad); border-radius: 4px; font-size: 13px; }
  .penalty .name { font-weight: 600; }
  .penalty .desc { color: var(--muted); font-size: 12px; margin-top: 2px; }
  .narrative { background: var(--panel-2); padding: 16px 20px; border-radius: 8px; font-size: 14px; }
  .narrative h1 { font-size: 18px; margin-top: 0; }
  .narrative h2 { font-size: 14px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 16px; }
  .narrative li { margin: 4px 0; }
  select { background: var(--panel-2); color: var(--text); border: 1px solid #2c3a64; padding: 6px 10px; border-radius: 4px; }
  .footer { padding: 16px 32px; color: var(--muted); font-size: 12px; text-align: center; }
</style>
</head>
<body>
<header>
  <div>
    <h1>MLB Logistics Optimizer</h1>
    <div class="sub">League-Grade Scheduling Intelligence · Saison 2026 · 30 Teams</div>
  </div>
  <div class="controls" id="profile-selector"></div>
</header>

<div class="grid">

  <!-- KPI-Karten -->
  <div class="card span-3">
    <h2>Reisedistanz (km)</h2>
    <div class="kpi" id="kpi-km">–</div>
    <div class="legend" id="kpi-km-sub">–</div>
  </div>
  <div class="card span-3">
    <h2>CO₂-Footprint (t)</h2>
    <div class="kpi" id="kpi-co2">–</div>
    <div class="legend" id="kpi-co2-sub">–</div>
  </div>
  <div class="card span-3">
    <h2>Reisekosten ($M)</h2>
    <div class="kpi" id="kpi-cost">–</div>
    <div class="legend" id="kpi-cost-sub">–</div>
  </div>
  <div class="card span-3">
    <h2>Gewichtete Kosten</h2>
    <div class="kpi" id="kpi-cost-w">–</div>
    <div class="legend" id="kpi-cost-w-sub">–</div>
  </div>

  <!-- Score Radar + Penalty-Liste -->
  <div class="card span-6">
    <h2>Multi-Score-Vergleich (Baseline → Optimiert)</h2>
    <canvas id="radar" height="280"></canvas>
    <div class="legend">7 Dimensionen: Travel, Fatigue, Fairness, Broadcast, Revenue, Weather, Resilience. Niedriger ist besser für Travel/Fatigue/Weather; höher ist besser für Broadcast-Value.</div>
  </div>

  <div class="card span-6">
    <h2>Aktive Penalties im optimierten Plan</h2>
    <div id="penalty-list"></div>
  </div>

  <!-- USA-Karte mit Reiserouten -->
  <div class="card span-8">
    <h2>Stadien & Reiseroute eines Teams
      <select id="team-select" style="float:right"></select>
    </h2>
    <div class="map-wrap"><svg id="map" viewBox="0 0 1000 600" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100%"></svg></div>
    <div class="legend">Grau = alle 30 Stadien · Blau = Heimstadion des ausgewählten Teams · Orange = Auswärtsstationen (in Reihenfolge der Saison im optimierten Plan)</div>
  </div>

  <!-- Team-Tabelle: km pro Team -->
  <div class="card span-4">
    <h2>Reisekilometer pro Team</h2>
    <div style="max-height:420px;overflow-y:auto">
      <table id="team-table">
        <thead><tr><th>Team</th><th class="num">Baseline km</th><th class="num">Optimiert km</th><th class="num">Δ</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <!-- Profil-Vergleich (alle Profile) -->
  <div class="card span-6">
    <h2>Profil-Vergleich (alle Tradeoff-Profile)</h2>
    <canvas id="profile-bar" height="220"></canvas>
    <div class="legend">Pareto-Beobachtung: kein Profil dominiert in allen Dimensionen.</div>
  </div>

  <!-- Narrative -->
  <div class="card span-6">
    <h2>KI-Erklärung</h2>
    <div class="narrative" id="narrative">–</div>
  </div>

</div>

<div class="footer">
  Forschungsprototyp · Travel-Modell vereinfacht (Haversine, Charter-Flugzeit) · Konfigurierbare Tradeoff-Profile · Daten: kuratierte MLB-Stammdaten (basiert auf MLB Stats API)
</div>

<script>
  const PAYLOAD = __PAYLOAD__;

  /* ---------- Setup ---------- */

  const profileSelector = document.getElementById('profile-selector');
  const profileKeys = Object.keys(PAYLOAD.profiles);
  let currentProfile = profileKeys[0];

  profileKeys.forEach((k, i) => {
    const btn = document.createElement('button');
    btn.className = 'profile-btn' + (i === 0 ? ' active' : '');
    btn.textContent = PAYLOAD.profiles[k].meta.profile.name;
    btn.onclick = () => switchProfile(k, btn);
    profileSelector.appendChild(btn);
  });

  /* ---------- Team-Selector ---------- */

  const teamSelect = document.getElementById('team-select');
  PAYLOAD.teams.forEach(t => {
    const o = document.createElement('option');
    o.value = t.id;
    o.textContent = t.name;
    teamSelect.appendChild(o);
  });
  teamSelect.value = 'LAD';
  teamSelect.onchange = render;

  /* ---------- Map Projection (vereinfachte Albers-ähnliche Lage) ---------- */

  // Bounding box der 30 Stadien (mit Toronto im Norden)
  // Lat: 25.78 (MIA) — 47.59 (SEA);  Lon: -122.39 (SFG) — -71.10 (BOS)
  function project(lat, lon) {
    const x = ((lon + 130) / 60) * 1000;       // -130..-70 -> 0..1000
    const y = (1 - (lat - 24) / 26) * 600;     // 24..50 -> 600..0
    return { x, y };
  }

  function drawMap() {
    const svg = document.getElementById('map');
    svg.innerHTML = '';
    // Hintergrund: leichte USA-Outline (rechteckiges Frame als Platzhalter)
    const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    bg.setAttribute('x', 0); bg.setAttribute('y', 0);
    bg.setAttribute('width', 1000); bg.setAttribute('height', 600);
    bg.setAttribute('fill', '#0c1428');
    svg.appendChild(bg);

    // Dezente Längen-/Breitengrade
    for (let lon = -120; lon <= -70; lon += 10) {
      const x = project(0, lon).x;
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', x); line.setAttribute('x2', x);
      line.setAttribute('y1', 0); line.setAttribute('y2', 600);
      line.setAttribute('stroke', '#1d2747'); line.setAttribute('stroke-width', '1');
      svg.appendChild(line);
    }
    for (let lat = 30; lat <= 50; lat += 5) {
      const y = project(lat, 0).y;
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', 0); line.setAttribute('x2', 1000);
      line.setAttribute('y1', y); line.setAttribute('y2', y);
      line.setAttribute('stroke', '#1d2747'); line.setAttribute('stroke-width', '1');
      svg.appendChild(line);
    }

    const teamId = teamSelect.value;
    const tById = Object.fromEntries(PAYLOAD.teams.map(t => [t.id, t]));
    const home = tById[teamId];

    // Route aus dem optimierten Plan
    const sched = PAYLOAD.profiles[currentProfile].optimized.series;
    const ofTeam = sched
      .filter(s => s.home === teamId || s.away === teamId)
      .sort((a, b) => a.slot - b.slot);
    const route = [teamId];
    ofTeam.forEach(s => {
      if (s.home !== route[route.length - 1]) route.push(s.home);
    });
    if (route[route.length - 1] !== teamId) route.push(teamId);

    // Reiselinien
    for (let i = 0; i < route.length - 1; i++) {
      const a = tById[route[i]];
      const b = tById[route[i + 1]];
      const pa = project(a.lat, a.lon);
      const pb = project(b.lat, b.lon);
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', pa.x); line.setAttribute('y1', pa.y);
      line.setAttribute('x2', pb.x); line.setAttribute('y2', pb.y);
      line.setAttribute('stroke', '#ffb74d');
      line.setAttribute('stroke-width', '1.5');
      line.setAttribute('opacity', '0.45');
      svg.appendChild(line);
    }

    // Alle Stadien als Punkte
    PAYLOAD.teams.forEach(t => {
      const p = project(t.lat, t.lon);
      const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      c.setAttribute('cx', p.x); c.setAttribute('cy', p.y);
      c.setAttribute('r', t.id === teamId ? 9 : 4);
      c.setAttribute('fill', t.id === teamId ? '#4fc3f7' : '#5d6a8a');
      const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      title.textContent = t.name + ' — ' + t.stadium;
      c.appendChild(title);
      svg.appendChild(c);
    });

    // Stops mit Reihenfolge
    const stops = route.slice(1, -1);
    stops.forEach((id, idx) => {
      const t = tById[id];
      const p = project(t.lat, t.lon);
      const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      c.setAttribute('cx', p.x); c.setAttribute('cy', p.y);
      c.setAttribute('r', 5);
      c.setAttribute('fill', '#ffb74d');
      svg.appendChild(c);
    });
  }

  /* ---------- Radar Chart ---------- */

  let radarChart = null;
  function drawRadar() {
    const scores = PAYLOAD.profiles[currentProfile].scores;
    const ib = scores.initial, fb = scores.final;
    const dims = ['travel', 'fatigue', 'fairness', 'weather', 'resilience'];
    // Wir invertieren die Werte zu einem "Quality-Score": je niedriger der Score, desto näher am Maximum.
    // Maxwert pro Achse aus Baseline.
    const maxes = dims.map(d => Math.max(ib[d].score, fb[d].score, 1));
    const baseN = dims.map((d, i) => Math.max(0, 100 - (ib[d].score / maxes[i]) * 100));
    const optN = dims.map((d, i) => Math.max(0, 100 - (fb[d].score / maxes[i]) * 100));

    const ctx = document.getElementById('radar');
    if (radarChart) radarChart.destroy();
    radarChart = new Chart(ctx, {
      type: 'radar',
      data: {
        labels: ['Travel', 'Fatigue', 'Fairness', 'Weather', 'Resilience'],
        datasets: [
          { label: 'Baseline', data: baseN, borderColor: '#8a96b3', backgroundColor: 'rgba(138,150,179,0.2)' },
          { label: 'Optimiert', data: optN, borderColor: '#4fc3f7', backgroundColor: 'rgba(79,195,247,0.3)' },
        ],
      },
      options: {
        scales: { r: { min: 0, max: 100, ticks: { color: '#8a96b3', backdropColor: 'transparent' }, grid: { color: '#233055' }, angleLines: { color: '#233055' }, pointLabels: { color: '#e8ecf6' } } },
        plugins: { legend: { labels: { color: '#e8ecf6' } } },
        elements: { point: { radius: 3 } },
      },
    });
  }

  /* ---------- Profil-Vergleichsbalken ---------- */

  let profileBarChart = null;
  function drawProfileBar() {
    const names = PAYLOAD.comparison.map(p => p.profile.name);
    const travel = PAYLOAD.comparison.map(p => p.travel_km);
    const cost = PAYLOAD.comparison.map(p => p.final_cost);
    const ctx = document.getElementById('profile-bar');
    if (profileBarChart) profileBarChart.destroy();
    profileBarChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: names,
        datasets: [
          { label: 'Travel-km', data: travel, backgroundColor: '#4fc3f7', yAxisID: 'y' },
          { label: 'Gewichtete Kosten', data: cost, backgroundColor: '#ffb74d', yAxisID: 'y1' },
        ],
      },
      options: {
        scales: {
          x: { ticks: { color: '#e8ecf6' }, grid: { color: '#233055' } },
          y: { type: 'linear', position: 'left', ticks: { color: '#4fc3f7' }, grid: { color: '#233055' } },
          y1: { type: 'linear', position: 'right', ticks: { color: '#ffb74d' }, grid: { display: false } },
        },
        plugins: { legend: { labels: { color: '#e8ecf6' } } },
      },
    });
  }

  /* ---------- Penalty-Liste ---------- */

  function renderPenalties() {
    const fb = PAYLOAD.profiles[currentProfile].scores.final;
    const list = document.getElementById('penalty-list');
    list.innerHTML = '';
    const hits = [];
    for (const cat of ['travel', 'fatigue', 'fairness', 'broadcast', 'weather', 'resilience']) {
      const ph = fb[cat]?.penalty_hits || {};
      for (const code in ph) hits.push({ code, n: ph[code], cat });
    }
    if (hits.length === 0) {
      list.innerHTML = '<div class="legend">Keine offenen Penalties — sauberer Plan.</div>';
      return;
    }
    hits.sort((a, b) => b.n - a.n);
    hits.forEach(h => {
      const div = document.createElement('div');
      div.className = 'penalty';
      const name = PENALTY_LABELS[h.code] || h.code;
      const desc = PENALTY_DESCS[h.code] || '';
      div.innerHTML = `<div class="name">${name} <span style="color:var(--muted);font-weight:400">· ${h.n}× ausgelöst</span></div><div class="desc">${desc}</div>`;
      list.appendChild(div);
    });
  }

  const PENALTY_LABELS = {
    "TRV_EAST_OVERNIGHT": "Westküste→Ostküste Übernachtflug",
    "TRV_FOURTH_TZ_8DAYS": "4. Zeitzonen-Hop in 8 Tagen",
    "TRV_CROSS_COUNTRY_TURNAROUND": "Cross-Country mit <24h Pause",
    "FAT_14_CONSEC_GAMES": "14+ Spiele in Serie ohne Off-Day",
    "FAT_LATE_ARRIVAL_RUN": "3 späte Ankünfte in 5 Tagen",
    "FAT_COMPRESSED_SCHEDULE": "Verdichteter Spielplan (Doubleheader nach Reisetag)",
    "FAIR_REST_DELTA_4PLUS": "Rest-Differenz >4 Tage zwischen Gegnern",
    "FAIR_ELITE_OPP_CLUSTER": "Elite-Gegner-Cluster ungleich verteilt",
    "BCAST_RIVALRY_HIDDEN": "Top-Rivalität ausserhalb Primetime",
    "BCAST_HOLIDAY_NO_MARQUEE": "Feiertag ohne hochwertiges Matchup",
    "REV_WEEKEND_LOW_DEMAND": "Schwacher Gegner an Top-Wochenende",
    "WX_COLD_OPEN_APRIL": "Heimserie in Kaltstadt im April (offenes Dach)",
    "WX_HEAT_DAY_GAME": "Tagspiel in Hitzestadt im Hochsommer",
    "WX_HURRICANE_WINDOW": "Heimserie im Hurricane-Risikofenster",
    "RES_NO_REPAIR_PATH": "Keine einfache Wiederholungs-Option bei Ausfall",
  };
  const PENALTY_DESCS = {
    "TRV_EAST_OVERNIGHT": "Eines der härtesten Belastungsmuster — kombiniert späten Abendflug mit Schlafdefizit am Folgetag.",
    "TRV_FOURTH_TZ_8DAYS": "Mehrere Zeitzonenwechsel in kurzer Folge führen zu kumulativer Müdigkeit.",
    "TRV_CROSS_COUNTRY_TURNAROUND": "Über 3000 km Flug ohne Erholungstag — hohes Verletzungsrisiko.",
    "FAT_14_CONSEC_GAMES": "Belastet Bullpen und Recovery; mehrere Verletzungen in MLB-Historie korrelierten damit.",
    "FAT_LATE_ARRIVAL_RUN": "Schlaf-Defizit akkumuliert, Performance sinkt nachweislich.",
    "FAT_COMPRESSED_SCHEDULE": "Doppelschicht nach Übernacht-Reise — operativ kritisch.",
    "FAIR_REST_DELTA_4PLUS": "Ein Team hat substantiellen Erholungsvorsprung über Gegner.",
    "FAIR_ELITE_OPP_CLUSTER": "Mehrere Top-Gegner direkt hintereinander, verletzt sportliche Fairness.",
    "BCAST_RIVALRY_HIDDEN": "Wertvolles Matchup landet in einem Slot ohne nationale TV-Reichweite.",
    "BCAST_HOLIDAY_NO_MARQUEE": "Feiertage brauchen attraktive Spiele zur Reichweiten-Maximierung.",
    "REV_WEEKEND_LOW_DEMAND": "Knappe Top-Wochenend-Slots an niedrigfrequente Märkte verschwendet.",
    "WX_COLD_OPEN_APRIL": "Schnee/Frost: Spielqualität sinkt, Verletzungsrisiko steigt.",
    "WX_HEAT_DAY_GAME": "Hitze-Stress für Spieler und Fans.",
    "WX_HURRICANE_WINDOW": "Reise-/Stadion-Risiko und Wettervorbehalt.",
    "RES_NO_REPAIR_PATH": "Bei Ausfall nur über Doubleheader-Stress nachholbar.",
  };

  /* ---------- KPIs ---------- */

  function fmt(n, dig=0) { return n.toLocaleString('de-DE', { maximumFractionDigits: dig }); }
  function fmtSigned(n, dig=1) {
    const s = (n >= 0 ? '+' : '');
    return s + n.toLocaleString('de-DE', { maximumFractionDigits: dig });
  }
  function pct(a, b) { return ((b - a) / a) * 100; }

  function renderKPIs() {
    const pdata = PAYLOAD.profiles[currentProfile];
    const b = pdata.baseline_metrics, o = pdata.optimized_metrics;

    const kmDelta = pct(b.total_km, o.total_km);
    document.getElementById('kpi-km').innerHTML = fmt(o.total_km) +
      ` <span class="delta ${kmDelta < 0 ? 'good' : 'bad'}">${fmtSigned(kmDelta)}%</span>`;
    document.getElementById('kpi-km-sub').textContent =
      `Baseline ${fmt(b.total_km)} km`;

    document.getElementById('kpi-co2').innerHTML = fmt(o.total_co2_kg / 1000, 0) +
      ` <span class="delta ${kmDelta < 0 ? 'good' : 'bad'}">${fmtSigned(kmDelta)}%</span>`;
    document.getElementById('kpi-co2-sub').textContent =
      `−${fmt((b.total_co2_kg - o.total_co2_kg) / 1000)} t gegenüber Baseline`;

    document.getElementById('kpi-cost').innerHTML = (o.total_cost_usd / 1e6).toFixed(2) +
      ` <span class="delta ${kmDelta < 0 ? 'good' : 'bad'}">${fmtSigned(kmDelta)}%</span>`;
    document.getElementById('kpi-cost-sub').textContent =
      `−$${((b.total_cost_usd - o.total_cost_usd) / 1e6).toFixed(2)} M gespart`;

    const sc = pdata.scores;
    const dCost = pct(sc.initial_cost, sc.final_cost);
    document.getElementById('kpi-cost-w').innerHTML = fmt(sc.final_cost) +
      ` <span class="delta ${dCost < 0 ? 'good' : 'bad'}">${fmtSigned(dCost)}%</span>`;
    document.getElementById('kpi-cost-w-sub').textContent =
      `Profilgewichtete Gesamtkosten (Travel + Soft-Penalties)`;
  }

  /* ---------- Team-Tabelle ---------- */

  function renderTable() {
    const pdata = PAYLOAD.profiles[currentProfile];
    const tb = document.querySelector('#team-table tbody');
    tb.innerHTML = '';
    const rows = [];
    for (const tid in pdata.baseline_metrics.by_team) {
      const b = pdata.baseline_metrics.by_team[tid].total_km;
      const o = pdata.optimized_metrics.by_team[tid].total_km;
      rows.push({ tid, b, o, d: o - b });
    }
    rows.sort((a, b) => a.d - b.d);
    rows.forEach(r => {
      const tr = document.createElement('tr');
      const deltaCls = r.d < 0 ? 'good' : (r.d > 0 ? 'bad' : '');
      tr.innerHTML = `<td>${r.tid}</td><td class="num">${fmt(r.b)}</td><td class="num">${fmt(r.o)}</td><td class="num"><span class="delta ${deltaCls}">${fmtSigned(r.d, 0)}</span></td>`;
      tb.appendChild(tr);
    });
  }

  /* ---------- Narrative ---------- */

  function renderNarrative() {
    const md = PAYLOAD.profiles[currentProfile].narrative;
    // Mini-Markdown-Konvertierung (nur Headers + Listen)
    const html = md
      .replace(/^# (.*)$/gm, '<h1>$1</h1>')
      .replace(/^## (.*)$/gm, '<h2>$1</h2>')
      .replace(/^- (.*)$/gm, '<li>$1</li>')
      .replace(/(<li>.*?<\/li>(\n)?)+/gs, m => '<ul>' + m + '</ul>')
      .replace(/\n\n/g, '</p><p>');
    document.getElementById('narrative').innerHTML = '<p>' + html + '</p>';
  }

  /* ---------- Switch ---------- */

  function switchProfile(k, btn) {
    currentProfile = k;
    document.querySelectorAll('.profile-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    render();
  }

  function render() {
    renderKPIs();
    drawRadar();
    drawProfileBar();
    drawMap();
    renderPenalties();
    renderTable();
    renderNarrative();
  }

  render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
