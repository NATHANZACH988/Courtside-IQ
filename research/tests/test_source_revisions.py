"""Synthetic regression tests: source revisions must not rewrite old snapshots."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import unittest

from research.quality.source_revisions import (
    EventClock, SourceRevision, SourceRevisionLedger,
)


def dt(hour, minute=0, day=25):
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


def event(sport="NBA"):
    return EventClock(sport, sport.lower() + ":test-game-01",
                      dt(20), "team:home", "team:away")


def revision(n="one", *, sport="NBA", provider="official", series="source:one",
             entity="athlete:one", metric="injury_status", value="questionable",
             captured=None, published=None, effective=None,
             team="team:home", state="active", supersedes=None, rights="unverified",
             digest=None):
    capture = captured or dt(14)
    return SourceRevision(
        revision_id="revision:" + n, series_id=series, sport=sport,
        event_id=sport.lower() + ":test-game-01", entity_id=entity,
        metric=metric, provider=provider, state=state, value=value,
        source_url="https://example.org/source/" + n,
        published_at=published or capture - timedelta(minutes=1),
        captured_at=capture, effective_at=effective or dt(20),
        raw_sha256=digest or (n[:1] * 64), team_id=team,
        rights_status=rights, supersedes=supersedes,
    )


class SourceRevisionTests(unittest.TestCase):
    def setUp(self):
        self.ledger = SourceRevisionLedger()
        self.ledger.add_event(event())

    def test_one_capture_visible_pre_tip(self):
        self.ledger.add_revision(revision())
        result = self.ledger.as_of("nba:test-game-01", dt(15))
        self.assertEqual(len(result.active_revisions), 1)
        self.assertEqual(result.active_revisions[0].value, "questionable")
        self.assertFalse(result.scoring_eligible)
        self.assertFalse(result.provenance_independently_verified)

    def test_source_not_known_before_capture_even_if_published_earlier(self):
        self.ledger.add_revision(revision(captured=dt(16), published=dt(13)))
        before = self.ledger.as_of("nba:test-game-01", dt(15))
        after = self.ledger.as_of("nba:test-game-01", dt(17))
        self.assertFalse(before.active_revisions)
        self.assertEqual(len(after.active_revisions), 1)

    def test_post_tip_correction_cannot_rewrite_pregame_view(self):
        self.ledger.add_revision(revision())
        self.ledger.add_revision(revision(
            "two", value="out", captured=dt(21), supersedes="revision:one"))
        pregame = self.ledger.as_of("nba:test-game-01", dt(19))
        retrospective = self.ledger.as_of("nba:test-game-01", dt(22), pregame=False)
        self.assertEqual(pregame.active_revisions[0].value, "questionable")
        self.assertEqual(retrospective.active_revisions[0].value, "out")

    def test_pregame_update_before_cutoff_visible(self):
        self.ledger.add_revision(revision())
        self.ledger.add_revision(revision(
            "two", value="available", captured=dt(17), supersedes="revision:one"))
        self.assertEqual(self.ledger.as_of("nba:test-game-01", dt(18)).
                         active_revisions[0].value, "available")

    def test_effective_date_is_not_a_retroactive_availability_timestamp(self):
        self.ledger.add_revision(revision(
            captured=dt(17), published=dt(16), effective=dt(10)))
        self.assertFalse(self.ledger.as_of("nba:test-game-01", dt(15)).active_revisions)

    def test_withdrawal_preserves_old_as_of_but_disappears_later(self):
        self.ledger.add_revision(revision())
        self.ledger.add_revision(revision(
            "two", state="withdrawn", value=None, captured=dt(18),
            supersedes="revision:one"))
        earlier = self.ledger.as_of("nba:test-game-01", dt(17))
        later = self.ledger.as_of("nba:test-game-01", dt(19))
        self.assertEqual(earlier.active_revisions[0].value, "questionable")
        self.assertFalse(later.active_revisions)
        self.assertEqual(later.withdrawn_series, ("source:one",))
        self.assertEqual(len(self.ledger.history("source:one")), 2)

    def test_reinstatement_after_withdrawal_preserves_chain(self):
        self.ledger.add_revision(revision())
        self.ledger.add_revision(revision(
            "two", state="withdrawn", value=None, captured=dt(17),
            supersedes="revision:one"))
        self.ledger.add_revision(revision(
            "three", state="active", value="available", captured=dt(18),
            supersedes="revision:two"))
        self.assertEqual(self.ledger.as_of("nba:test-game-01", dt(19)).
                         active_revisions[0].value, "available")
        self.assertEqual([x.revision_id for x in self.ledger.history("source:one")],
                         ["revision:one", "revision:two", "revision:three"])

    def test_disagreement_between_two_independent_providers(self):
        self.ledger.add_revision(revision())
        self.ledger.add_revision(revision(
            "other", provider="second", series="source:second",
            value="out"))
        view = self.ledger.as_of("nba:test-game-01", dt(15))
        self.assertEqual(len(view.disagreements), 1)
        self.assertEqual(view.disagreements[0].revision_ids,
                         ("revision:one", "revision:other"))

    def test_disagreement_not_silently_voted_away_by_third_provider(self):
        self.ledger.add_revision(revision())
        self.ledger.add_revision(revision(
            "other", provider="second", series="source:second", value="out"))
        self.ledger.add_revision(revision(
            "third", provider="third", series="source:third",
            value="questionable"))
        self.assertEqual(len(self.ledger.as_of("nba:test-game-01", dt(15)).
                             disagreements), 1)

    def test_matching_facts_across_providers_are_not_a_conflict(self):
        self.ledger.add_revision(revision())
        self.ledger.add_revision(revision(
            "other", provider="second", series="source:second",
            value="questionable"))
        self.assertFalse(self.ledger.as_of("nba:test-game-01", dt(15)).
                         disagreements)

    def test_same_numeric_value_int_float_not_conflict(self):
        self.ledger.add_revision(revision(metric="minutes_expected", value=20))
        self.ledger.add_revision(revision(
            "other", provider="second", series="source:second",
            metric="minutes_expected", value=20.0))
        self.assertFalse(self.ledger.as_of("nba:test-game-01", dt(15)).
                         disagreements)

    def test_numeric_and_string_value_are_distinct(self):
        self.ledger.add_revision(revision(metric="minutes_expected", value=20))
        self.ledger.add_revision(revision(
            "other", provider="second", series="source:second",
            metric="minutes_expected", value="20"))
        self.assertEqual(len(self.ledger.as_of("nba:test-game-01", dt(15)).
                             disagreements), 1)

    def test_conflict_resolves_only_once_correction_is_captured(self):
        self.ledger.add_revision(revision())
        self.ledger.add_revision(revision(
            "other", provider="second", series="source:second", value="out"))
        self.ledger.add_revision(revision(
            "secondversion", provider="second", series="source:second",
            value="questionable", captured=dt(17), supersedes="revision:other"))
        self.assertEqual(len(self.ledger.as_of("nba:test-game-01", dt(16)).
                             disagreements), 1)
        self.assertFalse(self.ledger.as_of("nba:test-game-01", dt(18)).
                         disagreements)

    def test_conflict_resolves_when_disagreeing_source_withdraws(self):
        self.ledger.add_revision(revision())
        self.ledger.add_revision(revision(
            "other", provider="second", series="source:second", value="out"))
        self.ledger.add_revision(revision(
            "secondversion", provider="second", series="source:second",
            state="withdrawn", value=None, captured=dt(18),
            supersedes="revision:other"))
        self.assertFalse(self.ledger.as_of("nba:test-game-01", dt(19)).
                         disagreements)

    def test_disagreeing_team_attribution_reported(self):
        self.ledger.add_revision(revision())
        self.ledger.add_revision(revision(
            "other", provider="second", series="source:second",
            team="team:away"))
        result = self.ledger.as_of("nba:test-game-01", dt(15))
        self.assertEqual(result.team_disagreements,
                         (("athlete:one", ("team:away", "team:home")),))

    def test_retraction_of_wrong_team_removes_disagreement(self):
        self.ledger.add_revision(revision())
        self.ledger.add_revision(revision(
            "other", provider="second", series="source:second",
            team="team:away"))
        self.ledger.add_revision(revision(
            "newteam", provider="second", series="source:second",
            team="team:home", captured=dt(17), supersedes="revision:other"))
        self.assertFalse(self.ledger.as_of("nba:test-game-01", dt(18)).
                         team_disagreements)

    def test_staleness_threshold_explicit(self):
        self.ledger.add_revision(revision())
        older = self.ledger.as_of("nba:test-game-01", dt(15), max_age_seconds=3599)
        boundary = self.ledger.as_of("nba:test-game-01", dt(15), max_age_seconds=3600)
        self.assertEqual(older.stale_revision_ids, ("revision:one",))
        self.assertFalse(boundary.stale_revision_ids)

    def test_staleness_not_assumed_without_policy(self):
        self.ledger.add_revision(revision())
        self.assertFalse(self.ledger.as_of("nba:test-game-01", dt(19)).
                         stale_revision_ids)

    def test_unverified_rights_flagged_but_licensed_not_authorized(self):
        self.ledger.add_revision(revision(rights="licensed"))
        view = self.ledger.as_of("nba:test-game-01", dt(15))
        self.assertFalse(view.rights_review_revision_ids)
        self.assertFalse(view.provenance_independently_verified)
        self.assertFalse(view.scoring_eligible)

    def test_unverified_and_restricted_rights_flagged(self):
        self.ledger.add_revision(revision())
        self.ledger.add_revision(revision(
            "other", provider="second", series="source:second",
            rights="restricted"))
        self.assertEqual(self.ledger.as_of("nba:test-game-01", dt(15)).
                         rights_review_revision_ids,
                         ("revision:one", "revision:other"))

    def test_duplicate_event_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate event_id"):
            self.ledger.add_event(event())

    def test_duplicate_revision_id_rejected(self):
        r = revision()
        self.ledger.add_revision(r)
        with self.assertRaisesRegex(ValueError, "duplicate revision_id"):
            self.ledger.add_revision(r)

    def test_other_event_rejected(self):
        with self.assertRaisesRegex(ValueError, "not registered"):
            self.ledger.add_revision(replace(revision(), event_id="nba:unknown"))

    def test_sport_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "sport mismatch"):
            self.ledger.add_revision(revision(sport="NFL"))

    def test_unknown_team_rejected(self):
        with self.assertRaisesRegex(ValueError, "not part of event"):
            self.ledger.add_revision(revision(team="team:unrelated"))

    def test_first_revision_cannot_supersede(self):
        with self.assertRaisesRegex(ValueError, "first revision"):
            self.ledger.add_revision(revision(supersedes="revision:unknown"))

    def test_revision_must_link_immediately_prior(self):
        self.ledger.add_revision(revision())
        with self.assertRaisesRegex(ValueError, "latest known version"):
            self.ledger.add_revision(revision(
                "two", captured=dt(17), supersedes="revision:unknown"))

    def test_revision_capture_must_increase(self):
        self.ledger.add_revision(revision())
        with self.assertRaisesRegex(ValueError, "follow predecessor"):
            self.ledger.add_revision(revision(
                "two", captured=dt(14), supersedes="revision:one"))

    def test_revision_series_identity_cannot_mutate_entity(self):
        self.ledger.add_revision(revision())
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.ledger.add_revision(revision(
                "two", entity="athlete:other", captured=dt(17),
                supersedes="revision:one"))

    def test_provider_cannot_sneak_duplicate_independent_series(self):
        self.ledger.add_revision(revision())
        with self.assertRaisesRegex(ValueError, "already has a series"):
            self.ledger.add_revision(revision("duplicate", series="source:duplicate"))

    def test_same_payload_cannot_claim_changed_fact(self):
        self.ledger.add_revision(revision(digest="a" * 64))
        with self.assertRaisesRegex(ValueError, "identical source payload"):
            self.ledger.add_revision(revision(
                "two", digest="a" * 64, value="out", captured=dt(17),
                supersedes="revision:one"))

    def test_wrong_base_branch_event_does_not_accept_provenance(self):
        with self.assertRaises(ValueError):
            EventClock("NBA", "nfl:event", dt(20), "team:home", "team:away")

    def test_non_utc_datetime_is_normalized(self):
        est = timezone(timedelta(hours=-4))
        r = replace(revision(), captured_at=dt(14).astimezone(est))
        self.assertEqual(r.captured_at, dt(14))

    def test_naive_timestamps_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            replace(revision(), captured_at=datetime(2026, 10, 25, 14))

    def test_publication_after_capture_rejected(self):
        with self.assertRaisesRegex(ValueError, "before source publication"):
            revision(captured=dt(14), published=dt(15))

    def test_http_url_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            replace(revision(), source_url="http://example.org/")

    def test_embedded_password_rejected(self):
        with self.assertRaisesRegex(ValueError, "credential"):
            replace(revision(), source_url="https://user:pass@example.org/")

    def test_token_in_query_rejected(self):
        with self.assertRaisesRegex(ValueError, "credential"):
            replace(revision(), source_url="https://example.org/data?api_key=secret")

    def test_url_fragment_rejected(self):
        with self.assertRaisesRegex(ValueError, "credential"):
            replace(revision(), source_url="https://example.org/data#token")

    def test_invalid_hash_and_rights_rejected(self):
        with self.assertRaises(ValueError):
            replace(revision(), raw_sha256="bad")
        with self.assertRaises(ValueError):
            replace(revision(), rights_status=["licensed"])

    def test_nonfinite_numeric_value_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf"), True, 10 ** 1500):
            with self.subTest(value=str(value)[:15]):
                with self.assertRaises(ValueError):
                    replace(revision(), value=value)

    def test_withdrawal_cannot_hide_active_fact(self):
        with self.assertRaises(ValueError):
            replace(revision(), state="withdrawn")
        with self.assertRaises(ValueError):
            replace(revision(), state="active", value=None)

    def test_invalid_metric_rejected(self):
        with self.assertRaisesRegex(ValueError, "metric"):
            replace(revision(), metric="Points Per Game")

    def test_pregame_cutoff_equal_start_rejected(self):
        with self.assertRaisesRegex(ValueError, "precede"):
            self.ledger.as_of("nba:test-game-01", dt(20))

    def test_unaware_cutoff_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            self.ledger.as_of("nba:test-game-01", datetime(2026, 10, 25, 15))

    def test_invalid_max_age_rejected(self):
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            self.ledger.as_of("nba:test-game-01", dt(15), max_age_seconds=-1)
        with self.assertRaises(ValueError):
            self.ledger.as_of("nba:test-game-01", dt(15), max_age_seconds=True)

    def test_unknown_event_view_rejected(self):
        with self.assertRaisesRegex(ValueError, "not registered"):
            self.ledger.as_of("nfl:not-present", dt(15))

    def test_source_dataclass_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            revision().value = "out"

    def test_missing_series_history_is_empty(self):
        self.assertEqual(self.ledger.history("source:unknown"), ())

    def test_registration_type_validation(self):
        with self.assertRaises(TypeError):
            self.ledger.add_event({"sport": "NBA"})
        with self.assertRaises(TypeError):
            self.ledger.add_revision({"value": 1})

    def test_same_ledger_works_for_nfl(self):
        other = SourceRevisionLedger()
        other.add_event(event("NFL"))
        other.add_revision(revision(sport="NFL", metric="snap_share", value=0.6))
        view = other.as_of("nfl:test-game-01", dt(15))
        self.assertEqual(view.active_revisions[0].value, 0.6)

    def test_same_ledger_works_for_mlb_nhl_and_soccer(self):
        for sport in ("MLB", "NHL", "SOCCER"):
            with self.subTest(sport=sport):
                other = SourceRevisionLedger()
                other.add_event(event(sport))
                other.add_revision(revision(
                    sport=sport, metric="lineup_status", value="pending"))
                self.assertEqual(other.as_of(sport.lower() + ":test-game-01", dt(15)).
                                 active_revisions[0].value, "pending")

    def test_independent_events_remain_isolated(self):
        self.ledger.add_revision(revision())
        self.ledger.add_event(EventClock(
            "NBA", "nba:other-game", dt(20), "team:home", "team:away"))
        self.assertFalse(self.ledger.as_of("nba:other-game", dt(15)).
                         active_revisions)


if __name__ == "__main__":
    unittest.main()
