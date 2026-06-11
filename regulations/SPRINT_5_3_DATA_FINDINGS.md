# Sprint 5.3 — Daten: Diagnosen & Kalibrierungs-Klärung (messen statt behaupten)

**Stand:** 2026-06-10. Behandelt die ohne externe Datenbeschaffung lösbaren 5.3-Punkte:
**E2** (warum 2025 schwächer), **C6** (Revenue-Kalibrierungsbasis), **E1** (Routing-
Determinismus). C1 (Gate-Receipts), C2 (verifizierte TV-Fenster), C3 (Venue-Konzerte)
brauchen externe Daten → bleiben als Beschaffungs-Items markiert.

---

## E2 — Warum erreicht der Warm-Start 2025 weniger km-Einsparung als 2024? (GELÖST)

**Frage (GAP-E2):** 2025 −2,6 % vs. 2024 −5,4 % km-Einsparung. Ursache?

**Messung (`tools/diagnose_e2_2025.py`, gleiche Iterationszahl je Jahr):**

| | 2024 | 2025 |
|---|---|---|
| reale Baseline-km | 1.709.835 | 1.715.743 |
| Δ bei 40k Iter | **−1,77 %** | **+0,13 %** |
| max away-days (Start) | **11** (alle ≤13) | **14** (TBR > 13) |
| max games-no-off (Start) | 18 | **20** |
| Spiele/Team-Spanne | 161–163 | 160–165 |
| intl/neutrale Spiele | 6 | 0 |
| relozierte Heim-Teams | OAK, HOU, MIA (Stadion-Namen) | **TBR → George M. Steinbrenner Field** |

**Ursache (belegt, nicht vermutet):**

1. **Der 2025-Realplan startet mit echtem Fatigue-Druck.** TBR hat eine **14-Tage-
   Auswärtstour** (>13) und max-games-no-off = 20 — Folge der **Hurricane-Milton-
   Relokation** (Tropicana Field beschädigt → Rays spielen 2025 im Steinbrenner Field,
   Tampa). 2024 startet sauber (max 11 away-days).
2. **Der SA gibt das beste Ergebnis nach ENERGIE zurück, nicht nach km** (`best_starts`
   per `best_energy`). Energie = `km + 1e6·fatigue + …`. Bei λ_fat = 1e6 dominiert eine
   Fatigue-Verletzung (14−13)²·1e6 = 1e6 „km-Äquivalent" klar die km-Loss. → Der 2025-SA
   investiert sein Budget zuerst in die **Fatigue-Reduktion** (TBR 14→13), nicht in km;
   bei kleinem Iterations-Budget endet der km-Wert sogar minimal höher.
3. **2024 startet fatigue-sauber** → das gesamte Budget fließt in km → größere km-Einsparung.
4. **Sekundär:** 2025-as-played ist noisier (Spielzahl-Streuung 160–165 vs. 161–163,
   Relokationen) → weniger sauberer Optimierungsspielraum.

**Wichtig (kein Messartefakt):** Entry-km (SA-Metrik) und Season-Travel-km sind für beide
Jahre **bit-genau identisch** (gap = 0) — die Repräsentation ist sauber, der Unterschied
ist echte Optimierungs-/Energie-Ökonomie, nicht ein Konvertierungsfehler.

**Fazit:** Die geringere 2025-km-Einsparung ist **korrektes Modellverhalten**, kein Bug:
der reale 2025-Plan ist fatigue-belasteter (Relokation), und der Optimierer priorisiert
(richtigerweise) die harte/teure Fatigue-Dimension über reine km. Bei vollem Produktions-
Budget (≥500k Iter) bleibt 2025 dennoch eine echte Verbesserung (Handover: −2,6 %).

---

## C6 — Revenue-Kalibrierungsbasis (GEKLÄRT)

**Frage (GAP-C6):** Was nutzt `data/revenue_model.json` real — Sportico oder Attendance?

**Antwort (eine kanonische Basis):**
- **Kalibrierungs-Basis = Sportico/Statista 2024**, franchise-Gate-Revenue → normiert als
  `base_team[home]` = erwarteter Gate-Revenue **pro Heimspiel** (Liga-Mittel ~1,4 Mio USD).
  Quelle: `docs/REVENUE_MODEL_RESEARCH.md`; `_calibrated_for_season: 2024`.
- `expected_revenue(game) = base_team[home] × daypart × doubleheader × rival/marquee …`
  (Multiplikatoren aus Soft-Factors/TV). **Attendance fließt NICHT in die Kalibrierung ein.**
- **Validierungs-Referenz (unabhängig) = ESPN-Attendance 2024** (`data/real_attendance_2024.json`)
  — nur als **struktureller Rang-Cross-Check** (`src/revenue_validation.py`,
  Spearman 0,892 / Pearson 0,798; `docs/REVENUE_VALIDATION_2024.md`). Kein Kalibrier-Input.

**Festlegung:** Kanonische Basis = **Sportico/Statista 2024 Gate-Revenue/Heimspiel**;
ESPN-Attendance bleibt reine Validierung. **Calibration-Warning** (im JSON dokumentiert):
auf 2024 geeicht, auf 2026 angewandt (2-Jahres-Extrapolation; Inflation, neue TV-Deals
nach Bally-Sports-Insolvenz, Renovierungen) → vor MLB-Übergabe auf aktuelle Saison neu
eichen, idealerweise pro Saison kalibrierbar.

---

## E1 — Routing-Determinismus (ASSESSED)

**Befund:** Der **Kern-Reisepfad ist bereits deterministisch** — alle km im Optimierer/
Compliance/Backtest kommen aus **Haversine** (`src/travel.py`/`distance.py`), keine
Netzwerk-/ORS-Abhängigkeit. Die in `regulations/APPENDIX_C_README.md` eingeführte
offizielle In-Flight-Matrix (Appendix C, 5.1) ist ebenfalls statisch + versioniert.

**ORS:** Der `ORS_API_KEY` (`.env`) ist ausschließlich für **Boden-Routing in der
Ops-Suite** (Sprint 5.5, `src/ops_routing.py`) vorgesehen und **noch nicht** in den
deterministischen Kern verdrahtet (Ops-Routing nutzt aktuell den koordinatenbasierten
Schätzer). → E1s Determinismus-Anforderung ist für den Kern **bereits erfüllt**.

**Empfehlung (wenn ORS für Ops-Routing aktiviert wird):** ORS-Antworten in einen
**eingefrorenen, versionierten Cache** (`data/ors_cache_<version>.json`) schreiben; zur
Laufzeit nur aus dem Cache lesen; ohne Key/Netz **Haversine-Fallback**. Damit bleibt auch
das Ops-Routing reproduzierbar. Umsetzung gehört zu 5.5 (Ops) und ist netz-gegatet → hier
nur dokumentiert, nicht live gebaut (kein Netzzugang im Kernlauf nötig).

---

## Offene 5.3-Punkte (externe Datenbeschaffung nötig)
- **C1 Gate-Receipts:** Forbes-Jahres-Gate als Skalen-Kalibrierung + Sensitivität — braucht Forbes-Daten.
- **C2 TV-Fenster:** verifizierte nationale Fenster 2024/2025 (Apple/ESPN/FOX) → optional an
  Startzeit-Slots pinnen (`assign_start_times(tv_pins=…)` ist vorbereitet) — braucht Broadcaster-Listen.
- **C3 Venue:** geteilte 2025-Venues exakt (River Cats/Tarpons) + Konzert-Blackouts — braucht Co-Tenant-Pläne.
