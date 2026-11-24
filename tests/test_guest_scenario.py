import copy
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from extract_preferences import FIELDS, extract_card
from guest_scenario import build_scenario, local_bedtime
from guest_service import prepare_guest
from make_cards import build_cards

ROOT = Path(__file__).resolve().parents[1]


class GuestScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads((ROOT / "examples/guest_input.json").read_text(encoding="utf-8"))[
            "dataset"
        ]
        cls.raw = json.loads(
            (ROOT / "examples/guest_model_response.json").read_text(encoding="utf-8")
        )
        cls.result = prepare_guest(
            cls.dataset, "stay_m7k2", model_call=lambda payload: (copy.deepcopy(cls.raw), {})
        )

    def test_history_conflict_uses_saved_model_result(self):
        card = self.result["preferences"]
        self.assertTrue(any("обожаю морской прибой" in e["text"].lower() for e in card["evidence"]))
        self.assertTrue(any("нужна тишина" in e["text"].lower() for e in card["evidence"]))
        self.assertEqual(card["fields"]["favorite_track_ids"]["value"], [])
        self.assertEqual(card["fields"]["temperature"]["value"], "cool")
        self.assertTrue(card["fields"]["gentle_alarm"]["value"])

    def test_missing_and_single_request_do_not_become_profile(self):
        dataset = copy.deepcopy(self.dataset)
        dataset["events"], dataset["chat_history"] = [], []
        dataset["requests"] = [
            {
                "user_id": dataset["users"][0]["user_id"],
                "utterances": [{"text": "Поставь 26 градусов прямо сейчас"}],
            }
        ]
        card = build_cards(dataset)[0]
        self.assertEqual(json.loads(card["evidence_json"]), [])
        unknown = {field: {"value": None, "source_ids": [], "conflict": False} for field in FIELDS}
        extracted, _ = extract_card(
            card, dataset["tracks"], dataset["devices"], lambda payload: (unknown, {})
        )
        self.assertIsNone(extracted["fields"]["temperature"]["value"])
        scenario = build_scenario(extracted, dataset["devices"], dataset["tracks"])
        self.assertTrue(any("стандарт R3" in text for text in scenario["assumptions"]))
        self.assertTrue(any("Любимые звуки неизвестны" in text for text in scenario["assumptions"]))
        self.assertEqual(extracted["fields"]["temperature"]["source"], "unknown")

    def test_past_one_off_remains_evidence_but_not_a_preference(self):
        dataset = copy.deepcopy(self.dataset)
        dataset["events"] = []
        dataset["chat_history"] = [
            {
                "user_id": dataset["users"][0]["user_id"],
                "message_id": "one_off",
                "role": "user",
                "at": "2026-11-11T18:00:00+03:00",
                "text": "Сегодня разово поставь 25 градусов, я простудилась.",
            }
        ]
        card = build_cards(dataset)[0]
        unknown = {field: {"value": None, "source_ids": [], "conflict": False} for field in FIELDS}

        def fake_model(payload):
            self.assertEqual(payload["evidence"][0]["id"], "one_off")
            return unknown, {}

        result, _ = extract_card(card, dataset["tracks"], dataset["devices"], fake_model)
        self.assertIsNone(result["fields"]["temperature"]["value"])
        self.assertEqual(result["fields"]["temperature"]["source"], "unknown")

    def test_conflict_unknown_not_treated_as_a_fact(self):
        card = build_cards(self.dataset)[0]
        raw = {field: {"value": None, "source_ids": [], "conflict": False} for field in FIELDS}
        raw["temperature"] = {"value": "warm", "source_ids": ["ev_e1b6a1db89"], "conflict": True}
        result, _ = extract_card(
            card, self.dataset["tracks"], self.dataset["devices"], lambda payload: (raw, {})
        )
        self.assertIsNone(result["fields"]["temperature"]["value"])
        self.assertEqual(result["fields"]["temperature"]["source"], "unknown")

    def test_sample_rules_r1_to_r8(self):
        result = self.result["scenario"]
        steps = result["scenario"]
        by_device = {}
        for step in steps:
            by_device.setdefault(step["device_id"], []).append(step)
        at = lambda step: datetime.fromisoformat(step["at"])
        at_str = lambda value: datetime.fromisoformat(value)
        bedtime, wake = at_str(result["bedtime_at"]), at_str("2026-11-13T07:30:00+03:00")
        self.assertEqual(result["timezone_difference_hours"], 0)  # R8
        self.assertEqual(bedtime.isoformat(), "2026-11-12T23:20:00+03:00")
        light = by_device["light"]
        evening = next(s for s in light if at(s) == bedtime - timedelta(hours=1))
        self.assertTrue(10 <= evening["values"]["brightness"] <= 30)  # R1
        self.assertLessEqual(evening["values"]["color_temperature_k"], 2700)
        self.assertEqual(
            next(s for s in light if at(s) == bedtime)["values"]["brightness"], 0
        )  # R2
        self.assertLessEqual(by_device["curtains"][0]["values"]["position"], 10)
        self.assertTrue(17 <= by_device["climate"][0]["values"]["temperature_c"] <= 18)  # R3
        self.assertEqual(
            next(s for s in by_device["sound"] if at(s) == bedtime)["values"]["volume"], 0
        )  # R4
        alarm = by_device["alarm"][0]["values"]
        self.assertEqual(at_str(alarm["at"]), wake)  # R5
        self.assertEqual(alarm["mode"], "light")
        sunrise = [
            s
            for s in light
            if wake - timedelta(minutes=30) <= at(s) <= wake - timedelta(minutes=15)
        ]
        self.assertEqual([s["values"]["brightness"] for s in sunrise], [10, 30, 50])  # R6
        dnd = by_device["dnd"]
        self.assertTrue(any(at(s) == bedtime and s["values"]["enabled"] for s in dnd))  # R7
        self.assertFalse(any(bedtime < at(s) < wake and not s["values"]["enabled"] for s in dnd))
        self.assertTrue(all(at_str("2026-11-12T21:50:00+03:00") <= at(s) <= wake for s in steps))

    def test_timezone_shift_from_dev_examples(self):
        west = {
            "weekday_bedtime": "00:30",
            "home_timezone": "Asia/Novosibirsk",
            "hotel_timezone": "Europe/Moscow",
            "target_wake_at": "2026-11-13T09:00:00+03:00",
        }
        east = {
            "weekday_bedtime": "01:30",
            "home_timezone": "Europe/Kaliningrad",
            "hotel_timezone": "Asia/Yekaterinburg",
            "target_wake_at": "2026-11-14T10:30:00+05:00",
        }
        self.assertEqual(local_bedtime(west)[0].isoformat(), "2026-11-12T21:30:00+03:00")
        self.assertEqual(local_bedtime(east)[0].isoformat(), "2026-11-14T03:30:00+05:00")

    def test_infeasible_stay_and_bad_track_are_rejected(self):
        card = copy.deepcopy(self.result["preferences"])
        card["context"]["target_wake_at"] = "2026-11-12T23:25:00+03:00"
        with self.assertRaises(ValueError):
            build_scenario(card, self.dataset["devices"], self.dataset["tracks"])
        card = copy.deepcopy(self.result["preferences"])
        card["fields"]["favorite_track_ids"]["value"] = ["unknown"]
        with self.assertRaises(ValueError):
            build_scenario(card, self.dataset["devices"], self.dataset["tracks"])


if __name__ == "__main__":
    unittest.main()
