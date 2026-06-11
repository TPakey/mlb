# SPRINT 5 — Plan (2026-06-08)

**Ziel der Session.** Sprint 5 in vier eigenständige Sub-Sprints (5.1–5.4) zerlegen,
sodass jeder einzeln planbar, messbar und abnehmbar ist — und das Gesamtprodukt am
Ende auf einem Niveau steht, das die MLB wirklich beeindruckt. Der Plan ist die
Charter; die Umsetzung passiert sub-sprintweise mit eigenem Test-Lauf.

Vorgelagert gelesen: `HANDOVER_SPRINT_5.md`, `STATUS_REVIEW_2026-06-07.md`,
`REFACTOR_BACKLOG.md` (Q10), `OPS_SUITE_DESIGN.md`, `SPRINT_4_REVIEW.md`.

---

## 0 — North Star & Lage

**North Star.** Ein MLB-Travel-Ops-/Scheduling-Team kann das System **direkt
einsetzen**: ein CBA-konformer, gegen den realen Plan messbar besserer Saisonplan
*plus* einsatzfertige operative Dossiers pro Trip *plus* nachvollziehbare,
quellenbelegte Begründung jeder harten Regel.

**Wo wir stehen (Ende Sprint 4).** Warm-Start ist der einzige Produktionspfad,
−5,4 % Reisekilometer (2024, 6M Iter), 0 CBA-Verletzungen, Revenue-Spearman 0,892,
373 Tests grün, Determinismus bit-identisch. Alle Sprint-4-Features gegated.

**Der ehrliche Befund aus dem Handover.** Es gibt **keine „billigen" offenen
Code-Punkte** mehr. Die verbleibenden Lücken zu „100 % MLB-tauglich" sind entweder
(a) externe Daten/Freigaben oder (b) Forschungs-Algorithmik mit hohem Aufwand. Genau
deshalb teilt Sprint 5 die Arbeit in vier Säulen — jede schließt eine andere Art von
Lücke.

**Maßstab (gilt durchgehend).** Durchdenken → recherchieren → **messen statt
behaupten** → Qualität vor Tempo. Determinismus nie brechen. Neue Features immer
gegated (Default = unverändertes Verhalten). Daten-Ehrlichkeit: Seed klar markieren,
Mechanik datenunabhängig bauen.

---

## 1 — Sequenzierung & Begründung

Die vier Sub-Sprints sind grob in dieser Reihenfolge geplant, weil jeder den nächsten
absichert. Sie sind teilweise parallelisierbar, aber die Abhängigkeitslogik ist:

```
5.1 Härtung & Refactor   ──► Fundament: stabil, getunt, wartbar
        │
        ▼
5.2 Externe Daten        ──► macht die „100 %"-Compliance-Claims real
        │
        ▼
5.3 Ops-Suite            ──► der sichtbare „Wow"-Layer fürs MLB-Ops-Team
        │
        ▼
5.4 Algorithmik-Forschung ─► höchste Decke, höchstes Risiko, zuletzt auf
                              gehärtetem Fundament
```

**Warum 5.1 zuerst.** Tuning-Kalibrierung und Refactor-Abschluss senken das Risiko
*aller* folgenden Arbeiten. Man baut keine neuen Türme auf ein ungetestetes Fundament.

**Warum 5.4 zuletzt.** Branch-and-Price ist das Item mit der größten Unsicherheit
(Lizenz, Tractability). Es profitiert davon, dass Datenschicht (5.2) und Test-Harness
(5.1) dann schon belastbar sind — und es ist das einzige Item, das auch scheitern
darf, ohne den Auslieferungsstand zu gefährden (Warm-Start bleibt P0).

**Empfehlung zur Reihenfolge der Wertschöpfung:** Wer den schnellsten sichtbaren
MLB-Effekt will, zieht **5.3 (Ops-Suite)** nach 5.1 vor — das ist der Teil, den ein
Ops-Mensch *anfasst*. Wer den stärksten Compliance-Claim will, priorisiert **5.2**.

---

## 2 — Übergreifende Prinzipien (für alle Sub-Sprints verbindlich)

- **Determinismus-Gate.** Jedes neue Feature kommt mit Default off. Nach jedem
  Sub-Sprint: bit-identischer Lauf (Default + feas/holiday on) nachweisen.
- **Messen statt behaupten.** Jeder Performance-/Qualitäts-Claim braucht eine Zahl,
  eine Instanz und einen reproduzierbaren Befehl. Kein „besser", ohne Baseline.
- **Daten-Ehrlichkeit.** Illustrative Seeds bleiben klar markiert; das Schema, in das
  echte Daten einlaufen, ist die eigentliche Lieferung.
- **Test-Disziplin.** `python -m pytest -m "not slow" -q -p no:cacheprovider`, in der
  Sandbox in 3–4 Gruppen < 45 s splitten. Pro Sub-Sprint eigene `tests/test_sprint_5_X.py`.
- **Dokumentations-Pflicht.** Jeder Sub-Sprint endet mit einem `SPRINT_5_X_REVIEW.md`
  (Was gebaut, was gemessen, was bewusst gelassen) — wie Sprint 4.

---

## SPRINT 5.1 — Härtung & Refactor (Fundament)

**Ziel.** Den Auslieferungsstand von „grün und schnell" auf „kalibriert,
audit-fest und wartbar" heben. Nichts Neues fachlich — alles, was die folgenden
drei Sub-Sprints sicher macht.

**Warum das MLB beeindruckt.** Ein Scheduling-System, das die MLB übernimmt, wird
auditiert. Reproduzierbare Tuning-Kurven, ein sauberes Modul-Layout und eine
Test-Suite, die Determinismus *beweist*, sind das, was den Unterschied zwischen
„nettes Forschungsprojekt" und „produktionsreif" ausmacht.

### Arbeitspakete

1. **Produktions-Tuning-Kalibrierung (P0-relevant).** Die im Status-Review offenen
   Parameter `--geo-topk 4–6`, `--feas-lambda 50000`, `--holiday-lambda 5000` auf
   vollen 6M-Iter-Läufen kalibrieren. Lieferung: eine **Tuning-Kurve** (km-Gewinn vs.
   Parameter) für 2024 *und* 2025, plus eine begründete Default-Empfehlung. Nutzt das
   vorhandene `tools/tune_run.py` / `tools/tuning.py` / `data/phase_calibration.json`.
   Lange Läufe in der Sandbox splitten (Konvention).
2. **Q10 — pragmatische Route (HOCH, der einzige echte offene Code-Punkt).** Den
   deterministischen SA-Repair in `generator_optimizer` erweitern, sodass er aktiv
   Heimstände in zu lange Road-Trips einschiebt (heute werden nur gleichlange Serien
   getauscht). Ziel: reale AC-2.1.8-Verletzungen von heute worst ~14–20 Tagen weiter
   senken, **1-Worker-deterministisch**. Das liefert keinen ≤13-Beweis (das ist
   5.4), aber eine messbare, ehrliche Verbesserung im Produktionspfad. xfail bleibt,
   wird aber mit der neuen Messzahl annotiert.
3. **Refactor-Backlog abschließen.** A20/A21 sind erledigt (Fassaden-Muster). Übrig:
   die markierten Sandbox-Artefakte (`src/colgen/_probe.txt`) lokal entfernen,
   `compileall` + `pyflakes` über `src/` sauber halten, und die in A20/A21 als
   „Fassade statt Package" verbliebenen Stellen dokumentieren (Architektur-Notiz,
   kein Refactor-Risiko kurz vor Übergabe).
4. **Test- & Determinismus-Härtung.** (a) Eine **Golden-Master-Signatur** des
   Produktionsplans (volle Spiel-Signatur) als Regressions-Anker einchecken, sodass
   jede künftige Änderung am Default-Pfad sofort auffällt. (b) Die `slow`-CP-SAT-Tests
   in einen optionalen Nightly-Lauf bündeln. (c) Coverage-Lücken in den neuesten
   Modulen (`event_conflicts`, `ops_*`) schließen.
5. **CLI- & Fehler-Härtung fortführen.** `main._validate_args` (Sprint 4) um die in
   5.2/5.3 neu hinzukommenden Flags vorbereiten; einheitliche `DataSourceError`-Pfade
   für alle neuen Datendateien.

### Akzeptanzkriterien
- Kalibrierungs-Report mit Kurven für 2024+2025, reproduzierbar per ein-Zeilen-Befehl.
- Q10-Repair: gemessene Reduktion der worst-case away-Tage, deterministisch, Default off.
- `pyflakes`/`compileall` sauber; keine Sandbox-Artefakte mehr im Repo.
- Golden-Master-Test grün und bit-identisch.
- Volle Nicht-Slow-Suite grün (Ziel: > 373 Tests, neue Tests inklusive).

### Risiken & Aufwand
- **Risiko:** Tuning-Läufe sind lang (6M Iter) → in der Sandbox splitten, ggf. über
  mehrere Sessions. **Mitigation:** reduzierte Instanzen für Kurvenform, voller Lauf
  nur zur Bestätigung der gewählten Defaults.
- **Aufwand:** mittel. Geringes Architektur-Risiko, hoher Absicherungs-Wert.

---

## SPRINT 5.2 — Externe Daten integrieren (Compliance real machen)

**Ziel.** Die vier daten-gegateten Blocker aus dem Handover von „Mechanik steht,
Daten illustrativ" auf „echte Daten laufen 1:1 ein" heben — durch eine saubere
**Ingestion-Schicht mit Schema-Validierung**, sodass MLB-Ops nur noch die echten
Dateien liefern muss.

**Warum das MLB beeindruckt.** Heute sagt das System „compliant, aber mit
Beispieldaten". Nach 5.2 sagt es „compliant gegen *eure* TV-Fenster, *euren*
Venue-Kalender, *eure* Gate-Receipts" — und validiert die gelieferten Daten beim
Import. Das ist der Schritt von Demo zu Betrieb.

### Arbeitspakete

1. **National-TV-Fenster als harte Anforderung.** Heute gibt es `src/tv_slots.py` +
   `data/tv_slots.json` (Revenue-Seite). Erweitern um eine **harte Compliance-Regel
   `TV-WINDOW`** (opt-in, gegated) analog zu VENUE-AVAIL aus Sprint 4: ESPN/FOX/TBS-
   Exklusivslots als Pflicht-/Sperr-Constraints im Compliance-Report
   (`src/compliance.py`) und als Soft-/Hard-Term im Optimierer. **Ingestion:**
   ein dokumentiertes JSON-Schema + Loader mit `DataSourceError` bei Verstoß.
2. **Venue-Belegungskalender mit echtem Schema.** Mechanik steht (VENUE-AVAIL +
   `home_blackout_days`, `event_conflicts.venue_conflicts`). 5.2 liefert das
   **produktive Importformat** (NFL-Shared-Stadien, Konzerte, andere Events) mit
   Validierung (Datumsbereiche, Venue-IDs gegen `teams.json`) und einen
   **Konflikt-Report**, der bei Import zeigt, welche geplanten Heimspiele kollidieren.
3. **Gate-Receipts statt Attendance-Proxy.** `src/revenue.py` /
   `src/revenue_validation.py` nutzen heute einen Attendance-Proxy (Spearman 0,892).
   5.2 baut den **Adapter für echte Gate-Receipts** (pro-Spiel-Einnahmen) ins selbe
   Validierungs-Harness, sodass beim Vorliegen echter Daten das Revenue-Modell
   pro Spiel kalibriert und der Spearman/MAE neu vermessen wird. Bis dahin: der
   Proxy bleibt Default, der Receipt-Pfad ist gegated und getestet.
4. **CBA-Wortlaut AC-2.1.8 strukturieren.** Den exakten Reisetag-Zähl-Wortlaut als
   **maschinenlesbare Definition** in `docs/CBA_DEFINITIONS.md` + `data`-Referenz
   ablegen, sodass der Compliance-Report die Regel zitiert *und* die Zählweise
   konfigurierbar ist (inkl./exkl. Off-Days an Trip-Rändern). Vorbereitung für 5.4.
5. **Datenquellen-Recherche & Beschaffungs-Briefing.** Für jede der vier Datenarten:
   Wo kommen die echten Daten her, in welchem Format, welche MLB-Stelle liefert sie,
   welche Felder sind Pflicht. Liefert Jonas eine **konkrete Anfrage-Vorlage** an
   MLB-Ops (kein Code, aber der Schlüssel, um die Blocker zu lösen).

### Akzeptanzkriterien
- Drei dokumentierte, validierende Loader (TV, Venue, Gate-Receipts) mit
  `DataSourceError`-Härtung und je einem Beispiel-Echtdatensatz-Schema.
- `TV-WINDOW`-Compliance-Regel im Report, opt-in, gegated, E2E-getestet.
- Venue-Konflikt-Report über echtes Schema, gegen realen 2024-Plan demonstriert.
- Gate-Receipt-Adapter im Validierungs-Harness, Default-Verhalten unverändert.
- Beschaffungs-Briefing als eigenes Dokument für Jonas.

### Risiken & Aufwand
- **Risiko:** Ohne echte Daten bleibt der Nachweis auf synthetischen/illustrativen
  Datensätzen. **Mitigation:** realistische synthetische Daten + glasklare
  Schema-Doku; der Wert ist die *einlauffähige* Schicht, nicht die Beispieldaten.
- **Aufwand:** mittel. Baut konsequent auf den Sprint-4-Mechaniken auf.

---

## SPRINT 5.3 — Ops-Suite ausbauen (der sichtbare Wow-Layer)

**Ziel.** Die in Sprint 3 angelegte Scheduler-Operations-Suite (Routing, Hotels,
Security-Briefing, Trip-Dossier) von „solider Schätzer + illustrativer Seed" auf
**echtes MLB-Travel-Ops-Niveau** heben — der Teil, den ein Ops-Mensch täglich anfasst.

**Warum das MLB beeindruckt.** Die Kalenderoptimierung ist die unsichtbare Kür; die
Ops-Suite ist das, was ein Travel-Coordinator *sieht*. Ein druckfertiges Trip-Dossier
mit echtem Routing, belastbarer Hotel-Empfehlung und einem professionellen
Security-Briefing ist der greifbarste „das nehmen wir"-Moment.

### Arbeitspakete

1. **Routing: echte Maps-/Routing-API anbinden.** Die `RouteLeg`-Schnittstelle in
   `src/ops_routing.py` ist bewusst so gebaut, dass ein API-Provider den Haversine-
   ×-Detour-Schätzer 1:1 ersetzt. 5.3 implementiert den **Provider-Adapter** (echte
   Straßendistanz/Fahrzeit/Verkehrslage), mit Caching und Fallback auf den Schätzer,
   wenn kein API-Key vorhanden. Default = Schätzer (deterministisch); API gegated.
2. **Stadion-genaue Koordinaten.** Heute Ballpark-Stadt-Koordinaten. 5.3 ersetzt sie
   durch **exakte Stadion-Koordinaten** (verfeinert Routing-Distanzen, vgl. P2-4) —
   verifizierbare, stabile Fakten, in `teams.json`/`team_airports.json` gepflegt.
3. **Hotel-Empfehlung produktionsreif.** Das Scoring (Nähe/Komfort/Security/Historie)
   steht. 5.3 liefert (a) den **Import-Pfad für echte Club-Buchungshistorie** ins
   `team_hotels.json`-Schema, (b) **Audit-Flags** für neue Häuser, (c) eine
   Sensitivitäts-Analyse der Score-Gewichte (welche Gewichtung bevorzugt was).
4. **Security-Briefing schärfen.** Die saison-bewusste Klimatologie + Level-I-Trauma-
   Center sind belastbar. 5.3 ergänzt (a) **Liaison-Kontakt-Felder** als strukturierte
   Schnittstelle (EMS/PD, am Spieltag zu befüllen — klar als Liaison markiert),
   (b) High-Profile-Flags für Rivalitäts-/Feiertags-/Primetime-Spiele aus 5.2-TV-Daten,
   (c) ein **Quellen-/Aktualitäts-Stempel** pro Faktum (Daten-Ehrlichkeit sichtbar).
5. **Dossier-Ausgabe auf Druckniveau.** `tools/generate_trip_dossier.py` +
   `dashboard/build_ops_dashboard.py`: ein **PDF-Export** des Trip-Dossiers (über die
   pdf-Pipeline), plus eine aufgeräumte HTML-Ansicht im Ops-Dashboard. Vorbild:
   `docs/EXAMPLE_TRIP_DOSSIER_NYY_2024.md`.

### Akzeptanzkriterien
- Routing-API-Adapter mit Cache + deterministischem Fallback, gegated, getestet.
- Exakte Stadion-Koordinaten in den Stammdaten; Routing-Distanz-Diff dokumentiert.
- Hotel-Import-Pfad + Audit-Flags; Sensitivitäts-Analyse als kurzer Report.
- Security-Briefing mit Liaison-Schema + Quellen-Stempel; keine erfundene
  Bedrohungsspezifik (Daten-Ehrlichkeit gewahrt).
- Druckfertiges Trip-Dossier (PDF) für mind. ein Team (z. B. NYY 2024).

### Risiken & Aufwand
- **Risiko:** Maps-API kostet/braucht Key → Adapter muss ohne Key voll funktionieren
  (Fallback). **Risiko:** Security-Briefing darf nie über belegbare Fakten hinaus
  „Bedrohungen erfinden". **Mitigation:** strikte Liaison-Feld-Trennung beibehalten.
- **Aufwand:** mittel-hoch (breit, aber gut vorbereitet durch Sprint 3).

---

## SPRINT 5.4 — Algorithmik-Forschung (höchste Decke)

**Ziel.** Die zwei offenen Forschungs-Items angehen, die das System von „schlägt den
realen Plan im Warm-Start" auf „garantiert CBA-konform auch from-scratch" heben
könnten — mit der gebotenen Ehrlichkeit, dass dies das Item mit dem höchsten Risiko ist.

**Warum das MLB beeindruckt.** Ein nachweisbar AC-2.1.8-garantierter, from-scratch
erzeugter Plan ist die „grüne Wiese" — der heilige Gral des Sports-Scheduling. Selbst
ein *belastbar dokumentierter Versuch* (mit Messungen) ist auf MLB-Niveau wertvoll,
weil er die Grenze des Machbaren sauber kartiert.

### Kontext (aus dem Refactor-Backlog, Q10)
AC-2.1.8 (max. 13 „days away") strukturell durchzusetzen wurde über **sechs
unabhängige CP-SAT-Ansätze** als mit Standardmitteln (1-Worker) **nicht tragfähig**
belegt: monolithische Gap, Gap+Break-Anker, Drei-Phasen-Decomposition, globales
Fix-and-Optimize, FIXED_SEARCH, Automaton/Window. **Korrektheit/Soundness aller
Formulierungen ist gesichert** (315-Instanz-Brute-Force-Orakel) — es scheitert
ausschließlich an der Solver-Tractability. Der dokumentierte nächste Schritt ist
Branch-and-Price / Spaltengenerierung.

### Arbeitspakete

1. **Branch-and-Price / Spaltengenerierung für From-Scratch (Forschung, gegated).**
   Das Subpackage `src/colgen/` (patterns/rmp/pricing/engine/hap) existiert bereits.
   5.4 baut darauf einen **Branch-and-Price-Rahmen**, der AC-2.1.8 strukturell im
   Pricing/Branching durchsetzt — das ist der einzige im Backlog verbliebene Weg zu
   einer ≤13-Garantie. **Zwei Gleise:**
   - **Gleis A (OSS-first, lizenzfrei):** CP-SAT-Pricing + GLOP-RMP weiter ausreizen,
     evtl. mit OR-Tools-Branch-and-Price-Mustern. Recherche zuerst (was gibt es an
     belastbarem OSS), dann fundiert integrieren oder selbst bauen.
   - **Gleis B (kommerziell, beschaffungs-gegatet):** Gurobi/CPLEX als optionaler
     Solver-Backend hinter einem Adapter. Nur wenn Jonas die Lizenz beschafft;
     vorbereitet, aber nicht erzwungen.
2. **AC-2.1.8 ≤13-Garantie nachweisen.** Akzeptanzkriterium aus dem Backlog: voller
   Pfad MIT All-Star-Break **zuverlässig** (auch 1-Worker, mehrere Seeds)
   OPTIMAL/FEASIBLE in akzeptabler Zeit, worst_away ≤ 13. Bei Erfolg:
   `_add_ac_2_1_8_gap_constraints` verdrahten, xfail entfernen. Bei Misserfolg:
   sauber dokumentierter Negativbefund (wie OROPT in Sprint 4).
3. **Volle TTP-Nachbarschaften (Forschung).** Ejection Chains, 2-opt über Trips —
   über die in Sprint 4 als „kein Win" vermessenen Einzel-Moves (OR-opt) hinaus.
   **Ehrlich vermessen** gegen den stochastischen GEO-Move-Baseline; nur integrieren,
   wenn ein realer km-Win bei ≥300k Iter nachweisbar ist. Default off.
4. **Negativ-Befund-Disziplin.** Jeder nicht gewonnene Ansatz wird wie OROPT/Q10
   dokumentiert (Messung + Begründung). Ein sauber kartierter Negativbefund ist hier
   ein gültiges, wertvolles Ergebnis — kein Misserfolg.

### Akzeptanzkriterien
- **Erfolgsfall:** ≤13-Garantie reproduzierbar, xfail entfernt, Determinismus gewahrt.
- **Teilerfolg:** messbar engere Schranke als heute, dokumentiert, gegated.
- **Negativfall:** belastbarer, gemessener Befund + Empfehlung — wie Sprint-4-OROPT.
- TTP-Nachbarschaften: entweder messbarer Win (dann gegated integriert) oder
  dokumentierter Negativbefund.

### Risiken & Aufwand
- **Risiko:** höchste Unsicherheit im ganzen Sprint. Branch-and-Price ist offen, ob
  es in akzeptabler Zeit löst; Gurobi braucht Lizenz. **Mitigation:** Warm-Start
  bleibt P0-Produktionspfad — 5.4 gefährdet die Auslieferung nie.
- **Aufwand:** hoch. Eigener Sprint, mehrere Sessions, Forschungscharakter.

---

## 3 — Roadmap (Überblick)

| Sub-Sprint | Fokus | Wert | Risiko | Aufwand | Liefert |
|---|---|---|---|---|---|
| **5.1** | Härtung & Refactor | Audit-Festigkeit, Tuning | niedrig | mittel | Kalibrierungs-Report, Golden-Master, Q10-Repair |
| **5.2** | Externe Daten | Compliance real machen | mittel | mittel | 3 Loader, TV-WINDOW-Regel, Beschaffungs-Briefing |
| **5.3** | Ops-Suite | sichtbarer Wow-Layer | mittel | mittel-hoch | Routing-API, PDF-Dossiers, Hotel-Import |
| **5.4** | Algorithmik | höchste Decke (≤13-Garantie) | hoch | hoch | B&P-Rahmen, AC-2.1.8-Nachweis o. Negativbefund |

**Vorgeschlagene Reihenfolge:** 5.1 → (5.2 ∥ 5.3) → 5.4. 5.2 und 5.3 sind weitgehend
unabhängig und können parallel/in beliebiger Reihenfolge laufen; beide brauchen das
gehärtete Fundament aus 5.1. 5.4 zuletzt.

---

## 4 — Was die MLB am Ende beeindruckt (Synthese)

1. **Plan-Qualität mit Beweis:** messbar besser als der reale Plan, kalibriert, mit
   Golden-Master-Regression und reproduzierbaren Tuning-Kurven (5.1).
2. **Compliance gegen echte Daten:** TV-Fenster, Venue-Kalender, Gate-Receipts laufen
   1:1 ein und werden beim Import validiert (5.2).
3. **Betriebsreife Dossiers:** druckfertige Trip-Briefings mit echtem Routing,
   belastbarer Hotel-Empfehlung und professionellem, ehrlichem Security-Briefing (5.3).
4. **Forschungs-Glaubwürdigkeit:** ein sauber kartierter (Erfolgs- oder Negativ-)
   Befund zur ≤13-Garantie und to TTP-Nachbarschaften — die Grenze des Machbaren
   ehrlich vermessen (5.4).

Der rote Faden: **alles gemessen, nichts behauptet; alles gegated, nichts gebrochen;
jede Beispieldatei klar als Seed markiert, jedes Schema produktionsreif.**

---

## 5 — Offene Punkte für Jonas (Entscheidungen, die den Sprint beeinflussen)

1. **Reihenfolge bestätigen:** 5.1 → (5.2 ∥ 5.3) → 5.4, oder eine andere Priorität
   (z. B. 5.3 zuerst für den schnellsten sichtbaren Effekt)?
2. **Gurobi/CPLEX:** Lizenz beschaffen (ermöglicht Gleis B in 5.4) — oder strikt
   OSS-first bleiben?
3. **Echte Daten:** Kannst du an MLB-Ops herantreten für TV-Fenster, Venue-Kalender,
   Gate-Receipts, CBA-Wortlaut? (5.2 liefert dir die Anfrage-Vorlage.)
4. **Maps-API:** Provider/Key für das Routing in 5.3 vorhanden, oder bauen wir
   strikt mit deterministischem Fallback?

> Sobald 5.1 startet, wird daraus eine eigene `SPRINT_5_1_CHARTER.md` mit konkreten
> Tasks, Befehlen und Messzielen — analog zu den bisherigen Sprint-Chartas.
