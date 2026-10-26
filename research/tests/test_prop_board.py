"""Synthetic tests only. No real sportsbook, player or NBA result is asserted."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from research.props.prop_board import (
    BoardAudit, Game, PropProjection, PropQuote, PropScreen, RosterAthlete,
    SourceStamp, SPORT_MARKETS, audit_prop_board,
)


def t(hour, minute=0):
    return datetime(2026, 10, 25, hour, minute, tzinfo=timezone.utc)


H = "a" * 64


def game(sport="NBA"):
    return Game(sport, sport.lower() + ":synthetic-01",
                "team:home", "team:away", t(20))


def stamp(captured=None, published=None, rights="unverified"):
    return SourceStamp("synthetic", "https://example.org/synthetic",
                       published or t(11), captured or t(12), H, rights)


def board(sport="NBA", market="points"):
    gm = game(sport)
    roster = (RosterAthlete("athlete:one", "team:home", "active", stamp()),
              RosterAthlete("athlete:two", "team:away", "unknown", stamp()))
    markets = (market,)
    screens = (
        PropScreen("athlete:one", "team:home", market, "consider", "verified active"),
        PropScreen("athlete:two", "team:away", market, "unresolved", "status unknown"),
    )
    proj = (PropProjection("athlete:one", "team:home", market, "21.5",
                           t(13), t(12), H),)
    quote = (PropQuote("quote:one", gm.event_id, "athlete:one", "team:home",
                       market, "full_game", "over", "20.5", -110,
                       "synthetic-book", stamp(t(14), t(13))),)
    return gm, roster, markets, screens, proj, quote, t(15)


def audit(case):
    return audit_prop_board(*case)


class PropBoardTests(unittest.TestCase):
    def test_valid_fixture_reconciles_full_roster(self):
        v = audit(board())
        self.assertTrue(v.structurally_valid, v.reasons)
        self.assertTrue(v.complete_roster_screen)
        self.assertEqual((v.expected_screen_rows, v.screened_rows,
                          v.considered, v.excluded, v.unresolved), (2, 2, 1, 0, 1))
        self.assertEqual(v.missing_quote_candidates, ())
        self.assertFalse(v.eligible_for_play)
        self.assertFalse(v.eligible_for_scoring)
        self.assertFalse(v.licensed_for_commercial_use)

    def test_delta_is_stat_units_never_a_probability(self):
        result = audit(board()).compared_quotes[0]
        self.assertEqual(result.model_minus_line, "1.0")
        self.assertEqual(result.independent_projection, "21.5")
        self.assertFalse(result.probability_estimated)
        self.assertFalse(result.play_authorized)

    def test_independent_projection_is_not_market_anchored(self):
        case = list(board())
        case[5] = (replace(case[5][0], line="25.5"),)
        v = audit(case)
        self.assertEqual(v.compared_quotes[0].independent_projection, "21.5")
        self.assertEqual(v.compared_quotes[0].model_minus_line, "-4.0")

    def test_other_sports_player_prop_taxonomies(self):
        options = {"NBA": "points", "NFL": "receiving_yards",
                   "MLB": "pitcher_strikeouts", "NHL": "shots_on_goal",
                   "SOCCER": "shots_on_target"}
        for sport, market in options.items():
            with self.subTest(sport=sport):
                self.assertTrue(audit(board(sport, market)).structurally_valid)

    def test_no_bet_board_with_zero_qualifying_candidates(self):
        case = list(board())
        case[3] = (replace(case[3][0], decision="exclude", reason="no opportunity"),
                   case[3][1])
        case[4], case[5] = (), ()
        result = audit(case)
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertTrue(result.complete_roster_screen)
        self.assertEqual(result.considered, 0)
        self.assertEqual(result.compared_quotes, ())

    def test_multiple_markets_full_player_coverage(self):
        case = list(board())
        case[2] = ("points", "rebounds")
        case[3] = case[3] + (
            PropScreen("athlete:one", "team:home", "rebounds", "exclude", "no role"),
            PropScreen("athlete:two", "team:away", "rebounds", "unresolved", "unknown"),
        )
        result = audit(case)
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertEqual((result.expected_screen_rows, result.excluded), (4, 1))

    def test_missing_bench_player_row_is_reported(self):
        case = list(board())
        case[3] = (case[3][0],)
        result = audit(case)
        self.assertFalse(result.complete_roster_screen)
        self.assertIn("full_roster_market_screen_incomplete", result.reasons)

    def test_missing_projection_fails_for_considered_player(self):
        case = list(board())
        case[4] = ()
        self.assertIn("considered_player_projection_missing", audit(case).reasons)

    def test_market_quote_optional_but_missing_exposed(self):
        case = list(board())
        case[5] = ()
        result = audit(case)
        self.assertTrue(result.structurally_valid, result.reasons)
        self.assertEqual(result.missing_quote_candidates, ("athlete:one:points",))
        self.assertEqual(result.compared_quotes, ())

    def test_explicit_missing_lines_never_fabricated(self):
        case = list(board())
        case[5] = ()
        self.assertEqual(len(audit(case).compared_quotes), 0)

    def test_roster_unknown_cannot_be_considered(self):
        case = list(board())
        case[3] = (case[3][0], replace(case[3][1], decision="consider",
                                     reason="big star"))
        self.assertIn("ineligible_or_uncertain_considered:athlete:two",
                      audit(case).reasons)

    def test_roster_questionable_must_remain_unresolved(self):
        case = list(board())
        case[1] = (case[1][0], replace(case[1][1], availability="questionable"))
        case[3] = (case[3][0], replace(case[3][1], decision="exclude",
                                     reason="questionable"))
        self.assertIn("uncertain_availability_not_unresolved:athlete:two",
                      audit(case).reasons)

    def test_out_player_never_considered(self):
        case = list(board())
        case[1] = (replace(case[1][0], availability="out"), case[1][1])
        self.assertIn("ineligible_or_uncertain_considered:athlete:one",
                      audit(case).reasons)

    def test_out_player_can_be_excluded(self):
        case = list(board())
        case[1] = (replace(case[1][0], availability="out"), case[1][1])
        case[3] = (replace(case[3][0], decision="exclude", reason="inactive"),
                   case[3][1])
        case[4], case[5] = (), ()
        self.assertTrue(audit(case).structurally_valid)

    def test_unknown_market_rejected(self):
        case = list(board())
        case[2] = ("quarterback_rush_yards",)
        with self.assertRaisesRegex(ValueError, "supported"):
            audit(case)

    def test_cross_sport_market_rejected(self):
        case = list(board("NFL", "receiving_yards"))
        case[2] = ("points",)
        with self.assertRaises(ValueError):
            audit(case)

    def test_duplicate_market_request_rejected(self):
        case = list(board())
        case[2] = ("points", "points")
        with self.assertRaises(ValueError):
            audit(case)

    def test_no_market_universe_rejected(self):
        case = list(board())
        case[2] = ()
        with self.assertRaises(ValueError):
            audit(case)

    def test_duplicate_roster_identity_flagged(self):
        case = list(board())
        case[1] = case[1] + (replace(case[1][0], team_id="team:away"),)
        self.assertIn("duplicate_roster_athlete:athlete:one", audit(case).reasons)

    def test_full_roster_requires_both_teams(self):
        case = list(board())
        case[1] = (case[1][0],)
        case[3] = (case[3][0],)
        self.assertIn("both_teams_roster_required", audit(case).reasons)

    def test_roster_other_team_rejected(self):
        case = list(board())
        case[1] = (replace(case[1][0], team_id="team:other"), case[1][1])
        self.assertIn("roster_team_not_in_event:athlete:one", audit(case).reasons)

    def test_duplicate_player_market_screen_rejected(self):
        case = list(board())
        case[3] = case[3] + (case[3][0],)
        self.assertIn("duplicate_player_market_screen:athlete:one:points",
                      audit(case).reasons)

    def test_screen_team_mismatch_rejected(self):
        case = list(board())
        case[3] = (replace(case[3][0], team_id="team:away"), case[3][1])
        self.assertIn("screen_team_mismatch:athlete:one", audit(case).reasons)

    def test_unexpected_market_screen_rejected(self):
        case = list(board())
        case[3] = case[3] + (
            PropScreen("athlete:one", "team:home", "rebounds", "exclude", "not in board"),)
        self.assertIn("unexpected_player_market_screen:athlete:one:rebounds",
                      audit(case).reasons)

    def test_unexpected_player_screen_rejected(self):
        case = list(board())
        case[3] = case[3] + (
            PropScreen("athlete:other", "team:home", "points", "consider", "unknown"),)
        self.assertIn("unexpected_player_market_screen:athlete:other:points",
                      audit(case).reasons)

    def test_no_secret_bearing_source_urls(self):
        for url in ("http://example.org/data", "https://user:pass@example.org",
                    "https://example.org/data?api_key=secret",
                    "https://example.org/data#fragment"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    replace(stamp(), url=url)

    def test_naive_source_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            replace(stamp(), captured_at=datetime(2026, 10, 25, 15))

    def test_published_after_capture_rejected(self):
        with self.assertRaises(ValueError):
            replace(stamp(), published_at=t(16))

    def test_source_rights_not_assumed(self):
        case = list(board())
        case[1] = (replace(case[1][0], source=stamp(rights="licensed")),
                   case[1][1])
        self.assertFalse(audit(case).licensed_for_commercial_use)

    def test_invalid_rights_type_rejected(self):
        with self.assertRaises(ValueError):
            replace(stamp(), rights_status=["licensed"])

    def test_late_roster_snapshot_rejected(self):
        case = list(board())
        case[1] = (replace(case[1][0], source=stamp(t(18))), case[1][1])
        self.assertIn("roster:athlete:one_source_not_known_pregame",
                      audit(case).reasons)

    def test_late_quote_cannot_enter_pregame_comparison(self):
        case = list(board())
        case[5] = (replace(case[5][0], source=stamp(t(17), t(13))),)
        result = audit(case)
        self.assertIn("quote:quote:one_source_not_known_pregame", result.reasons)
        self.assertEqual(result.compared_quotes, ())

    def test_quote_after_tip_cannot_be_used(self):
        case = list(board())
        case[5] = (replace(case[5][0], source=stamp(t(21), t(19))),)
        self.assertEqual(audit(case).compared_quotes, ())

    def test_post_tip_projection_rejected(self):
        case = list(board())
        case[4] = (replace(case[4][0], frozen_at=t(21)),)
        self.assertIn("projection_not_frozen_pregame:athlete:one",
                      audit(case).reasons)

    def test_future_model_inputs_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            replace(board()[4][0], inputs_as_of=t(17))

    def test_model_projection_must_be_independently_frozen_before_quote(self):
        case = list(board())
        case[4] = (replace(case[4][0], frozen_at=t(14, 30)),)
        self.assertIn("market_quoted_before_independent_projection:quote:one",
                      audit(case).reasons)
        self.assertEqual(audit(case).compared_quotes, ())

    def test_projection_team_mismatch_rejected(self):
        case = list(board())
        case[4] = (replace(case[4][0], team_id="team:away"),)
        self.assertIn("projection_team_mismatch:athlete:one", audit(case).reasons)

    def test_duplicate_projection_rejected(self):
        case = list(board())
        case[4] = case[4] + (case[4][0],)
        self.assertIn("duplicate_projection:athlete:one:points", audit(case).reasons)

    def test_invalid_or_fabricated_float_line_rejected(self):
        q = board()[5][0]
        for line in ("NaN", "Infinity", "-1", "1e3", "01", "0.1234", 20.5, True):
            with self.subTest(line=str(line)):
                with self.assertRaises(ValueError):
                    replace(q, line=line)

    def test_exact_line_fraction_allowed(self):
        case = list(board())
        case[5] = (replace(case[5][0], line="20.125"),)
        self.assertTrue(audit(case).structurally_valid)

    def test_quote_side_period_and_price_must_be_explicit(self):
        q = board()[5][0]
        for field, value in [("side", "both"), ("period", "first_half"),
                             ("american_odds", -99), ("american_odds", True),
                             ("sportsbook", "")]:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    replace(q, **{field: value})

    def test_both_over_and_under_independently_recordable(self):
        case = list(board())
        q = case[5][0]
        case[5] = (q, replace(q, quote_id="quote:two", side="under"))
        v = audit(case)
        self.assertTrue(v.structurally_valid, v.reasons)
        self.assertEqual({x.side for x in v.compared_quotes}, {"under", "over"})

    def test_duplicate_side_from_same_book_rejected(self):
        case = list(board())
        q = case[5][0]
        case[5] = (q, replace(q, quote_id="quote:two"))
        self.assertIn("duplicate_book_side_market_quote:quote:two", audit(case).reasons)

    def test_different_sportsbooks_may_disagree_on_line(self):
        case = list(board())
        q = case[5][0]
        case[5] = (q, replace(q, quote_id="quote:two", sportsbook="other",
                               line="25.5"))
        v = audit(case)
        self.assertTrue(v.structurally_valid)
        self.assertEqual(len(v.compared_quotes), 2)

    def test_quote_event_mismatch_rejected(self):
        case = list(board())
        case[5] = (replace(case[5][0], event_id="nba:other"),)
        self.assertIn("quote_event_or_market_mismatch:quote:one", audit(case).reasons)

    def test_quote_player_team_mismatch_rejected(self):
        case = list(board())
        case[5] = (replace(case[5][0], team_id="team:away"),)
        self.assertIn("quote_player_team_mismatch:quote:one", audit(case).reasons)

    def test_out_or_excluded_player_quote_does_not_create_recommendation(self):
        case = list(board())
        case[3] = (replace(case[3][0], decision="exclude", reason="role too small"),
                   case[3][1])
        case[4] = ()
        self.assertEqual(audit(case).compared_quotes, ())

    def test_missing_athlete_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "stable"):
            replace(board()[1][0], athlete_id="John Smith")

    def test_bad_sport_event_prefix_rejected(self):
        with self.assertRaises(ValueError):
            Game("NBA", "nfl:game", "team:one", "team:two", t(20))

    def test_evaluation_cutoff_after_start_rejected(self):
        case = list(board())
        case[-1] = t(20)
        with self.assertRaises(ValueError):
            audit(case)

    def test_immutable_evidence_dataclasses(self):
        with self.assertRaises(FrozenInstanceError):
            board()[5][0].line = "25.5"

    def test_unrecognized_non_roster_projection_rejected(self):
        case = list(board())
        case[4] = case[4] + (
            replace(case[4][0], athlete_id="athlete:other"),)
        self.assertIn("projection_not_screened_consider:athlete:other",
                      audit(case).reasons)

    def test_market_changes_do_not_change_projection(self):
        original = board()[4][0]
        self.assertEqual(original.predicted_stat, "21.5")
        self.assertNotIn("probability_estimated", BoardAudit.__dataclass_fields__)


if __name__ == "__main__":
    unittest.main()
