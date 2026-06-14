# Assessment 2026-06-11 — Wie gut sind wir wirklich, was fehlt noch?

**Anlass:** Zweite unabhängige Standortbestimmung nach Review (2026-06-10), zwei
Remediation-Runden und dem Daten-Ausbau (Originalpläne, Broadcasts, Co-Tenant,
Gate-Receipts, Drittnutzungen). **Methode:** ausschließlich frische Messungen in
dieser Session — keine übernommenen Behauptungen. Maßstab unverändert: *direkt
von einem MLB-Scheduler nutzbar.*

---

## 1 — Die neue Kernmessung: der echte Produktionsfall (erstmals möglich)

Seit heute liegt der **publizierte 2026-Originalplan** (Retrosheet, Rating A) im
Projekt — damit ist erstmals der reale Einsatzfall messbar: *nicht* einen
as-played-Plan mit Artefakten nachoptimieren, sondern den **Originalplan der
laufenden Saison** verbessern, mit allen realen Venue-Blackouts (River-Cats-
Co-Tenancy + 29 Konzert-/Event-Termine = 124 aktive Blackout-Tage über 14 Teams):

| Messung (Seed 42, 3 M Iter, Produktions-Config) | Ergebnis |
|---|---|
| Reise-km | 1.719.516 → 1.688.450 (**−1,81 %**, ≈ 31.000 km Liga-weit) |
| Publish-Gate | **PASS** |
| V(C)(13) Off-Day-Verteilung im Output | **0** |
| V(C)(14)/(15) Doubleheader im Output | **0** |
| Venue-Konflikte (Co-Tenant + Konzerte) im Output | **0** |
| Laufzeit | 23 s (Sandbox; 6 M+ auf echter Hardware offen) |

Das ist der erste End-to-End-Beweis der Produktkette *Originalplan → konformer,
besserer Plan*: keine geerbten Artefakte, alle Strukturregeln im Output sauber,
alle realen Stadion-Belegungen respektiert.

### Zwei neue Befunde aus dieser Messung (beide sofort behandelt)

**B1 — Reise-Envelope durch 2026 falsifiziert (gefixt).** Das publizierte
2026-Original legt BOS→OAK (4.223 km, 2×) und BOS→SFG (4.328 km) als
Back-to-Backs — Distanzen, die 2024/2025 nie vorkamen und auf denen unsere
4.200-km-Schwelle beruhte. Der im Review notierte Selbstbestätigungs-Verdacht
(„Envelope aus 2 Saisons kalibriert") ist damit eingetreten. **Fix:** Schwelle
datenbasiert auf **4.350** angehoben (deckt alles bis 2026 Beobachtete, blockiert
weiter die nie gelegte Klasse ≥ 4.392 SEA↔MIA), Historie im Code dokumentiert;
2026-Original danach hart-konform (0 Fails), Suite grün. *Lehre: Envelope bei
jedem neuen Originalplan re-validieren (gehört jetzt zur Messroutine).*

**B2 — All-Star-Break 2026 ist gestaffelt (Check-Verfeinerung nötig).** Die
league-wide-Heuristik meldet 3 ASB-Tage; per-Team gemessen haben **28/30 Teams
die vollen 4 Tage** (V(C)(17)-konform) — nur NYM@PHI spielen am 16.07. ein
Einzelspiel (3 Tage; mutmaßlich Special im ASG-Host-Kontext, V(C)(18)-Waiver-
Klasse). Der CBA-ASB-Softcheck misst also zu grob → **offener Punkt: per-Team-
ASB-Check** (klein, P1).

---

## 2 — Scorecard je Säule (Belege = Messungen dieser/letzter Session)

| Säule | Note | Beleg / Zustand | Was fehlt |
|---|---|---|---|
| **CBA-Regelwerk + Compliance-Messung** | **9/10** | 14 Regeln mit Verbatim-Quellen; V(C)(5)–(9), (11)–(15), (17) modelliert; Publish-Gate hinter ALLEN Output-Pfaden (backtest/main/api/pareto/whatif/disruption); Originalplan-Messungen: 2026 = 0/0, 2025 = 0/0, 2024 = 5 internationale Sonderfenster | per-Team-ASB (B2); PTET-≤7-Liga-Ausnahme unmodelliert (strikter Default); V(C)(8)-„home off-day"-Teilfall konservativ; **CBA läuft 12/2026 aus → Versionsschalter fehlt** |
| **Produktions-Optimierer (Warm-Start)** | **7/10** | Konformität durch Gate-Ablehnung + ausreichende Iterationen (NICHT "per Konstruktion": der Optimierer allein kann neue Verstöße erzeugen — gemessen ~29 V(C)(13) bei falschem/fehlendem ASB; sched13-/PTET-/Envelope-Penalty senkt die Wahrscheinlichkeit, das Publish-Gate ist die harte Garantie, ASB-Guard fängt die Fehlbedienung früh ab) + Gate-Beweis je Lauf; deterministisch (bit-identisch; Legacy-Anker jetzt als Test verankert = **1672794**, Finalisierung Punkt 4 — der früher dokumentierte 1680131 ist gedriftet und reproduziert auf dem aktuellen Stand NICHT mehr, daher korrigiert); 2026-Original −1,81 %, 2024 −2,39 %, 2025 −1,86 % (je 3 M) | km-Tiefe unbewiesen: 6 M+/Tuning (geo_topk, Phasen) nur auf echter Hardware; ehrlich: Konformität kostete km (alt −4,9 % war regelwidrig); **Pareto-SA regel-blind** (Punkte nur markiert); OROPT experimentell |
| **Datenfundament** | **9/10** | 15 Dateien SHA256-gefroren (Tool-Stand `verify_data_manifest`; Config-/Derived-Dateien wie revenue_model/tv_slots/phase_calibration bewusst nicht eingefroren); Originalpläne 3 Saisons (Gold, kreuzvalidiert: 2024 = 0 Abw.); TV-Fakten statt Heuristik (29/25 ESPN-Sonntage); Co-Tenant venueId-belegt, 0 Kollisionen; Gate-Receipts 28/30 echt (Spearman-Trio **0,892/0,922/0,958**); 29 Drittnutzungen 2026, 0 Kollisionen mit Original | TEX/CLE-Gate 2024 (paywalled); **Premium-Rekalibrierung offen** (Top-Teams absolut −22…−42 %); Konzert-Pflege bleibt manuell (Validierung automatisiert); Tokyo-Lücke im as-played-JSON (Gold deckt) |
| **Startzeiten/TV-Schicht** | **8/10** | Zuweisung Teil des Outputs; V(C)(5)/(6)/(8)/(9) auf zugewiesenen Zeiten = 0/0/0/0, deterministisch; reale Pläne mit CBA-Ausnahmen = 0 Verstöße | TV-Pins (nationale Fenster) noch nicht als harte SA-Constraints; per-Club-First-Pitch-Konventionen statt 19:00-Default |
| **Green-field (From-Scratch)** | **3/10** | Solver-Kern korrekt (n≤4 optimal, kreuzvalidiert), Lizenz-Plumbing + Beweis-Solve stehen | **Lizenz nicht aktiviert** (Uni-Netz); Skalierungstreppe ungemessen; Regel-Schicht im MIP unvollständig (nur B3+V(C)(12)+Trips); Voll-Saison = Forschungsfront (B&P) |
| **Disruption/What-if/Ops** | **7/10** | Repair V(C)(12)-fest (25→17-Beweis); volles Gate je Alternative; Perf-AC ≤60 s (5,5 s); What-if gate-markiert | Ops-Suite auf Seed-Daten (Hotels 5 Teams); Milton-e2e nur nightly messbar; Strategie-B-Regenerate ohne eigene Strukturregel-Garantien |
| **Engineering/Betrieb** | **5/10** | 463/513 Tests grün (50 slow nightly), Lint sauber, Manifest+Driftwarnung, Top-Level-Tools (`update_external_data`, `setup_gurobi`, Doppelklick-Commands), Provenienz-Doku | **KEIN GIT-REPO** — keinerlei Versionskontrolle/Historie/Rollback (größtes Einzelrisiko!); CI-Datei existiert, ist aber ohne Remote nie gelaufen; api.py ohne Auth/Job-Queue (dokumentierte TODOs); Dashboards nicht mit neuen Daten regeneriert |

---

## 3 — Ehrliches Gesamturteil

**Was wir heute wirklich können (belegt):** Einen publizierten MLB-Originalplan
einlesen, gegen das vollständigste öffentlich rekonstruierbare CBA-Regelwerk
auditieren, per Warm-Start messbar verbessern (−1,8 bis −2,4 % Reise-km bei
nachweislich null neuen Verstößen, inkl. realer Stadion-Belegungen), Startzeiten
regelkonform zuweisen, Disruptionen in Sekunden mit validen Alternativen
beantworten — alles deterministisch, manifest-gesichert, mit Compliance-Report
als Pflicht-Artefakt je Lauf. **In dieser Rolle — Audit-, Analyse- und
Verbesserungswerkzeug neben dem bestehenden Planungsprozess — ist das Tool heute
MLB-vorführbar.**

**Was wir ehrlich (noch) nicht sind:** das alleinige Saisonplanungs-Tool. Dafür
fehlen (a) Green-field in Liga-Größe (Lizenz + B&P-Skalierung + volle Regel-
Schicht im MIP), (b) die vertraglich-kommerzielle Schicht (nationale TV-Fenster
als harte Constraints, Interleague-/Rivalry-Konventionen, Sunday-Night-Rotation
über Jahre), (c) der Beweis der km-Obergrenze (6 M+/Tuning auf echter Hardware,
Benchmark gegen Literatur/Industrie), und (d) Betriebsreife im engen Sinn
(Versionskontrolle!, CI live, API-Härtung). Die −1,8 % auf 2026 sind solide,
aber als Verkaufsargument erst belastbar, wenn die Obergrenze ausgereizt und
extern eingeordnet ist.

---

## 4 — Was als Nächstes fehlt (priorisiert)

**P0 — Betrieb & externe Schalter (Tage):**
1. **Git-Repo initialisieren + GitHub-Remote + CI aktivieren.** Ohne
   Versionskontrolle ist jede weitere Arbeit fragil (kein Rollback, kein Diff,
   nightly-Suite läuft nie). Eine Stunde Arbeit, größter Risikoabbau pro Minute.
2. **Gurobi aktivieren** (Uni-Netz/VPN, `GUROBI_SETUP.command`) → sofort danach
   die Skalierungstreppe messen (n=6/8/10 … rounds vs. windowed).
3. **Messreihe auf echter Hardware:** 6–20 M Iterationen + `--geo-topk 4..8`
   auf dem 2026-Original; README-/Claim-Zahlen darauf umstellen (der
   2026-Original-Lauf ist ab jetzt DIE Referenzmessung, nicht as-played 2024).

**P1 — Produktwert (je 1–3 Tage):**
4. **Premium-Rekalibrierung entscheiden** (Befund: Top-Teams −22…−42 % absolut;
   Sportico-Anker liegen bereit) — bewusste Entscheidung, ändert Revenue-Zahlen
   projektweit.
5. **Pareto-Pfad regelfest machen** (sched13/ptet-Terme in `optimize_pareto`
   portieren) oder Frontier auf publizierbare Punkte filtern — aktuell nur
   Markierung.
6. **Per-Team-ASB-Check** (B2) + PTET-≤7-Ausnahme mit Startzeiten modellieren.
7. **TV-Pins als harte SA-Fenster** (Daten-Schnittstelle existiert:
   `assign_start_times(tv_pins=…)` + Broadcast-Fakten) — macht die TV-Schicht
   vom Validator zum Planungs-Feature.
8. **CBA-2027-Versionsschalter designen** (Regeln versionieren; Vertrag läuft
   01.12.2026 aus — Lockout-Risiko real).
9. **Benchmark-Einordnung** (TTP-Literatur, Industrie-Zahlen) für die km-Claims.

**P2 — Vervollständigung (Backlog):**
`dh_type` durch den SA-Roundtrip tragen (V(C)(14)-Satz-2 auf SA-Output messbar);
V(C)(8)-„home off-day"-Vollabdeckung; api.py Auth + Job-Queue; Ops-Realdaten
(C5) statt Seeds; TEX/CLE-Gate-Receipts bei Statista-Zugang; Dashboard-Rebuild
mit 2026-Daten; Quartals-Routine Konzert-Watchlist; 2027-Co-Tenant nach
MiLB-Planveröffentlichung; Envelope-Re-Validierung als fester Schritt in
`update_external_data --measure-original`.

---

## 5 — Messprotokoll dieser Session (Reproduktion)

```bash
export PYTHONPATH="$(pwd)"
# Kernmessung 2026-Produktionsfall (Skript siehe Chat / analog tools.backtest):
#   Retrosheet-2026-Original + production_optimizer_config + alle Blackouts
#   → -1,81 % km, Gate PASS, 0/0/0 Strukturverstöße
python -m tools.update_external_data --measure-original --years 2026
python -m tools.validate_revenue_model     # Spearman 0,892 / 0,922 / 0,958, PASS
python -m tools.fetch_cotenant_calendars --validate-only
python -m tools.verify_data_manifest       # 15/15 OK
python -m pytest -q -m "not slow"          # 463 passed (513 collected)
```
*Envelope-Fix: `src/feasibility.py` (4200 → 4350, Begründung + Historie im Code).*
