# Design-Vorschlag: CBA-Versionsschalter (NICHT umgesetzt — wartet auf Jonas)

**Anlass:** Das Basic Agreement 2022–2026 läuft am 01.12.2026 aus (Lockout-Risiko
real). Alle harten Regeln referenzieren heute den 2022er-Wortlaut; ein neues CBA
ändert potenziell Limits (≤20-Tage, PT→ET-Ausnahmen, DH-Regeln, ASB-Länge).
**Status: reiner Vorschlag** — Umsetzung erst nach Review durch Jonas
(Nacht-Session-Auftrag: „erst Design-Vorschlag schreiben, nicht blind bauen").

## Ziel
Pläne für Saison X werden gegen die **für X gültige** Regel-Version geprüft;
historische Messungen (2024–2026) bleiben unverändert reproduzierbar.

## Vorschlag (minimal-invasiv, 3 Bausteine)

1. **Regel-Parameter aus Daten statt Konstanten.**
   Neues `data/cba_versions.json`:
   ```json
   {"versions": [{
      "id": "CBA-2022-2026", "valid_seasons": [2022, 2026],
      "verbatim_doc": "regulations/CBA_2022-2026_Article_V_Scheduling.md",
      "params": {"vc12_max_consecutive": 20, "vc12_resched_max": 24,
                 "vc11_league_exceptions": 7, "vc13_max_open_per7": 2,
                 "vc13_min_last67": 7, "vc13_min_last32": 3,
                 "vc15_max_twinight": 3, "vc17_asb_days": 4,
                 "vc8_inflight_threshold_min": 150}}]}
   ```
   Loader `src/cba_version.py`: `params_for(season:int) -> CbaParams`
   (frozen dataclass; unbekannte Saison → neueste Version + lauter Warnhinweis).

2. **Einspeisung über bestehende Signaturen.** Die Checker haben die Limits
   bereits als Keyword-Defaults (`check_offday_distribution(max_per_7=2, …)`,
   `VC12_STREAK_LIMIT`, `getaway_latest_start_min` …). Schritt 1: Defaults
   bleiben identisch (bit-Identität!), `compliance_report`/`publish_gate`/
   `repair_local`/`start_times` reichen `CbaParams(season)` explizit durch.
   Schritt 2 (nach neuem CBA): nur JSON + neues Verbatim-Doc ergänzen.

3. **Provenance-Kopplung.** `ComplianceRule.reference` bekommt die Versions-ID;
   der Compliance-Report druckt die Version im Kopf. Manifest friert
   `cba_versions.json` ein; Test: jede Version referenziert ein existierendes
   Verbatim-Doc, Parameter-Satz vollständig.

## Aufwand & Risiken
~1–2 Tage. Risiko: versteckte Hartkodierungen (z. B. 19:00/17:00 in
start_times) — Inventar nötig (grep-Liste liegt der Umsetzung bei).
Determinismus-Anker und Suite müssen unverändert bleiben (Schritt 1 ist reine
Durchreichung mit identischen Werten).

## Entscheidung nötig (Jonas)
(a) Vorschlag so bauen? (b) Sollen V(C)-Paragraphen-NUMMERN versioniert werden
(neues CBA nummeriert evtl. um) — d. h. Regel-IDs abstrakt halten
(`RULE-CONSEC-DAYS` statt `V(C)(12)`) mit Mapping je Version?
