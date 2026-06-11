# CBA-Definitionen — Fatigue-Constraints AC-2.1.8 / AC-2.1.9

**Stand:** Sprint 2.7 (2026-05-27)
**Status:** Verbindliche Definitionsgrundlage für alle Fatigue-Berechnungen, Tests und Berichte.

Dieses Dokument hält fest, *welche Größe* das System unter AC-2.1.8 und AC-2.1.9
misst. Es wurde im Zuge von Sprint 2.7 erstellt, nachdem das externe Review (C1)
gezeigt hatte, dass der Code bis dahin eine andere (schwächere) Größe gemessen
hat als die CBA-Regel meint.

---

## AC-2.1.8 — "Days away from home" (Ziel ≤ 13)

> **ENTSCHEIDUNG 2026-06-09 (Jonas):** AC-2.1.8 ist ein **WEICHES Qualitätsziel**, KEIN
> hartes CBA-Erfordernis. Volltext-Verifikation (`regulations/FINDING_AC-2.1.8_vs_CBA.md`):
> „13 days away" steht NICHT im CBA Article V — es ist eine Belastungs-Heuristik
> („13-Game-Gauntlet"). Das harte CBA-Muss ist V(C)(12) = **AC-2.1.9** (≤ 20 konsekutive
> Spieltage, strukturell garantiert). Konsequenz: In `compliance.py` ist AC-2.1.8 jetzt
> `severity="soft"`; die frühere ≤13-Garantie-Frage (Q10) ist **obsolet** — kein
> Branch-and-Price dafür nötig. Der TODO „CBA-Wortlaut bestätigen" unten ist damit erledigt.

### Definition (gültig seit Sprint 2.7)

Eine **Road-Trip** ist ein zusammenhängender Block, in dem ein Team **nicht zu
Hause** ist. Sie beginnt mit dem ersten Auswärtsspiel und endet mit dem letzten
Auswärtsspiel, bevor das nächste **Heimspiel** das Team zurück nach Hause bringt.

**Off-Days mitten in der Road-Trip zählen mit**, weil das Team auch an einem
spielfreien Tag zwischen zwei Auswärtsspielen weiterhin auf Achse / im Hotel ist.
Nur ein **Heimspiel** beendet die Road-Trip.

Gemessen wird die Spanne in **Kalendertagen** vom ersten bis zum letzten
Auswärtsspiel der Road-Trip, inklusive:

```
days_away_from_home = (last_away_date - first_away_date).days + 1
```

Das Limit beträgt **13 Tage**.

### Beispiel

```
Tag 0  Auswärts BOS
Tag 1  Auswärts BOS
Tag 2  Off-Day        (Team weiterhin auswärts/auf Achse)
Tag 3  Auswärts BAL
Tag 4  Auswärts BAL
```

Road-Trip-Länge = `(Tag4 − Tag0) + 1 = 5` Tage away from home.

Ein **Heimspiel** zwischen zwei Auswärtsspielen beendet dagegen die Road-Trip:

```
Tag 0  Auswärts BOS
Tag 1  Auswärts BOS
Tag 2  Heimspiel      ← beendet die Road-Trip
Tag 3  Auswärts BAL
Tag 4  Auswärts BAL
```

→ zwei getrennte Road-Trips von je 2 Tagen, `max = 2`.

### Abgrenzung zur alten (fehlerhaften) Definition

Vor Sprint 2.7 zählte der Code die längste Folge **konsekutiver Kalendertage mit
Auswärtsspiel** und setzte den Streak bei einem Off-Day mitten in der Reise
zurück. Das unterzählte echte Road-Trips systematisch (im Beispiel oben: 2 statt
5). Diese Definition ist nicht mehr gültig.

### Annahmen / offene Punkte

- **Reise-/Travel-Tage** vor dem ersten Auswärtsspiel bzw. nach dem letzten
  werden nicht separat modelliert; gezählt wird die Spanne erstes→letztes
  Auswärtsspiel. Falls MLB-Ops bestätigt, dass der Reisetag *vor* dem ersten
  Auswärtsspiel mitzählen soll, ist die Definition um +1 (bzw. den konkreten
  Reisetag) zu erweitern.
- **Saisonanfang/-ende:** Eine offene Road-Trip am Saisonende (kein
  abschließendes Heimspiel) wird normal als Spanne gewertet.

> **TODO (Vorarbeit, extern abzuklären):** Exakten Wortlaut aus dem aktuellen
> MLB-CBA / MoU bestätigen (Ansprechpartner MLB-Ops, Datum). Bis dahin gilt die
> hier dokumentierte, konservative Auslegung "Spanne erstes→letztes
> Auswärtsspiel, Off-Days inklusive".

---

## AC-2.1.9 — Max. 20 Spieltage in jedem 21-Tage-Fenster

Unverändert: In jedem rollierenden Fenster von 21 Kalendertagen darf ein Team
höchstens 20 Spieltage haben (mindestens ein Off-Day je 21 Tage). Ein
Doubleheader zählt als **ein** Spieltag.

---

## Wie die Constraints durchgesetzt werden

| AC | Mechanismus | Ort |
|---|---|---|
| **AC-2.1.9** | Strukturell (Pigeonhole): periodische Break-Days alle 21 Tage im CP-SAT | `generator._periodic_break_days(total_days, max_gap=21)` |
| **AC-2.1.8** | Weich (SA-Penalty, λ = 1.000.000) + deterministischer Greedy-Repair. **Noch nicht strukturell garantiert** — gemessen am realen 2026-Plan bleiben typ. ~4 Teams über dem 13-Tage-Limit (worst-case ~20). Offenes Item, siehe unten. | `generator_optimizer.optimize_travel` |

**Wichtig:** `_periodic_break_days` garantiert mit `max_gap=21` **nur AC-2.1.9**,
nicht AC-2.1.8. Der frühere Pigeonhole-"Beweis" für AC-2.1.8 war falsch (Review C3)
und wurde entfernt.

**Status AC-2.1.8 (2026-05-29, QA-Audit):** AC-2.1.8 wird aktuell *nur* weich in
der SA durchgesetzt. Messung am realen 2026-Plan (voller Pfad `generate()`+SA,
Seed 42): **4 Teams über dem Limit** (CLE 20, OAK 15, BOS 14, TEX 14 Tage).

Eine **strukturelle, verifiziert-sounde** Formulierung existiert bereits als
nicht-verdrahteter Helfer `generator._add_ac_2_1_8_gap_constraints`: pro Team
muss jede Heim-Serie i einen Nachfolger-Heimstand in `(end_i, end_i+13]` haben
(oder nahe am Saisonende liegen), plus ein Heimstand in den ersten 14 Tagen →
keine 14-Tage-Lücke ohne Heimspiel → Spanne ≤ 13. Korrektheit gegen ein
Brute-Force-Orakel abgesichert (315 Fälle, 0 Verletzungen; Repo-Test
`test_ac218_gap_formulation_is_sound`).

Sie ist **bewusst nicht verdrahtet**, weil sie die volle Saison MIT All-Star-Break
nur intermittierend löst (1-Worker deterministisch UNKNOWN/36 s; 8-Worker
unzuverlässig) — eine intermittierend infeasible Generierung wäre für MLB
schlimmer als die weiche Durchsetzung. Die verworfene Cover-Matrix-Variante
(~140k Booleans, UNKNOWN/40 s) bestätigte zudem den `add_offday_slots`-Befund
(`docs/AUDIT_A1_NOTE.md`). AC-2.1.8 bleibt daher xfail; die verbleibende Arbeit
ist reine Solver-Tractability (Plan + Akzeptanzkriterium:
`docs/REFACTOR_BACKLOG.md` Q10, `docs/QA_AUDIT_2026-05-29.md` Q10).

---

## Implementierungen (alle konsistent zu dieser Definition)

| Funktion | Datei | Zweck |
|---|---|---|
| `max_consecutive_away_days(season, team)` | `src/player_fatigue.py` | Validierung / Reporting (Road-Trip-Spanne) |
| `_team_max_streaks(team, entries, team_idx)` | `src/generator_optimizer.py` | Inkrementelle Berechnung im SA |
| AC-2.1.8-Constraint (`sum(home[d:d+14]) >= 1`) | `src/column_generation.py` | CP-SAT-Pricing-Subproblem |

Alle drei zählen Off-Days innerhalb einer Road-Trip mit und werten ein Heimspiel
als Trip-Ende.

---

## Empirische Verifikation (Sprint 2.7)

Siehe `docs/SPRINT_2_7_REVIEW.md` für die Multi-Seed-Verifikation (Seeds 42, 7,
11, 17), dass die SA-Penalty auch unter der schärferen Definition zu 0
Verletzungen konvergiert.
