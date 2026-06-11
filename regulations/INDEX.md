# Regelwerk-Ordner — offizielle MLB-Quellen

**Zweck.** Zentrale, zitierbare Ablage aller offiziellen MLB-Regelwerke, damit
Compliance-Regeln im Projekt jederzeit gegen den **echten Wortlaut** belegt werden
können (statt gegen Annahmen). Angelegt in Sprint 5, Datengrundlage 5.2.

**Prinzip:** Jede harte Regel im Optimierer muss auf eine Zeile in einem dieser
Dokumente zeigen. Wo das nicht geht, ist die Regel eine *Annahme* und wird als
solche markiert (siehe `FINDING_AC-2.1.8_vs_CBA.md`).

## Inhalt dieses Ordners

| Datei | Inhalt | Status |
|---|---|---|
| `CBA_2022-2026_Article_V_Scheduling.md` | Verbatim-Auszug Article V (Scheduling) des aktuellen Basic Agreement | ✅ extrahiert |
| `FINDING_AC-2.1.8_vs_CBA.md` | Verifikation: „13 days away" (Projekt) vs. realer CBA-Wortlaut | ✅ dokumentiert |

## Offizielle Quell-Dokumente (Volltext, Download-URLs)

| Regelwerk | Geltung | Quelle (offiziell) |
|---|---|---|
| **Basic Agreement 2022–2026** (CBA) | Arbeits-/Scheduling-Bedingungen, Article V = Scheduling | https://registrationz.mlbpa.org/pdf/MLB%20Basic%20Agreement%202022-26.pdf |
| **Basic Agreement 2017–2021** (CBA, Vorgänger) | historischer Vergleich (Article V(B)(12) = 20 Tage) | https://sports-entertainment.brooklaw.edu/wp-content/uploads/2021/01/Major-League-Baseball-Collective-Bargaining-Agreement-2017-2021-reduced.pdf |
| **Official Baseball Rules 2024** | Spielregeln (Playing Rules), nicht Scheduling | https://mktg.mlbstatic.com/mlb/official-information/2024-official-baseball-rules.pdf |
| **MLB Official Information (Hub)** | Sammelseite aller offiziellen Dokumente | https://www.mlb.com/official-information |

**Hinweis zum Mirroring.** Die Volltext-PDFs sind oben verlinkt; der für dieses
Projekt relevante Teil (Article V, Scheduling) ist verbatim in diesem Ordner
extrahiert. Wer die kompletten Original-PDFs lokal spiegeln will, lädt sie über die
obigen URLs herunter und legt sie hier ab (Dateinamen-Konvention:
`<Regelwerk>_<Jahr>.pdf`).

## Welche CBA-Klauseln sind scheduling-relevant?

Aus Article V(C) — die harten, datenunabhängigen Scheduling-Regeln:

- **V(C)(12)** — max. **20 konsekutive Spieltage** ohne Off-Day (Heimteam ≤24 nur bei Regen-Reschedule).
- **V(C)(13)** — max. 2 Off-Days je 7-Tage-Fenster; ≥7 Off-Days in den letzten 67 Tagen, ≥3 in den letzten 32.
- **V(C)(11)** — Off-Day **verpflichtend** bei Reise Pacific → Eastern Time Zone (max. 7 Ausnahmen/Liga).
- **V(C)(8)** — Getaway-Startzeit-Formel (In-Flight > 2½h von 19:00 abziehen); **Ausnahme: ESPN Sunday Night Baseball** → koppelt Scheduling an TV-Fenster.
- **V(C)(9)** — kein Spielstart vor 17:00, wenn ein Club am Vorabend ≥19:00 in anderer Stadt spielte (mit Ausnahmen, u. a. Cubs/Chicago).
- **V(C)(17)** — All-Star-Break = 4 Tage, keine Spiele.
- **V(C)(14)/(15)** — Doubleheader-Limits (keine an konsekutiven Tagen; Twi-Night ≤3/Heimclub).
- **V(C)(18)** — jede Regel per Spieler-Mehrheitsbeschluss (secret ballot) waiver-bar.
