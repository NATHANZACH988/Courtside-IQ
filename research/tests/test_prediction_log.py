"""Deterministic unit tests for research/gameflow/prediction_log.py."""
import importlib.util
import os
import json
import tempfile
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
import unittest

HERE = os.path.dirname(__file__)
SPEC = importlib.util.spec_from_file_location(
    "prediction_log", os.path.join(HERE, "..", "gameflow", "prediction_log.py"))
PL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PL)


def entry(mech, **kw):
    base = {"player": "Test Player", "mechanism": mech,
            "banked_pts_pg": 12.0, "banked_min_pg": 28.0}
    base.update(kw)
    return base


def final(players, notes=None):
    return {"status": "Final", "players": players, "notes": notes or [],
            "segments": []}


def player(name, **kw):
    base = {"name": name, "team": "TST", "pos": "G", "starter": True,
            "min": "28", "pts": 10, "fga": 8, "fgm": 4, "pf": 2, "reb": 3}
    base.update(kw)
    return base


class TestPMin(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(PL.pmin("33"), 33.0)
        self.assertEqual(PL.pmin("12:30"), 12.5)
        self.assertEqual(PL.pmin("--"), 0.0)
        self.assertEqual(PL.pmin(None), 0.0)
        self.assertEqual(PL.pmin(7), 7.0)


class TestGrading(unittest.TestCase):
    def test_foul_cap_hit_on_five_fouls(self):
        fin = final([player("Test Player", pf=5, min="19")])
        grade, _ = PL.grade_entry(entry("FOUL_CAP"), fin)
        self.assertEqual(grade, "HIT")

    def test_foul_cap_miss_when_clean(self):
        fin = final([player("Test Player", pf=1, min="30", pts=14)])
        grade, _ = PL.grade_entry(entry("FOUL_CAP"), fin)
        self.assertEqual(grade, "MISS")

    def test_no_decision_under_ten_minutes(self):
        fin = final([player("Test Player", min="6", pts=0)])
        grade, _ = PL.grade_entry(entry("STEADY"), fin)
        self.assertEqual(grade, "NO_DECISION")

    def test_steady_hit_and_miss(self):
        hit, _ = PL.grade_entry(entry("STEADY"),
                                final([player("Test Player", pts=10, min="30")]))
        miss, _ = PL.grade_entry(entry("STEADY"),
                                 final([player("Test Player", pts=4, min="30")]))
        self.assertEqual(hit, "HIT")
        self.assertEqual(miss, "MISS")


class TestCannibalShape(unittest.TestCase):
    def test_shape_detected(self):
        players = [
            player("Starter Guard", starter=True, min="24", pts=8, fga=6),
            player("Bench Spark", starter=False, min="20", pts=10, fga=12),
        ]
        self.assertTrue(PL.cannibal_shape(players, "Bench Spark"))
        self.assertFalse(PL.cannibal_shape(players, "Starter Guard"))


class TestBuildGuards(unittest.TestCase):
    def test_past_date_refused(self):
        class Args:
            date = "2000-01-01"
        with self.assertRaises(SystemExit):
            PL.cmd_build(Args())



class TestImmutableResearchArtifacts(unittest.TestCase):
    def frozen(self, *, built="2026-10-24T12:43:09Z",
               logged="2026-10-24T12:43:09Z",
               tip="2026-10-24T22:00:00Z"):
        return {"frozen": True, "built_at_utc": built, "games": 1,
                "predictions": [{
                    "event_id": "synthetic-game-01",
                    "tip_utc": tip, "logged_at_utc": logged,
                    "player": "Test Player", "mechanism": "STEADY",
                    "banked_pts_pg": 12, "banked_min_pg": 28,
                    "grade": None,
                }]}

    def test_pretip_rejects_event_at_or_before_capture(self):
        now = datetime(2026, 10, 25, 15, tzinfo=timezone.utc)
        for tip in ("2026-10-25T15:00:00Z", "2026-10-25T14:59:59Z"):
            with self.subTest(tip=tip), self.assertRaisesRegex(SystemExit, "post-tip"):
                PL._require_pretip([{"event_id": "one", "tip_utc": tip}], now)

    def test_pretip_accepts_future_events(self):
        now = datetime(2026, 10, 25, 15, tzinfo=timezone.utc)
        PL._require_pretip([{"event_id": "one",
                             "tip_utc": "2026-10-25T15:00:01Z"}], now)

    def test_pretip_fails_closed_on_empty_and_bad_schedules(self):
        now = datetime(2026, 10, 25, 15, tzinfo=timezone.utc)
        for slate in ([], [{"event_id": "one", "tip_utc": "bad"}],
                      [{"event_id": "one", "tip_utc": "2026-10-25T17:00:00"}],
                      [{"tip_utc": "2026-10-25T17:00:00Z"}]):
            with self.subTest(slate=slate), self.assertRaises(SystemExit):
                PL._require_pretip(slate, now)

    def test_date_path_validation_rejects_traversal_and_impossible_dates(self):
        for date in ("../../secrets", "2026-02-30", "2026-1-1", "", None):
            with self.subTest(date=date), self.assertRaises(SystemExit):
                PL._valid_date(date)
        PL._valid_date("2028-02-29")

    def test_freeze_integrity_rejects_hindsight_or_existing_grades(self):
        PL._verify_original_freeze(self.frozen())
        for mutated in (
            self.frozen(built="2026-10-24T23:00:00Z"),
            self.frozen(logged="2026-10-24T23:00:00Z"),
            self.frozen(logged="2026-10-24T12:50:00Z"),
            self.frozen(tip="2026-10-24T22:00:00"),
            {**self.frozen(), "frozen": False},
        ):
            with self.subTest(mutated=mutated), self.assertRaises(SystemExit):
                PL._verify_original_freeze(mutated)
        graded = self.frozen()
        graded["predictions"][0]["grade"] = "HIT"
        with self.assertRaisesRegex(SystemExit, "already contains a grade"):
            PL._verify_original_freeze(graded)

    def test_build_rejects_same_day_after_tip_without_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            board_path = os.path.join(folder, "board.json")
            with open(board_path, "w", encoding="utf-8") as file:
                json.dump({"finals_used": 1, "players": []}, file)
            local_today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
            tip = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            slate = [{"event_id": "synthetic-game-01", "tip_utc": tip,
                      "home": "AAA", "away": "BBB"}]
            with patch.object(PL, "PRED_DIR", folder), patch.object(PL, "BOARD", board_path), \
                 patch.object(PL, "fetch_board_games", return_value=slate):
                with self.assertRaisesRegex(SystemExit, "post-tip"):
                    PL.cmd_build(SimpleNamespace(date=local_today))
            self.assertFalse(os.path.exists(
                os.path.join(folder, f"predictions-{local_today}.json")))

    def test_build_creates_first_snapshot_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            board_path = os.path.join(folder, "board.json")
            with open(board_path, "w", encoding="utf-8") as file:
                json.dump({"finals_used": 1, "players": []}, file)
            date = "2099-01-01"
            slate = [{"event_id": "synthetic-game-01", "tip_utc": "2099-01-01T22:00:00Z",
                      "home": "AAA", "away": "BBB"}]
            with patch.object(PL, "PRED_DIR", folder), patch.object(PL, "BOARD", board_path), \
                 patch.object(PL, "fetch_board_games", return_value=slate):
                PL.cmd_build(SimpleNamespace(date=date))
                path = os.path.join(folder, "predictions-2099-01-01.json")
                original = open(path, "rb").read()
                manifest = json.loads(original)
                self.assertEqual(manifest["board_sha256"],
                                 hashlib.sha256(open(board_path, "rb").read()).hexdigest())
                self.assertEqual(len(manifest["schedule_projection_sha256"]), 64)
                with self.assertRaisesRegex(SystemExit, "already exists"):
                    PL.cmd_build(SimpleNamespace(date=date))
                self.assertEqual(open(path, "rb").read(), original)

    def test_grades_are_immutable_and_explicit_revisions_link_to_original(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "predictions-2026-10-24.json")
            with open(source, "w", encoding="utf-8") as file:
                json.dump(self.frozen(), file)
            final_data = final([player("Test Player", pts=14)])
            args = SimpleNamespace(date="2026-10-24")
            with patch.object(PL, "PRED_DIR", folder), \
                 patch.object(PL, "load_final", return_value=final_data):
                PL.cmd_grade(args)
                original_path = os.path.join(folder, "predictions-2026-10-24-graded.json")
                original = open(original_path, "rb").read()
                self.assertEqual(json.loads(original)["grade_revision"], "original")
                with self.assertRaisesRegex(SystemExit, "already exists"):
                    PL.cmd_grade(args)
                self.assertEqual(open(original_path, "rb").read(), original)
                revision_args = SimpleNamespace(
                    date="2026-10-24", revision="finals-update", reason="settlement revised")
                PL.cmd_grade(revision_args)
                revised_path = os.path.join(
                    folder, "predictions-2026-10-24-graded-finals-update.json")
                revised = json.load(open(revised_path, encoding="utf-8"))
                self.assertEqual(revised["grade_revision"], "finals-update")
                self.assertEqual(revised["grade_revision_reason"], "settlement revised")
                self.assertEqual(revised["original_grade_sha256"],
                                 hashlib.sha256(original).hexdigest())
                self.assertEqual(open(original_path, "rb").read(), original)
                with self.assertRaisesRegex(SystemExit, "already exists"):
                    PL.cmd_grade(revision_args)

    def test_revision_requires_reason_safe_id_and_prior_grade(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "predictions-2026-10-24.json")
            with open(source, "w", encoding="utf-8") as file:
                json.dump(self.frozen(), file)
            with patch.object(PL, "PRED_DIR", folder):
                for args in (
                    SimpleNamespace(date="2026-10-24", revision="../escape", reason="x"),
                    SimpleNamespace(date="2026-10-24", revision="safe", reason=None),
                    SimpleNamespace(date="2026-10-24", reason="orphan"),
                    SimpleNamespace(date="2026-10-24", revision="safe", reason="x"),
                ):
                    with self.subTest(args=args), self.assertRaises(SystemExit):
                        PL.cmd_grade(args)
            self.assertEqual(sorted(os.listdir(folder)), ["predictions-2026-10-24.json"])

    def test_original_grade_rejects_late_input_before_fetching_results(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "predictions-2026-10-24.json")
            with open(source, "w", encoding="utf-8") as file:
                json.dump(self.frozen(logged="2026-10-24T23:00:00Z"), file)
            with patch.object(PL, "PRED_DIR", folder), \
                 patch.object(PL, "load_final", side_effect=AssertionError("should not fetch")):
                with self.assertRaisesRegex(SystemExit, "not frozen before tip"):
                    PL.cmd_grade(SimpleNamespace(date="2026-10-24"))
            self.assertEqual(sorted(os.listdir(folder)), ["predictions-2026-10-24.json"])


if __name__ == "__main__":
    unittest.main()
