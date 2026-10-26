"""Synthetic tests for frozen player-prop quote-content binding.

No live odds, historical ticket data, licensed feeds or real betting claims.
"""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone, timedelta
import unittest

from research.props.frozen_batch_audit import FrozenPropSelection
from research.props.prop_board import Game, PropQuote, SourceStamp
from research.props.quote_binding_audit import (
    FrozenQuoteBinding, audit_frozen_quote_bindings,
    binding_record_sha256, quote_content_sha256,
)

H = "b" * 64


def t(hour, minute=0):
    return datetime(2026, 10, 25, hour, minute, tzinfo=timezone.utc)


def stamp(published=t(18), captured=t(18, 5), digest=H):
    return SourceStamp("synthetic", "https://example.org/quote",
                       published, captured, digest)


def make_binding(selection, quote, archive_published=t(18, 10),
                 archive_captured=t(18, 15)):
    quote_digest = quote_content_sha256(quote)
    digest = binding_record_sha256(
        selection.selection_id, selection.quote_id,
        selection.frozen_at, quote_digest)
    source = SourceStamp("archive", "https://example.org/archive",
                         archive_published, archive_captured, digest)
    return FrozenQuoteBinding(selection.selection_id, selection.quote_id,
                              selection.frozen_at, quote_digest, source)


def fixture():
    gm = Game("NBA", "nba:synthetic", "team:home", "team:away", t(20))
    quote = PropQuote("quote:one", gm.event_id, "athlete:one", "team:home",
                      "points", "full_game", "over", "20.5", -110,
                      "synthetic-book", stamp())
    selection = FrozenPropSelection("selection:one", quote.quote_id, t(19), H)
    binding = make_binding(selection, quote)
    return [gm, (selection,), (quote,), (binding,), t(23)]


def audit(case):
    return audit_frozen_quote_bindings(*case)


class QuoteBindingTests(unittest.TestCase):
    def test_valid_snapshot_is_bound_but_never_source_verified(self):
        result = audit(fixture())
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertEqual((result.declared_selection_count, result.bound,
                          result.invalid, result.missing_binding), (1, 1, 0, 0))
        self.assertEqual(result.rows[0].status, "bound")
        self.assertFalse(result.source_independently_verified)
        self.assertFalse(result.manifest_completeness_verified)
        self.assertFalse(result.scoring_eligible)
        self.assertFalse(result.official_book_settlement_verified)

    def test_quote_line_mutation_is_detected(self):
        case = fixture()
        case[2] = (replace(case[2][0], line="25.5"),)
        self.assertIn("original_quote_content_changed", audit(case).rows[0].reasons)

    def test_side_mutation_is_detected(self):
        case = fixture()
        case[2] = (replace(case[2][0], side="under"),)
        self.assertIn("original_quote_content_changed", audit(case).rows[0].reasons)

    def test_price_mutation_is_detected(self):
        case = fixture()
        case[2] = (replace(case[2][0], american_odds=125),)
        self.assertIn("original_quote_content_changed", audit(case).rows[0].reasons)

    def test_sportsbook_mutation_is_detected(self):
        case = fixture()
        case[2] = (replace(case[2][0], sportsbook="different-book"),)
        self.assertIn("original_quote_content_changed", audit(case).rows[0].reasons)

    def test_athlete_swap_is_detected(self):
        case = fixture()
        case[2] = (replace(case[2][0], athlete_id="athlete:two"),)
        self.assertIn("original_quote_content_changed", audit(case).rows[0].reasons)

    def test_team_swap_is_detected(self):
        case = fixture()
        case[2] = (replace(case[2][0], team_id="team:away"),)
        self.assertIn("original_quote_content_changed", audit(case).rows[0].reasons)

    def test_market_swap_is_detected(self):
        case = fixture()
        case[2] = (replace(case[2][0], market="rebounds"),)
        self.assertIn("original_quote_content_changed", audit(case).rows[0].reasons)

    def test_source_payload_digest_swap_is_detected(self):
        case = fixture()
        case[2] = (replace(case[2][0], source=replace(
            case[2][0].source, raw_sha256="a" * 64)),)
        self.assertIn("original_quote_content_changed", audit(case).rows[0].reasons)

    def test_source_capture_time_swap_is_detected(self):
        case = fixture()
        case[2] = (replace(case[2][0], source=replace(
            case[2][0].source, captured_at=t(18, 6))),)
        self.assertIn("original_quote_content_changed", audit(case).rows[0].reasons)

    def test_source_provider_swap_is_detected(self):
        case = fixture()
        case[2] = (replace(case[2][0], source=replace(
            case[2][0].source, provider="other-provider")),)
        self.assertIn("original_quote_content_changed", audit(case).rows[0].reasons)

    def test_source_rights_label_swap_is_detected(self):
        case = fixture()
        case[2] = (replace(case[2][0], source=replace(
            case[2][0].source, rights_status="licensed")),)
        self.assertIn("original_quote_content_changed", audit(case).rows[0].reasons)

    def test_quote_id_mutation_cannot_resolve_selection(self):
        case = fixture()
        case[2] = (replace(case[2][0], quote_id="quote:two"),)
        self.assertIn("original_quote_missing", audit(case).rows[0].reasons)

    def test_selection_freeze_time_mutation_rejected(self):
        case = fixture()
        case[1] = (replace(case[1][0], frozen_at=t(19, 1)),)
        self.assertIn("binding_freeze_time_mismatch", audit(case).rows[0].reasons)

    def test_binding_fingerprint_tampering_breaks_archive_digest(self):
        case = fixture()
        case[3] = (replace(case[3][0], quote_sha256="f" * 64),)
        result = audit(case)
        self.assertIn("binding_archive_payload_digest_mismatch",
                      result.rows[0].reasons)
        self.assertIn("original_quote_content_changed", result.rows[0].reasons)

    def test_archive_digest_tampering_rejected(self):
        case = fixture()
        case[3] = (replace(case[3][0], archive_source=replace(
            case[3][0].archive_source, raw_sha256="f" * 64)),)
        self.assertIn("binding_archive_payload_digest_mismatch",
                      audit(case).rows[0].reasons)

    def test_archive_capture_after_selection_freeze_rejected(self):
        case = fixture()
        case[3] = (replace(case[3][0], archive_source=replace(
            case[3][0].archive_source, captured_at=t(19, 1))),)
        self.assertIn("binding_archive_captured_after_freeze",
                      audit(case).rows[0].reasons)

    def test_archive_capture_at_or_after_tip_rejected(self):
        case = fixture()
        case[3] = (replace(case[3][0], archive_source=replace(
            case[3][0].archive_source, captured_at=t(20, 1))),)
        self.assertIn("binding_archive_captured_at_or_after_tip",
                      audit(case).rows[0].reasons)

    def test_archive_published_before_quote_capture_rejected(self):
        case = fixture()
        case[3] = (replace(case[3][0], archive_source=replace(
            case[3][0].archive_source, published_at=t(17))),)
        self.assertIn("binding_archive_published_before_quote_capture",
                      audit(case).rows[0].reasons)

    def test_archive_captured_before_quote_capture_rejected(self):
        case = fixture()
        case[3] = (replace(case[3][0], archive_source=replace(
            case[3][0].archive_source, published_at=t(18),
            captured_at=t(18, 1))),)
        self.assertIn("binding_archive_captured_before_quote_capture",
                      audit(case).rows[0].reasons)

    def test_quote_captured_after_selection_freeze_rejected(self):
        case = fixture()
        case[2] = (replace(case[2][0], source=stamp(t(19, 1), t(19, 2))),)
        self.assertIn("quote_captured_after_selection_freeze",
                      audit(case).rows[0].reasons)

    def test_quote_captured_after_tip_rejected(self):
        case = fixture()
        case[2] = (replace(case[2][0], source=stamp(t(20), t(20, 1))),)
        self.assertIn("quote_captured_at_or_after_tip",
                      audit(case).rows[0].reasons)

    def test_wrong_event_quote_rejected(self):
        case = fixture()
        case[2] = (replace(case[2][0], event_id="nba:other"),)
        self.assertIn("quote_event_mismatch", audit(case).rows[0].reasons)

    def test_wrong_team_quote_rejected(self):
        case = fixture()
        case[2] = (replace(case[2][0], team_id="team:other"),)
        self.assertIn("quote_team_not_in_event", audit(case).rows[0].reasons)

    def test_unsupported_nba_market_rejected(self):
        case = fixture()
        case[2] = (replace(case[2][0], market="receiving_yards"),)
        self.assertIn("quote_market_not_supported_for_sport",
                      audit(case).rows[0].reasons)

    def test_missing_binding_keeps_selection_denominator(self):
        case = fixture()
        case[3] = ()
        result = audit(case)
        self.assertEqual(result.declared_selection_count, 1)
        self.assertEqual(result.invalid, 1)
        self.assertEqual(result.missing_binding, 1)
        self.assertIn("original_quote_binding_missing", result.rows[0].reasons)

    def test_orphan_binding_blocks_batch_without_changing_denominator(self):
        case = fixture()
        orphan = replace(case[3][0], selection_id="selection:orphan")
        case[3] = case[3] + (orphan,)
        result = audit(case)
        self.assertEqual(result.orphan_bindings, 1)
        self.assertEqual(result.declared_selection_count, 1)
        self.assertFalse(result.structurally_valid)

    def test_duplicate_binding_blocks_selected_row(self):
        case = fixture()
        case[3] = case[3] + (case[3][0],)
        self.assertIn("duplicate_or_ambiguous_binding_for_selection",
                      audit(case).rows[0].reasons)

    def test_duplicate_quote_id_blocks_selected_row(self):
        case = fixture()
        case[2] = case[2] + (replace(case[2][0], sportsbook="other-book"),)
        self.assertIn("duplicate_or_ambiguous_quote_id",
                      audit(case).rows[0].reasons)

    def test_duplicate_selection_id_blocks_both_rows(self):
        case = fixture()
        case[1] = case[1] + (case[1][0],)
        result = audit(case)
        self.assertEqual(result.invalid, 2)
        self.assertTrue(all("duplicate_frozen_selection_id" in r.reasons
                            for r in result.rows))

    def test_reused_quote_id_blocks_both_rows(self):
        case = fixture()
        case[1] = case[1] + (replace(case[1][0],
                                    selection_id="selection:two"),)
        result = audit(case)
        self.assertEqual(result.invalid, 2)
        self.assertTrue(all("duplicate_selected_quote_id" in r.reasons
                            for r in result.rows))

    def test_binding_quote_id_mismatch_rejected(self):
        case = fixture()
        case[3] = (replace(case[3][0], quote_id="quote:two"),)
        self.assertIn("binding_quote_id_mismatch", audit(case).rows[0].reasons)

    def test_freeze_at_tip_rejected(self):
        case = fixture()
        case[1] = (replace(case[1][0], frozen_at=t(20)),)
        self.assertIn("selection_frozen_at_or_after_tip",
                      audit(case).rows[0].reasons)

    def test_no_selections_not_a_valid_batch(self):
        case = fixture()
        case[1] = ()
        result = audit(case)
        self.assertFalse(result.structurally_valid)
        self.assertIn("selection_manifest_empty", result.reasons)

    def test_audit_at_tip_rejected(self):
        case = fixture()
        case[4] = t(20)
        self.assertIn("audit_not_after_event_start", audit(case).rows[0].reasons)

    def test_audit_before_binding_capture_rejected(self):
        case = fixture()
        case[4] = t(18, 11)
        self.assertIn("binding_archive_after_review_cutoff",
                      audit(case).rows[0].reasons)

    def test_selection_freeze_after_review_cutoff_rejected(self):
        case = fixture()
        case[4] = t(18, 30)
        self.assertIn("selection_frozen_after_review_cutoff",
                      audit(case).rows[0].reasons)

    def test_wrong_types_rejected(self):
        case = fixture()
        case[1] = list(case[1])
        with self.assertRaises(TypeError):
            audit(case)
        case = fixture()
        case[3] = ({"quote_sha256": H},)
        with self.assertRaises(TypeError):
            audit(case)

    def test_source_archive_must_be_valid_stamp(self):
        case = fixture()
        with self.assertRaises(ValueError):
            replace(case[3][0], archive_source={"captured_at": t(18)})

    def test_credentialed_archive_source_rejected(self):
        case = fixture()
        with self.assertRaises(ValueError):
            replace(case[3][0].archive_source,
                    url="https://example.org/archive?token=secret")

    def test_quote_sha256_must_be_64_hex(self):
        case = fixture()
        with self.assertRaises(ValueError):
            replace(case[3][0], quote_sha256="not-a-sha256")

    def test_binding_freeze_must_be_timezone_aware(self):
        case = fixture()
        with self.assertRaises(ValueError):
            replace(case[3][0], frozen_at=datetime(2026, 10, 25, 19))

    def test_archive_digest_is_deterministic(self):
        case = fixture()
        selection, quote = case[1][0], case[2][0]
        self.assertEqual(
            binding_record_sha256(selection.selection_id, quote.quote_id,
                                  selection.frozen_at, quote_content_sha256(quote)),
            case[3][0].archive_source.raw_sha256)

    def test_quote_hash_differs_on_exact_decimal_format(self):
        case = fixture()
        q = case[2][0]
        self.assertNotEqual(quote_content_sha256(q),
                            quote_content_sha256(replace(q, line="20.50")))

    def test_utc_timezone_normalization_is_stable(self):
        case = fixture()
        freeze = case[1][0].frozen_at
        shifted = freeze.astimezone(timezone(timedelta(hours=-4)))
        self.assertEqual(
            binding_record_sha256("selection:one", "quote:one", freeze,
                                  case[3][0].quote_sha256),
            binding_record_sha256("selection:one", "quote:one", shifted,
                                  case[3][0].quote_sha256))

    def test_two_distinct_book_quotes_for_same_athlete_both_bind(self):
        case = fixture()
        quote2 = replace(case[2][0], quote_id="quote:two",
                         sportsbook="other-book", line="21.5")
        selection2 = FrozenPropSelection("selection:two", "quote:two", t(19), H)
        binding2 = make_binding(selection2, quote2)
        case[1] += (selection2,)
        case[2] += (quote2,)
        case[3] += (binding2,)
        result = audit(case)
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertEqual((result.declared_selection_count, result.bound), (2, 2))

    def test_nfl_player_prop_binding_without_nba_assumption(self):
        case = fixture()
        gm = Game("NFL", "nfl:synthetic", "team:home", "team:away", t(20))
        quote = replace(case[2][0], event_id=gm.event_id,
                        market="receiving_yards")
        binding = make_binding(case[1][0], quote)
        case[0], case[2], case[3] = gm, (quote,), (binding,)
        self.assertTrue(audit(case).structurally_valid)

    def test_rows_are_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            audit(fixture()).rows[0].status = "bound"

    def test_repeat_audit_is_deterministic(self):
        case = fixture()
        self.assertEqual(audit(case), audit(case))


if __name__ == "__main__":
    unittest.main()
