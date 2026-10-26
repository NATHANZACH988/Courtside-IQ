"""Synthetic-only tests: no live book, verified line or sportsbook settlement."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import unittest

from research.props.frozen_batch_audit import FrozenPropSelection
from research.props.prop_board import Game, PropQuote, SourceStamp
from research.props.quote_binding_audit import (
    FrozenQuoteBinding, binding_record_sha256, quote_content_sha256,
)
from research.props.pretip_recheck_audit import (
    PretipMarketRecheck, audit_pretip_market_rechecks,
)


def t(hour, minute=0):
    return datetime(2026, 10, 25, hour, minute, tzinfo=timezone.utc)


H = "d" * 64


def stamp(published, captured, url="https://example.org/source", digest=H):
    return SourceStamp("synthetic", url, published, captured, digest)


def fixture():
    game = Game("NBA", "nba:fake-1", "team:home", "team:away", t(20))
    quote = PropQuote(
        "quote:one", game.event_id, "athlete:one", "team:home", "points",
        "full_game", "over", "20.5", -110, "synthetic-book",
        stamp(t(18), t(18, 5)),
    )
    selection = FrozenPropSelection("selection:one", quote.quote_id, t(19), H)
    qhash = quote_content_sha256(quote)
    digest = binding_record_sha256(
        selection.selection_id, quote.quote_id, selection.frozen_at, qhash)
    binding = FrozenQuoteBinding(
        selection.selection_id, quote.quote_id, selection.frozen_at,
        qhash, stamp(t(18, 10), t(18, 15), digest=digest))
    recheck = PretipMarketRecheck(
        quote.quote_id, game.event_id, quote.athlete_id, quote.team_id,
        quote.market, quote.period, quote.side, quote.sportsbook, "open",
        quote.line, quote.american_odds, stamp(t(19, 45), t(19, 50)),
    )
    return [game, (selection,), (quote,), (binding,), (recheck,), t(19, 55)]


def audit(case, **overrides):
    params = dict(max_recheck_age_minutes=15, pretip_window_minutes=60)
    params.update(overrides)
    return audit_pretip_market_rechecks(*case, **params)


class PretipRecheckTests(unittest.TestCase):
    def test_unchanged_quote_is_not_a_verified_offer_or_play(self):
        result = audit(fixture())
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertTrue(result.all_original_lines_still_observed)
        self.assertEqual(result.rows[0].status, "unchanged")
        self.assertEqual(result.declared_selection_count, 1)
        self.assertFalse(result.play_authorized)
        self.assertFalse(result.source_independently_verified)
        self.assertFalse(result.licensed_for_commercial_use)
        self.assertFalse(result.rows[0].play_authorized)

    def test_moved_line_is_not_silently_replaced_in_original(self):
        case = fixture()
        case[4] = (replace(case[4][0], line="25.5"),)
        result = audit(case)
        self.assertTrue(result.structurally_valid)
        self.assertFalse(result.all_original_lines_still_observed)
        self.assertEqual(result.rows[0].status, "moved")
        self.assertEqual(result.rows[0].original_line, "20.5")
        self.assertEqual(result.rows[0].latest_line, "25.5")
        self.assertEqual(case[2][0].line, "20.5")

    def test_odds_movement_also_matters(self):
        case = fixture()
        case[4] = (replace(case[4][0], american_odds=-125),)
        result = audit(case)
        self.assertEqual(result.rows[0].status, "moved")
        self.assertEqual(result.rows[0].original_american_odds, -110)
        self.assertEqual(result.rows[0].latest_american_odds, -125)

    def test_suspended_quote_not_marked_open(self):
        case = fixture()
        case[4] = (replace(case[4][0], status="suspended",
                           line=None, american_odds=None),)
        self.assertEqual(audit(case).rows[0].status, "suspended")
        self.assertFalse(audit(case).all_original_lines_still_observed)

    def test_withdrawn_quote_not_marked_open(self):
        case = fixture()
        case[4] = (replace(case[4][0], status="withdrawn",
                           line=None, american_odds=None),)
        self.assertEqual(audit(case).rows[0].status, "withdrawn")

    def test_unknown_status_remains_unknown(self):
        case = fixture()
        case[4] = (replace(case[4][0], status="unknown",
                           line=None, american_odds=None),)
        self.assertEqual(audit(case).rows[0].status, "unknown")

    def test_no_recheck_is_not_assumed_still_open(self):
        case = fixture()
        case[4] = ()
        result = audit(case)
        self.assertFalse(result.structurally_valid)
        self.assertEqual(result.rows[0].status, "missing")
        self.assertIn("missing_pretip_recheck", result.rows[0].reasons)

    def test_stale_recheck_rejected(self):
        case = fixture()
        case[4] = (replace(case[4][0],
                           source=stamp(t(19, 10), t(19, 20))),)
        result = audit(case)
        self.assertEqual(result.rows[0].status, "stale")
        self.assertIn("recheck_stale_at_cutoff", result.rows[0].reasons)

    def test_freshness_threshold_must_be_explicit(self):
        with self.assertRaises(TypeError):
            audit_pretip_market_rechecks(*fixture())

    def test_thresholds_must_be_valid_integer_not_bool(self):
        for kwargs in (
            {"max_recheck_age_minutes": True},
            {"max_recheck_age_minutes": 0},
            {"max_recheck_age_minutes": 241},
            {"pretip_window_minutes": 0},
            {"pretip_window_minutes": 241},
            {"pretip_window_minutes": 1.5},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    audit(fixture(), **kwargs)

    def test_pretip_window_cannot_be_replaced_by_morning_snapshot(self):
        case = fixture()
        case[5] = t(19, 55)
        result = audit(case, pretip_window_minutes=4)
        self.assertFalse(result.structurally_valid)
        self.assertIn("review_cutoff_outside_explicit_pretip_window",
                      result.reasons)

    def test_after_tip_cutoff_rejected(self):
        case = fixture()
        case[5] = t(20, 1)
        self.assertFalse(audit(case).structurally_valid)

    def test_latest_recheck_wins_not_more_favorable_earlier_line(self):
        case = fixture()
        early = replace(case[4][0], line="19.5",
                        source=stamp(t(19, 30), t(19, 35)))
        latest = replace(case[4][0], line="25.5",
                         source=stamp(t(19, 48), t(19, 51)))
        case[4] = (latest, early)
        result = audit(case)
        self.assertEqual(result.rows[0].status, "moved")
        self.assertEqual(result.rows[0].latest_line, "25.5")
        case[4] = (early, latest)
        self.assertEqual(result, audit(case))

    def test_same_capture_time_conflicting_rechecks_rejected(self):
        case = fixture()
        case[4] = case[4] + (replace(case[4][0], line="25.5"),)
        result = audit(case)
        self.assertEqual(result.rows[0].status, "invalid")
        self.assertIn("ambiguous_latest_recheck_same_capture_time",
                      result.rows[0].reasons)

    def test_future_recheck_cannot_be_selected(self):
        case = fixture()
        case[4] = case[4] + (replace(
            case[4][0], line="25.5",
            source=stamp(t(19, 56), t(19, 57))),)
        result = audit(case)
        self.assertEqual(result.rows[0].status, "invalid")
        self.assertIn("future_or_posttip_recheck_supplied", result.rows[0].reasons)

    def test_posttip_recheck_cannot_retroactively_prove_market(self):
        case = fixture()
        case[4] = (replace(case[4][0],
                           source=stamp(t(20), t(20, 1))),)
        self.assertFalse(audit(case).structurally_valid)

    def test_recheck_before_selection_freeze_is_not_new_observation(self):
        case = fixture()
        case[4] = (replace(case[4][0],
                           source=stamp(t(18, 30), t(18, 40))),)
        self.assertIn("recheck_not_after_selection_freeze",
                      audit(case).rows[0].reasons)

    def test_recheck_published_before_freeze_is_not_new_update(self):
        case = fixture()
        case[4] = (replace(case[4][0],
                           source=stamp(t(18, 30), t(19, 50))),)
        self.assertIn("recheck_publication_predates_selection",
                      audit(case).rows[0].reasons)

    def test_market_identity_mismatch_rejected(self):
        base = fixture()
        fields = [
            ("event_id", "nba:other"), ("athlete_id", "athlete:other"),
            ("team_id", "team:away"), ("market", "rebounds"),
            ("side", "under"), ("sportsbook", "another-book"),
        ]
        for field, value in fields:
            with self.subTest(field=field):
                case = list(base)
                case[4] = (replace(case[4][0], **{field: value}),)
                self.assertIn("recheck_original_market_identity_mismatch",
                              audit(case).rows[0].reasons)

    def test_original_line_mutation_detected_by_binding(self):
        case = fixture()
        case[2] = (replace(case[2][0], line="25.5"),)
        self.assertIn("original_quote_content_mismatch",
                      audit(case).rows[0].reasons)

    def test_original_price_mutation_detected_by_binding(self):
        case = fixture()
        case[2] = (replace(case[2][0], american_odds=110),)
        self.assertIn("original_quote_content_mismatch",
                      audit(case).rows[0].reasons)

    def test_archive_digest_mutation_detected(self):
        case = fixture()
        case[3] = (replace(case[3][0], archive_source=replace(
            case[3][0].archive_source, raw_sha256="a" * 64)),)
        self.assertIn("binding_archive_digest_mismatch",
                      audit(case).rows[0].reasons)

    def test_archive_after_freeze_rejected(self):
        case = fixture()
        case[3] = (replace(case[3][0], archive_source=stamp(
            t(19, 1), t(19, 2), digest=case[3][0].archive_source.raw_sha256)),)
        self.assertIn("binding_not_archived_by_selection_freeze",
                      audit(case).rows[0].reasons)

    def test_original_quote_after_freeze_rejected(self):
        case = fixture()
        case[2] = (replace(case[2][0],
                           source=stamp(t(19, 1), t(19, 2))),)
        self.assertIn("original_quote_not_captured_before_freeze",
                      audit(case).rows[0].reasons)

    def test_wrong_event_quote_rejected(self):
        case = fixture()
        case[2] = (replace(case[2][0], event_id="nba:other"),)
        self.assertIn("original_quote_wrong_event_or_team",
                      audit(case).rows[0].reasons)

    def test_missing_original_binding_blocks_recheck(self):
        case = fixture()
        case[3] = ()
        self.assertIn("missing_or_ambiguous_frozen_quote_binding",
                      audit(case).rows[0].reasons)

    def test_duplicate_original_quote_id_blocks_recheck(self):
        case = fixture()
        case[2] += (case[2][0],)
        self.assertIn("missing_or_ambiguous_original_quote",
                      audit(case).rows[0].reasons)

    def test_duplicate_selection_id_preserves_denominator(self):
        case = fixture()
        case[1] += (case[1][0],)
        result = audit(case)
        self.assertEqual(result.declared_selection_count, 2)
        self.assertEqual(len(result.rows), 2)
        self.assertFalse(result.structurally_valid)

    def test_orphan_recheck_is_not_silently_ignored(self):
        case = fixture()
        case[4] += (replace(case[4][0], quote_id="quote:other"),)
        result = audit(case)
        self.assertIn("orphan_pretip_recheck", result.reasons)
        self.assertFalse(result.structurally_valid)

    def test_orphan_binding_is_not_silently_ignored(self):
        case = fixture()
        case[3] += (replace(case[3][0], selection_id="selection:other"),)
        self.assertIn("orphan_original_binding", audit(case).reasons)

    def test_empty_selection_manifest_not_valid(self):
        case = fixture()
        case[1], case[3], case[4] = (), (), ()
        result = audit(case)
        self.assertFalse(result.structurally_valid)
        self.assertEqual(result.declared_selection_count, 0)

    def test_recheck_non_open_cannot_fabricate_live_price(self):
        case = fixture()
        with self.assertRaises(ValueError):
            replace(case[4][0], status="withdrawn")

    def test_recheck_open_must_have_line_and_price(self):
        case = fixture()
        with self.assertRaises(ValueError):
            replace(case[4][0], line=None)
        with self.assertRaises(ValueError):
            replace(case[4][0], american_odds=None)

    def test_recheck_line_rejects_nan_or_float(self):
        case = fixture()
        for line in ("NaN", "Infinity", -1, 20.5):
            with self.subTest(line=line):
                with self.assertRaises(ValueError):
                    replace(case[4][0], line=line)

    def test_recheck_credential_bearing_source_url_rejected(self):
        case = fixture()
        with self.assertRaises(ValueError):
            replace(case[4][0].source, url="https://example.org/?token=secret")

    def test_cross_sport_market_recheck(self):
        case = fixture()
        gm = Game("NFL", "nfl:fake-1", "team:home", "team:away", t(20))
        q = replace(case[2][0], event_id=gm.event_id,
                    market="receiving_yards")
        qhash = quote_content_sha256(q)
        sel = case[1][0]
        binding = replace(case[3][0], quote_sha256=qhash,
                          archive_source=replace(
                              case[3][0].archive_source,
                              raw_sha256=binding_record_sha256(
                                  sel.selection_id, q.quote_id,
                                  sel.frozen_at, qhash)))
        r = replace(case[4][0], event_id=gm.event_id,
                    market="receiving_yards")
        case[0], case[2], case[3], case[4] = gm, (q,), (binding,), (r,)
        self.assertTrue(audit(case).structurally_valid)

    def test_two_distinct_props_preserve_all_rows(self):
        case = fixture()
        q2 = replace(case[2][0], quote_id="quote:two",
                     athlete_id="athlete:two", team_id="team:away",
                     line="15.5")
        s2 = FrozenPropSelection("selection:two", q2.quote_id, t(19), H)
        qhash = quote_content_sha256(q2)
        b2 = FrozenQuoteBinding(
            s2.selection_id, q2.quote_id, s2.frozen_at, qhash,
            stamp(t(18, 10), t(18, 15),
                  digest=binding_record_sha256(
                      s2.selection_id, q2.quote_id, s2.frozen_at, qhash)))
        r2 = replace(case[4][0], quote_id=q2.quote_id,
                     athlete_id=q2.athlete_id, team_id=q2.team_id,
                     line="15.5")
        case[1] += (s2,)
        case[2] += (q2,)
        case[3] += (b2,)
        case[4] += (r2,)
        result = audit(case)
        self.assertEqual(result.declared_selection_count, 2)
        self.assertEqual(len(result.rows), 2)
        self.assertTrue(result.all_original_lines_still_observed)

    def test_earlier_wrong_player_snapshot_cannot_be_hidden_by_later_good_one(self):
        case = fixture()
        earlier = replace(case[4][0], athlete_id="athlete:other",
                          source=stamp(t(19, 20), t(19, 25)))
        case[4] = (earlier, case[4][0])
        result = audit(case)
        self.assertEqual(result.rows[0].status, "invalid")
        self.assertIn("recheck_lineage_contains_identity_mismatch",
                      result.rows[0].reasons)

    def test_earlier_wrong_market_snapshot_cannot_be_hidden(self):
        case = fixture()
        earlier = replace(case[4][0], market="rebounds",
                          source=stamp(t(19, 20), t(19, 25)))
        case[4] = (earlier, case[4][0])
        self.assertIn("recheck_lineage_contains_identity_mismatch",
                      audit(case).rows[0].reasons)

    def test_earlier_prefreeze_snapshot_cannot_be_hidden(self):
        case = fixture()
        earlier = replace(case[4][0],
                          source=stamp(t(18, 30), t(18, 40)))
        case[4] = (earlier, case[4][0])
        self.assertIn("recheck_lineage_contains_prefreeze_capture",
                      audit(case).rows[0].reasons)

    def test_invalid_status_and_side_types_fail_closed(self):
        case = fixture()
        with self.assertRaises(ValueError):
            replace(case[4][0], status=["open"])
        with self.assertRaises(ValueError):
            replace(case[4][0], side=["over"])

    def test_latest_market_recheck_not_tied_to_result_after_tip(self):
        case = fixture()
        result = audit(case)
        self.assertLess(result.checked_at, case[0].scheduled_start)
        self.assertFalse(result.play_authorized)

    def test_row_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            audit(fixture()).rows[0].status = "moved"


if __name__ == "__main__":
    unittest.main()
