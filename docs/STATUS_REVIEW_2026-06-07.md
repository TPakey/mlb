# Status-Review — Stand 2026-06-07 (Ende der Sprint-3-Session)

Kurzes Lagebild: **Was haben wir? Was fehlt? Was musst du (Jonas) noch tun?**

## Was wir jetzt haben (diese Session gebaut, getestet, dokumentiert)

**P0 — Produktionspfad festgeschrieben.** Warm-Start ist der einzige
Auslieferungspfad (CBA-konform, schlägt den realen Plan −5,4 %/2024). From-Scratch
nur noch Validierung. `docs/DECISION_P0_PRODUCTION_PATH.md`.

**P1 — Verteidigbarkeit + Realregeln + Verdichtung.**
- Getaway-Feasibility (`src/feasibility.py`) — flaggt unrealistische Back-to-Backs;
  datenbasierte Schwellen aus real 2024/2025.
- Feiertags-Pins (`src/holidays.py`, `data/holiday_pins.json`).
- Compliance-Report (`src/compliance.py`) — jede Hard-Rule ↔ CBA-Quelle + Messwert,
  maschinenlesbar. Realer Plan = voll compliant.
- Plan-Begründung (`src/explain.py`) — deutschsprachig, inkl. CO₂/Fairness.
- Doubleheader-Verdichtung (`src/doubleheaders.py`) — DH zur Trip-Verkürzung.
- SA-Soft-Terme: Feasibility + Feiertage als gegatete Energie-Terme in
  `optimize_travel` UND `optimize_pareto` (P1-5), plus Geo-Move im Pareto-Pfad.

**P2 — Verfeinerungen.**
- CO₂/Fairness im Backtest-Report + Explain.
- Revenue-Modell pro Team gegen reale Attendance validiert (Spearman 0,89).
- Flughafen-Koordinaten-Analyse (Default bleibt Stadt, evidenzbasiert).
- Reduced-Instance-Smoke-Set + langsame CP-SAT-Tests als `slow` markiert.
- Stärkere Geo-Nachbarschaft (`geo_topk`), gemessen −1,1 % bei hohen Iter.

**Qualität:** ~360+ Tests, determinismus-kritische Suites bit-identisch grün,
alle neuen Features gegated (Default = unverändertes Verhalten).

## Was noch fehlt / offen ist (priorisiert)

**Braucht echte MLB-Daten/Freigabe (extern, nicht von hier lösbar):**
- National-TV-Fenster (ESPN/FOX/TBS-Exklusivslots) als harte Anforderung.
- Venue-Verfügbarkeits-Kalender (NFL-Shared-Stadien, Konzerte) als *harter*
  Belegungskalender (aktuell nur weiche Event-Friction).
- Echte Gate-Receipts statt Attendance-Proxy (MLB-interner Report).
- Exakter CBA-Wortlaut AC-2.1.8 (Reisetag-Zählung) von MLB-Ops bestätigen.

**Algorithmik (optional, Forschungs-Items):**
- Branch-and-Price / kommerzieller Solver (Gurobi/CPLEX) → würde From-Scratch
  MLB-tauglich machen (echte „grüne Wiese", AC-2.1.8 garantiert).
- Volle TTP-Nachbarschaften (Ejection Chains, 2-opt über Trips).
- DH-Compression v2 (Compression + Pull-in der Folgeserien).

## Was du (Jonas) noch tun müsstest

1. **Bei MLB-Ops anfragen** für: TV-Fenster-Daten, Venue-Belegungskalender,
   Gate-Receipts, CBA-Wortlaut-Bestätigung. Das sind die einzigen echten Blocker
   für „100 % MLB-tauglich".
2. **Entscheiden**, ob Branch-and-Price/Gurobi beschafft wird (Lizenz + Aufwand) —
   nur nötig, wenn echte From-Scratch-Pläne (ohne Vorjahresplan) gebraucht werden.
3. **Produktions-Tuning** freigeben: `--geo-topk 4–6`, `--feas-lambda 50000`,
   `--holiday-lambda 5000` auf vollen 6M-Iter-Läufen kalibrieren.

## Nächster Block (in dieser Session direkt angehängt)

**Scheduler-Operations-Suite** — der eigentliche Job eines MLB-Schedulers über die
Kalender-Optimierung hinaus: pro Auswärts-Trip operative Dossiers mit
Hotel-Empfehlung (inkl. Historie/Reviews), Routing (Flughafen↔Hotel↔Stadion,
zuverlässigste Wege) und einem professionellen City-Security-/Risiko-Briefing auf
MLB-tauglichem Niveau. Siehe `docs/OPS_SUITE_DESIGN.md` (in dieser Session gebaut).
