# Independent October 24 NBA mechanism-result reconciliation

**Research-only external check — October 26, 2026. Not a sportsbook backtest or authorization to score picks.**

## Scope and frozen denominator

- Source: Pax's [PR #6](https://github.com/NATHANZACH988/Courtside-IQ/pull/6), `research/gameflow/predictions-2026-10-24.json` on `pax/full-roster-predictions`, Git blob `61a973e2a1e41590045c1cbdcb053cc684d3e563`.
- The file declares **53 predictions / 8 events**: 30 FOUL_CAP, 12 CANNIBAL, 10 VICTIM, 1 STEADY; 11 thin-sample entries. Every original `grade` is `null`.
- Its `built_at_utc` and per-row `logged_at_utc` are `2026-10-24T12:43:09.323745+00:00`; Git's corresponding commit timestamp is `2026-10-24T12:57:25Z`; earliest listed tipoff is `2026-10-24T22:00Z`. PR #6's prose instead says **12:53 UTC**. These timestamps are internally compatible with pre-tip publication but **do not authenticate the source inputs or freeze time**.
- The declared universe has three simultaneous opposite-direction research hypotheses (Kel'el Ware, Tre Johnson, Jordan Poole). They are not three distinct, actionable sportsbook propositions. See existing [PR #7](https://github.com/NATHANZACH988/Courtside-IQ/pull/7).

## Independent final-stat sources and replay method

On October 26, 2026, retrieved ESPN public NBA event summaries for all eight frozen event IDs. All eight reported `STATUS_FINAL` and supplied player minutes, points, field-goal attempts, fouls, team, starter status, and coarse G/F/C positions:

| Event | Matchup | Final-score source |
| --- | --- | --- |
| 401909853 | Charlotte 115, Miami 110 | [ESPN event summary](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909853) |
| 401909854 | Cleveland 125, Brooklyn 121 | [ESPN event summary](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909854) |
| 401909855 | Philadelphia 127, Milwaukee 116 | [ESPN event summary](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909855) |
| 401909856 | Houston 121, Atlanta 114 | [ESPN event summary](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909856) |
| 401909857 | Washington 124, Chicago 120 | [ESPN event summary](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909857) |
| 401909858 | San Antonio 122, Dallas 106 | [ESPN event summary](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909858) |
| 401909859 | Denver 141, New Orleans 135 | [ESPN event summary](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909859) |
| 401909860 | Phoenix 131, Golden State 122 | [ESPN event summary](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401909860); [NBA team box score](https://www.nba.com/warriors/game/0022600111-warriors-vs-suns-phoenix-az-10-24-2026/box-score) |

The independent comparison applied the **original PR #6 grader's numerical predicates** to team-matched player rows: `minutes < 10` -> NO_DECISION; FOUL_CAP `PF >= 5` or `PF == 4 and minutes <= 0.65 * frozen banked minutes`; CANNIBAL `FGA/min >= .45` plus same-position starter comparison and blowout guard; VICTIM `PTS < .6 * frozen banked PPG` with `minutes >= 15`, or a teammate's CANNIBAL shape; STEADY `PTS >= banked PPG - 3`. For CANNIBAL and VICTIM teammate comparisons, ESPN's coarse G/F/C position is only a **proxy** for the watcher's original position field.

The original watcher adds an **independent foul-event note path** to FOUL_CAP. ESPN box scores do not expose those watcher-generated notes or their retraction history. Accordingly, this check does **not** treat every numerically negative FOUL_CAP as a verified MISS.

## Reconciliation of all 53 declared calls

| Mechanism | Original count | What external box scores support | Remaining dependency |
| --- | ---: | --- | --- |
| FOUL_CAP | 30 | 2 numeric HIT (Isaac Okoro, Herbert Jones); 2 NO_DECISION (Ousmane Dieng, Draymond Green); **26 note-dependent** | Original watcher foul notes, identity, retractions, and grade versions |
| CANNIBAL | 12 | 1 HIT (Mikel Brown Jr.) and 11 MISS under ESPN coarse-position proxy | Original watcher positions and gameflow final schema |
| VICTIM | 10 | 1 direct points-threshold HIT (Myles Turner), 1 teammate-shape HIT (Keon Ellis), 8 MISS under same proxy | Original watcher teammate-position evidence for Ellis |
| STEADY | 1 | Tyler Herro MISS: 13 points vs frozen 26-point minimum | None for the numeric predicate |

**Conditional aggregate:** The [PR #11](https://github.com/NATHANZACH988/Courtside-IQ/pull/11) reported **6 HIT / 45 MISS / 2 NO_DECISION** is **consistent with the external box scores** *if and only if* one of the 26 note-dependent FOUL_CAP entries (identified by Pax as Morez Johnson Jr.) was legitimately HIT via an unretracted original watcher foul note and the other 25 were MISS. This is **not an independently reproduced final grade ledger**.

Morez Johnson Jr.'s external box-score line was **4 personal fouls in 12 minutes**. His frozen `banked_min_pg` is **15.5**, giving a numerical FOUL_CAP limit of **10.075 minutes** at four fouls. His claimed HIT therefore **cannot be established by the numerical rule alone**; the original watcher note is decisive. Draymond Green did not dress; Ousmane Dieng had no minutes, consistent with the two NO_DECISION calls. Graham Ike (4 PF, 26 min) and Will Richard (3 PF, 31 min) were numerically negative in the final event, subject to the same missing-note limitation.

## Separate ticket-study arithmetic requiring clarification

PR #11's `TICKET_ARCHAEOLOGY_V1.md` says **254 legs graded in total**, while its five reported construction rows add to **258** (52 + 164 + 34 + 4 + 4). The **254** figure equals the first four rows *excluding four ANTI control legs*, so this may be an unlabeled strategy-only denominator rather than a data error. The report should explicitly distinguish **254 strategy legs / 4 control legs / 258 including controls** after the author confirms cohort semantics.

The same study labels COLD losses as 21 PUBLIC_STAR + 39 ROLE_OVER = **60**, while V2 decomposes **61 COLD** losses into 44 shots missed + 17 attempts taken away. That difference may reflect another cohort or recoding, but the available documents do not provide a reconciliation. Neither ticket study includes historical sportsbook lines; proxy-line hit rates are **not actual betting returns**.

## Provenance, security, and release gates

This review read public ESPN final box scores and the committed frozen JSON. It did **not** retrieve the agency's original eight watcher-final files, foul-note/retraction ledger, frozen input bank, graded sibling file, pregame roster/injury snapshots, sportsbook quotes, ticket-construction scripts, or the 127-of-141 projection error records. The ESPN pages are third-party final-stat evidence, not proof of the original pre-tip information state or a licensed data feed. Do not infer model accuracy, ROI, or an actionable prop from these mechanism classifications.

**Required for full independent replay:** original watcher finals and immutable grade revisions; foul-note evidence for Morez and every other FOUL_CAP; stable athlete/team identifiers; source capture and observation times; the full projection baseline data and evaluation code; and ticket-study input, proxy-line generation, and cohort definitions. Run the existing [PR #17 source-identity audit](https://github.com/NATHANZACH988/Courtside-IQ/pull/17) before promoting any mechanism grade. Keep the five-current-season-banked-games-per-team minimum before NBA Play.

**Scope of this contribution:** documentation only, no API-contract changes, authentication changes, dependencies, network code, production scoring changes, or merges. There are no new code tests; evidence consists of the eight live final-stat source checks and frozen-manifest arithmetic. This report must not be used as a substitute for authenticated source archives or a reproducible grading run.
