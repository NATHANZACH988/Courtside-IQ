"""Regression tests for historical quote readiness (not betting predictions)."""
import unittest
from datetime import datetime, timedelta, timezone

from research.core.evidence import Event, MarketQuote, SourceProof
from research.core.market_audit import audit_quote

UTC = timezone.utc
TIP = datetime(2026, 10, 25, 20, tzinfo=UTC)
CUTOFF = TIP - timedelta(minutes=30)
DIGEST = "a" * 64


def fixture(*, sport="NFL", market="passing_yards", published=None,
            captured=None, digest=DIGEST, rights="licensed",
            event_id=None, team_id="team:home"):
    event = Event(sport, event_id or sport.lower() + ":fixture", TIP,
                  "team:home", "team:away")
    source = SourceProof(
        "Fixture provider", "https://example.org/quote/123",
        published or TIP - timedelta(hours=2),
        captured or TIP - timedelta(hours=1),
        rights=rights, content_sha256=digest,
    )
    quote = MarketQuote("fixture:quote", event.event_id, "fixture:athlete",
                        team_id, market, 250.5, -110, "Fixture Book", source)
    return event, quote


class MarketQuoteReadinessTests(unittest.TestCase):
    def test_good_chronology_is_replay_only_never_scoring_or_settlement(self):
        event, quote = fixture()
        result = audit_quote(event, quote, CUTOFF)
        self.assertTrue(result.point_in_time_replay_ready)
        self.assertFalse(result.scoring_eligible)
        self.assertFalse(result.settlement_eligible)
        self.assertTrue(result.rights_review_required)
        self.assertIn("selection_side_missing", result.reasons)
        self.assertIn("market_period_missing", result.reasons)
        self.assertIn("rights_attestation_not_independently_verified", result.reasons)

    def test_missing_raw_digest_blocks_replay(self):
        event, quote = fixture(digest=None)
        result = audit_quote(event, quote, CUTOFF)
        self.assertFalse(result.point_in_time_replay_ready)
        self.assertIn("raw_payload_digest_missing", result.reasons)

    def test_late_capture_blocks_replay_even_if_publication_is_old(self):
        event, quote = fixture(captured=TIP - timedelta(minutes=10))
        result = audit_quote(event, quote, CUTOFF)
        self.assertFalse(result.point_in_time_replay_ready)
        self.assertIn("captured_after_cutoff", result.reasons)

    def test_future_publication_blocks_replay(self):
        event, quote = fixture(
            published=TIP - timedelta(minutes=15),
            captured=TIP - timedelta(minutes=10),
        )
        self.assertIn("published_after_cutoff",
                      audit_quote(event, quote, CUTOFF).reasons)

    def test_event_and_team_mismatch_fail_closed(self):
        event, quote = fixture(team_id="team:visitor")
        result = audit_quote(event, quote, CUTOFF)
        self.assertFalse(result.point_in_time_replay_ready)
        self.assertIn("team_mismatch", result.reasons)
        other = Event("NFL", "nfl:other", TIP, "team:home", "team:away")
        self.assertIn("event_mismatch", audit_quote(other, quote, CUTOFF).reasons)

    def test_cross_sport_market_mismatch(self):
        event, quote = fixture(sport="NBA", market="passing_yards")
        result = audit_quote(event, quote, CUTOFF)
        self.assertFalse(result.point_in_time_replay_ready)
        self.assertIn("market_not_registered_for_sport", result.reasons)

    def test_replay_cutoff_must_precede_start(self):
        event, quote = fixture()
        result = audit_quote(event, quote, TIP)
        self.assertFalse(result.point_in_time_replay_ready)
        self.assertIn("cutoff_not_pregame", result.reasons)

    def test_naive_cutoff_rejected(self):
        event, quote = fixture()
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            audit_quote(event, quote, datetime(2026, 10, 25, 19))

    def test_unverified_rights_never_imply_permission(self):
        event, quote = fixture(rights="unverified")
        result = audit_quote(event, quote, CUTOFF)
        self.assertTrue(result.point_in_time_replay_ready)
        self.assertTrue(result.rights_review_required)
        self.assertFalse(result.scoring_eligible)
        self.assertIn("rights_not_declared_licensed", result.reasons)


if __name__ == "__main__":
    unittest.main()
