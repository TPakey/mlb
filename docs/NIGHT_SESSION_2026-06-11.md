# Nacht-Härtungs-Session 2026-06-11 → 12 — Übergabe

Autonome Session lt. Auftrag; alle Punkte abgearbeitet, jeder mit Messung/Test
und eigenem Commit. Suite am Ende: **471/521 not-slow grün** (Start: 463; +8 neue
Tests), Determinismus-Anker **1680131 nach jedem Punkt unverändert**, Lint sauber.

---

## ⚠ Die 3 Dinge für morgen früh

1. **`GIT_SETUP.command` doppelklicken (2 Min).** Die Sandbox konnte im
   Projektordner keine Git-Locks löschen (Mount erlaubt kein Unlink) — die
   komplette 9-Commit-Historie liegt deshalb in
   `night-haertung-2026-06-11.bundle`. Das Skript stellt das echte Repo her und
   löscht den kaputten `.git_broken_sandbox_DELETE_ME`-Rest. Danach
   GitHub-Remote anlegen + pushen → CI (inkl. nightly slow-Suite) läuft an.
2. **Nacht-Fund A lesen (Commit 3c90140):** Vier Gate-Pfade (Pareto-Punkte,
   What-if, Disruption, api) liefen ohne die harte VENUE-AVAIL-Regel — ein auf
   einen River-Cats-Tag verschobenes OAK-Heimspiel passierte das Gate
   (gemessen!). Gefixt: das Gate lädt die Stadion-Belegungen jetzt automatisch.
   Bitte einmal nicken, dass Auto-Load als Default ok ist (Opt-out: `events=[]`).
3. **Zwei Design-Entscheidungen warten:** `docs/DESIGN_CBA_VERSIONING.md`
   (CBA läuft 01.12.2026 aus — Vorschlag steht, bewusst nicht gebaut) und die
   Premium-Rekalibrierung (Befund −22…−42 % Top-Teams; Geschäftsentscheidung,
   nur als offener Punkt geführt). Dazu unverändert extern: Gurobi (Uni-VPN)
   und die 6-M-Messreihe auf deiner Hardware.

---

## Punkt-für-Punkt mit Beweis (vorher → nachher)

| # | Punkt | Status | Beweis | Commit |
|---|---|---|---|---|
| 1 | Git + lokale CI | **erledigt (mit Workaround)** | Repo via externem GIT_DIR (Mount erlaubt kein Lock-Unlink → Bundle + `GIT_SETUP.command` für dein lokales Repo); CI-Schritte lokal: Manifest 16/16 OK, Lint 0, Anker 1680131 | 7d46b74 (Baseline) |
| 2 | Pareto regelfest (P1-5) | **behoben** | Real 2024 @4k Iter: Frontier hatte 7 Punkte, **nur 2 publizierbar** (Fehlerklasse real!) → Auslieferung (main `--mode publizierbar`, api) liefert exakt die 2; Forschungs-Default unverändert; degraded-Fallback statt Leer-Output | 98dbfea |
| 3 | Per-Team-ASB (B2) | **behoben** | Vorher: falscher Liga-Befund „3 Tage"; nachher: 2026 = **28/30 Teams ≥4 Tage + exakt NYM/PHI** als Ausnahme (V(C)(18)-Klasse), 2024/25 = 30/30 | 2ee716e |
| 4 | PTET-≤7-Ausnahme (P1-6) | **behoben** | V(C)(11)-Ausnahme modelliert (ET>19:00 + PT<17:00 + Einzelspiel + Liga-Limit 7, chronologisch ab Nr. 8 Verstoß); 6 synthetische Fälle als Tests; real 2024/25 weiterhin 0; ohne Startzeiten strikt wie zuvor (Gate-Pfade unverändert) | 06e70d0 |
| 5 | TV-Pins hart (P1-7) | **behoben** | `build_tv_pins` aus Broadcast-Fakten + `validate_tv_pins` (Pin-Treue + CBA-Konflikt): real **691/691 (2024) und 594/594 (2025) Pins exakt übernommen, 0 echte CBA-Konflikte**; synthetisch: gebrochener Pin + V(C)(8)-Konflikt-Pin werden gemeldet; Toleranz-Konstante (±40 min) auf eine Quelle vereinheitlicht | 4c653f8 |
| 6a | dh_type durch SA-Roundtrip | **behoben** | Alle 28 getypten DH-Tage überleben entries→season typgleich; SA-Output trägt **58 getypte DH-Spiele statt 0** → V(C)(14)-Satz-2 auf echtem Output nicht mehr vakuos. 2 vorbestehende Randfälle dokumentiert (Halb-DH ATL 7/24; 3 von statsapi ungetypte 2-Spiele-Tage) | 64e247c |
| 6b | V(C)(8)-Restlücke | **quantifiziert + dokumentiert** | Bewusste Restmenge (Gast-Folgetag frei, Weiterreise in Drittstadt → Heimreise unbestimmbar, nicht erzwungen): **exakt 99 Fälle** (real 2024, Test fixiert den Wert); zusätzlich falschen Alt-Kommentar im Docstring ersetzt. Erste Assert-Schätzung (200–320) war falsch → auf Messwert korrigiert, nicht umgekehrt | 1140da8 |
| 6c | Envelope-Wache | **behoben** | `--measure-original` re-validiert die Reise-Schwelle bei jedem Originalplan (B1-Lehre): 2024/25 max 4164, 2026 max 4328, Schwelle 4350 → Reserve gemessen; Falsifikation würde den Lauf FAIL setzen | 1140da8 |
| + | Schwachstellensuche Fund A | **gefunden + behoben** | Gate ohne `events` in 4 Pfaden → VENUE-AVAIL griff nicht; Beweis: OAK-auf-River-Cats-Tag-Plan **vorher PASS, nachher FAIL**; Auto-Load mit Cache + bewusstem Opt-out | 3c90140 |
| + | Schwachstellensuche Fund B | **gefunden + behoben** | `main --from-scratch` plante ohne `home_blackout_days` (Gate fing Konflikte erst hinterher) → Generator bekommt die Belegungen jetzt selbst | 3c90140 |
| + | CBA-Versionsschalter | **Design geschrieben, nicht gebaut** (Auftrag) | `docs/DESIGN_CBA_VERSIONING.md` — 3-Baustein-Vorschlag + die 2 offenen Entscheidungen | ccbddb0 |

## Commit-Liste (chronologisch, im Bundle)
```
7d46b74  Baseline vor Nacht-Härtung
98dbfea  P1-5 Pareto publishable_only
2ee716e  B2 ASB per Team
06e70d0  P1-6 PTET-≤7-Ausnahme
4c653f8  P1-7 TV-Pins hart
64e247c  P2 dh_type-Roundtrip
1140da8  P2 V(C)(8)-Restlücke + Envelope-Wache
3c90140  Funde A+B (Gate-Venue-Default, from-scratch-Blackouts)
ccbddb0  CBA-Versionierungs-Design (Vorschlag)
```

## Wartet auf Jonas (extern / Entscheidung — nichts davon blockierte die Nacht)
- **GitHub-Remote** anlegen + push (nach `GIT_SETUP.command`).
- **Gurobi** im Uni-Netz/VPN (`GUROBI_SETUP.command`; Code unverbraucht).
- **6-M+-Messreihe** auf deiner Hardware (2026-Original = Referenzmessung);
  README-km-Zahlen danach aktualisieren.
- **Premium-Rekalibrierung** (Geschäftsentscheidung; Anker liegen in
  `data/gate_receipts_2024.json`; bewusst nicht vorentschieden).
- **CBA-Versionsschalter**: Design freigeben (2 Fragen am Ende des Docs).
- TEX/CLE-Gate-Receipts (Statista-Paywall), 2027-Co-Tenant (MiLB-Plan fehlt),
  Konzert-Watchlist-Pflege (Quartalsroutine) — unverändert offen.

## Ehrliche Anmerkungen
- Milton-e2e (slow) weiterhin nur via nightly CI messbar (Sandbox-Zeitfenster).
- Die slow-Suite (50 Tests) lief auch diese Nacht nicht vollständig — erst mit
  GitHub-Remote/nightly real.
- Das kaputte `.git_broken_sandbox_DELETE_ME` im Projektordner ist Absicht
  (Sandbox kann es nicht löschen); `GIT_SETUP.command` räumt es weg.
