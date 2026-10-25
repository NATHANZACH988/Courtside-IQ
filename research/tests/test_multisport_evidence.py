import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from research.core import (
    EvidenceLedger, Event, MarketQuote, Observation, SourceProof, SPORT_MARKETS
)

UTC = timezone.utc
TIP = datetime(2026, 10, 25, 20, tzinfo=UTC)


def stamp(*, published=TIP - timedelta(hours=3),
          captured=TIP - timedelta(hours=2), rights="unverified"):
    return SourceProof("Example provider", "https://example.org/archived/123",
                       published, captured, rights)


def event(sport="NBA", event_id=None):
    return Event(sport, event_id or sport.lower() + ":event-1", TIP,
                 "team:home", "team:away")


def observation(*, eid="nba:event-1", oid="source:obs-1", kind="pregame",
                team="team:home", player="provider:athlete-1", source=None):
    return Observation(oid, eid, kind, "injury_status", "available",
                       source or stamp(), player, team)


def quote(*, eid="nba:event-1", qid="source:quote-1", market="points",
          source=None, team="team:home", odds=-110, line=24.5):
    return MarketQuote(qid, eid, "provider:athlete-1", team, market, line,
                       odds, "Example Sportsbook", source or stamp())


class MultiSportEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.ledger = EvidenceLedger()
        self.ledger.add_event(event())

    def test_nba_nfl_and_other_sports_have_distinct_stat_taxonomies(self):
        self.assertTrue({"NBA", "NFL", "MLB", "NHL", "SOCCER"}.issubset(SPORT_MARKETS))
        self.ledger.add_event(event("NFL"))
        self.ledger.add_market_quote(quote())
        self.ledger.add_market_quote(
            quote(eid="nfl:event-1", qid="source:nfl-quote",
                  market="passing_yards", line=250.5)
        )
        self.assertEqual(self.ledger.pregame_as_of(
            "nfl:event-1", TIP - timedelta(minutes=5)
        ).market_quotes[0].market, "passing_yards")
        self.assertEqual(len(self.ledger.pregame_as_of(
            "nba:event-1", TIP - timedelta(minutes=5)
        ).market_quotes), 1)

    def test_wrong_sport_market_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "not registered"):
            self.ledger.add_market_quote(quote(market="passing_yards"))
        self.assertEqual(self.ledger.pregame_as_of(
            "nba:event-1", TIP - timedelta(minutes=1)
        ).market_quotes, ())

    def test_as_of_excludes_evidence_not_yet_captured(self):
        early = TIP - timedelta(hours=2, minutes=30)
        self.ledger.add_observation(observation())
        self.assertEqual(self.ledger.pregame_as_of(
            "nba:event-1", early
        ).observations, ())
        self.assertEqual(len(self.ledger.pregame_as_of(
            "nba:event-1", TIP - timedelta(hours=1)
        ).observations), 1)

    def test_historical_publication_does_not_override_late_capture(self):
        late_capture = stamp(published=TIP - timedelta(days=2),
                             captured=TIP - timedelta(minutes=10))
        self.ledger.add_market_quote(quote(source=late_capture))
        self.assertEqual(self.ledger.pregame_as_of(
            "nba:event-1", TIP - timedelta(minutes=11)
        ).market_quotes, ())

    def test_postgame_outcomes_never_enter_pregame_replay(self):
        final = stamp(published=TIP + timedelta(hours=3),
                      captured=TIP + timedelta(hours=4))
        self.ledger.add_observation(
            observation(kind="postgame", oid="source:final", source=final)
        )
        self.assertEqual(self.ledger.pregame_as_of(
            "nba:event-1", TIP - timedelta(minutes=1)
        ).observations, ())

    def test_post_tipoff_pregame_evidence_is_rejected(self):
        after_tip = stamp(published=TIP, captured=TIP + timedelta(seconds=1))
        with self.assertRaisesRegex(ValueError, "at or after"):
            self.ledger.add_observation(observation(source=after_tip))
        with self.assertRaisesRegex(ValueError, "at or after"):
            self.ledger.add_market_quote(quote(source=after_tip))

    def test_postgame_source_cannot_precede_tipoff(self):
        with self.assertRaisesRegex(ValueError, "cannot precede"):
            self.ledger.add_observation(observation(kind="postgame"))

    def test_pregame_cutoff_must_precede_tipoff(self):
        for cutoff in [TIP, TIP + timedelta(minutes=1)]:
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                self.ledger.pregame_as_of("nba:event-1", cutoff)

    def test_naive_timestamps_and_inverted_publication_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            event(event_id="nba:bad", sport="NBA").__class__(
                "NBA", "nba:bad", datetime(2026, 10, 25), "team:a", "team:b"
            )
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            stamp(captured=datetime(2026, 10, 25))
        with self.assertRaisesRegex(ValueError, "before it was published"):
            stamp(published=TIP, captured=TIP - timedelta(minutes=1))

    def test_provider_qualified_ids_prevent_name_only_keys(self):
        with self.assertRaisesRegex(ValueError, "provider-qualified"):
            Observation("repeated-name", "nba:event-1", "pregame",
                        "injury", "out", stamp(), "John Smith", "team:home")
        self.ledger.add_observation(observation())
        self.ledger.add_observation(observation(
            oid="source:obs-2", player="provider:athlete-2"
        ) if False else Observation(
            "source:obs-2", "nba:event-1", "pregame", "injury_status", "available",
            stamp(), "provider:athlete-2", "team:home"
        ))
        self.assertEqual(len(self.ledger.pregame_as_of(
            "nba:event-1", TIP - timedelta(minutes=1)
        ).observations), 2)

    def test_team_mismatch_and_missing_athlete_team_rejected(self):
        with self.assertRaisesRegex(ValueError, "not part"):
            self.ledger.add_observation(observation(team="team:elsewhere"))
        with self.assertRaisesRegex(ValueError, "game-specific team"):
            observation(team=None)
        with self.assertRaisesRegex(ValueError, "not part"):
            self.ledger.add_market_quote(quote(team="team:elsewhere"))

    def test_duplicate_ids_do_not_double_count_evidence(self):
        self.ledger.add_observation(observation())
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.ledger.add_observation(observation())
        self.ledger.add_market_quote(quote())
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.ledger.add_market_quote(quote(line=23.5))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.ledger.add_event(event())

    def test_unsafe_source_urls_rejected(self):
        for url in ("http://example.org/a", "https://user:pass@example.org/a",
                    "file:///var/secrets", "https:///missing-host"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                SourceProof("provider", url, TIP - timedelta(hours=2),
                            TIP - timedelta(hours=1))

    def test_market_prices_and_lines_are_validated(self):
        for odds in (0, 99, -99, True):
            with self.subTest(odds=odds), self.assertRaises(ValueError):
                quote(odds=odds)
        for line in (-1, float("nan"), float("inf"), True):
            with self.subTest(line=line), self.assertRaises(ValueError):
                quote(line=line)
        self.assertEqual(quote(odds=+100).american_odds, 100)
        self.assertEqual(quote(odds=-100).american_odds, -100)

    def test_unverified_or_restricted_records_do_not_gain_scoring_authority(self):
        self.ledger.add_observation(observation(source=stamp(rights="restricted")))
        snapshot = self.ledger.pregame_as_of(
            "nba:event-1", TIP - timedelta(minutes=1))
        self.assertFalse(snapshot.scoring_eligible)
        self.assertEqual(snapshot.observations[0].source.rights, "restricted")
        with self.assertRaises(FrozenInstanceError):
            snapshot.scoring_eligible = True

    def test_bad_hash_or_unrecognized_rights_rejected(self):
        with self.assertRaisesRegex(ValueError, "64-character"):
            SourceProof("provider", "https://example.org", TIP - timedelta(hours=3),
                        TIP - timedelta(hours=2), content_sha256="not-a-hash")
        with self.assertRaisesRegex(ValueError, "rights"):
            stamp(rights="free_to_scrape")

    def test_timezone_normalization(self):
        west = timezone(timedelta(hours=-4))
        input_tip = TIP.astimezone(west)
        e = Event("NFL", "nfl:timezone-test", input_tip, "team:a", "team:b")
        self.assertEqual(e.scheduled_start, TIP)


if __name__ == "__main__":
    unittest.main()
