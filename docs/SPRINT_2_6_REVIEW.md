# Sprint 2.6 Review — What-if CLI Demo

**Datum:** 2026-05-26
**Status:** ✅ Abgeschlossen

---

## Ziele des Sprints

| # | Deliverable | Status |
|---|---|---|
| Task #29 | `tools/whatif_demo.py` — interaktives CLI für alle 3 What-if-Szenario-Typen | ✅ |
| Task #30 | `tests/test_whatif_demo.py` — 40 Unit-Tests | ✅ |
| Task #31 | `docs/SPRINT_2_6_REVIEW.md` + Handover | ✅ |

---

## Was ist die What-if Demo?

`tools/whatif_demo.py` ist das primäre CLI-Werkzeug für MLB-Operatoren, um
schnelle Szenario-Analysen ohne Programmierkenntnis durchzuführen. Es
bündelt alle drei What-if-Szenario-Typen aus Sprint 2.5 in einem einzigen,
selbsterklärenden Skript mit vollständigem JSON-Report-Export.

---

## CLI-Interface

```bash
# Standard: alle 3 Szenarien, Saison 2026, Seed 42
python -m tools.whatif_demo

# Einzelne Szenarien
python -m tools.whatif_demo --scenario force      # NYY@BOS am 4. Juli
python -m tools.whatif_demo --scenario blackout   # HOU Minute Maid Park Konzert
python -m tools.whatif_demo --scenario compare    # Balanced vs. Travel-Optimiert

# Parameter
python -m tools.whatif_demo --seed 7 --sa-iter 5000 --verbose

# Export-Kontrolle
python -m tools.whatif_demo --json-out output/my_analysis.json
python -m tools.whatif_demo --no-json
```

### Alle Flags

| Flag | Typ | Default | Beschreibung |
|---|---|---|---|
| `--seed` | int | 42 | Master-Seed für Reproduzierbarkeit |
| `--sa-iter` | int | 3000 | SA-Iterationen für Pareto-Vergleich (Szenario 3) |
| `--scenario` | choice | all | `all` / `force` / `blackout` / `compare` |
| `--json-out` | str | "" | Ausgabepfad (leer = auto-Timestamp in `output/`) |
| `--no-json` | flag | False | Kein JSON-Export |
| `--verbose` | flag | False | Detaillierte Generator-Ausgabe |

---

## Szenarien im Detail

### Szenario 1 — Force Series: NYY@BOS am 4. Juli 2026

**Frage:** Was passiert mit Travel, Revenue und Fatigue, wenn die Yankees
am Independence Day in Fenway Park spielen?

**Algorithmus:**
1. Vorhandene NYY@BOS-Serie im aktuellen Plan finden (nächste zum 4. Juli)
2. Kollidierende Serien am 4. Juli identifizieren
3. Kollisionen durch Verschiebung auf nächsten freien Slot lösen
4. NYY@BOS auf 4. Juli legen
5. ParetoBundle-Delta berechnen

**Ausgabe-Beispiel:**
```
══════════════════════════════════════════════════════════════════════
  WHAT-IF: Force NYY@BOS — Independence Day 4. Juli
  NYY@BOS (3 Spiele) am 2026-07-04 (vorher: 2026-05-12)
──────────────────────────────────────────────────────────────────────
  Dimension                Original          Modifiziert  Delta
──────────────────────────────────────────────────────────────────────
  ✓ Reisedistanz          1,990,000.0 →  1,977,000.0 km (-0.7%)
  ✗ Gate-Revenue        8,000,000,000 →  7,998,000,000 USD (-0.0%)
  ~ Fatigue-Score             450.0 →            450.0 pts
  ...
```

Zusätzlich: pro Team (NYY, BOS) wird ein `TeamImpact` ausgegeben — Travel-Delta,
Heim/Auswärts-Delta und eine Liste der betroffenen Spiele.

---

### Szenario 2 — Venue Blackout: HOU Minute Maid Park, 15.–16. Aug 2026

**Frage:** Ein Konzert blockiert das Astros-Stadion für 2 Tage. Welche Serien
müssen verschoben werden, und was kostet das?

**Algorithmus:**
1. Alle HOU-Heimspiele am 15./16. Aug finden
2. Vollständige Serien dieser Spiele ermitteln
3. Jede Serie auf nächsten freien Slot nach dem 16. Aug verschieben
4. ParetoBundle-Delta zurückgeben

---

### Szenario 3 — Plan-Vergleich: Balanced vs. Travel-Optimiert

**Frage:** In welchen Dimensionen kauft man sich echte Verbesserung durch
Travel-Optimierung, welche verschlechtern sich?

**Algorithmus:**
1. Pareto-Front mit 6 Anker-Profilen berechnen (n_interior_points=0 für Speed)
2. "balanced"-Plan und "travel_min"-Plan aus der Front extrahieren
3. `whatif_compare()` → reiner Bundle-Vergleich (< 100ms)
4. Alle Pareto-Punkte in kompakter Tabelle anzeigen

---

## JSON-Report-Struktur

```json
{
  "meta": {
    "generated_at": "2026-05-26T14:30:00",
    "season": 2026,
    "seed": 42,
    "generator_time_s": 19.4,
    "n_games": 2432,
    "tool": "whatif_demo.py",
    "sprint": "2.6"
  },
  "scenarios": [
    {
      "scenario": "force_nyyatbos_jul4",
      "elapsed_s": 0.85,
      "feasible": true,
      "warnings": [],
      "n_better": 3,
      "n_worse": 2,
      "original_bundle": { ... },
      "modified_bundle": { ... },
      "deltas": [
        {
          "name": "travel_km",
          "label": "Reisedistanz",
          "original": 1990000.0,
          "modified": 1977000.0,
          "delta": -13000.0,
          "delta_pct": -0.65,
          "direction": "better"
        },
        ...
      ]
    },
    { "scenario": "blackout_hou_aug15", ... },
    { "scenario": "compare_balanced_vs_travel", ... }
  ]
}
```

---

## Test-Ergebnisse

```
tests/test_whatif_demo.py       40 passed   0.64s
```

| Klasse | Tests | Thema |
|---|---|---|
| `TestParseArgs` | 9 | argparse: alle Flags, Invalid-Input |
| `TestBuildCfg` | 6 | GeneratorConfig: Saison, Seed, Fatigue-Flag |
| `TestFmtTime` | 5 | Zeitformatierung ms / s |
| `TestResultToJsonEntry` | 8 | JSON-Struktur, Serialisierbarkeit, Unicode |
| `TestExportJson` | 7 | Datei-Erstellung, Pfad-Hierarchie, Meta-Felder |
| `TestRunDemoSmoke` | 5 | run_demo() Smoke-Tests, Szenario-Routing |

Alle öffentlichen Funktionen durch Mock-Patches getestet → kein Generator-Run
in Unit-Tests → 0.64s Laufzeit.

---

## Design-Entscheidungen

### Szenario-Routing via `--scenario`
Statt drei separater Demo-Skripte (demo_force.py, demo_blackout.py, etc.)
wurde ein einziges Skript mit `--scenario`-Flag gewählt. Das erleichtert
den Einstieg für ML-Operatoren: ein Befehl, alle Varianten.

### Szenario 3 mit n_interior_points=0
Die Pareto-Front wird für den Demo-Vergleich mit nur 6 Anker-Profilen
berechnet (Interior-Punkte werden übersprungen). Das reduziert die Laufzeit
von ~2 Minuten auf ~30 Sekunden und ist für einen Vergleich ausreichend.
Für eine vollständige Analyse verwendet man stattdessen `demo_pareto.py`.

### TeamImpact in Szenario 1 und 2
Der Team-spezifische Impact-Report gibt MLB-Operatoren einen direkten Blick
auf die betroffenen Teams — wichtiger als der Liga-Gesamt-Delta für
operative Entscheidungen ("Welches Team leidet am meisten?").

### JSON immer vollständig
Das JSON enthält alle 8 Dimension-Deltas, das vollständige Original- und
Modified-Bundle, Feasibility-Flag und Warnungen. Damit kann der Bericht
programmatisch weiterverarbeitet oder in ein Dashboard integriert werden.

---

## Bekannte Einschränkungen

- Szenario 3 erfordert eine vollständige Pareto-Front (6 SA-Läufe à ~5s).
  Mit `--sa-iter 500` ist ein schnellerer aber weniger genauer Durchlauf
  möglich.
- `analyze_team_impact()` verwendet einen Proxy für Travel-Delta
  (Standortwechsel × 500km), nicht exakte Haversine-Berechnung.
  Für exakte Zahlen: `compute_season_travel()` auf der modifizierten Season.
- Das Demo-Skript hat keinen interaktiven Modus. Für eine Browser-basierte
  What-if-UI: Sprint 2.7 (Web-Interface).
