import copy
import json
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from fastapi.testclient import TestClient
from main import app

EXAMPLE = json.loads(
    (Path(__file__).resolve().parents[1] / "examples/guest_input.json").read_text(encoding="utf-8")
)["dataset"]


class RunContractTests(unittest.TestCase):
    def test_incoming_token_and_code_whole_dataset_and_no_validation_call(self):
        dataset = copy.deepcopy(EXAMPLE)
        template = dataset["stays"][0]
        dataset["stays"] = [
            dict(template, record_id="stay_first"),
            dict(template, record_id="stay_second"),
        ]
        initial = {
            d["device_id"]: {f["field_id"]: f["default_value"] for f in d["fields"]}
            for d in dataset["devices"]
        }
        dataset["requests"] = [
            {
                "record_id": "rq_later",
                "stay_id": "stay_second",
                "user_id": template["user_id"],
                "at": "2026-11-12T23:20:00+03:00",
                "initial_state": copy.deepcopy(initial),
                "utterances": [{"text": "Теплее."}],
            },
            {
                "record_id": "rq_earlier",
                "stay_id": "stay_first",
                "user_id": template["user_id"],
                "at": "2026-11-12T22:20:00+03:00",
                "initial_state": copy.deepcopy(initial),
                "utterances": [{"text": "Холодно."}, {"text": "Теплее."}],
            },
        ]
        calls, rooms, order = [], {}, []

        def transport(client, endpoint, body=None, **kwargs):
            self.assertEqual(client.authorization, "Bearer incoming-check-token")
            calls.append((endpoint, body))
            if endpoint.startswith("/case/2/getData?"):
                self.assertEqual(
                    parse_qs(urlsplit(endpoint).query), {"dataset_code": ["runtime-dataset"]}
                )
                return {"dataset": dataset, "reference": None}
            if endpoint == "/room/session":
                session_id = str(uuid5(NAMESPACE_URL, body["record_id"]))
                rooms[session_id] = copy.deepcopy(initial)
                return {
                    "record_id": body["record_id"],
                    "kind": body["kind"],
                    "session_id": session_id,
                    "at": "2026-11-12T23:20:00+03:00",
                    "initial_state": copy.deepcopy(initial),
                }
            if endpoint.endswith("/scenario"):
                return {"session_id": endpoint.split("/")[2], "state": initial}
            if endpoint.endswith("/action"):
                session_id = endpoint.split("/")[2]
                rooms[session_id][body["device_id"]].update(body["values"])
                return {"session_id": session_id, "state": rooms[session_id]}
            self.fail("Unexpected endpoint: " + endpoint)

        def prepare(ds, stay_id):
            self.assertIs(ds, dataset)
            return {"scenario": {"scenario": []}, "preferences": {"fields": {}}}

        def plan(record, _initial, preferences, history, devices, tracks):
            order.append(record["record_id"])
            return [("apply", {"climate": {"temperature_c": 22}})] * len(record["utterances"])

        with (
            patch.dict("os.environ", {"HACK_TEAM_TOKEN": "different-team-token"}),
            patch(
                "case2_run.Case2Api.call",
                transport,
            ),
            patch("case2_run.prepare_guest", prepare),
            patch("case2_run.plan_request", plan),
        ):
            response = TestClient(app).post(
                "/run",
                headers={"Authorization": "Bearer incoming-check-token"},
                json={"case": 2, "dataset_code": "runtime-dataset"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual([row["record_id"] for row in body["stays"]], ["stay_first", "stay_second"])
        self.assertEqual([row["record_id"] for row in body["requests"]], ["rq_later", "rq_earlier"])
        self.assertEqual(order, ["rq_earlier", "rq_later"])
        self.assertEqual(len(body["requests"][1]["replies"]), 2)
        self.assertEqual(sum("/getData" in path for path, _ in calls), 1)
        self.assertFalse(any("/validate" in path for path, _ in calls))


if __name__ == "__main__":
    unittest.main()
