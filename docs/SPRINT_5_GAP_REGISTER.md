# Sprint 5 — Gap-Register (ehrliche MLB-Readiness-Analyse)

**Stand:** 2026-06-09. Was ist *noch nicht* so, dass die MLB es **heute** ungeprüft
einsetzen könnte? Evidenzbasiert aus Code-Review (`compliance.py`, `player_fatigue.py`,
`generator_optimizer.py`, `CBA_DEFINITIONS.md`, README), nicht aus Annahmen.
Severity: **Blocker** (verhindert MLB-Einsatz) · **Hoch** · **Mittel** · **Niedrig**.
🆕 = im zweiten Durchgang neu entdeckt (vorher nicht bedacht).

---

## A — CBA-Compliance-Vollständigkeit (der größte blinde Fleck) 🆕

Der Compliance-Report (`compliance.py RULES`) prüft genau **sieben** Regeln:
AC-2.1.8, AC-2.1.9, SCHED-162, SCHED-HA, FEAS-GETA, VENUE-AVAIL, PIN-LEAGUE.
Damit fehlen **mehrere reale harte Article-V-Regeln**, die ich erst beim
Volltext-Studium des CBA gefunden habe:

| ID | Reale CBA-Regel (Article V) | Im System? | Severity |
|---|---|---|---|
| GAP-A1 🆕 | **V(C)(11) — Pacific→Eastern erzwingt Off-Day** | **nein** — und das ist *reise-relevant*, also Kerngebiet | **Hoch** |
| GAP-A2 🆕 | **V(C)(13) — Off-Day-Verteilung** (≤2 Open Days/7 Tage; ≥7 in letzten 67; ≥3 in letzten 32) | **nein** | **Hoch** |
| GAP-A3 🆕 | **V(C)(8)/(9) — Getaway-/Tag-nach-Nacht-Startzeiten** | **nein** (Modell kennt keine Startzeiten, s. GAP-B1) | **Mittel** |
| GAP-A4 🆕 | **V(C)(14)/(15) — Doubleheader-Scheduling-Limits** (keine an Folgetagen; Twi-Night ≤3; nicht am Getaway) | teilweise — `doubleheaders.py` macht *Verdichtung*, prüft die *Limits* nicht | **Mittel** |
| GAP-A5 | V(C)(17) — All-Star-Break 4 Tage | ja (Break-Days im Generator) | erledigt |

**Warum das zählt:** Ein MLB-Scheduler verlangt Einhaltung *aller* harten Article-V-
Regeln, nicht einer Auswahl. Besonders **GAP-A1 (PT→ET-Off-Day)** ist heikel, weil es
direkt im Reise-Optimierungs-Kern liegt und der Optimierer es heute verletzen könnte.

> **Hinweis:** Im Warm-Start-Pfad sind viele dieser Regeln implizit erfüllt, weil der
> reale Seed sie schon einhält — aber der SA-Move-Set (GEO/SHIFT/SWAP) verschiebt
> Serien und kann sie brechen, **ohne dass es geprüft wird.** Das ist die eigentliche
> Gefahr: ungeprüfte stille Verletzungen.

---

## B — Modell-Scope (fundamentale Grenzen) 🆕

| ID | Lücke | Warum MLB-relevant | Severity |
|---|---|---|---|
| GAP-B1 🆕 | **Granularität = Kalendertag, nicht Startzeit.** Das Modell weist Serien *Tagen* zu, nicht Uhrzeiten. | Ein realer MLB-Plan braucht **Startzeiten** (Day/Night, Getaway, TV). Ohne sie sind V(C)(8)/(9) und echte TV-Slots nicht abbildbar. | **Hoch** |
| GAP-B2 | **From-Scratch ist nicht MLB-tauglich** (README sagt es selbst). Produktion = Warm-Start vom realen Vorjahresplan. | Das System optimiert *Varianten* eines existierenden Plans, kann aber keinen **neuartigen** konformen Plan grün auf der Wiese erzeugen (z. B. Expansion, Strukturreform). | **Hoch** (je nach MLB-Ziel) |
| GAP-B3 🆕 | **Balanced-Schedule-Format-Regeln (seit 2023)** nur implizit via Warm-Start geerbt, nicht als eigene Constraints kodiert. | From-Scratch kennt das aktuelle Matchup-Format nicht strukturell. | Mittel |
| GAP-B4 🆕 | **Kein Makeup-/Rainout-Reschedule, keine Postseason/Tiebreaker.** | Reales MLB-Ops-Scheduling umfasst Spielverlegungen während der Saison. | Mittel |

---

## C — Datenrealismus (alles, was noch Proxy/Seed ist)

| ID | Lücke | Severity |
|---|---|---|
| GAP-C1 | **Gate-Receipts = Proxy** (Attendance × Preis). Echte Pro-Spiel-Receipts nicht öffentlich; Forbes fixt nur die *Jahres-Skala*, nicht die Pro-Spiel-Verteilung. | Mittel |
| GAP-C2 | **TV pro Spiel** noch nicht erfasst; 2025-Struktur nicht spielfenster-genau verifiziert (nur asseriert „= 2024"). | Mittel |
| GAP-C3 | **Venue-Konzert-/Event-Daten fehlen für 28 von 30 Stadien** (nur die geteilten 2025-Venues belegt). | Mittel |
| GAP-C4 | **Appendix-C-Reisezeiten:** Volltabelle nur als Bild (B2-Quelle), nicht 1:1 aus dem CBA übernommen; aktuell Proxy. | Mittel |
| GAP-C5 | **Ops-Suite-Daten (Hotels/Security/Routing) = illustrative Seeds**, nicht real. | Mittel (für Ops-Modul) |
| GAP-C6 🆕 | **Revenue-Kalibrierungs-Inkonsistenz:** README sagt „Sportico-kalibriert", andere Docs „Attendance-Proxy/Spearman 0,89", ich schlug Forbes vor — *drei* Bezugsgrößen. Welche gilt? | Niedrig (Klärung) |

---

## D — Wissenschaftliche Fundierung (offen) 🆕

| ID | Lücke | Severity |
|---|---|---|
| GAP-D1 🆕 | **Chronobiologie-Effektstärken aus 1992–2011** (PNAS) — vor Charter-Standard und 2022er-Ruheregeln → überschätzen heutigen Jetlag vermutlich. | Mittel |
| GAP-D2 🆕 | **Mapping „Performance-Effekt → Reisekosten-Strafgewicht" ist selbst eine Annahme**, nicht aus den Studien direkt ableitbar. | Mittel |
| GAP-D3 🆕 | **Fairness:** Jetlag-Gewichte dürfen keine Wettbewerbsvorteile einbauen — müssen symmetrisch/neutral wirken. Noch nicht reflektiert. | Mittel |

---

## E — Determinismus vs. Echtwelt-Integration

| ID | Lücke | Severity |
|---|---|---|
| GAP-E1 | **Externe APIs (ORS-Routing, Live-Daten) brechen Determinismus.** Lösung steht (Cache einfrieren), aber noch nicht umgesetzt. | Mittel |
| GAP-E2 🆕 | **2025-Warm-Start deutlich schwächer** (README: 2024 −5,4 % vs. 2025 nur −2,6 %). Ursache ungeklärt (Venue-Sonderfälle 2025? Datenqualität?). | Mittel |

---

## F — Aufräumen nach der AC-2.1.8-Entscheidung (2026-06-09)

Jonas hat bestätigt: **13 days away ist KEIN Erfordernis.** Daraus folgt konkret:

| ID | Aufgabe | Severity |
|---|---|---|
| GAP-F1 | **AC-2.1.8 in `compliance.py` von `severity="hard"` auf `"soft"` umstellen** (steht aktuell als hart). | **Hoch** (Korrektheit der Compliance-Aussage) |
| GAP-F2 | **Q10 schließen / xfail umwidmen:** keine ≤13-Garantie mehr nötig; Test auf weiches Ziel umstellen. | Hoch |
| GAP-F3 | **5.4 Branch-and-Price entlasten:** nicht mehr Pflicht für ≤13; nur noch optional für echte From-Scratch-Pläne. | Mittel |
| GAP-F4 | **Doku bereinigen:** REFACTOR_BACKLOG Q10, CBA_DEFINITIONS, README („AC-2.1.8/9 hard") an die neue Einstufung anpassen. | Mittel |

---

## G — Prozess / Methodik (Selbstkritik)

| ID | Lücke | Severity |
|---|---|---|
| GAP-G1 | **Viel geplant/recherchiert, nichts gebaut/gemessen.** Sprint 5 hat bisher 0 Zeilen Funktionalität und 0 neue Messungen — entgegen „messen statt behaupten". | **Hoch** |
| GAP-G2 | **Reliabilitäts-Ratings inkonsistent angewandt** (z. B. Appendix-C-Anker fälschlich A1 statt B2). Framework eher behauptet als durchgesetzt. | Niedrig |
| GAP-G3 | **TV-WINDOW als *harte* Regel (im Sprint-5-Plan vorgeschlagen) ist fragwürdig:** TV ist im Code rein weich (Scoring) und betrifft nur eine Handvoll Spiele. Hart wäre evtl. überzogen. | Niedrig (Plan-Korrektur) |

---

## Priorisierung (Top 5, nach Hebel)

1. **GAP-F1/F2** — AC-2.1.8 auf weich umstellen + Q10 schließen. *Sofort, billig, hoher Hebel* (entlastet den schwersten Projektteil, direkt aus Jonas' Entscheidung).
2. **GAP-A1** — V(C)(11) PT→ET-Off-Day als harte Regel ergänzen (reise-relevant, prüfbar).
3. **GAP-A2** — V(C)(13) Off-Day-Verteilung als Compliance-Check ergänzen.
4. **GAP-G1** — endlich etwas *bauen + messen* (z. B. die fehlenden Compliance-Checks gegen den realen 2024+2025-Plan laufen lassen).
5. **GAP-B1** — Entscheidung: bleibt das Modell tag-granular (dann TV/Startzeit-Regeln explizit als „out of scope" deklarieren), oder wird Startzeit eine Dimension?

---

## Definition of „MLB-ready today" (Soll-Zustand)

Ein MLB-Scheduler könnte es einsetzen, wenn: **(1)** *alle* harten Article-V-Regeln
geprüft werden (nicht 7 von ~12), **(2)** Startzeiten modelliert ODER explizit als
außerhalb des Scope deklariert sind, **(3)** jede Datenart entweder echt oder klar als
Proxy mit Sensitivitätsanalyse markiert ist, **(4)** der SA-Move-Set keine harte Regel
still verletzen kann (Post-Move-Validierung), und **(5)** Compliance-Aussagen
korrekt eingestuft sind (kein „hart", was nur Heuristik ist).
