# Daten-Provenienz — vollständige Registry aller Datendateien

**Stand: 2026-06-11.** Eine Zeile pro Datei in `data/`: Was ist es, woher kommt es,
wie vertrauenswürdig ist es (Rating), wie wird es aufgefrischt, wie wird es validiert.
**Ratings:** A = offizielle/publizierte Primärquelle (bzw. deren API), B = faktenbasierte
Rekonstruktion oder Sekundär-Mirror einer Primärquelle, **Seed** = illustrative
Platzhalter (in Produktion durch Club-Realdaten zu ersetzen).
Drift-Schutz: alle Kern-Dateien sind SHA256-gefroren in `data/MANIFEST.sha256.json`
(Check beim Laden + `python -m tools.verify_data_manifest`; nach bewusstem Update
`--update`). Sammel-Einstieg: `python -m tools.update_external_data --status|--all`.

## Pläne & Regeln (harte Entscheidungsgrundlage)

| Datei | Inhalt | Rating | Refresh | Validierung |
|---|---|---|---|---|
| `mlb_schedule_2024/2025.json` | As-played-Saisons (MLB Stats API) | A (as-played-Semantik!) | `tools/fetch_schedule.py` | Manifest; SCHED-162/HA mit Referenz-Counts; BEKANNTE LÜCKE: Tokyo-Series 2025 fehlt (2 Spiele) |
| `retrosheet/{2024,2025,2026}SKED.TXT` | **Original**-Spielpläne (publiziert) | **A (Goldquelle)** | `tools/fetch_retrosheet` | Parse-Test 2430 Spiele/Saison; Kreuzvalidierung vs. Rekonstruktion: 2024 = 0 Abw., 2025 = 4 erklärte (Tokyo ×2, STL@TBR ×2); Lizenz-Vermerk in `retrosheet/README.txt` (Pflicht) |
| (abgeleitet) `src/original_schedule.py` | Originalplan-Rekonstruktion aus statsapi-Feldern | B | automatisch | dient als Gegenprobe zur Goldquelle |
| `appendix_c_travel_times.json` | CBA-Appendix-C-Flugzeiten, 30×30 | A (transkribiert + verifiziert) | manuell (CBA-Dokument) | Symmetrie 0/406 Mismatches, Anker-Stichproben (`tools/transcribe_appendix_c.py`) |
| `regulations/` | CBA Article V verbatim | A | manuell bei neuem CBA | jede harte Regel referenziert Wortlaut |
| `teams.json` | Stammdaten 30 Teams (Koordinaten/TZ/Dach) | A | manuell (Relokationen!) | Manifest; Loader-Validierung |
| `cotenant_sharing.json` | **Registry: wer teilt sich welches Stadion** (venueId-belegt) | A | manuell bei Relokation; Beleg-URLs im File | `tools/fetch_cotenant_calendars --validate-only` |
| `local_events.json` → `stadium_booking` | Harte Venue-Belegungen, inkl. **River-Cats-Homestands** (cotenant:OAK:2025/2026, je 75 Tage) | A (MiLB-API) | `tools/fetch_cotenant_calendars` (idempotent, note-Schlüssel) | 0 Kollisionen mit realem OAK-Plan 2025 + Original 2026; Negativ-Probe getestet |
| `local_events.json` → `thirdparty:*` | **Konzert-/Event-Drittnutzungen 2026** (29 Voll-Stadion-Termine: Wrigley 6, Fenway 12, Citi 4, Yankee 5 Tage, Dodger/T-Mobile/Petco + Bananas-Tour in 8 Parks) | B+ (Venue-/Tour-Ankündigungen, Quelle je Eintrag) | **manuell** (Konzerte haben keine API) + Kollisions-Validierung | **0 Kollisionen mit 2026-Originalplan (Gold)** — Konzerte sind um den Plan herum gebucht; Watchlist unbestätigter Acts im `_note_thirdparty_2026` (Gallagher-Square-Events bewusst NICHT als Blackout) |
| `local_events.json` → übrige Kategorien | Festivals/Verkehr 2026 (Scoring, weich) | B (Recherche) | manuell | nur weiches Scoring, keine harte Entscheidung |

## Startzeiten & TV

| Datei | Inhalt | Rating | Refresh | Validierung |
|---|---|---|---|---|
| `mlb_broadcasts_{2024,2025,2026}.json` | Nationale TV-Broadcasts je Spiel (`isNational`) | A | `tools/fetch_broadcasts` | Scan-Zähler ≥2430/Saison (2469/2464/2444); SNB = Sonntag+ESPN-Fakt (29/25 Spiele; Heuristik übersah 12/10 — Urteile unverändert) |
| `mlb_national_tv.json` | Punkt-verifizierte TV-Fakten (urteils-relevante Spiele) | A je Eintrag | wird durch volle Broadcast-Dateien ersetzt | Fallback-Stufe 2 in `load_exempt_pks` |
| `tv_slots.json` | Broadcaster-Fenster-Muster (Scoring) | B (Recherche) | manuell | `tools/validate_revenue_model` (TV-Slot-Plausibilität) |

## Revenue & Validierungsreferenzen

| Datei | Inhalt | Rating | Refresh | Validierung |
|---|---|---|---|---|
| `revenue_model.json` | Gate-Revenue-Modell (Kalibrierbasis Sportico/Statista 2024) | B (kalibrierter Proxy) | bei neuen Gate-Daten | siehe rechts ↓ |
| `real_attendance_2024.json` | ESPN-Heim-Attendance 2024 | A | manuell/Saison | Referenz 1: Spearman 0,892 |
| `forbes_team_financials_2025.json` | Forbes-Gesamt-Revenue alle 30 Teams (Saison 2024) | B (Wikipedia-Mirror von Forbes) | manuell/jährlich (Quellen-URLs im File) | Referenz 2: Spearman 0,922 (in `tools/validate_revenue_model` verankert, Schwelle 0,80) |
| `gate_receipts_2024.json` | **Echte per-Team-Gate-Receipts** (Forbes-Definition, 28 Teams 2023/24 + Sportico-Anker aus MLBs internem Gate-Report inkl. Premium) | B+ (je Team einzeln über Statista-Teaser zitiert; Sportico-Anker A−) | manuell/jährlich; Erhebungsmethode im File | Referenz 3: **Spearman 0,958** (verankert, Schwelle 0,85); Summen-Check 3,23 von ~3,41 Mrd plausibel. **Kalibrier-Befund dokumentiert:** Modell unterschätzt Top-Teams absolut um 22–42 % (Premium-Seating-Anteil) — Re-Kalibrierung = bewusste Folgeentscheidung |
| — | Gate-Receipts TEX/CLE (2024) | — | **OFFEN: Statista-Teaser paywalled** (letztbekannt 2021: 94/35) | dokumentierte Rest-Lücke (28/30 abgedeckt) |

## Ops-Schicht (illustrativ, KEINE harte Entscheidungsgrundlage)

| Datei | Inhalt | Rating | Hinweis |
|---|---|---|---|
| `team_hotels.json` | Hotels (nur 5 Teams) | **Seed** | in Produktion durch Club-Buchungsdaten ersetzen |
| `city_ops_profiles.json` | Stau/Klima/Trauma-Center | B (gemischt, im File je Feld markiert) | Scoring/Reports |
| `team_airports.json` | Primär-Flughäfen (IATA) | A (publizierte Referenzpunkte) | Charter-Abweichungen möglich (vermerkt) |
| `holiday_pins.json` | Feiertags-Slates | A (gesetzl. Regeln) + Konvention | weiches Incentive |
| `soft_factors.json`, `phase_calibration.json`, `milton_scenario.json` | Tuning/Szenario-Seeds | Seed/B | nur Forschung/Demos |

## Betriebs-Runbook (Daten)

```bash
python -m tools.update_external_data --status        # Bestandsübersicht
python -m tools.update_external_data --all           # Retrosheet + Broadcasts + Co-Tenant + Messung
python -m tools.fetch_cotenant_calendars --validate-only   # offline Konsistenz-Check
python -m tools.verify_data_manifest                 # Drift-Check (auch in CI)
python -m tools.validate_revenue_model               # beide Revenue-Referenzen + TV
```

**Bekannte offene Daten-Punkte (ehrlich, Stand 2026-06-11 nach C1/C3-Tiefe):**
(1) Gate-Receipts: nur noch TEX/CLE-2024 fehlen (28/30 erhoben; Sportico-Anker
decken die Spitze); Premium-Seating-Re-Kalibrierung als dokumentierte
Folgeentscheidung offen. (2) `mlb_schedule_2025.json` ohne Tokyo-Series (Gold
deckt es). (3) Drittnutzungen: 29 datierte Voll-Stadion-Events 2026 erfasst und
gegen den Originalplan kollisionsvalidiert; Watchlist unbestätigter
Ankündigungen in `local_events.json::_note_thirdparty_2026` — Konzerte bleiben
manuelle Pflege (keine API), Validierung automatisiert. (4) Ops-Seeds (Hotels)
bis Club-Daten kommen. (5) 2027: Co-Tenant-Fetch erst nach
MiLB-Planveröffentlichung (`fetch_cotenant_calendars` meldet das als Info).
