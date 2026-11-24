import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from uuid import UUID

from fastapi import HTTPException
from fastapi.testclient import TestClient

from interactive_room import InteractiveRooms, InteractiveSession
from main import app
from room_simulator import SimulatorRoom


def active_session():
    return InteractiveSession(
        "https://simulator.test",
        "interactive-run-token",
        UUID("00000000-0000-4000-8000-000000000001"),
        UUID("00000000-0000-4000-8000-000000000002"),
        datetime.fromisoformat("2026-11-12T18:35:00+03:00"),
        datetime.now(timezone.utc) + timedelta(minutes=45),
    )


class InteractiveRoomTests(unittest.TestCase):
    def test_independent_run_created_with_team_token_and_reused(self):
        manager = InteractiveRooms()
        session = active_session()
        instances = []

        def api(base, authorization):
            instance = Mock()
            instances.append((authorization, instance))
            if len(instances) == 1:
                instance.call.return_value = {
                    "stage": "dev",
                    "run_id": str(session.run_id),
                    "run_token": session.run_token,
                    "expires_at": session.expires_at.isoformat(),
                }
            else:
                instance.call.return_value = {"dataset": {"requests": [{"record_id": "rq_ui"}]}}
                instance.open_session.return_value = {
                    "run_id": str(session.run_id),
                    "session_id": str(session.session_id),
                    "at": session.at.isoformat(),
                }
            return instance

        with (
            patch.dict("os.environ", {"HACK_TEAM_TOKEN": "team-token"}),
            patch("interactive_room.Case2Api", api),
        ):
            first = manager.create()
            self.assertIs(manager.create(), first)
        self.assertEqual(len(instances), 2)
        self.assertEqual(instances[0][0], "Bearer team-token")
        instances[0][1].call.assert_called_once_with("/runs", {"case": 2}, attempts=1)
        self.assertEqual(instances[1][0], "Bearer interactive-run-token")
        instances[1][1].open_session.assert_called_once_with("rq_ui", "request")
        self.assertNotIn("run_token", first.public_info())

    def test_expired_session_is_reported_and_not_reused(self):
        manager = InteractiveRooms()
        original = active_session()
        manager._session = InteractiveSession(
            original.base_url,
            original.run_token,
            original.run_id,
            original.session_id,
            original.at,
            datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        for get in (manager.get, manager.create):
            with self.assertRaises(HTTPException) as error:
                get()
            self.assertEqual(error.exception.status_code, 410)

    def test_light_writes_simulator_and_verifies_separate_state(self):
        room = SimulatorRoom(
            "https://simulator.test", "ui-token", active_session().session_id, active_session().at
        )
        with (
            patch("room_simulator.configured_room", return_value=room),
            patch.object(
                SimulatorRoom,
                "request",
                side_effect=[
                    {"state": {"light": {"brightness": 10}}},
                    {"state": {"light": {"brightness": 40}}},
                ],
            ) as request,
        ):
            response = TestClient(app).patch("/api/room/light", json={"brightness": 40})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"brightness": 40, "lightOn": True})
        self.assertTrue(request.call_args_list[0].args[0].endswith("/action"))
        self.assertEqual(request.call_args_list[0].args[1]["device_id"], "light")
        self.assertEqual(request.call_args_list[0].args[1]["values"], {"brightness": 40})
        self.assertTrue(request.call_args_list[1].args[0].endswith("/state"))

    def test_light_unconfirmed_value_returns_error(self):
        room = SimulatorRoom(
            "https://simulator.test", "ui-token", active_session().session_id, active_session().at
        )
        with (
            patch("room_simulator.configured_room", return_value=room),
            patch.object(
                SimulatorRoom,
                "request",
                return_value={"state": {"light": {"brightness": 70}}},
            ),
        ):
            response = TestClient(app).patch("/api/room/light", json={"brightness": 40})
        self.assertEqual(response.status_code, 502)
        self.assertIn("не подтвердил", response.json()["detail"])

    def test_closed_session_write_returns_409(self):
        from urllib.error import HTTPError
        from room_simulator import interactive_rooms

        session = active_session()
        manager = InteractiveRooms()
        manager._session = session
        room = SimulatorRoom(session.base_url, session.run_token, session.session_id, session.at)
        closed = HTTPError("https://simulator.test/action", 409, "Closed", {}, None)
        with (
            patch("room_simulator.interactive_rooms", manager),
            patch("room_simulator.configured_room", return_value=room),
            patch(
                "room_simulator.urlopen",
                side_effect=closed,
            ),
        ):
            response = TestClient(app).patch("/api/room/light", json={"brightness": 40})
        self.assertEqual(response.status_code, 409)
        with self.assertRaises(HTTPException) as error:
            manager.get()
        self.assertEqual(error.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
