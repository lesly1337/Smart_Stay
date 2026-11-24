import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from case2_contracts import validate_answers
from request_handler import (
    RequestError,
    RoomClient,
    RoomError,
    handle_request,
    plan_request,
    plan_temperature,
    recognize_request,
)

ROOT = Path(__file__).resolve().parents[1]


class FakeRoom:
    def __init__(self, request, *, fail_on=None):
        self.request = request
        self.state = copy.deepcopy(request["initial_state"])
        self.actions = []
        self.fail_on = fail_on
        self.opens = []

    def open_session(self, record_id):
        self.opens.append(record_id)
        return {
            "session_id": "test-session",
            "record_id": record_id,
            "kind": "request",
            "initial_state": copy.deepcopy(self.request["initial_state"]),
        }

    def action(self, session_id, device, values, at):
        if device == self.fail_on:
            raise RoomError("failure")
        self.actions.append((device, copy.deepcopy(values), at))
        self.state[device].update(values)
        return {"session_id": session_id, "state": copy.deepcopy(self.state)}


class RequestHandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dataset = json.loads((ROOT / "examples/guest_input.json").read_text(encoding="utf-8"))[
            "dataset"
        ]
        cls.devices = dataset["devices"]
        cls.tracks = dataset["tracks"]
        cls.intents = dataset["intents"]
        cls.state = {
            d["device_id"]: {f["field_id"]: f["default_value"] for f in d["fields"]}
            for d in cls.devices
        }
        cls.at = "2026-11-12T21:00:00+03:00"
        cls.preferences = {
            "user_id": "u",
            "stay_id": "stay",
            "fields": {
                "temperature": {"value": "warm"},
                "favorite_track_ids": {"value": ["track_03"]},
                "home_settings": {"value": {"climate": {"temperature_c": 19}}},
                "previous_evening_settings": {
                    "value": {"sound": {"track_id": "track_03", "volume": 10, "timer_minutes": 30}}
                },
                "wake_settings": {
                    "value": {"light": {"brightness": 50}, "curtains": {"position": 0}}
                },
            },
        }

    def request(self, text="Сделай теплее"):
        return {
            "record_id": "rq",
            "user_id": "u",
            "stay_id": "stay",
            "at": self.at,
            "initial_state": copy.deepcopy(self.state),
            "utterances": [{"role": "user", "at": self.at, "text": text}],
        }

    def recognize(self, intent, params=None):
        return lambda payload: {"intent": intent, "parameters": params or {}}

    def context(self, intent="warmer", params=None):
        return {
            "preferences": copy.deepcopy(self.preferences),
            "tracks": self.tracks,
            "intents": self.intents,
            "model_call": self.recognize(intent, params),
        }

    def test_temperature_bounds_and_explicit_invalid_values(self):
        state = copy.deepcopy(self.state)
        for start, intent, expected in [
            (20, "warmer", 21),
            (25.5, "warmer", 26),
            (16.5, "cooler", 16),
            (20, "cooler", 19),
        ]:
            state["climate"]["temperature_c"] = start
            with self.subTest(start=start, intent=intent):
                self.assertEqual(
                    plan_temperature(intent, state, self.devices),
                    {"climate": {"temperature_c": expected}},
                )
        for start, intent in [(26, "warmer"), (16, "cooler")]:
            state["climate"]["temperature_c"] = start
            with self.subTest(start=start), self.assertRaises(RequestError):
                plan_temperature(intent, state, self.devices)
        for value in (15, 35, True, "22", float("nan")):
            with self.subTest(value=value), self.assertRaises(RequestError):
                plan_temperature(
                    {"intent": "set_temperature", "parameters": {"value": value}},
                    state,
                    self.devices,
                )

    def test_end_to_end_warmer_preserves_other_fields_and_schema(self):
        request = self.request()
        request["initial_state"]["climate"]["temperature_c"] = 20
        room = FakeRoom(request)
        context = self.context()
        result = handle_request(request, context, self.devices, room)
        self.assertEqual(result["replies"][0]["response_class"], "done")
        self.assertEqual(room.actions, [("climate", {"temperature_c": 21}, self.at)])
        original = copy.deepcopy(request["initial_state"])
        original["climate"]["temperature_c"] = 21
        self.assertEqual(room.state, original)
        self.assertEqual(len(context["history"]["u"]), 1)
        validate_answers({"stays": [], "requests": [result]})

    def test_refusals_still_create_session_without_actions(self):
        for intent in ("medical", "invalid_value", "out_of_scope"):
            request = self.request()
            room = FakeRoom(request)
            result = handle_request(request, self.context(intent), self.devices, room)
            with self.subTest(intent=intent):
                self.assertEqual(room.opens, ["rq"])
                self.assertFalse(room.actions)
                self.assertEqual(room.state, request["initial_state"])
                self.assertEqual(result["replies"][0]["response_class"], "refused")

    def test_model_and_simulator_failure_never_claim_success(self):
        request = self.request()
        room = FakeRoom(request, fail_on="sound")
        result = handle_request(request, self.context("all_off"), self.devices, room)
        self.assertEqual(result["replies"][0]["response_class"], "refused")
        self.assertIn("Часть настроек могла измениться", result["replies"][0]["text"])
        self.assertEqual([a[0] for a in room.actions], ["light"])
        for result_from_model in (
            {"intent": "warmer", "parameters": {"extra": 1}},
            {"intent": "wrong", "parameters": {}},
            "bad",
        ):
            room = FakeRoom(request)
            context = self.context()
            context["model_call"] = lambda payload: result_from_model
            result = handle_request(request, context, self.devices, room)
            self.assertEqual(result["replies"][0]["response_class"], "refused")
            self.assertFalse(room.actions)

    def test_history_is_scoped_to_guest_and_initial_state_is_per_request(self):
        request = self.request()
        context = self.context()
        seen = []

        def model(payload):
            seen.append(copy.deepcopy(payload))
            return {"intent": "warmer", "parameters": {}}

        context["model_call"] = model
        handle_request(request, context, self.devices, FakeRoom(request))
        next_request = copy.deepcopy(request)
        next_request["record_id"] = "rq2"
        next_request["initial_state"]["climate"]["temperature_c"] = 18
        room = FakeRoom(next_request)
        handle_request(next_request, context, self.devices, room)
        self.assertEqual(len(seen[1]["history"]), 1)
        self.assertEqual(room.state["climate"]["temperature_c"], 19)
        other = copy.deepcopy(next_request)
        other["user_id"] = "other"
        other["stay_id"] = "other-stay"
        context["preferences"] = {}
        handle_request(other, context, self.devices, FakeRoom(other))
        self.assertEqual(seen[2]["history"], [])

    def test_session_initial_state_must_match_and_bad_guest_is_rejected(self):
        request = self.request()
        room = FakeRoom(request)
        room.request = copy.deepcopy(request)
        room.request["initial_state"]["climate"]["temperature_c"] = 17
        with self.assertRaises(RoomError):
            handle_request(request, self.context(), self.devices, room)
        context = self.context()
        context["preferences"]["user_id"] = "other"
        with self.assertRaises(ValueError):
            handle_request(request, context, self.devices, room)

    def test_plans_cover_devices_alarm_and_modes(self):
        state = copy.deepcopy(self.state)
        state["alarm"]["at"] = "2026-11-13T06:30:00+03:00"
        examples = [
            ("brighter", {}, {"light": {"brightness": 80}}),
            ("dimmer", {}, {"light": {"brightness": 60}}),
            ("quieter", {}, {"sound": {"volume": 10}}),
            ("all_off", {}, {"light": {"brightness": 0}, "sound": {"volume": 0}}),
            ("curtains", {"position": 0}, {"curtains": {"position": 0}}),
            ("do_not_disturb", {"enabled": False}, {"dnd": {"enabled": False}}),
            (
                "alarm_set",
                {"at": "2026-11-13T07:30:00+03:00", "mode": "light"},
                {"alarm": {"at": "2026-11-13T07:30:00+03:00", "mode": "light"}},
            ),
            ("alarm_shift", {"minutes": -15}, {"alarm": {"at": "2026-11-13T06:15:00+03:00"}}),
            ("alarm_cancel", {}, {"alarm": {"at": None}}),
            ("like_home", {}, {"climate": {"temperature_c": 19}}),
            (
                "like_yesterday",
                {},
                {"sound": {"track_id": "track_03", "volume": 10, "timer_minutes": 30}},
            ),
            ("sound_on", {}, {"sound": {"track_id": "track_03", "volume": 20}}),
            (
                "going_to_bed",
                {},
                {
                    "light": {"brightness": 0},
                    "curtains": {"position": 0},
                    "dnd": {"enabled": True},
                    "climate": {"temperature_c": 21.5},
                    "sound": {"track_id": "track_03", "volume": 10, "timer_minutes": 30},
                },
            ),
            (
                "woke_up",
                {},
                {
                    "alarm": {"at": None},
                    "dnd": {"enabled": False},
                    "light": {"brightness": 50},
                    "curtains": {"position": 0},
                },
            ),
        ]
        for intent, params, expected in examples:
            with self.subTest(intent=intent):
                actual = plan_request(
                    {"intent": intent, "parameters": params},
                    state,
                    self.devices,
                    self.preferences,
                    self.tracks,
                    self.at,
                )
                self.assertEqual(actual, expected)

    def test_bad_alarm_and_unknown_preferences_are_refused(self):
        for intent, params in [
            ("alarm_shift", {"minutes": -15}),
            ("alarm_set", {"at": "2026-11-12T20:00:00+03:00"}),
            ("curtains", {}),
            ("sound_on", {}),
            ("like_home", {}),
        ]:
            with self.subTest(intent=intent), self.assertRaises(RequestError):
                plan_request(
                    {"intent": intent, "parameters": params},
                    self.state,
                    self.devices,
                    {},
                    self.tracks,
                    self.at,
                )

    def test_wake_cancels_alarm_and_dnd_even_if_card_conflicts(self):
        preferences = copy.deepcopy(self.preferences)
        preferences["fields"]["wake_settings"]["value"].update(
            {"alarm": {"at": "2026-11-13T08:00:00+03:00"}, "dnd": {"enabled": True}}
        )
        plan = plan_request(
            {"intent": "woke_up", "parameters": {}},
            self.state,
            self.devices,
            preferences,
            self.tracks,
            self.at,
        )
        self.assertIsNone(plan["alarm"]["at"])
        self.assertIs(plan["dnd"]["enabled"], False)
        self.assertEqual(plan["light"]["brightness"], 50)

    def test_unconfirmed_action_is_refused(self):
        request = self.request()
        room = FakeRoom(request)
        room.action = lambda session_id, device, values, at: {
            "session_id": session_id,
            "state": copy.deepcopy(request["initial_state"]),
        }
        result = handle_request(request, self.context(), self.devices, room)
        self.assertEqual(result["replies"][0]["response_class"], "refused")

    def test_room_http_contract(self):
        requests = []

        class Response:
            def __init__(self, value):
                self.value = json.dumps(value).encode()

            def __enter__(self):
                import io

                self.stream = io.BytesIO(self.value)
                return self.stream

            def __exit__(self, *args):
                self.stream.close()

        def opener(req, timeout):
            requests.append(
                (
                    req.method,
                    req.full_url,
                    json.loads(req.data) if req.data else None,
                    req.get_header("Authorization"),
                )
            )
            return Response({"session_id": "abc", "state": {}})

        room = RoomClient("https://example.test", "Bearer secret", run_id="run", opener=opener)
        room.open_session("rq")
        room.action("abc", "climate", {"temperature_c": 21}, self.at)
        room.log("abc")
        self.assertEqual(
            requests[0][:3],
            (
                "POST",
                "https://example.test/room/session",
                {"run_id": "run", "record_id": "rq", "kind": "request"},
            ),
        )
        self.assertEqual(
            requests[1][:3],
            (
                "POST",
                "https://example.test/room/abc/action",
                {"device_id": "climate", "values": {"temperature_c": 21}, "at": self.at},
            ),
        )
        self.assertEqual(requests[2][:3], ("GET", "https://example.test/room/abc/log", None))
        self.assertTrue(all(item[3] == "Bearer secret" for item in requests))


if __name__ == "__main__":
    unittest.main()
