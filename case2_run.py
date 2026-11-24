"""Оркестратор кейса 2 для входящего POST /run."""

import json
import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from case2_contracts import validate_answers
from extract_preferences import FIELDS
from guest_requests import MODEL_ERRORS, make_reply, plan_request
from guest_service import prepare_guest
from make_cards import as_time

logger = logging.getLogger(__name__)
TRANSIENT = {429, 500, 502, 503, 504}


class SimulatorError(Exception):
    def __init__(self, endpoint, status=None):
        super().__init__(endpoint)
        self.endpoint = endpoint
        self.status = status


@dataclass(frozen=True)
class Case2Api:
    base_url: str
    authorization: str

    def call(self, endpoint, body=None, *, attempts=3):
        headers = {"Authorization": self.authorization, "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, allow_nan=False).encode()
        request = Request(self.base_url + endpoint, headers=headers, data=data)
        for attempt in range(attempts):
            try:
                with urlopen(request, timeout=30) as response:
                    result = json.load(response)
            except HTTPError as error:
                status = error.code
                error.close()
                if status not in TRANSIENT or attempt + 1 == attempts:
                    raise SimulatorError(endpoint, status) from None
            except (URLError, TimeoutError):
                if attempt + 1 == attempts:
                    raise SimulatorError(endpoint) from None
            except (ValueError, UnicodeError):
                raise SimulatorError(endpoint) from None
            else:
                if not isinstance(result, dict):
                    raise SimulatorError(endpoint)
                return result
            time.sleep(2**attempt)

    def dataset(self, dataset_code):
        endpoint = "/case/2/getData?" + urlencode({"dataset_code": dataset_code})
        return self.call(endpoint)["dataset"]

    def open_session(self, record_id, kind):
        session = self.call("/room/session", {"record_id": record_id, "kind": kind})
        if (
            session.get("kind") != kind
            or session.get("record_id") != record_id
            or not session.get("session_id")
        ):
            raise SimulatorError("/room/session")
        return session

    def upload(self, session_id, steps):
        endpoint = f"/room/{session_id}/scenario"
        received = self.call(endpoint, {"steps": steps})
        if received.get("session_id") != session_id or not isinstance(received.get("state"), dict):
            raise SimulatorError(endpoint)

    def apply(self, session_id, at, device, values):
        endpoint = f"/room/{session_id}/action"
        try:
            reply = self.call(
                endpoint, {"at": at, "device_id": device, "values": values}, attempts=1
            )
        except SimulatorError as error:
            if error.status is not None and error.status not in TRANSIENT:
                raise
            # После таймаута команда могла примениться. Сначала читаем состояние.
            reply = self.call(f"/room/{session_id}/state?" + urlencode({"at": at}), attempts=2)
        if reply.get("session_id") != session_id or not isinstance(reply.get("state"), dict):
            raise SimulatorError(endpoint)
        actual = reply["state"].get(device)
        if not isinstance(actual, dict) or any(
            key not in actual or actual[key] != value for key, value in values.items()
        ):
            raise SimulatorError(endpoint)


def unknown_preferences(_payload):
    fields = {field: {"value": None, "source_ids": [], "conflict": False} for field in FIELDS}
    return fields, {}


def open_stay(api, dataset, stay):
    record_id = stay["record_id"]
    try:
        result = prepare_guest(dataset, record_id)
    except MODEL_ERRORS as error:
        logger.warning(
            "Case 2: using profile after guest preparation failed (%s)", type(error).__name__
        )
        result = prepare_guest(dataset, record_id, model_call=unknown_preferences)
    session_id = api.open_session(record_id, "stay")["session_id"]
    api.upload(session_id, result["scenario"]["scenario"])
    preferences = {key: field["value"] for key, field in result["preferences"]["fields"].items()}
    return {"record_id": record_id, "session_id": session_id}, preferences


def handle_request(api, record, dataset, preferences, history):
    session = api.open_session(record["record_id"], "request")
    session_id, at = session["session_id"], session["at"]
    initial = session["initial_state"]
    for device, values in record.get("initial_state", {}).items():
        actual = initial.get(device)
        if not isinstance(actual, dict) or any(
            actual.get(key) != value for key, value in values.items()
        ):
            raise SimulatorError("/room/session")
    plans = plan_request(
        record, initial, preferences, history, dataset["devices"], dataset["tracks"]
    )
    replies, confirmed = [], {}
    for reason, settings in plans:
        # Связанные реплики образуют одну просьбу. Подтверждаем её после
        # выполнения итогового плана, не выдавая раннее «Понял» как успех.
        if reason == "acknowledge":
            continue
        if reason == "apply":
            try:
                for device, values in settings.items():
                    api.apply(session_id, at, device, values)
                    confirmed.setdefault(device, {}).update(values)
            except SimulatorError:
                reason = "failed"
        replies.append(make_reply(reason, at))
    history.append(
        {
            "at": at,
            "utterances": [turn["text"] for turn in record["utterances"]],
            "replies": [reply["response_class"] for reply in replies],
            "confirmed_settings": confirmed,
        }
    )
    return {"record_id": record["record_id"], "session_id": session_id, "replies": replies}


def solve_case2(dataset_code, authorization):
    base_url = os.getenv("HACK_API_URL", "https://hack-api.be-healthy.tech").rstrip("/")
    api = Case2Api(base_url, authorization)
    dataset = api.dataset(dataset_code)
    stays_by_user = defaultdict(list)
    requests_by_user = defaultdict(list)
    for stay in dataset["stays"]:
        stays_by_user[stay["user_id"]].append(stay)
    for record in sorted(dataset["requests"], key=lambda item: as_time(item["at"])):
        requests_by_user[record["user_id"]].append(record)

    def process_guest(user_id):
        stays, requests, preferences = [], [], {}
        for stay in stays_by_user[user_id]:
            answer, guest_preferences = open_stay(api, dataset, stay)
            stays.append(answer)
            preferences[stay["record_id"]] = guest_preferences
        history = []
        for record in requests_by_user.get(user_id, []):
            requests.append(
                handle_request(api, record, dataset, preferences[record["stay_id"]], history)
            )
        return stays, requests

    stay_answers, request_answers = {}, {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        for stays, requests in executor.map(process_guest, stays_by_user):
            stay_answers.update((row["record_id"], row) for row in stays)
            request_answers.update((row["record_id"], row) for row in requests)
    result = {
        "stays": [stay_answers[stay["record_id"]] for stay in dataset["stays"]],
        "requests": [request_answers[record["record_id"]] for record in dataset["requests"]],
    }
    validate_answers(result)
    return result
