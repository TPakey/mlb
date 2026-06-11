# Revenue-Modell — Pro-Team-Strukturvalidierung 2024 (P2-1)

**Stand:** 2026-06-07 (Sprint 3, P2)
**Frage:** Bildet das Revenue-Modell nicht nur die **Liga-Summe** (bereits auf
−1,4 % vs. Sportico geeicht), sondern auch die **Pro-Team-Struktur** korrekt ab?

## Methode

Reale, öffentlich verfügbare **2024-Heim-Zuschauerzahlen** aller 30 Teams
(ESPN MLB Attendance Report, `data/real_attendance_2024.json`) als Proxy für
Gate-Revenue. Verglichen mit dem Modell-Pro-Team-Revenue
(`revenue.team_revenue`) über:

- **Spearman-Rangkorrelation** (rankt das Modell die Teams wie die Realität?) —
  das primäre Akzeptanzkriterium, robust gegen Niveau-Unterschiede.
- **Pearson-Korrelation** (linearer Zusammenhang).
- **Verhältnis-Streuung** Modell/Attendance.
- **Rang-Ausreißer** (wo Priors auffrischbar wären).

Implementierung: `src/revenue_validation.py` (ohne externe Abhängigkeiten),
Tool: `python -m tools.validate_revenue_model`, Tests:
`tests/test_revenue_validation.py`.

## Ergebnis (ehrlich)

| Kennzahl | Wert | Bewertung |
|---|---:|---|
| **Spearman-Rangkorrelation** | **0,892** | stark — das Modell rankt die Zugkraft strukturell wie die Realität ✅ |
| Pearson-Korrelation | 0,798 | stark linear |
| Modell/Attendance-Streuung | 2,90× | erwartet (Revenue ≠ Attendance: Ticketpreise/Premium variieren je Markt) |

**Befund:** Die Pro-Team-Struktur ist **valide** — die Rang-Treue von 0,89 belegt,
dass das Modell die Teams nicht nur in der Summe, sondern auch relativ korrekt
bewertet. Das war zuvor nicht geprüft (P2-1 offen).

### Konkrete Rang-Ausreißer (Priors auffrischbar)

| Team | Modell-Rang | Attendance-Rang 2024 | Δ | Lesart |
|---|---:|---:|---:|---|
| PHI | 9 | 2 | 7 | Phillies-Attendance-Boom 2024 über dem Marktgrößen-Prior |
| SFG | 5 | 12 | 7 | Giants-Prior (großer Markt) über realer 2024-Attendance |
| NYM | 10 | 18 | 8 | Mets-Prior über realer 2024-Attendance |
| MIN | 15 | 23 | 8 | Twins-Prior über realer Attendance |
| BOS | 4 | 10 | 6 | Red-Sox-Prior (Premium-Markt) über Stadion-Kapazität gedeckelt |
| COL | 21 | 15 | 6 | Rockies-Attendance über dem Prior |

Die Bottom-Gruppe (TBR, MIA, OAK) und die Spitze (LAD) stimmen exakt. Die
Ausreißer sind plausibel: das Modell nutzt **markt-/größenbasierte Priors**, die
den **realen 2024-Attendance-Verläufen** (Phillies-/Padres-/Braves-Hoch,
schwächere Mets/Twins) naturgemäß etwas nachlaufen.

## Empfehlung

1. **Modell ist für die Optimierung tauglich** — die Rang-Treue 0,89 reicht, damit
   der Revenue-Term Pläne korrekt nach Zugkraft differenziert.
2. **Optionaler Refresh** (sobald gewünscht): die `base_team`-Priors in
   `data/revenue_model.json` an den 2-3-Jahres-Attendance-Schnitt anlehnen — würde
   v.a. PHI/SDP/ATL anheben und NYM/MIN/SFG/BOS leicht senken. **Nicht** auf ein
   einzelnes Jahr überfitten (Attendance schwankt mit Team-Performance).
3. **Echte Gate-Receipts statt Attendance** bleiben das Goldstandard-Item, sobald
   MLB den internen Gate-Report bereitstellt (P2-1 Restpunkt). Attendance ist der
   beste öffentlich verfügbare Proxy.

## TV-Modell (P2-2)

Das TV-Slot-Modell bleibt heuristisch (Erwartungswert über day/night-Mix,
Marquee-Multiplikatoren). Eine echte Validierung braucht Broadcaster-Pick-Daten
(nationale ESPN/FOX/TBS-Fenster), die nicht granular öffentlich sind. Der
bestehende C2-Sanity-Check (Sunday-Night-Premium, Saturday day/night) bleibt das
verfügbare Kriterium. Empfehlung unverändert: echte TV-Fenster-Daten von MLB
einholen (überschneidet mit P1-3 National-TV-Fenster).

## Quellen
- ESPN MLB Attendance Report 2024 — https://www.espn.com/mlb/attendance/_/year/2024
- Bestehende Liga-Summen-Eichung: `docs/REVENUE_MODEL_RESEARCH.md`
