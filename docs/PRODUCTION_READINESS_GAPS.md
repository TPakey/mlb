# Produktionsreife — Lückenliste „Was ist heute noch nicht MLB-tauglich?"

**Stand:** 2026-06-09 (Sprint 5, nach Code-Review & kritischer Außenprüfung).
**Zweck:** Ehrliche, priorisierte Gesamtliste aller offenen Punkte bis „MLB könnte
es heute direkt nutzen". Severity: **P0** = blockiert Tauglichkeit/Korrektheit ·
**P1** = wichtige Qualität/Glaubwürdigkeit · **P2** = Politur.
Flag: 🔒 = extern blockiert (Daten/Freigabe), 🧪 = unverifiziert/zu messen.

---

## A — Compliance & Regelkorrektheit

| # | Lücke | Sev | Aktion |
|---|---|---|---|
| A1 | **AC-2.1.8 (13) noch als harte Regel im Code/Docs**, obwohl als nicht-erforderlich entschieden | P1 | Auf weiches Qualitätsziel zurückstufen; Compliance-Report, `CBA_DEFINITIONS.md`, Handover, Refactor-Backlog Q10 bereinigen |
| A2 | **Q10 `xfail`-Test** prüft eine nicht erforderliche ≤13-Garantie | P1 | Entfernen oder zu reinem Soft-Metrik-Test umwidmen |
| A3 | **AC-2.1.9 hat 3 Formulierungen** (konsekutiver Lauf / 21-Tage-Fenster / periodischer Break) ohne dokumentierten Äquivalenzbeweis | P1 | Äquivalenz beweisen + dokumentieren (oder Abweichung benennen) |
| A4 | **V(C)(12)-Heimteam-Ausnahme (24 bei Regen-Reschedule)** nicht modelliert | P2 | Bei Reschedule-Logik ergänzen |
| A5 | **Weitere harte V(C)-Regeln** (Getaway-Startzeit V(C)(8), PT→ET-Off-Day V(C)(11), Tag-nach-Nacht V(C)(9)) nicht als Compliance-Checks abgebildet | P1 | Verbatim liegen vor (`regulations/`); als Checks formalisieren |
| A6 | **„Nicht im CBA"-Aussage** nur gegen getrunkierten Text + Article V geprüft | P2 🔒 | Voll-PDF/Appendices/MoU gegenchecken |

## B — Externe Daten (echt vs. Proxy/illustrativ)

| # | Lücke | Sev | Aktion |
|---|---|---|---|
| B1 | **TV-Fenster:** nur Struktur; keine Spiel-für-Spiel-Daten, keine harte `TV-WINDOW`-Regel gebaut | P1 🧪 | SMW×Schedule-JSON-Join; Grenznutzen vorher messen (s. G2) |
| B2 | **Venue:** Konzert-/Event-Kalender für 28 von 30 Stadien fehlen komplett | P1 🧪 | Venue-Kalender + Ticketing; nur die 2 geteilten Venues sind erfasst |
| B3 | **Gate-Receipts:** bleibt Attendance-Proxy; echte Receipts nicht öffentlich | P2 🔒 | Forbes-Kalibrierung + Sensitivität; ehrlich als Proxy halten |
| B4 | **Appendix C Reisezeiten:** offizielle Tabelle nur als Bild lokalisiert, im Repo nur Proxy | P1 🔒 | Bild in `regulations/` sichern; Werte 1:1 übernehmen |
| B5 | **Ticketpreise pro Team/Jahr** teils hinter Paywall (TMR/Statista) | P2 🔒 | Liga-Ø + Ranking öffentlich; exakt = Beschaffung |
| B6 | **Hotel-Daten** (`team_hotels.json`) sind illustrativer Seed | P1 🔒 | Club-Buchungshistorie importieren |
| B7 | **Security-Liaison-Daten** (EMS/PD-Spieltagslage) leer | P1 🔒 | Lokale Liaison-Kontakte anbinden |
| B8 | **Daten-Jahres-Konsistenz:** Recherche 2024/25, Constraint-Messungen auf 2026-Plan | P1 | Auf einheitliches Referenzjahr ziehen |

## C — Optimierung & Algorithmik

| # | Lücke | Sev | Aktion |
|---|---|---|---|
| C1 | **From-Scratch-Pläne nicht MLB-tauglich** (nur Warm-Start ist Produktionspfad) | P1 | Akzeptiert, solange Warm-Start P0; B&P nur optional (nach A1-Entscheidung) |
| C2 | **TTP-Nachbarschaften** (Ejection Chains, 2-opt über Trips) unerforscht | P2 | Nur wenn messbarer km-Win; sonst Negativbefund |
| C3 | **Produktions-Tuning** (`geo-topk`, `feas-lambda`, `holiday-lambda`) nicht auf vollen 6M-Iter kalibriert | P1 | Kurven 2024+2025; Default begründen |
| C4 | **Kein kommerzieller Solver** angebunden (Gurobi-Adapter) | P2 🔒 | Optional; Academic-Key kommt, nur für Experimente |

## D — Ops-Suite (Sprint 5.3)

| # | Lücke | Sev | Aktion |
|---|---|---|---|
| D1 | **Routing = Schätzer**, echte Maps-API (ORS) nicht verdrahtet | P1 | ORS-Key liegt; Adapter + eingefrorener Cache bauen |
| D2 | **Stadion-Koordinaten** = Ballpark-Stadt statt exakt | P2 | Exakte Koords in Stammdaten |
| D3 | **Trip-Dossier-Export** nur Markdown, kein druckfertiges PDF | P2 | PDF-Pipeline |
| D4 | **Security-Briefing** ohne Quellen-/Aktualitäts-Stempel pro Faktum | P2 | Provenienz-Felder ergänzen |

## E — Evidenz & Modellgüte (Fatigue, Revenue)

| # | Lücke | Sev | Aktion |
|---|---|---|---|
| E1 | **Fatigue-Gewichte nicht evidenz-kalibriert**; Ost/West-Asymmetrie fehlt | P1 | Aus PNAS-2017/Winter-2009 ableiten |
| E2 | **Chrono-Effektgrößen aus 1992–2011** (vor Charter/2022-Ruheregeln) — evtl. überzeichnet | P1 🧪 | Auf heutige Ära skalieren/diskontieren |
| E3 | **Performance→Reisekosten-Mapping** ist selbst eine ungetestete Annahme | P1 🧪 | Sensitivitätsanalyse; Fairness wahren (keine Wettbewerbsvorteile) |
| E4 | **Revenue-Proxy pro Spiel unvalidiert** (Forbes fixt nur Jahres-Skala) | P2 | Sensitivität; Scope (Gate ≠ Gesamtrevenue) klar abgrenzen |

## F — Engineering & Produktreife

| # | Lücke | Sev | Aktion |
|---|---|---|---|
| F1 | **Determinismus vs. externe API:** Cache-/Freeze-Mechanik (ORS) noch nicht gebaut | P1 | Frozen-Cache + Haversine-Fallback |
| F2 | **Keine MLB-taugliche Oberfläche** (CLI + statische Dashboards; kein bedienbares UI/Service für Ops) | P1 🧪 | Klären, ob MLB CLI akzeptiert oder UI/API braucht |
| F3 | **Refactor-Backlog-Reste** (Fassaden statt Packages, `_probe.txt`-Artefakt) | P2 | Aufräumen, dokumentieren |
| F4 | **CLI-/Fehler-Härtung** für neue 5.2/5.3-Flags noch offen | P2 | `_validate_args` erweitern; `DataSourceError`-Pfade |
| F5 | **2025-Pfad nicht voll durchgemessen** (Warm-Start −5,4 % nur 2024 belegt) | P1 | 2025 voll laufen lassen + Compliance prüfen |

## G — Validierung & Vertrauen

| # | Lücke | Sev | Aktion |
|---|---|---|---|
| G1 | **Kein Golden-Master-Regressionsanker** für den Produktionsplan | P1 | Voll-Signatur einchecken (Sprint 5.1) |
| G2 | **Grenznutzen der externen Daten UNVERIFIZIERT** — Warm-Start erfüllt Venue/TV implizit schon; bewegt der Optimierer überhaupt etwas, das sie verletzt? | **P0** 🧪 | Move-Set des Optimierers im Code prüfen, BEVOR Daten gebaut werden |
| G3 | **Schedule-JSONs als Ground Truth** ungeprüft (Vollständigkeit/Korrektheit angenommen) | P2 | Stichprobe gegen offizielle MLB-Quelle |

## H — Prozess & Doku-Hygiene

| # | Lücke | Sev | Aktion |
|---|---|---|---|
| H1 | **Doku teils widersprüchlich** nach AC-2.1.8-Entscheidung (Handover, Q10, CBA_DEFINITIONS sagen noch „13 hart") | P1 | Repo-weit angleichen |
| H2 | **Viel Planung, noch keine Sprint-5-Funktionalität gebaut/gemessen** | P1 | Auf Build+Messung umschalten |
| H3 | **Reliabilitäts-Ratings (Admiralty) nur teilweise konsequent** angewandt | P2 | Beim Daten-Build konsequent mitführen |

---

## Die drei mit dem höchsten Hebel (zuerst)

1. **G2 — Grenznutzen messen** (P0): Im Code prüfen, was der Warm-Start-Optimierer
   tatsächlich verschiebt. Ergebnis entscheidet, ob B1/B2 (TV/Venue) überhaupt lohnen.
   *Verhindert, dass wir tagelang Daten bauen, die nichts bewegen.*
2. **A1/A2/H1 — AC-2.1.8-Aufräumen** (P1): Die getroffene Entscheidung sauber durch
   Code + Docs ziehen. Klein, aber beseitigt eine Korrektheits-/Konsistenzlücke.
3. **C3 + F5 — Tuning & 2025 messen** (P1): Den Produktionspfad auf beiden Jahren
   belastbar kalibrieren und belegen. *Das ist „messen statt behaupten".*
