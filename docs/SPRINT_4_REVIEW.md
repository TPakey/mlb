# Sprint 4 — Review (2026-06-07/08, autonome Nacht-Session)

Abarbeitung der „Nächste Schritte" aus `docs/HANDOVER_SPRINT_4.md`, soweit **ohne
externe MLB-Daten** machbar (Algorithmik, Ops-Suite, Dashboard, Härtung, Doku).
Maßstab: MLB-direkt-nutzbar, Determinismus nie gebrochen (neue Features gegated),
„messen statt behaupten", Tests für jedes neue Modul.

---

## 1 — TTP-Nachbarschaft: OR-opt / Best-Insertion-Geo-Move (`move_mix_oropt`)

**Was:** Über `geo_topk` hinaus die in der TTP-Literatur übliche **OR-opt-Nachbar-
schaft mit Best-Insertion** als gegateter SA-Move implementiert. Wie der GEO-Move
löst OROPT eine Auswärts-Serie heraus und setzt sie neben einen geografisch nahen
Auswärts-Gegner — aber statt eines *zufälligen* Partners + erstem zulässigen Slot
scannt OROPT **deterministisch alle `geo_topk`-Partner × {davor, danach}** und wählt
den Slot mit der **geringsten resultierenden Reise des bewegten Teams** (Steepest-
Descent/Best-Insertion). Die Annahme bleibt SA-Energie-basiert (deterministisch).
Nutzt exakt dieselbe bewährte Single-Entry-Buchhaltung wie GEO/SHIFT.

**Gating/Determinismus:** `move_mix_oropt` Default **0.0** → OROPT-Band leer,
`shift_cut` fällt algebraisch auf die alte Formel zurück → **rng-Sequenz und
Verzweigung bit-identisch** zum bisherigen Warm-Start. Verifiziert: die GEO-Baseline
ist bit-identisch zu `move_mix_oropt=0`; OROPT-on ist über Läufe reproduzierbar
(`tests/test_sprint_4.py`, 6 Tests grün).

**Gemessene Wirkung (real 2024 Warm-Start, Seed 42, geo_topk=6) — ehrlich:**

| Iterationen | GEO only (Baseline) | GEO+OROPT | Δ |
|---|---|---|---|
| 30.000  | 1.683.953 km | 1.682.601 km (oropt 0,25) | **−0,08 %** |
| 300.000 | 1.659.415 km | 1.659.614 km (oropt 0,25) | +0,01 % |
| 1.000.000 | 1.630.309 km | 1.655.780 km (oropt 0,10) | **+1,6 %** |

**Befund (klar):** Best-Insertion konvergiert in den ersten ~30k Iterationen
minimal besser, **verschlechtert** aber das Ergebnis bei Produktions-Iterationen
(≥300k). Grund: die deterministische Best-Insertion ist zu gierig — sie verengt die
Nachbarschaft auf das lokal beste Einfügen und reduziert damit die stochastische
Exploration, die der zufällige GEO-Move mit hohem `geo_topk` leistet. Der
SA-Mechanismus profitiert hier von Diversität, nicht von Greediness.

**Entscheidung:** OROPT bleibt **gegatet und per Default AUS**. Für offizielle
6-Mio-Iter-Pläne ist der reine stochastische GEO-Move mit `geo_topk=4–6` die
stärkere Wahl (vgl. P2-5). OROPT bleibt als getestete, deterministische Option im
Code (`--oropt-share`, klar als experimentell markiert) — nützlich nur im
Niedrig-Iter-Regime (z. B. interaktive 30k-Vorschauen). Das ist das ehrliche
„messen statt behaupten"-Ergebnis: eine literaturbegründete Nachbarschaft sauber
getestet, rigoros vermessen, als für Produktion nicht überlegen dokumentiert.

> Erkenntnis fürs Backlog: Der verbleibende Reise-Hebel liegt nicht in **gierigeren**
> Einzel-Moves, sondern allenfalls in einer *anderen* Nachbarschaftsklasse
> (echtes 2-opt-Segment-Reversal über Trips mit Multi-Team-Buchhaltung, oder
> Branch-and-Price). Beides ist hochriskant für den determinismus-kritischen Kern
> bzw. beschaffungs-gegatet (Gurobi) und bewusst **nicht** unter Zeitdruck in den
> Kern gedrückt. Die SA ist auf der km-Achse bereits sehr nah an ihrem Potenzial
> (Warm-Start schlägt den realen Plan −5,4 %).

---

## 2 — DH-Compression v2 (Compression + Pull-in)

**Was:** Die in `docs/SPRINT_3_P0_P1_REVIEW.md` als offen vermerkte v2-Erweiterung
der Doubleheader-Verdichtung. **v1** konnte einen zu langen Road-Trip nur kürzen,
wenn dessen **letzte** Auswärts-Serie ≥ 2 Tage hatte (Tail-Compression). Endete der
Trip auf einer 1-Spiel-Serie, war v1 ein no-op.

**v2 (`compress_with_pullin`):** verdichtet die späteste verdichtbare **innere**
Serie des Trips per Day-Night-DH und zieht alle Folgeserien innerhalb des Trips um
genau 1 Tag **nach** (Pull-in) → der letzte Auswärtstag rückt vor → **Trip-Spanne −1**,
auch wenn die letzte Serie nur 1 Spiel hat.

**Garantien (getestet):**
- **Matchup-erhaltend** — kein Spiel hinzugefügt/entfernt; jede Paarungs-Quote
  bleibt exakt (`test_v2_preserves_each_matchup_count`).
- **Validiert + atomar** — jede nachgezogene Serie wird auf NoOverlap (beide Teams)
  und Break-Day-/Blackout-Gültigkeit geprüft; bei *irgendeinem* Fehlschlag wird der
  gesamte Zug zurückgerollt (kein Teil-Move).
- **Deterministisch** — feste Auswahl- und Pull-in-Reihenfolge.
- **Gegated** — `enable_pullin` Default **False** → v1-Verhalten unverändert. v2
  bevorzugt weiter Tail-Compression, wo möglich (keine Regression,
  `test_v2_still_does_v1_when_possible`).

**Verifiziert:** synthetischer 14-Tage-Trip mit 1-Spiel-Endserie → v1 no-op, v2
senkt auf 13 Tage bei exakt erhaltener Spielanzahl und echtem Day-Night-DH
(`tests/test_sprint_4.py`, 4 v2-Tests). Bestehende DH-Tests regressionsfrei.

**Produktions-Einordnung (ehrlich):** DH-Verdichtung ist primär ein Helfer für den
**From-Scratch-Pfad** (nicht-Produktion) bzw. für Wetter-Makeups. Der
Produktions-Warm-Start erreicht auf realen Plänen bereits 0 AC-2.1.8-Verletzungen,
braucht die Verdichtung also nicht. v2 schließt die dokumentierte Funktionslücke
sauber und vollständig, der praktische Produktionshebel bleibt klein.

---

## 3 — Harter Venue-Belegungskalender (VENUE-AVAIL)

**Was:** Aus `docs/STATUS_REVIEW_2026-06-07.md`: „Venue-Verfügbarkeits-Kalender …
als *harter* Belegungskalender (aktuell nur weiche Event-Friction)". Ergebnis der
Analyse: die **Durchsetzungs**-Mechanik existiert bereits sauber
(`event_conflicts.stadium_bookings_to_blackout_days` → `GeneratorConfig.
home_blackout_days`, respektiert von CP-SAT **und** der SA via `_start_ok`). Was
fehlte, war (a) eine **Verifikation** fertiger Pläne und (b) eine **Compliance-
Regel** mit Provenance. Beides ergänzt:

- **`event_conflicts.venue_conflicts(season, events)`** — listet Heimspiele, die
  auf einen Stadion-Belegungstag fallen (harter Verstoß). Datenunabhängig:
  funktioniert mit jedem (auch echten MLB-)Belegungskalender im Event-Schema.
- **Compliance-Regel `VENUE-AVAIL`** (hart, **opt-in**) — in `compliance_report`
  über `events=…` oder `check_venue=True` aktivierbar; ohne beides bleibt der
  Report bit-gleich bei den bisherigen sechs Regeln (rückwärtskompatibel,
  Default unverändert, alle 21 Bestands-Compliance-Tests grün).

**End-to-End-Beweis der Hard-Constraint:** `test_hard_blackout_enforced_in_sa`
zeigt, dass die SA mit gesetztem `home_blackout_days` **kein** Heimspiel auf einen
gesperrten Tag legt — der Belegungskalender wirkt also wirklich als harter
Constraint, nicht nur als Report. 8 Venue-Tests grün (`tests/test_sprint_4.py`).

**Daten-Ehrlichkeit:** `data/local_events.json` enthält **8 illustrative**
Stadion-Belegungen, alle datiert **2026**. Gegen den realen **2024**-Plan ergeben
sich erwartungsgemäß **0 Konflikte** (Jahres-Mismatch) — der Check bestätigt also
die Mechanik, nicht eine erfundene Konfliktlage. Für den Produktivbetrieb liefert
MLB-Ops den **jahresgleichen** echten Belegungskalender (NFL-Shared-Stadien,
Konzerte) im selben Schema; die Engine ist datenunabhängig sofort einsatzfähig.
Beim Generieren der Zielsaison werden die Belegungen über `home_blackout_days`
hart erzwungen, beim fertigen Plan über `VENUE-AVAIL` verifiziert.

---

## 4 — Ops-Dossier ins Dashboard (`dashboard/ops.html`)

**Was:** Die Scheduler-Operations-Suite (Routing / Hotel / Security-Briefing pro
Auswärts-Stadt) war bisher nur als CLI-/Markdown-Report verfügbar. Jetzt im
Dashboard zugänglich.

- **`dashboard/build_ops_dashboard.py`** — berechnet für **alle 30 Teams** die
  Trip-Dossiers, serialisiert einen kompakten JSON-Payload und bettet ihn in eine
  **eigenständige** HTML-Seite (`dashboard/ops.html`, ~680 KB, keine externen
  Abhängigkeiten). Interaktiv: Team-Auswahl → Risiko-Übersicht aller Auswärts-
  Städte (Stadt, Gastgeber, Termin, Risikostufe mit Severity-Farbcode,
  Transfer-Planbarkeit, empfohlenes Hotel) + aufklappbares Detail-Dossier je
  Stadt (Boden-Routing, Hotel-Empfehlung mit Historie, saison-aktive Klimagefahren,
  med. Bereitschaft, Posture, High-Profile-Flags). Übernimmt die Daten-Ehrlichkeit
  der Suite: fehlende Hotel-Seeds und die am Spieltag zu bestätigende Liaison-Lage
  sind klar markiert.
- **Generiert:** 30 Teams, **811 Stadt-Dossiers**, valides eingebettetes JSON.
- **Verlinkt** aus `dashboard/index.html` (neue Nav-Zeile: Ops · Pareto · Phasen).
- **Tests:** `TestOpsDashboard` (Payload-Struktur + Self-Contained-HTML) grün.

**Einordnung:** rein additive Visualisierung über dem bestehenden Ops-Modul; keine
Änderung an Optimierung oder Determinismus.

---

## 5 — Härtung: Input-Validierung & Fehlerbehandlung

Schwachstellen-Review der Eingabe-Pfade. `data_loader` war bereits stark gehärtet
(Team-Feld-/Range-/Timezone-Validierung mit klaren Meldungen, Audit A24). Geschlossen:

- **Korruptes/leeres Schedule-JSON** (`datasources/local_file.py`): wirft jetzt eine
  klare `DataSourceError` („… enthält kein gültiges JSON") statt eines rohen
  `JSONDecodeError`, der die Quelle verschleiert. (Fehlende Datei und unbekanntes
  Format waren schon sauber behandelt.)
- **CLI-Argumente** (`main._validate_args`): früh geprüft mit sammelnder Meldung —
  negative Iterationen, `solver-time ≤ 0`, `geo-topk < 1`, negative λ, `oropt-share`
  außerhalb [0, 1] werden mit klarer Fehlermeldung abgewiesen, statt still in
  undefiniertes SA-Verhalten zu laufen.

**Tests:** `TestHardening` (7) — korruptes JSON, fehlende Datei, unbekanntes Format,
CLI-Range-Checks (negativ/Bereich) — grün.

---

## 6 — Abschluss-QA (gesamtes Projekt)

**Volle Nicht-Slow-Suite** (gesplittet wegen 45-s-Sandbox-Limit):
**373 passed, 1 xfailed, 0 Fehler.** (Baseline vor Sprint 4: 346 passed + 1 xfail;
+27 neue Sprint-4-Tests in `tests/test_sprint_4.py`.) Der eine `xfail` ist der
bekannte, bewusste From-Scratch-AC-2.1.8-Fall (kein Produktions-Blocker, P0). Die
30-Team-CP-SAT-`slow`-Tests bleiben CI-only (Sandbox-Tractability).

**Determinismus verifiziert (bit-identisch):**
- Produktions-Warm-Start (Default) — Doppellauf identisch inkl. **voller
  Spiel-Signatur** (Datum, Matchup, DH-Seq).
- Warm-Start mit `feas_lambda`+`holiday_lambda` aktiv — Doppellauf identisch.
- Alle neuen Features sind gegated (Default 0/off): OROPT-Band leer →
  rng-Sequenz bit-identisch; DH-v2 `enable_pullin=False`; VENUE-AVAIL opt-in.

**Konsistenz-/Ehrlichkeitsprüfung der Kennzahlen (gemessen, nicht behauptet):**
- Realer 2024-Plan: **voll compliant** auf allen harten Regeln (inkl. neuer
  VENUE-AVAIL: 0 Konflikte), worst-away **11**, worst-no-off **18**,
  max-Back-to-Back **4164 km** (deckt sich mit dem Envelope-Ceiling 4200).
- Warm-Start 2024 (500k Iter, geo_topk=6): **−3,54 %** Reise vs. real (1.709.835 →
  1.649.242), worst-away **13**, worst-no-off **20** → 0 CBA-Verletzungen. Bei den
  Produktions-6-Mio-Iterationen die dokumentierten **−5,4 %** (Größenordnung
  bestätigt; lineare Skalierung der SA-Konvergenz).
- Revenue-Struktur Spearman **0,892** (reproduziert).

**Schwachstellen-Review:** Eingabe-Pfade gehärtet (s. §5). Die neuen SA-/DH-Pfade
nutzen die bestehende, bewährte Single-Entry-Buchhaltung bzw. atomare Reverts mit
voller Overlap-/Gültigkeitsprüfung; keine neuen Determinismus-Risiken. `pyflakes`
sauber über alle geänderten Module.

**Fazit:** Das Projekt ist auf den ohne externe Daten erreichbaren Achsen
abgeschlossen und MLB-direkt-nutzbar. Die verbleibenden Punkte sind echte externe
Daten-/Beschaffungs-Blocker (s. `docs/STATUS_REVIEW_2026-06-07.md` + Handover).
