# Sprint 5.1 — Architektur-Design: Startzeit-Dimension

**Stand:** 2026-06-09. Design-Pass VOR der Implementierung (Jonas: „erst gründlich
planen, dann bauen"). Ziel: Startzeiten als Modell-Dimension einführen, sodass die
CBA-Startzeit-Regeln (V(C)(6)–(9)) hart durchsetzbar werden und TV-Fenster an Slots
gebunden werden können — **ohne den bewährten, deterministischen Reise-Optimierpfad
zu brechen**.

Grundlage: `regulations/CBA_2022-2026_Article_V_Scheduling.md` (Regeln verbatim),
`regulations/APPENDIX_C_README.md` (Reisezeiten), Code (`generator_optimizer.py`,
`timezones.py`, `compliance.py`, `tv_slots.py`).

---

## 1 — Designprinzip: Startzeit als separate, nachgelagerte Schicht

**Kernentscheidung:** Startzeiten werden **nicht** in die Reise-SA/CP-SAT als
zusätzliche Entscheidungsvariablen gemischt, sondern als **eigene, deterministische
Zuweisungs-Schicht** *nach* der date-level-Optimierung implementiert.

**Begründung (Trade-off-Analyse):**

| Ansatz | Pro | Contra | Urteil |
|---|---|---|---|
| **(i) Nachgelagerte Schicht** (empfohlen) | Reise-SA bleibt unverändert → **Determinismus trivial erhalten**; isoliert testbar; gegated | Reise-Entscheidung „sieht" Startzeit-Feasibility nicht direkt | **gewählt** |
| (ii) In SA/CP-SAT integriert | gemeinsame Optimierung | Suchraum-Explosion, Determinismus-/Tractability-Risiko, großer Rewrite | verworfen |

**Warum (i) tragfähig ist:** Reisedistanz hängt von **Städten und Tagen** ab, nicht
von Uhrzeiten. Die Startzeit-Zuweisung ist — bei fixierten Tagen — ein **fast
entkoppeltes, lokal lösbares** Feasibility-Problem pro Team-Tag. Die seltenen Fälle,
in denen eine date-level-Entscheidung start-time-infeasible wäre, werden über einen
**weichen Rückkopplungs-Penalty** an die SA gemeldet (statt voller Integration).

```
   ┌─────────────────────┐   fixe Tage    ┌────────────────────────┐
   │ Reise-SA / CP-SAT   │ ─────────────► │ Startzeit-Zuweisung    │
   │ (unverändert, P0)   │                │ src/start_times.py     │
   └─────────────────────┘ ◄───────────── └────────────────────────┘
            ▲   weicher Infeasibility-Penalty (optional, gegated)
```

---

## 2 — Slot-Modell

Jedes **Spiel** (nicht nur Serie — Spiele einer Serie können unterschiedliche Slots
haben) erhält einen Slot:

| Slot | Lokalzeit | Quelle |
|---|---|---|
| `DAY` | ~13:00 (frühestens, V(C)(6); Noon nur unter Bedingungen) | Default Tag-Spiel |
| `NIGHT` | ~19:00 | Default Abend-Spiel |
| `GETAWAY` | berechnet via V(C)(8): `19:00 − max(0, inflight − 2:30)` | wenn Reise zu Off-Day/Folgespiel |
| `TV_FIXED` | Netzwerk-vorgegeben (ESPN So 19:00 ET, Apple Fr, FOX Sa) | `tv_slots.json` |

Datenrepräsentation: `GameSlot = Enum + optional exakte `time`` (für GETAWAY/TV_FIXED).
Neue Datei `data/start_time_slots.json` hält **TV-Pins** + Default-Regeln pro Venue
(z. B. Lease-Day-Game-Limits aus V(C)(8)-Ausnahme).

---

## 3 — CBA-Regel-Mapping (was die Schicht durchsetzt)

| Regel | Durchsetzung in der Startzeit-Schicht |
|---|---|
| **V(C)(6)/(7)** Day-Game ≥ 13:00 (Noon nur mit Off-Day-Vortag / Spiel ≤24 h gleiche Stadt) | DAY-Slot validieren gegen Vortagskontext |
| **V(C)(8)** Getaway latest start = 19:00 − (inflight−2:30); **Ausnahme ESPN So-Night** | GETAWAY-Zeit aus Appendix-C-Lookup berechnen; SNB-Ausnahme |
| **V(C)(9)** kein Start < 17:00, wenn Club am Vorabend ≥ 19:00 in anderer Stadt (Ausnahmen: Inflight ≤ 1:30 + Feiertag/Opener; ≤6× Cubs/Chicago; Reschedule ≤1:30) | Slot-Untergrenze aus Vortags-Slot + Inflight |
| **TV-Fenster** (nun hart, FORK 1) | TV_FIXED-Slots gepinnt; übrige Slots dürfen sie nicht verletzen |

Alle Schwellen (2:30, 1:30) und die Inflight-Zeiten kommen aus **Appendix C** (echte
Matrix), nicht aus dem Schätzer.

---

## 4 — Determinismus-Strategie

- Die Startzeit-Schicht ist eine **reine deterministische Funktion** von (fixierter
  Plan + Appendix C + TV-Pins + Zeitzonen). **Kein RNG** (oder fester Seed).
- **Gating:** Default **off** → bestehende Outputs bleiben **bit-identisch**. Aktiviert
  per Flag (`--assign-start-times`). Neue Module/Datenfelder ändern den Default-Pfad nicht.
- Der optionale Rückkopplungs-Penalty an die SA ist ebenfalls gegated (Default 0).

---

## 5 — Pipeline- & Code-Integration

- **Neu:** `src/start_times.py` — `assign_start_times(season, appendix_c, tv_pins) -> SlotMap`,
  deterministisch; `validate_start_times(...)` für die V(C)(6)–(9)-Checks.
- **compliance.py:** neue Regeln `STARTTIME-GETAWAY` (V(C)(8)), `STARTTIME-NIGHTDAY`
  (V(C)(9)), `STARTTIME-DAYMIN` (V(C)(6)/(7)) — greifen nur, wenn Slots zugewiesen sind
  (sonst „skipped/inherited"). Severity hart.
- **tv_slots.py / data:** TV-Fenster werden zu Pins (hart) statt nur Score.
- **explain.py:** Startzeit-Begründung pro Getaway-Spiel (zeigt die V(C)(8)-Rechnung).

---

## 6 — Validierung gegen Ground Truth (der entscheidende Test)

Der **reale 2024- und 2025-Plan enthält bereits echte Startzeiten** und erfüllt die
CBA-Startzeit-Regeln. Damit:

1. **Reproduktions-Test:** Unsere Schicht weist dem realen Plan Slots/Zeiten zu und
   muss die **tatsächlichen Getaway-Startzeiten reproduzieren** (z. B. das dokumentierte
   Dodgers-Braves-5:38-PT-Spiel aus V(C)(8) + Appendix C). Trifft unsere Formel die
   realen Zeiten → Modell **bewiesen korrekt** an echten Daten.
2. **Compliance-Test:** Der reale Plan muss unter den neuen Checks 0 Verstöße zeigen
   (er ist per Konstruktion regelkonform) — falls nicht, ist unser Check falsch.

Akzeptanzkriterium 5.1: (a) Reproduktions-Test trifft die realen Getaway-Zeiten in
≥95 % der Fälle (Rest = dokumentierte Sonderregeln); (b) realer Plan compliant unter
den neuen Startzeit-Regeln; (c) Determinismus des Default-Pfads bit-identisch.

---

## 7 — Risiken & offene Punkte

- **Appendix-C-Transkription** muss verifiziert sein, bevor V(C)(8) scharf rechnet
  (sonst falsche Getaway-Zeiten) — Verifikations-Gate, s. `APPENDIX_C_README.md`.
- **Lokalzeit vs. Reisezeit:** V(C)(8) rechnet in Lokalzeit der abreisenden Stadt;
  Zeitzonen sauber über `timezones.py` (DST-korrekt) führen.
- **Rückkopplung an SA:** zunächst nur Penalty (weich); echte Integration nur, falls
  Messung zeigt, dass date-level-Pläne häufig start-time-infeasibel sind (unwahrscheinlich).
- **TV-Pins-Datenqualität:** hängt an der verifizierten TV-Spiel-Liste (5.3/C2).

---

## 8 — Umsetzungsschritte (wenn gebaut wird)

1. `data/appendix_c_travel_times.json` aus dem Bild transkribieren + verifizieren.
2. `src/start_times.py` (Zuweisung + Validierung), deterministisch, gegated.
3. Reproduktions-Test gegen reale 2024/2025-Getaway-Zeiten.
4. Compliance-Regeln STARTTIME-* ergänzen + realer Plan compliant.
5. TV-Pins (hart) verdrahten (nach C2-Datenstand).
6. Messung + Determinismus-Check → Block 5.1 abgeschlossen.
