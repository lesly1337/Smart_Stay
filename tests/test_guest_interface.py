import copy
import json
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import HTTPException
from fastapi.testclient import TestClient

from interactive_guests import GuestPlans
from interactive_room import InteractiveRooms, InteractiveSession
from main import app

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads((ROOT / "examples/guest_input.json").read_text(encoding="utf-8"))["dataset"]
MODEL = json.loads((ROOT / "examples/guest_model_response.json").read_text(encoding="utf-8"))


class SimulatorFixture:
    def __init__(self):
        self.dataset = copy.deepcopy(EXAMPLE)
        user = copy.deepcopy(self.dataset["users"][0])
        user["user_id"] = "u_second"
        user["sleep_preferences"]["temperature"] = "warm"
        user["sleep_preferences"]["favorite_track_ids"] = ["track_04"]
        self.dataset["users"].append(user)
        stay = dict(self.dataset["stays"][0], record_id="stay_second", user_id=user["user_id"])
        self.dataset["stays"].append(stay)
        self.initial = {
            d["device_id"]: {f["field_id"]: f["default_value"] for f in d["fields"]}
            for d in self.dataset["devices"]
        }
        self.dataset["requests"] = [
            {
                "record_id": "rq_" + s["record_id"],
                "user_id": s["user_id"],
                "stay_id": s["record_id"],
                "at": s["check_in_at"],
                "initial_state": copy.deepcopy(self.initial),
                "utterances": [{"role": "user", "at": s["check_in_at"], "text": "Теплее."}],
            }
            for s in self.dataset["stays"]
        ]
        self.run_id = uuid4()
        self.sessions = {}
        self.rooms = InteractiveRooms()
        opened = self.open(self.dataset["requests"][0]["record_id"], "request")
        self.rooms._session = InteractiveSession(
            "https://simulator.test",
            "ui-only-token",
            self.run_id,
            UUID(opened["session_id"]),
            datetime.fromisoformat(opened["at"]),
            datetime.now(timezone.utc) + timedelta(minutes=45),
            stay_id=self.dataset["stays"][0]["record_id"],
        )
        self.rooms._dataset = self.dataset
        self.rooms._stay_id = self.dataset["stays"][0]["record_id"]
        self.service = GuestPlans(self.rooms)
        self.confirm_scenario = True
        self.fail_device = None
        self.action_count = 0
        self.paths = []

    def open(self, record_id, kind):
        session_id = str(uuid5(NAMESPACE_URL, str(self.run_id) + kind + record_id))
        at = (
            next(s["check_in_at"] for s in self.dataset["stays"] if s["record_id"] == record_id)
            if kind == "stay"
            else next(q["at"] for q in self.dataset["requests"] if q["record_id"] == record_id)
        )
        session = {
            "session_id": session_id,
            "run_id": str(self.run_id),
            "kind": kind,
            "record_id": record_id,
            "at": at,
            "initial_state": copy.deepcopy(self.initial),
        }
        self.sessions.setdefault(
            session_id, {"session": session, "steps": [], "actions": [], "entries": []}
        )
        return session

    def state(self, session_id, at):
        room = self.sessions[session_id]
        state = copy.deepcopy(self.initial)
        for step in sorted(
            room["steps"] + room["actions"], key=lambda s: datetime.fromisoformat(s["at"])
        ):
            if datetime.fromisoformat(step["at"]) <= datetime.fromisoformat(at):
                state[step["device_id"]].update(step["values"])
        return state

    def call(self, path, body=None, **query):
        self.paths.append(path)
        parsed = urlsplit(path)
        query = {**{k: v[0] for k, v in parse_qs(parsed.query).items()}, **query}
        if parsed.path == "/room/session":
            return self.open(body["record_id"], body["kind"])
        if parsed.path == "/room/devices":
            return {"devices": self.dataset["devices"], "tracks": self.dataset["tracks"]}
        parts = parsed.path.split("/")
        session_id, operation = parts[2], parts[3]
        room = self.sessions[session_id]
        if operation == "scenario":
            room["steps"] = copy.deepcopy(body["steps"])
            room["entries"].append({"kind": "scenario", "steps": copy.deepcopy(body["steps"])})
            return {
                "session_id": session_id,
                "state": self.state(session_id, room["session"]["at"]),
            }
        if operation == "action":
            if body["device_id"] == self.fail_device:
                raise HTTPException(502, "Simulator write failed")
            room["actions"].append(copy.deepcopy(body))
            room["entries"].append({"kind": "action", "steps": [copy.deepcopy(body)]})
            self.action_count += 1
            return {"session_id": session_id, "state": self.state(session_id, body["at"])}
        if operation == "state":
            return {"session_id": session_id, "state": self.state(session_id, query["at"])}
        if operation == "log":
            return {
                "session": room["session"],
                "entries": room["entries"] if self.confirm_scenario else [],
            }
        raise AssertionError(path)

    def install(self):
        stack = ExitStack()
        stack.enter_context(patch("room_simulator.interactive_rooms", self.rooms))
        stack.enter_context(patch("interactive_guests.guest_plans", self.service))
        stack.enter_context(
            patch(
                "case2_run.Case2Api.call",
                lambda client, path, body=None, **kwargs: self.call(path, body),
            )
        )
        stack.enter_context(
            patch(
                "room_simulator.SimulatorRoom.request",
                lambda room, path, body=None, **query: self.call(path, body, **query),
            )
        )
        return stack


class GuestInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.simulator = SimulatorFixture()
        self.stack = self.simulator.install()
        self.addCleanup(self.stack.close)
        self.client = TestClient(app)

    def command(self, text, command_id=None):
        return self.client.post(
            "/api/room/command", json={"text": text, "command_id": str(command_id or uuid4())}
        )

    def test_home_plan_uses_guest_data_and_does_not_call_model_or_apply_implicitly(self):
        with patch(
            "guest_service.call_model", side_effect=AssertionError("Unexpected paid model call")
        ):
            response = self.client.get("/api/room/plan")
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()
        self.assertEqual(plan["status"], "draft")
        self.assertEqual(plan["stay"]["check_in_at"], EXAMPLE["stays"][0]["check_in_at"])
        self.assertEqual(plan["bedtime_at"], "2026-11-12T23:20:00+03:00")
        self.assertEqual([p["id"] for p in plan["periods"]], ["evening", "night", "morning"])
        self.assertTrue(plan["assumptions"])
        self.assertEqual(self.simulator.action_count, 0)
        self.assertFalse(any(p.endswith("/scenario") for p in self.simulator.paths))

    def test_history_preparation_is_cached_and_restores_confirmed_preferences(self):
        with patch("guest_service.call_model", return_value=(copy.deepcopy(MODEL), {})) as model:
            first = self.client.post("/api/room/plan/prepare")
            second = self.client.post("/api/room/plan/prepare")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(first.json()["personalization"], "history")
        self.assertEqual(first.json()["preferences"]["temperature"]["value"], "cool")

    def test_unavailable_personalization_preserves_basic_plan_without_false_history_badge(self):
        with patch("guest_service.call_model", side_effect=URLError("Unavailable")):
            response = self.client.post("/api/room/plan/prepare")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get("/api/room/plan").json()["personalization"], "profile")
        self.assertEqual(self.simulator.action_count, 0)

    def test_scenario_is_uploaded_and_period_preview_drives_actual_device_state(self):
        response = self.client.post("/api/room/plan/apply")
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()
        self.assertEqual(plan["status"], "applied")
        self.assertEqual(plan["session"]["kind"], "stay")
        night = next(p for p in plan["periods"] if p["id"] == "night")
        response = self.client.post("/api/room/time", json={"at": night["at"]})
        self.assertEqual(response.status_code, 200, response.text)
        state = self.client.get("/api/room/devices").json()
        self.assertEqual(state["light"]["brightness"], 0)
        self.assertEqual(state["curtains"]["position"], 0)
        self.assertTrue(state["dnd"]["enabled"])
        self.assertEqual(state["climate"]["temperature"], 20)
        for step in plan["steps"]:
            if step["device_id"] == "climate":
                self.assertEqual(step["values"]["temperature_c"] % 1, 0)
        self.assertEqual(
            self.client.post(
                "/api/room/time", json={"at": "2026-11-15T10:00:00+03:00"}
            ).status_code,
            400,
        )

    def test_scenario_success_requires_log_confirmation(self):
        self.simulator.confirm_scenario = False
        response = self.client.post("/api/room/plan/apply")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.client.get("/api/room/plan").json()["status"], "draft")

    def test_chat_uses_actual_state_and_is_idempotent(self):
        command_id = uuid4()
        with patch(
            "guest_requests.call_model",
            side_effect=AssertionError("Simple command should not use model"),
        ):
            first = self.command("Сделай теплее", command_id)
            second = self.command("Сделай теплее", command_id)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json()["replies"][0]["response_class"], "done")
        self.assertEqual(self.simulator.action_count, 1)
        self.assertEqual(
            self.client.get("/api/room/temperature").json()["temperature"],
            self.simulator.initial["climate"]["temperature_c"] + 1,
        )

    def test_card_commands_and_followup_share_server_history(self):
        commands = [
            "Яркость света 60 процентов",
            "Поставь таймер звука на 15 минут",
            "Поставь будильник на 07:30",
        ]
        with patch(
            "guest_requests.call_model", side_effect=AssertionError("Exact commands need no model")
        ):
            for text in commands:
                response = self.command(text)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["replies"][0]["response_class"], "done")

        def followup(payload, **kwargs):
            self.assertEqual([item["utterances"][0] for item in payload["history"]], commands)
            self.assertEqual(
                payload["history"][0]["confirmed_settings"], {"light": {"brightness": 60}}
            )
            self.assertTrue(payload["history"][0]["reply_texts"])
            self.assertEqual(payload["initial_state"]["sound"]["timer_minutes"], 15)
            return {"replies": [{"intent": "alarm_shift", "parameters": {"minutes": 60}}]}, {}

        with patch("guest_requests.call_model", side_effect=followup):
            response = self.command("А теперь на час позже")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get("/api/room/devices").json()["alarm"]["time"], "08:30")

    def test_invalid_chat_values_are_recorded_without_actions(self):
        response = self.command("Яркость света 150 процентов")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["replies"][0]["response_class"], "refused")
        self.assertEqual(self.simulator.action_count, 0)
        history = next(iter(self.simulator.service._history.values()))
        self.assertEqual(history[0]["confirmed_settings"], {})

    def test_exact_card_commands_keep_all_controls_available(self):
        commands = [
            ("Теплый свет", "light", "color_temperature_k", 2700),
            ("Температура 22 градуса", "climate", "temperature_c", 22),
            ("Громкость 30 процентов", "sound", "volume", 30),
            ("Закрой шторы", "curtains", "position", 0),
            ("Включи не беспокоить", "dnd", "enabled", True),
            ("Выключи не беспокоить", "dnd", "enabled", False),
            ("Будильник только светом", "alarm", "mode", "light"),
            ("Отмени таймер звука", "sound", "timer_minutes", 0),
        ]
        with patch(
            "guest_requests.call_model", side_effect=AssertionError("Unexpected model call")
        ):
            for text, device, field, value in commands:
                with self.subTest(text=text):
                    response = self.command(text)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["confirmed_settings"][device][field], value)

    def test_help_and_guest_history_are_isolated(self):
        response = self.command("Команды")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.simulator.action_count, 0)
        self.simulator.rooms.select_stay("stay_second")

        def followup(payload, **kwargs):
            self.assertEqual(payload["history"], [])
            return {"replies": [{"intent": "out_of_scope", "parameters": {}}]}, {}

        with patch("guest_requests.call_model", side_effect=followup):
            self.assertEqual(self.command("Какой сегодня день?").status_code, 200)

    def test_confirmed_home_and_yesterday_settings_reach_current_guest_simulator(self):
        with patch("guest_service.call_model", return_value=(copy.deepcopy(MODEL), {})):
            prepared = self.client.post("/api/room/plan/prepare")
        self.assertEqual(prepared.status_code, 200, prepared.text)
        with patch(
            "guest_requests.call_model",
            side_effect=AssertionError("Preset does not need another model call"),
        ):
            for text, field in [
                ("Сделай как дома", "home_settings"),
                ("Сделай как вчера", "previous_evening_settings"),
            ]:
                with self.subTest(text=text):
                    expected = prepared.json()["preferences"][field]["value"]
                    self.assertTrue(expected)
                    response = self.command(text)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["replies"][0]["response_class"], "done")
                    self.assertEqual(response.json()["confirmed_settings"], expected)
                    session = self.simulator.rooms.get()
                    actual = self.simulator.state(str(session.session_id), session.at.isoformat())
                    for device, values in expected.items():
                        for name, value in values.items():
                            self.assertEqual(actual[device][name], value)

    def test_partial_chat_failure_never_claims_success_and_is_not_reapplied(self):
        self.simulator.fail_device = "sound"
        command_id = uuid4()
        first = self.command("Выключи всё", command_id)
        second = self.command("Выключи всё", command_id)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["replies"][0]["response_class"], "refused")
        self.assertEqual(first.json()["confirmed_settings"], {"light": {"brightness": 0}})
        self.assertEqual(first.json(), second.json())
        self.assertEqual(self.simulator.action_count, 1)

    def test_guest_selection_binds_profile_to_new_stay_and_rejects_stale_writes(self):
        old_context = self.simulator.rooms.get().public_info()["context_id"]
        result = self.client.post("/api/room/guest", json={"stay_id": "stay_second"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["preferences"]["temperature"]["value"], "warm")
        response = self.client.patch(
            "/api/room/temperature",
            headers={"X-Room-Session": old_context},
            json={"temperature": 25},
        )
        self.assertEqual(response.status_code, 412)
        self.assertEqual(self.simulator.action_count, 0)

    def test_medical_and_invalid_requests_make_no_actions(self):
        for text in ["Проснулась, сердце колотится. Что принять?", "Поставь 35 градусов"]:
            with self.subTest(text=text):
                response = self.command(text)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["replies"][0]["response_class"], "refused")
        self.assertEqual(self.simulator.action_count, 0)

    def test_expired_session_cannot_apply_plan_or_execute_commands(self):
        from dataclasses import replace

        self.simulator.rooms._session = replace(
            self.simulator.rooms.get(), expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
        )
        self.assertEqual(self.client.get("/api/room/plan").status_code, 410)
        self.assertEqual(self.command("Ложусь").status_code, 410)
        self.assertEqual(self.simulator.action_count, 0)

    def test_new_light_and_timer_fields_reach_simulator_and_are_range_checked(self):
        light = self.client.patch(
            "/api/room/light", json={"brightness": 30, "color_temperature_k": 2700}
        )
        self.assertEqual(light.status_code, 200, light.text)
        sound = self.client.patch(
            "/api/room/sound", json={"track_id": "track_04", "volume": 15, "timer_minutes": 30}
        )
        self.assertEqual(sound.status_code, 200, sound.text)
        actual = self.client.get("/api/room/devices").json()
        self.assertEqual(actual["light"]["color_temperature_k"], 2700)
        self.assertEqual(actual["sound"]["timer_minutes"], 30)
        self.assertEqual(
            self.client.patch(
                "/api/room/light", json={"brightness": 30, "color_temperature_k": 7000}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.patch(
                "/api/room/sound",
                json={"track_id": "track_04", "volume": 15, "timer_minutes": 1500},
            ).status_code,
            422,
        )


if __name__ == "__main__":
    unittest.main()
