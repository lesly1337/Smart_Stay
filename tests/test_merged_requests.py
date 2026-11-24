import json
import unittest
from pathlib import Path
from unittest.mock import patch

from guest_requests import plan_request, simple_intent

DATASET = json.loads(
    (Path(__file__).resolve().parents[1] / "examples/guest_input.json").read_text(encoding="utf-8")
)["dataset"]
AT = "2026-11-12T23:20:00+03:00"


class MergedRequestTests(unittest.TestCase):
    def plans(self, texts, recognized, *, initial=None, preferences=None, history=None):
        state = initial or {
            d["device_id"]: {f["field_id"]: f["default_value"] for f in d["fields"]}
            for d in DATASET["devices"]
        }
        record = {"at": AT, "utterances": [{"role": "user", "at": AT, "text": t} for t in texts]}
        with patch(
            "guest_requests.call_model", return_value=({"replies": recognized}, {})
        ) as model:
            result = plan_request(
                record,
                state,
                preferences or {},
                history or [],
                DATASET["devices"],
                DATASET["tracks"],
            )
        self.assertEqual(model.call_count, 1)
        return result

    def test_context_then_temperature_uses_deterministic_plan(self):
        plans = self.plans(
            ["Холодно.", "Сделай теплее."],
            [
                {"intent": "acknowledge", "parameters": {}},
                {"intent": "warmer", "parameters": {}},
            ],
            initial={"climate": {"temperature_c": 21}},
        )
        self.assertEqual(
            plans, [("acknowledge", {}), ("apply", {"climate": {"temperature_c": 22}})]
        )

    def test_independent_device_and_medical_turns_stay_separate(self):
        plans = self.plans(
            ["Выключи всё.", "Что принять?"],
            [
                {"intent": "all_off", "parameters": {}},
                {"intent": "medical", "parameters": {}},
            ],
        )
        self.assertEqual(
            plans,
            [("apply", {"light": {"brightness": 0}, "sound": {"volume": 0}}), ("medical", {})],
        )

    def test_confirmed_home_and_yesterday_settings_reach_live_planner(self):
        for intent, key, settings in [
            ("like_home", "home_settings", {"light": {"color_temperature_k": 2700}}),
            ("like_yesterday", "previous_evening_settings", {"climate": {"temperature_c": 19}}),
        ]:
            with self.subTest(intent=intent):
                plans = self.plans(
                    ["Повтори."],
                    [{"intent": intent, "parameters": {}}],
                    preferences={key: settings},
                )
                self.assertEqual(plans, [("apply", settings)])

    def test_alarm_shift_uses_last_confirmed_time_and_cancel_is_not_skipped(self):
        history = [{"confirmed_settings": {"alarm": {"at": "2026-11-13T07:30:00+03:00"}}}]
        plans = self.plans(
            ["На полчаса раньше."],
            [{"intent": "alarm_shift", "parameters": {"minutes": -30}}],
            history=history,
        )
        self.assertEqual(plans, [("apply", {"alarm": {"at": "2026-11-13T07:00:00+03:00"}})])
        history.append({"confirmed_settings": {"alarm": {"at": None}}})
        self.assertNotEqual(
            self.plans(
                ["Раньше."],
                [{"intent": "alarm_shift", "parameters": {"minutes": -30}}],
                history=history,
            )[0][0],
            "apply",
        )

    def test_invalid_temperature_and_hallucinated_parameters_produce_no_actions(self):
        for params in ({"value": 35}, {"value": True}, {"value": 22, "extra": 1}):
            with self.subTest(params=params):
                plan = self.plans(
                    ["Температура."], [{"intent": "set_temperature", "parameters": params}]
                )
                self.assertEqual(plan[0][1], {})
                self.assertNotEqual(plan[0][0], "apply")

    def test_favorite_sound_does_not_copy_an_unrequested_timer_or_volume(self):
        plans = self.plans(
            ["Включи мой обычный звук для сна."],
            [
                {
                    "intent": "sound_on",
                    "parameters": {"track_id": "track_04", "volume": 15, "timer_minutes": 30},
                },
            ],
            initial={"sound": {"track_id": "track_01", "volume": 12, "timer_minutes": 65}},
        )
        self.assertEqual(plans, [("apply", {"sound": {"track_id": "track_04", "volume": 12}})])

    def test_exact_sleep_command_works_without_model_but_medical_phrase_does_not_match(self):
        record = {"at": AT, "utterances": [{"role": "user", "at": AT, "text": "Всё, отбой!"}]}
        with patch("guest_requests.call_model", side_effect=AssertionError("Unnecessary LLM call")):
            plans = plan_request(record, {}, {}, [], DATASET["devices"], DATASET["tracks"])
        self.assertEqual(plans[0][0], "apply")
        self.assertEqual(plans[0][1]["dnd"], {"enabled": True})
        self.assertIsNone(simple_intent([{"text": "Проснулась, сердце колотится. Что принять?"}]))

    def test_repeating_old_settings_preserves_current_alarm_date(self):
        settings = {
            "climate": {"temperature_c": 19},
            "alarm": {"at": "2026-11-11T07:00:00+03:00", "mode": "light"},
        }
        plans = self.plans(
            ["Как вчера."],
            [{"intent": "like_yesterday", "parameters": {}}],
            preferences={"previous_evening_settings": settings},
        )
        self.assertEqual(
            plans, [("apply", {"climate": {"temperature_c": 19}, "alarm": {"mode": "light"}})]
        )
        self.assertEqual(settings["alarm"]["at"], "2026-11-11T07:00:00+03:00")


if __name__ == "__main__":
    unittest.main()
