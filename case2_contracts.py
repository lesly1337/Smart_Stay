"""Локальная проверка схем кейса 2; не заменяет проверку /room организаторами."""

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent
FORMATS = FormatChecker()


@FORMATS.checks("date-time", raises=ValueError)
def is_datetime(value):
    if not isinstance(value, str):
        return True
    return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None


@FORMATS.checks("date", raises=ValueError)
def is_date(value):
    if isinstance(value, str):
        date.fromisoformat(value)
    return True


@FORMATS.checks("iana-timezone", raises=(ZoneInfoNotFoundError, ValueError))
def is_timezone(value):
    if not isinstance(value, str):
        return True  # Тип проверяет схема.
    ZoneInfo(value)
    return True


def validate(schema, value, label):
    Draft202012Validator.check_schema(schema)
    error = next(Draft202012Validator(schema, format_checker=FORMATS).iter_errors(value), None)
    if error:
        path = ".".join(map(str, error.absolute_path)) or "<root>"
        # Не включаем исходные записи и тексты гостя в сообщения об ошибках.
        raise ValueError(f"{label}.{path}: нарушено ограничение {error.validator}")


def validate_dataset(dataset):
    with (ROOT / "requests.json").open(encoding="utf-8") as file:
        validate(json.load(file), dataset, "dataset")
    catalogs = {}
    for collection, key in (
        ("users", "user_id"),
        ("stays", "record_id"),
        ("requests", "record_id"),
        ("events", "event_id"),
        ("chat_history", "message_id"),
        ("devices", "device_id"),
        ("tracks", "track_id"),
        ("intents", "intent_id"),
        ("sleep_rules", "rule_id"),
    ):
        entries = dataset[collection]
        # В dev event_id/message_id повторяются у разных гостей: ключ составной.
        catalogs[collection] = {
            (
                (entry["user_id"], entry[key])
                if collection in ("events", "chat_history")
                else entry[key]
            ): entry
            for entry in entries
        }
        if len(catalogs[collection]) != len(entries):
            raise ValueError(f"{collection}: повторяющийся {key}")
    for collection in ("stays", "requests", "events", "chat_history"):
        for entry in dataset[collection]:
            if entry["user_id"] not in catalogs["users"]:
                raise ValueError(f"{collection}: неизвестный user_id")
    for request in dataset["requests"]:
        stay = catalogs["stays"].get(request["stay_id"])
        if stay is None or stay["user_id"] != request["user_id"]:
            raise ValueError("requests: заезд не принадлежит гостю")
        validate_settings(request["initial_state"], dataset["devices"])
    for event in dataset["events"]:
        if event["type"] == "conversation":
            for message_id in event["payload"]["message_ids"]:
                message = catalogs["chat_history"].get((event["user_id"], message_id))
                if message is None or message["user_id"] != event["user_id"]:
                    raise ValueError("events: сообщение не принадлежит гостю")
    for user in dataset["users"]:
        for track in (user.get("sleep_preferences") or {}).get("favorite_track_ids") or []:
            if track not in catalogs["tracks"]:
                raise ValueError("users: неизвестный favorite_track_id")
    for device in dataset["devices"]:
        if len({f["field_id"] for f in device["fields"]}) != len(device["fields"]):
            raise ValueError("devices: повторяющийся field_id")
        for field in device["fields"]:
            validate(field["value_schema"], field["default_value"], "device.default_value")


def validate_settings(settings, devices):
    """Частичный набор настроек {device_id: {field_id: value}}, без придуманных полей."""
    if not isinstance(settings, dict) or not settings:
        raise ValueError("settings: нужен непустой объект")
    catalog = {
        device["device_id"]: {f["field_id"]: f["value_schema"] for f in device["fields"]}
        for device in devices
    }
    for device_id, values in settings.items():
        if device_id not in catalog or not isinstance(values, dict) or not values:
            raise ValueError("settings: неизвестное устройство или пустые настройки")
        for field_id, value in values.items():
            if field_id not in catalog[device_id]:
                raise ValueError("settings: неизвестное поле устройства")
            validate(catalog[device_id][field_id], value, f"settings.{device_id}.{field_id}")


def validate_answers(answers):
    with (ROOT / "schemas" / "Case2Answers.schema.json").open(encoding="utf-8") as file:
        validate(json.load(file), answers, "answers")
