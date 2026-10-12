"""Behavior of fictional experiments, ordered cases, and local lore migrations."""

import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import Mock

from lrp.bureau import Bureau, fly_rank
from lrp.content import INCIDENTS
from lrp.state import Store


class BureauTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = Store(Path(directory.name) / "state.json")
        self.bureau = Bureau(self.store.data, random.Random(7))

    def test_audit_consumes_charity_once_and_bounds_debt(self):
        data = self.store.data
        data["brofists"] = 3
        balance = data["aura"]
        self.bureau.action("audit")
        self.assertEqual(data["aura"], balance - 46)
        self.assertEqual(data["brofists"], 0)
        self.bureau.action("audit")
        self.assertEqual(data["aura"], balance - 46 - 67)
        data["aura"] = -999990
        self.bureau.action("audit")
        self.assertEqual(data["aura"], -999999)
        self.assertEqual(data["audits"], 3)

    def test_swarm_escalates_and_banana_ranks_roundtrip(self):
        for _ in range(4):
            self.bureau.action("swarm")
        self.assertEqual(self.store.data["agents"], 128)
        self.assertIn("Escalation contact: the fly", " ".join(self.bureau.report))
        for _ in range(4):
            self.bureau.action("swarm")
        self.assertIn("back to you", " ".join(self.bureau.report))
        for bananas, rank in ((0, "UNQUALIFIED INTERN"), (2, "NEURAL OPERATOR"),
                              (5, "INCIDENT COMMANDER"), (9, "INTERIM CTO")):
            self.store.data["bananas"] = bananas
            self.assertTrue(self.store.save())
            loaded = Store(self.store.path)
            self.assertEqual(fly_rank(loaded.data["bananas"]), rank)
        self.assertEqual(loaded.data["agents"], 192)

    def test_rare_collider_and_storage_results_and_shutdown(self):
        self.bureau.rng = Mock()
        self.bureau.rng.randrange.return_value = 0
        events = self.bureau.action("lockin")
        self.assertIn("ACTUAL PRODUCTIVITY", " ".join(text for _, text in events))
        self.bureau.action("breach")
        self.assertTrue(self.bureau.storage_open)
        self.assertIn("first attempt", " ".join(self.bureau.report))
        self.bureau.action("nonchalance")
        self.bureau.action("incident")
        self.assertTrue(self.bureau.nonchalant)
        self.assertTrue(self.bureau.case_active)
        self.bureau.shutdown()
        self.assertFalse(self.bureau.storage_open)
        self.assertFalse(self.bureau.nonchalant)
        self.assertFalse(self.bureau.case_active)
        self.assertEqual(self.bureau.advance(1), [])

    def test_case_beats_stay_ordered_and_explicit_next_works_without_clock(self):
        events = self.bureau.action("incident")
        self.assertEqual(len(events), 1)
        self.assertEqual(self.bureau.advance(3.19), [])
        events += self.bureau.advance(.02)
        self.assertEqual(len(events), 2)
        while self.bureau.case_active:
            before = self.bureau.time
            events += self.bureau.action("incident", "next")
            self.assertEqual(self.bureau.time, before)
        expected = [line for _, line in INCIDENTS[0][1]]
        self.assertEqual(self.bureau.case_lines, expected)
        self.assertEqual(len(events), len(expected))
        self.assertTrue(all("CASE 0001 / QUICK QUESTION" in text for _, text in events))
        self.assertEqual(self.bureau.advance(17.9), [])
        next_case = self.bureau.advance(.2)
        self.assertEqual(len(next_case), 1)
        self.assertIn("SWARM STANDUP", next_case[0][1])
        self.assertEqual(self.store.data["cases"], 2)

    def test_nonchalance_expires_without_overwriting_another_experiment(self):
        self.bureau.action("nonchalance")
        self.assertEqual(self.bureau.advance(11.9), [])
        self.assertTrue(self.bureau.nonchalant)
        events = self.bureau.advance(.2)
        self.assertFalse(self.bureau.nonchalant)
        self.assertIn("nobody noticed", events[0][1])
        self.bureau.action("nonchalance")
        self.bureau.action("lockin")
        receipt = self.bureau.report
        self.bureau.advance(12.1)
        self.assertEqual(self.bureau.mode, "lockin")
        self.assertEqual(self.bureau.report, receipt)

    def test_existing_state_migrates_and_invalid_lore_is_preserved(self):
        original = {"callsign": "NIGHTSHIFT", "aura": 400, "sessions": 3,
                    "notes": [{"time": "today", "text": "keep this lore"}], "calm": True}
        self.store.path.write_text(json.dumps(original))
        loaded = Store(self.store.path)
        self.assertFalse(loaded.blocked)
        self.assertEqual(loaded.data["agents"], 64)
        self.assertEqual(loaded.data["bananas"], 0)
        self.assertTrue(loaded.save())
        for key, value in original.items():
            self.assertEqual(Store(self.store.path).data[key], value)
        for field in ("agents", "bananas", "audits", "brofists", "cases"):
            corrupt = json.dumps(dict(original, **{field: "banana"}))
            self.store.path.write_text(corrupt)
            loaded = Store(self.store.path)
            self.assertTrue(loaded.blocked)
            self.assertFalse(loaded.save())
            self.assertEqual(self.store.path.read_text(), corrupt)


if __name__ == "__main__":
    unittest.main()
