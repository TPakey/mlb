#!/usr/bin/env python3
"""Transcribe Appendix C travel-time matrix, verify symmetry + anchors, emit JSON."""
import json, sys
OUT_PATH = "/sessions/amazing-hopeful-johnson/mnt/MLB Logistics Optimizer/data/appendix_c_travel_times.json"

# Column order as printed in the image (29 cols; no WSH column -> derive by symmetry)
COLS = ["ARI","ATL","BAL","BOS","CHI","CIN","CLE","COL","CWS","DET","HOU","KC",
        "LAA","LAD","MIA","MIL","MIN","NYM","NYY","OAK","PHI","PIT","SD","SF",
        "STL","SEA","TB","TEX","TOR"]

# Each row transcribed from the image. 29 values per row, aligned to COLS.
ROWS = {
"ARI": "0 3:11 4:01 4:36 2:54 3:10 3:30 1:10 2:54 3:23 2:02 2:06 :41 :43 3:58 2:56 2:34 4:17 4:17 1:18 4:10 3:39 :36 1:18 2:33 2:14 3:36 1:44 3:47",
"ATL": "3:11 0 1:09 1:52 1:10 :45 1:07 2:25 1:10 1:12 1:24 1:21 3:50 3:52 1:13 1:20 1:56 1:30 1:30 4:16 1:20 1:03 3:47 4:17 :56 4:22 :50 1:28 1:28",
"BAL": "4:01 1:09 0 :43 1:13 :51 :37 3:04 1:13 :48 2:30 1:56 4:37 4:38 1:55 1:17 1:58 :20 :20 4:54 :11 :24 4:36 4:55 1:28 4:40 1:42 2:27 :40",
"BOS": "4:36 1:52 :43 0 1:42 1:28 1:06 3:36 1:42 1:14 3:13 2:30 5:10 5:12 2:31 1:43 2:19 :23 :23 5:23 :33 :58 5:10 5:24 2:05 4:59 2:22 3:07 :52",
"CHI": "2:54 1:10 1:13 1:42 0 :30 :37 1:54 :30 :37 1:53 :44 3:28 3:29 2:22 :30 :49 1:26 1:26 3:42 1:21 :49 3:28 3:43 :31 3:28 2:00 1:36 :52",
"CIN": "3:10 :45 :51 1:28 :30 0 :26 2:14 :30 :28 1:48 1:05 3:46 3:48 1:55 :39 1:19 1:08 1:08 4:04 1:01 :30 3:45 4:05 :37 3:57 1:34 1:39 :49",
"CLE": "3:30 1:07 :37 1:06 :37 :26 0 2:27 :37 :11 2:14 1:24 4:05 4:06 2:10 :40 1:21 :49 :49 4:19 :43 :14 4:04 4:20 :59 4:03 1:52 2:04 :23",
"COL": "1:10 2:25 3:04 3:36 1:54 2:14 2:27 0 1:54 2:19 1:45 1:07 1:39 1:40 3:27 1:50 1:24 3:16 3:16 1:53 3:09 2:38 1:40 1:54 1:36 2:03 3:03 1:18 2:41",
"CWS": "2:54 1:10 1:13 1:42 :30 :30 :37 1:54 0 :37 1:53 :49 3:28 3:29 2:22 :30 :49 1:26 1:26 3:42 1:21 :49 3:28 3:43 :31 3:28 2:00 1:36 :52",
"DET": "3:23 1:12 :48 1:14 :37 :28 :11 2:19 :37 0 2:13 1:17 3:57 3:58 2:18 :30 1:11 :58 :58 4:10 :53 :25 3:57 4:11 :55 3:53 1:59 2:00 :25",
"HOU": "2:02 1:24 2:30 3:13 1:53 1:48 2:14 1:45 1:53 2:13 0 1:17 2:42 2:45 1:55 2:01 2:13 2:50 2:50 3:17 2:41 2:16 2:36 3:17 1:21 3:47 1:35 :29 2:36",
"KC":  "2:06 1:21 1:56 2:30 :44 1:05 1:24 1:07 :49 1:17 1:17 0 2:41 2:43 2:29 :53 :55 2:12 2:12 3:00 2:04 1:34 2:40 3:01 :29 3:01 2:04 :54 1:42",
"LAA": ":41 3:50 4:37 5:10 3:28 3:46 4:05 1:39 3:28 3:57 2:42 2:41 0 :03 4:38 3:28 3:01 4:53 4:53 :44 4:46 4:15 :11 :45 3:09 1:57 4:16 2:25 4:20",
"LAD": ":43 3:52 4:38 5:12 3:29 3:48 4:06 1:40 3:29 3:58 2:45 2:43 :03 0 4:41 3:29 3:02 4:54 4:54 :41 4:47 4:16 :13 :42 3:11 1:55 4:18 2:27 4:21",
"MIA": "3:58 1:13 1:55 2:31 2:22 1:55 2:10 3:27 2:22 2:18 1:55 2:29 4:38 4:41 0 2:32 3:09 2:11 2:11 5:10 2:02 2:01 4:33 5:11 2:07 5:28 :25 2:15 2:28",
"MIL": "2:56 1:20 1:17 1:43 :30 :39 :40 1:50 :30 :30 2:01 :53 3:28 3:29 2:32 0 :42 1:28 1:28 3:40 1:23 :54 3:29 3:41 :39 3:23 2:10 1:43 :52",
"MIN": "2:34 1:56 1:58 2:19 :49 1:19 1:21 1:24 :49 1:11 2:13 :55 3:01 3:02 3:09 :42 0 1:57 1:57 3:06 2:04 1:35 3:03 3:07 1:03 2:42 2:45 1:43 1:27",
"NYM": "4:17 1:30 :20 :23 1:26 1:08 :49 3:16 1:26 :58 2:50 2:12 4:53 4:54 2:11 1:28 1:57 0 0 5:08 :10 :38 4:52 5:09 1:45 4:49 2:00 2:46 :41",
"NYY": "4:17 1:30 :20 :23 1:26 1:08 :49 3:16 1:26 :58 2:50 2:12 4:53 4:54 2:11 1:28 1:57 0 0 5:08 :10 :38 4:52 5:09 1:45 4:49 2:00 2:46 :41",
"OAK": "1:18 4:16 4:54 5:23 3:42 4:04 4:19 1:53 3:42 4:10 3:17 3:00 :44 :41 5:10 3:40 3:06 5:08 5:08 0 5:02 4:31 :55 :01 3:28 1:21 4:47 2:55 4:31",
"PHI": "4:10 1:20 :11 :33 1:21 1:01 :43 3:09 1:21 :53 2:41 2:04 4:46 4:47 2:02 1:23 2:04 :10 :10 5:02 0 :31 4:45 5:03 1:37 4:46 1:51 2:37 :40",
"PIT": "3:39 1:03 :24 :58 :49 :30 :14 2:38 :49 :25 2:16 1:34 4:15 4:16 2:01 :54 1:35 :38 :38 4:31 :31 0 4:14 4:32 1:07 4:17 1:45 2:09 :27",
"SD":  ":36 3:47 4:36 5:10 3:28 3:45 4:04 1:40 3:28 3:57 2:36 2:40 :11 :13 4:33 3:29 3:03 4:52 4:52 :55 4:45 4:14 0 :55 3:08 2:08 4:11 2:20 4:20",
"SF":  "1:18 4:17 4:55 5:24 3:43 4:05 4:20 1:54 3:43 4:11 3:17 3:01 :45 :42 5:11 3:41 3:07 5:09 5:09 :01 5:03 4:32 :55 0 3:29 1:21 4:48 2:56 4:32",
"STL": "2:33 :56 1:28 2:05 :31 :37 :59 1:36 :31 :55 1:21 :29 3:09 3:11 2:07 :39 1:03 1:45 1:45 3:28 1:37 1:07 3:08 3:29 0 3:27 1:43 1:06 1:19",
"SEA": "2:14 4:22 4:40 4:59 3:28 3:57 4:03 2:03 3:28 3:53 3:47 3:01 1:57 1:55 5:28 3:23 2:42 4:49 4:49 1:21 4:46 4:17 2:08 1:21 3:27 0 5:03 3:20 4:08",
"TB":  "3:36 :50 1:42 2:22 2:00 1:34 1:52 3:03 2:00 1:59 1:35 2:04 4:16 4:18 :25 2:10 2:45 2:00 2:00 4:47 1:51 1:45 4:11 4:48 1:43 5:03 0 1:52 2:12",
"TEX": "1:44 1:28 2:27 3:07 1:36 1:39 2:04 1:18 1:36 2:00 :29 :54 2:25 2:27 2:15 1:43 1:43 2:46 2:46 2:55 2:37 2:09 2:20 2:56 1:06 3:20 1:52 0 2:25",
"TOR": "3:47 1:28 :40 :52 :52 :49 :23 2:41 :52 :25 2:36 1:42 4:20 4:21 2:28 :52 1:27 :41 :41 4:31 :40 :27 4:20 4:32 1:19 4:08 2:12 2:25 0",
"WSH": "3:58 1:05 :04 :47 1:11 :48 :37 3:02 1:11 :47 2:26 1:53 4:34 4:34 1:51 1:16 1:58 :25 :25 4:52 :15 :23 4:33 4:53 1:25 4:39 1:38 2:23 :42",
}

IMG2PROJ = {"CHI":"CHC","KC":"KCR","SD":"SDP","SF":"SFG","TB":"TBR","WSH":"WSN"}
def proj(x): return IMG2PROJ.get(x, x)

def to_min(s):
    s = s.strip()
    if s == "0": return 0
    if s.startswith(":"): return int(s[1:])
    h, m = s.split(":"); return int(h)*60 + int(m)

# Build raw value table keyed by IMAGE ids: raw[row][col] = minutes
raw = {}
for r, line in ROWS.items():
    vals = line.split()
    assert len(vals) == len(COLS), f"{r}: {len(vals)} values != {len(COLS)}"
    raw[r] = {c: to_min(v) for c, v in zip(COLS, vals)}

ALL = COLS + ["WSH"]  # 30 ids; WSH only has a row

# Symmetry check: for every unordered pair where both directions exist
mismatches = []
for a in ALL:
    for b in ALL:
        if a >= b: continue
        ab = raw.get(a, {}).get(b)
        ba = raw.get(b, {}).get(a)
        if ab is not None and ba is not None and ab != ba:
            mismatches.append((a, b, ab, ba))

print("=== SYMMETRY MISMATCHES ===")
if not mismatches:
    print("none")
for a, b, ab, ba in mismatches:
    print(f"{a}->{b}={ab}m  vs  {b}->{a}={ba}m")

# Anchors (image ids)
def fmt(m):
    return f"{m//60}:{m%60:02d}" if m>=60 else (f":{m:02d}" if m>0 else "0")
print("\n=== ANCHORS ===")
print("LAD-ATL:", fmt(raw['LAD']['ATL']), "(expect 3:52)")
print("LAD-CIN:", fmt(raw['LAD']['CIN']), "(expect 3:48)")
print("LAA-LAD:", fmt(raw['LAA']['LAD']), "(expect :03)")
print("OAK-SF :", fmt(raw['OAK']['SF']), "(expect :01)")
print("NYM-NYY:", fmt(raw['NYM']['NYY']), "(expect 0)")

if mismatches:
    sys.exit(1)

# ---- Build full symmetric 30x30 in PROJECT ids ----
proj_ids = sorted(proj(x) for x in ALL)
# minutes lookup by project id (symmetric); WSH row provides WSH column
pm = {}
for r in ALL:
    for c in ALL:
        if r == c:
            v = 0
        else:
            v = raw.get(r, {}).get(c)
            if v is None:  # only WSH column missing -> use WSH row (symmetry)
                v = raw[c][r]
        pm[(proj(r), proj(c))] = v

hhmm = {a: {b: fmt(pm[(a, b)]) for b in proj_ids} for a in proj_ids}
minutes = {a: {b: pm[(a, b)] for b in proj_ids} for a in proj_ids}

# final symmetry assert on projected full matrix
for a in proj_ids:
    for b in proj_ids:
        assert minutes[a][b] == minutes[b][a], (a, b)
        if a == b:
            assert minutes[a][b] == 0

out = {
    "__meta__": {
        "source": "MLB-MLBPA Basic Agreement 2022-2026, Appendix C — Travel Times for Scheduling",
        "description": "Official in-flight travel times between MLB cities, symmetric, diagonal 0.",
        "format": "H:MM strings in 'travel_times'; integer minutes in 'travel_minutes'.",
        "team_ids": "project IDs from data/teams.json (CHI->CHC, KC->KCR, SD->SDP, SF->SFG, TB->TBR, WSH->WSN)",
        "provenance": "Transcribed from official image (Jonas, 2026-06-09). Verified: full symmetry (0 mismatches), anchors LAD-ATL=3:52, LAD-CIN=3:48, LAA-LAD=:03, OAK-SF=:01, NYM=NYY=0.",
        "rating": "A1",
        "transcribed_by": "appendix_c transcription script, Sprint 5.1",
    },
    "travel_times": hhmm,
    "travel_minutes": minutes,
}

with open(OUT_PATH, "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False, sort_keys=True)
print(f"\nWROTE {OUT_PATH}  ({len(proj_ids)} teams, {len(proj_ids)**2} cells)")

