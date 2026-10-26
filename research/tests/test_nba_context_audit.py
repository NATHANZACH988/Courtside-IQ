"""Synthetic-only NBA player-prop evidence gates. No real game or odds."""
from dataclasses import replace
from datetime import datetime, timezone
import unittest

from research.props.prop_board import (
    Game, PropProjection, PropQuote, PropScreen, RosterAthlete, SourceStamp,
)
from research.props.nba_context_audit import (
    BankedGameEvidence, OpponentDefenseEvidence, PlayerRoleEvidence,
    audit_nba_prop_context,
)


def t(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


def stamp(day, hour, minute=0, digest="a" * 64):
    return SourceStamp(
        "synthetic", "https://example.org/evidence",
        t(day, hour), t(day, hour, minute), digest,
    )


def fixture():
    gm = Game("NBA", "nba:current", "team:home", "team:away", t(25, 20))
    roster = (
        RosterAthlete("athlete:one", "team:home", "active", stamp(25, 9)),
        RosterAthlete("athlete:two", "team:away", "unknown", stamp(25, 9)),
    )
    markets = ("points",)
    screens = (
        PropScreen("athlete:one", "team:home", "points", "consider", "active"),
        PropScreen("athlete:two", "team:away", "points", "unresolved", "unknown"),
    )
    projections = (
        PropProjection("athlete:one", "team:home", "points", "22.0",
                       t(25, 13), t(25, 12), "b" * 64),
    )
    quotes = (
        PropQuote("quote:one", gm.event_id, "athlete:one", "team:home",
                  "points", "full_game", "over", "21.5", -110,
                  "synthetic-book", stamp(25, 14)),
    )
    bank = tuple(
        BankedGameEvidence(
            f"nba:bank-{team.replace(':', '-')}-{day}", team, "2026-27",
            t(day, 20), stamp(day, 21),
        )
        for team in ("team:home", "team:away") for day in range(18, 23)
    )
    roles = (
        PlayerRoleEvidence(
            "athlete:one", "team:home", "available", "official_report",
            stamp(25, 10), "30.0", "starter", stamp(25, 11),
        ),
    )
    defense = (
        OpponentDefenseEvidence(
            "team:away", "points", "full_game", 8, "22.4",
            "opponent allowed points per full game, synthetic",
            True, stamp(24, 10, digest="c" * 64),
        ),
    )
    return [gm, roster, markets, screens, projections, quotes, bank,
            roles, defense, t(25, 15)]


def audit(case, **kwargs):
    return audit_nba_prop_context(*case, season=kwargs.get("season", "2026-27"))


class NBAContextAuditTests(unittest.TestCase):
    def test_complete_context_still_not_a_play(self):
        result = audit(fixture())
        self.assertTrue(result.board_structurally_valid, result.reasons)
        self.assertTrue(result.context_complete, result.reasons)
        self.assertTrue(result.five_game_bank_met)
        self.assertEqual(result.team_game_counts,
                         (("team:away", 5), ("team:home", 5)))
        self.assertEqual(result.expected_player_market_rows, 2)
        self.assertEqual(len(result.rows), 2)
        self.assertTrue(result.rows[0].context_complete)
        self.assertFalse(result.rows[1].context_complete)
        self.assertEqual(result.rows[1].decision, "unresolved")
        self.assertFalse(result.play_authorized)
        self.assertFalse(result.scoring_authorized)
        self.assertFalse(result.probability_calibrated)
        self.assertFalse(result.sources_independently_verified)

    def test_bank_below_five_blocks_context(self):
        case = fixture()
        case[6] = tuple(b for b in case[6] if b.event_id != "nba:bank-team-away-22")
        result = audit(case)
        self.assertFalse(result.five_game_bank_met)
        self.assertIn("five_game_bank_not_met", result.rows[0].reasons)

    def test_duplicate_banked_game_does_not_inflate_count(self):
        case = fixture()
        case[6] = case[6] + (case[6][0],)
        result = audit(case)
        self.assertFalse(result.context_complete)
        self.assertEqual(result.team_game_counts, (("team:away", 5), ("team:home", 4)))
        self.assertTrue(any("bank_duplicate_event" in s for s in result.reasons))

    def test_duplicate_banked_game_with_different_receipt_still_rejected(self):
        case = fixture()
        case[6] = case[6] + (replace(case[6][0], source=stamp(23, 9)),)
        self.assertFalse(audit(case).context_complete)

    def test_old_season_bank_does_not_count(self):
        case = fixture()
        case[6] = (replace(case[6][0], season="2025-26"),) + case[6][1:]
        result = audit(case)
        self.assertIn("five_current_season_games_per_team_not_banked", result.reasons)

    def test_current_game_cannot_be_banked(self):
        case = fixture()
        case[6] = (replace(case[6][0], event_id=case[0].event_id),) + case[6][1:]
        self.assertTrue(any("bank_includes_current_event" in s
                            for s in audit(case).reasons))

    def test_future_final_cannot_be_banked(self):
        case = fixture()
        case[6] = (replace(case[6][0], game_final_at=t(26, 20)),) + case[6][1:]
        self.assertTrue(any("bank_game_not_completed_pregame" in s
                            for s in audit(case).reasons))

    def test_bank_source_before_final_not_counted(self):
        case = fixture()
        case[6] = (replace(case[6][0], source=stamp(18, 19)),) + case[6][1:]
        self.assertTrue(any("bank_source_chronology_invalid" in s
                            for s in audit(case).reasons))

    def test_bank_source_after_cutoff_not_counted(self):
        case = fixture()
        case[6] = (replace(case[6][0], source=stamp(25, 16)),) + case[6][1:]
        self.assertFalse(audit(case).five_game_bank_met)

    def test_wrong_team_bank_does_not_count(self):
        case = fixture()
        case[6] = (replace(case[6][0], team_id="team:other"),) + case[6][1:]
        self.assertTrue(any("bank_team_not_in_event" in s
                            for s in audit(case).reasons))

    def test_wrong_season_format_rejected(self):
        with self.assertRaises(ValueError):
            audit(fixture(), season="2026")
        with self.assertRaises(ValueError):
            audit(fixture(), season="2026-29")

    def test_nba_only(self):
        case = fixture()
        case[0] = Game("NFL", "nfl:current", "team:home", "team:away", t(25, 20))
        with self.assertRaisesRegex(ValueError, "NBA"):
            audit(case)

    def test_missing_role_evidence_blocks_considered_player(self):
        case = fixture()
        case[7] = ()
        self.assertIn("missing_or_ambiguous_injury_role_evidence",
                      audit(case).rows[0].reasons)

    def test_duplicate_role_evidence_blocks_considered_player(self):
        case = fixture()
        case[7] = case[7] + (case[7][0],)
        result = audit(case)
        self.assertIn("missing_or_ambiguous_injury_role_evidence", result.rows[0].reasons)
        self.assertIn("duplicate_role_evidence:athlete:one", result.reasons)

    def test_wrong_team_role_rejected(self):
        case = fixture()
        case[7] = (replace(case[7][0], team_id="team:away"),)
        self.assertIn("injury_role_wrong_team", audit(case).rows[0].reasons)

    def test_questionable_is_not_available(self):
        case = fixture()
        case[7] = (replace(case[7][0], injury_status="questionable"),)
        self.assertIn("injury_status_not_confirmed_available", audit(case).rows[0].reasons)

    def test_probable_is_not_assumed_available(self):
        case = fixture()
        case[7] = (replace(case[7][0], injury_status="probable"),)
        self.assertFalse(audit(case).rows[0].context_complete)

    def test_out_player_is_not_available(self):
        case = fixture()
        case[7] = (replace(case[7][0], injury_status="out"),)
        self.assertFalse(audit(case).context_complete)

    def test_unverified_injury_report_cannot_satisfy_official_claim(self):
        case = fixture()
        case[7] = (replace(case[7][0], injury_source_kind="unverified"),)
        self.assertIn("official_injury_report_not_claimed", audit(case).rows[0].reasons)

    def test_role_unknown_blocks_context(self):
        case = fixture()
        case[7] = (replace(case[7][0], role="unknown"),)
        self.assertIn("rotation_role_unresolved", audit(case).rows[0].reasons)

    def test_expected_minutes_missing_blocks_context(self):
        case = fixture()
        case[7] = (replace(case[7][0], expected_minutes=None),)
        self.assertIn("expected_minutes_missing_or_zero", audit(case).rows[0].reasons)

    def test_expected_minutes_zero_blocks_context(self):
        case = fixture()
        case[7] = (replace(case[7][0], expected_minutes="0"),)
        self.assertFalse(audit(case).rows[0].context_complete)

    def test_invalid_expected_minutes_rejected(self):
        case = fixture()
        with self.assertRaises(ValueError):
            replace(case[7][0], expected_minutes="NaN")

    def test_injury_source_after_projection_inputs_requires_refreeze(self):
        case = fixture()
        case[7] = (replace(case[7][0], injury_source=stamp(25, 12, 30)),)
        self.assertIn("injury_or_minutes_updated_after_projection_inputs",
                      audit(case).rows[0].reasons)

    def test_role_source_after_projection_inputs_requires_refreeze(self):
        case = fixture()
        case[7] = (replace(case[7][0], role_source=stamp(25, 13)),)
        self.assertIn("injury_or_minutes_updated_after_projection_inputs",
                      audit(case).rows[0].reasons)

    def test_orphan_role_evidence_reported(self):
        case = fixture()
        case[7] = case[7] + (replace(case[7][0], athlete_id="athlete:other"),)
        self.assertIn("orphan_role_evidence:athlete:other", audit(case).reasons)

    def test_missing_opponent_defense_blocks_context(self):
        case = fixture()
        case[8] = ()
        self.assertIn("missing_or_ambiguous_standalone_opponent_defense",
                      audit(case).rows[0].reasons)

    def test_duplicate_defense_blocks_context(self):
        case = fixture()
        case[8] = case[8] + (case[8][0],)
        self.assertIn("missing_or_ambiguous_standalone_opponent_defense",
                      audit(case).rows[0].reasons)

    def test_wrong_opponent_defense_is_not_substituted(self):
        case = fixture()
        case[8] = (replace(case[8][0], opponent_team_id="team:home"),)
        self.assertFalse(audit(case).context_complete)

    def test_defense_must_be_standalone(self):
        case = fixture()
        case[8] = (replace(case[8][0], independent_of_player_projection=False),)
        self.assertIn("opponent_defense_not_independent", audit(case).rows[0].reasons)

    def test_defense_source_after_projection_inputs_requires_refreeze(self):
        case = fixture()
        case[8] = (replace(case[8][0], source=stamp(25, 13, digest="c" * 64)),)
        self.assertIn("defense_not_independent_pregame_input",
                      audit(case).rows[0].reasons)

    def test_defense_digest_cannot_equal_projection_artifact(self):
        case = fixture()
        case[8] = (replace(case[8][0], source=stamp(24, 10, digest="b" * 64)),)
        self.assertIn("defense_not_independent_pregame_input",
                      audit(case).rows[0].reasons)

    def test_defense_methodology_required(self):
        case = fixture()
        with self.assertRaises(ValueError):
            replace(case[8][0], methodology="")

    def test_defense_games_count_must_be_positive_int(self):
        case = fixture()
        for n in (0, -1, True):
            with self.subTest(n=n):
                with self.assertRaises(ValueError):
                    replace(case[8][0], observed_games=n)

    def test_orphan_defense_reported(self):
        case = fixture()
        case[8] = case[8] + (
            replace(case[8][0], opponent_team_id="team:other"),)
        self.assertTrue(any("orphan_opponent_defense" in s
                            for s in audit(case).reasons))

    def test_every_bench_player_market_remains_in_denominator(self):
        case = fixture()
        case[1] = case[1] + (
            RosterAthlete("athlete:bench", "team:home", "active", stamp(25, 9)),)
        result = audit(case)
        self.assertEqual(result.expected_player_market_rows, 3)
        self.assertEqual(result.rows[-1].decision, "missing")
        self.assertIn("missing_full_roster_market_screen", result.rows[-1].reasons)
        self.assertFalse(result.context_complete)

    def test_every_market_needs_its_own_defense_context(self):
        case = fixture()
        case[2] = ("points", "rebounds")
        case[3] = case[3] + (
            PropScreen("athlete:one", "team:home", "rebounds", "consider", "active"),
            PropScreen("athlete:two", "team:away", "rebounds", "unresolved", "unknown"),
        )
        case[4] = case[4] + (
            replace(case[4][0], market="rebounds", artifact_sha256="d" * 64),)
        result = audit(case)
        self.assertEqual(result.expected_player_market_rows, 4)
        self.assertFalse(result.context_complete)
        self.assertIn("missing_or_ambiguous_standalone_opponent_defense",
                      result.rows[1].reasons)

    def test_full_roster_board_mismatch_is_reported(self):
        case = fixture()
        case[3] = (case[3][0],)
        result = audit(case)
        self.assertFalse(result.board_structurally_valid)
        self.assertFalse(result.context_complete)

    def test_no_candidate_does_not_create_a_play(self):
        case = fixture()
        case[3] = (replace(case[3][0], decision="exclude", reason="not qualified"),
                   case[3][1])
        case[4] = ()
        case[5] = ()
        result = audit(case)
        self.assertTrue(result.board_structurally_valid)
        self.assertFalse(result.play_authorized)
        self.assertEqual(sum(row.decision == "consider" for row in result.rows), 0)

    def test_wrong_input_container_type_rejected(self):
        case = fixture()
        case[6] = list(case[6])
        with self.assertRaises(TypeError):
            audit(case)

    def test_unsupported_injury_status_rejected(self):
        case = fixture()
        with self.assertRaises(ValueError):
            replace(case[7][0], injury_status="confirmed starter")

    def test_defense_coverage_is_not_probability_calibration(self):
        result = audit(fixture())
        self.assertFalse(result.probability_calibrated)
        self.assertFalse(result.scoring_authorized)


if __name__ == "__main__":
    unittest.main()
