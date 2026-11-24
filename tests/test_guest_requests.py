import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from case2_run import Case2Api, SimulatorError, handle_request
from guest_requests import plan_request

DATASET = json.loads(
    (Path(__file__).resolve().parents[1] / "examples" / "guest_input.json").read_text(
        encoding="utf-8"
    )
)["dataset"]
AT = "2026-11-12T23:20:00+03:00"
SESSION = {
    "session_id": "b6bb40db-b9e5-4e94-a654-052691db6a09",
    "at": AT,
    "initial_state": {"climate": {"temperature_c": 21}, "sound": {"volume": 20}},
}


def record(*texts):
    return {
        "record_id": "rq_fixture",
        "at": AT,
        "utterances": [{"role": "user", "at": AT, "text": text} for text in texts],
    }


class GuestRequestTests(unittest.TestCase):
    def test_two_turns_and_history(self):
        history = [{"confirmed_settings": {"alarm": {"at": "2026-11-13T07:30:00+03:00"}}}]
        active = record("Перенеси будильник.", "На полчаса раньше.")
        alarm = {"alarm": {"at": "2026-11-13T07:00:00+03:00"}}
        planner = Mock(
            return_value={
                "replies": [
                    {"reason": "acknowledge", "settings": {}},
                    {"reason": "apply", "settings": alarm},
                ]
            }
        )
        plans = plan_request(
            active,
            SESSION["initial_state"],
            {},
            history,
            DATASET["devices"],
            DATASET["tracks"],
            planner,
        )
        self.assertEqual(plans, [("acknowledge", {}), ("apply", alarm)])
        self.assertEqual(planner.call_args.args[0]["history"], history)

    def test_rejects_invalid_values_and_counts(self):
        active = record("Установи 35 градусов.")
        for value in (35, float("nan"), True):
            plan = {
                "replies": [{"reason": "apply", "settings": {"climate": {"temperature_c": value}}}]
            }
            actual = plan_request(
                active, {}, {}, [], DATASET["devices"], DATASET["tracks"], lambda _: plan
            )
            self.assertEqual(actual, [("out_of_range", {})])
        actual = plan_request(
            active, {}, {}, [], DATASET["devices"], DATASET["tracks"], lambda _: {"replies": []}
        )
        self.assertEqual(actual, [("unavailable", {})])

    def test_executes_only_valid_settings_and_records_actual_success(self):
        api = Mock()
        api.open_session.return_value = SESSION
        api.apply.side_effect = [None, SimulatorError("/action", 502)]
        history = []
        active = record("Выключи свет и звук.", "Что принять, чтобы уснуть?")
        with patch(
            "case2_run.plan_request",
            return_value=[
                ("apply", {"light": {"brightness": 0}, "sound": {"volume": 0}}),
                ("medical", {}),
            ],
        ):
            answer = handle_request(api, active, DATASET, {}, history)
        self.assertEqual(api.apply.call_count, 2)
        self.assertEqual(
            [reply["response_class"] for reply in answer["replies"]], ["refused", "refused"]
        )
        self.assertEqual(history[0]["confirmed_settings"], {"light": {"brightness": 0}})

    def test_uncertain_write_checks_state(self):
        api = Case2Api("http://localhost", "Bearer test")
        session = SESSION["session_id"]
        snapshot = {"session_id": session, "state": {"climate": {"temperature_c": 22}}}
        with patch.object(
            Case2Api, "call", side_effect=[SimulatorError("/action"), snapshot]
        ) as call:
            api.apply(session, AT, "climate", {"temperature_c": 22})
        self.assertEqual(call.call_count, 2)
        self.assertIn("/state?", call.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
