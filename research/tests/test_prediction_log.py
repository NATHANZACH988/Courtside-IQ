"""Deterministic unit tests for research/gameflow/prediction_log.py."""
import importlib.util
import os
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


if __name__ == "__main__":
    unittest.main()
