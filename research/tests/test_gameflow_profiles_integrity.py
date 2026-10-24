"""Regression tests for final-only, deduplicated NBA profile evidence."""
import json
import tempfile
import unittest
from pathlib import Path
from research.gameflow.scoring_profiles import aggregate, mins


def player(name, team, minutes="25:30", pts=12):
    return {"name": name, "team": team, "starter": True, "min": minutes,
            "pts": pts, "fga": 10, "pf": 3}


def game(event, status="Final", players=None):
    return {"league": "nba", "event": event, "status": status,
            "players": players if players is not None else [player("Same Name", "AAA")]}


class ProfileIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.notes = self.root / "notes.jsonl"

    def write_game(self, filename, data):
        path = self.root / filename
        path.write_text(json.dumps(data))
        return path

    def write_notes(self, *entries):
        self.notes.write_text("\n".join(json.dumps(e) for e in entries))

    def test_minutes_include_seconds(self):
        self.assertAlmostEqual(mins("25:30"), 25.5)
        self.assertEqual(mins("DNP"), 0)

    def test_only_distinct_final_games_enter_profiles(self):
        paths = [
            self.write_game("a.json", game("101")),
            self.write_game("b.json", game("101")),
            self.write_game("c.json", game("102", status="In Progress")),
        ]
        board, diag = aggregate(paths, self.notes)
        self.assertEqual(diag["games_used"], 1)
        self.assertEqual(diag["games_skipped_duplicate"], 1)
        self.assertEqual(diag["games_skipped_nonfinal"], 1)
        self.assertEqual(board["AAA|Same Name"]["games"], 1)

    def test_notes_require_final_event_and_known_player(self):
        path = self.write_game("a.json", game("101"))
        self.write_notes(
            {"league": "nba", "event": "102", "notes": [
                {"type": "foul_trouble_cap", "team": "AAA", "player": "Same Name"}]},
            {"league": "nba", "event": "101", "notes": [
                {"type": "foul_trouble_cap", "team": "AAA", "player": "Ghost"}]},
            {"league": "nba", "event": "101", "notes": [
                {"type": "foul_trouble_cap", "team": "AAA", "player": "Same Name"}]},
            {"league": "nba", "event": "101", "notes": [
                {"type": "foul_trouble_cap", "team": "AAA", "player": "Same Name"}]},
        )
        board, diag = aggregate([path], self.notes)
        self.assertEqual(board["AAA|Same Name"]["capped_events"], 1)
        self.assertNotIn("AAA|Ghost", board)
        self.assertEqual(diag["notes_skipped_unverified"], 1)

    def test_retracted_surges_never_enter_profiles(self):
        path = self.write_game("a.json", game("401909840", players=[
            player("Bench", "AAA"), player("Starter", "AAA")]))
        self.write_notes({"league": "nba", "event": "401909840", "notes": [
            {"type": "bench_usage_surge", "team": "AAA",
             "bench_player": "Bench", "slot_starter": "Starter"}]})
        board, diag = aggregate([path], self.notes)
        self.assertEqual(board["AAA|Bench"]["cannibal_events"], 0)
        self.assertEqual(board["AAA|Starter"]["victim_events"], 0)
        self.assertEqual(diag["surge_notes_skipped_retracted"], 1)

    def test_note_must_match_player_in_same_event(self):
        a = self.write_game("a.json", game("101", players=[
            player("Only In A", "AAA"), player("Duplicate", "AAA"),
            player("Duplicate", "AAA")]))
        b = self.write_game("b.json", game("102", players=[
            player("Only In B", "AAA")]))
        self.write_notes({"league": "nba", "event": "102", "notes": [
            {"type": "foul_trouble_cap", "team": "AAA", "player": "Only In A"}]})
        board, _ = aggregate([a, b], self.notes)
        self.assertEqual(board["AAA|Only In A"]["capped_events"], 0)
        self.assertEqual(board["AAA|Duplicate"]["games"], 1)

    def test_same_named_players_are_team_separated(self):
        path = self.write_game("a.json", game("101", players=[
            player("Same Name", "AAA", pts=10),
            player("Same Name", "BBB", pts=20)]))
        board, _ = aggregate([path], self.notes)
        self.assertEqual(board["AAA|Same Name"]["pts_pg"], 10)
        self.assertEqual(board["BBB|Same Name"]["pts_pg"], 20)


if __name__ == "__main__":
    unittest.main()
