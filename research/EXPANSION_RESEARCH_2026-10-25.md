# Expansion research — public, eyes, causes, market (Oct 25, 2026)

Four parallel research streams, each sourced and evidence-graded at the source.
This document is the synthesis; per-stream detail lives in the research passes.

## The headline

Two unoccupied seats exist, and both are archives only *self-capture* can build:
**(1) nobody publishes a complete, timestamped, settled archive of the picks they
sell** — Dimers (Pro $29.99/mo, Verified) is graded only through a third party's
consensus game picks, not its paywalled picks; OddsJam sells tools with user
stats; PicksWise publishes no record at all. **(2) nobody publishes game-to-game
minutes-persistence data** — the cause-persistence literature has no public
persistence coefficients; the agency's own banked gameflow is the only source.
Both archives compound daily and cannot be backfilled later. Start capturing now.

## Layer 1 — the public, measured (two different products)

**A. Book-published demand data — clean, free, immediate.**
- DK Network publishes daily "Most Bet NBA Player Props" **by handle** (~5-min
  refresh) and daily public betting trend articles (bets %/handle % per game),
  dated URLs forming an archive. Verified, free, no login.
- VSiN publishes DK + Circa splits every 5 minutes, and — uniquely —
  **past-game pages retain final splits**, so a historical splits set can be
  built page-by-page. VSiN's own analyst has tracked DK splits since Jan 2023.
- Action Network and Covers **expressly ban scraping in their terms** (Verified);
  Covers "consensus" is contest picks, not money. Neither is a scraper target.
- DK most-bet is the only prop-demand signal that exists (no prop splits anywhere).

**B. Real posted picks — the ticket layer.**
- **r/sportsbook Pick of the Day is the crown jewel**: daily, one pick per
  comment, odds bounded, mandatory write-ups, posters carry tracked
  Record/Units/ROI — a ready-made public-picks ledger, directly gradeable.
  Backfill exists via **Arctic Shift** (free, current). Live official-API use is
  non-commercial and approval-gated; a commercial product needs a negotiated
  Reddit agreement. RSS reportedly retires Nov 13, 2026 — do not build on it.
- **Telegram public previews** (`t.me/s/<handle>`) are the only community source
  readable today with no account — good for an ecosystem census and slip-format
  sampling; worst signal quality (VIP funnels, self-reported records).
- **X** has the volume but only via the official API; pricing is **Reported**
  (~$0.005/post read, pay-per-use) and still **unverified at source** — an open
  item before any commitment. Scraping X is terms-prohibited.
- Discord/Facebook content sits behind joining/private walls — out of
  read-only scope.

**What the evidence says the public layer is FOR (not a fade machine):**
peer-reviewed work (Paul & Weinbach 2008) finds NBA bet-count bias is real but
contrarian ATS play does **not** beat efficiency; a 4-year BetMGM dataset
(Verified) shows the public side went 49.19% ATS and *blind fading also lost*
(−160 units). Bias bites in longshot moneyline prices; majority-handle totals
actually won in 2024-25 (+4.2% ROI, Reported). The product is therefore:
construction library + popularity curves + graded posters — measuring the
public's influence, never asserting it.

## Layer 2 — eyes (buildable; one door closed)

- Beat directories exist and are current: **58 named accounts across 30 teams**
  (~2/team) in one maintained list. Ecosystem is thinning (many teams lack a
  full-time traveling reporter) — road/small-market coverage will be spotty.
- **Coach pressers are obtainable at scale via team YouTube channels, same
  night** (verified for Oct 24 games). ASAP transcripts are playoff-strong,
  regular-season unproven. Pressers are next-game cause evidence, not live signal.
- **No project mines local broadcast commentary** — rights-fragmented; mark
  blocked, do not budget.
- Spotter form: 8 fixed questions per quarter (shell, matchup, rotation
  surprise, availability signal, doghouse trigger, shot-diet shift, foul
  context, one-line thesis + "nothing observed" option), PFF-style discipline:
  narrow taxonomy, uncertainty flag, adjudication, agreement audits.
- Fan-eye text (SB Nation threads public; RSN live blogs occasionally carry
  exactly the needed note) = corroboration only, never sole evidence.

## Layer 3 — causes (coding rules, evidence-graded)

| Cause | Persistence | Rule |
|---|---|---|
| Own injury / mid-game exit | PERSISTS, type-scaled | Default OUT/REDUCED until designation upgrade; Stotts-type priors (low-grade AC sprain ≈ 4.3 games) |
| Questionable designation | SOMETIMES, suppressed | ~0.35–0.5 play probability; 15–30% minutes haircut if active |
| Teammate injury (opportunity surge) | PERSISTS while absence lasts | The ONE surge never regressed — carry until the injured player's upgrade |
| Doghouse | SOMETIMES, graduated | Needs 2 straight DNP-CD or 3-game decline; coach modifier (Thibodeau/Nurse deepen) |
| Matchup/scheme one-off | RARELY | Explicit coach framing = single-game event, zero carryover |
| Foul trouble (single game) | RARELY as event | Ignore last game's count entirely |
| Foul rate (trait) | PERSISTS, decays with experience | Trailing top-decile PF/36 → minutes-*variance* penalty; young-big discount |
| Blowout / garbage time | RARELY (non-signal) | CTG filter tags every player-game; tagged minutes excluded from baselines and event detection |
| Unexplained surge/collapse | RARELY | Full regression to comparable-games baseline |

## Layer 4 — market twin (costed)

- Cadence (NBA plays ~180 days): **4 snapshots/day** — 09:00 open, 13:00 props
  sweep, 17:00 lines, T‑60 props sweep (de-facto close), + T‑5 lines ≈
  4–6K Odds API credits/mo → **one key, ~$25–30/mo (Reported price; $25 vs $30
  conflict to resolve at the provider page)**, with headroom for audits.
- Free complements, daily: DK most-bet grabs ×2, VSiN splits grabs ×2,
  SBR/BetMGM most-bet table ×1.
- Backfill validation: DunkAPI free tier (500 credits/mo, no card) — ~50
  prop-history calls/mo to measure our T‑60 close proxy against their
  designated closes (their archive: closing props since May 2023, $19/mo;
  caveat: pre-Oct 2026 = one pre-game capture per line).
- Prop-close history verdict: **no free archive exists** (checked: Kaggle,
  GitHub, SBR, books); paid routes all start May 2023. Self-capture is the
  industry workaround — and now, ours.

## Build order

- **P0 — this week, $0:** DK Network daily grabs; VSiN splits grabs incl.
  past-game finals backfill; r/sportsbook POTD census via Arctic Shift
  (research use); beat-list v1 into the intel pull; cause-coding v1 on our
  detected events (presser videos + CTG garbage-time tags in the watcher);
  pair-outcome cannibal grading fix (from the Oct 24 grading lessons).
- **P1 — ~$25–30/mo (owner decision: Odds API key):** 4×/day snapshot cadence;
  prop-close self-archive begins; DunkAPI free-tier validation.
- **P2 — later:** X API capper watchlist (after at-source price verification);
  spotter-form pilot; Reddit commercial agreement only if the product goes
  commercial; DunkAPI $19/mo backfill purchase if backtests justify it.

## Open verification items

X API pricing at developer.x.com (unreachable by text fetch); Reddit's
reported Mar-2027 public-API closure (conflicting reports); VSiN/DK terms on
automated collection (not located); The Odds API $25 vs $30 tier price;
Facebook group contents (login-gated).
