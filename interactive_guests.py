"""Планы и просьбы текущего гостя в отдельном интерактивном dev-прогоне."""

import typing
import copy
import hashlib
import json
import logging
import re
import math
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from case2_run import Case2Api, SimulatorError, unknown_preferences
from guest_requests import MODEL_ERRORS, make_reply, model_plan, plan_request, simple_intent
from guest_service import prepare_guest
from chat_commands import HELP_TEXT, card_settings, is_help
from interactive_room import interactive_rooms
from make_cards import as_time
from request_handler import RequestError, plan_request as plan_intent
from room_simulator import checked_room, configured_room, operation_lock

router = APIRouter(prefix="/api/room")
logger = logging.getLogger(__name__)


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def _digest(steps):
    return hashlib.sha256(json.dumps(steps, sort_keys=True).encode()).hexdigest()


def _whole_temperatures(result):
    """Use whole degrees for the interactive plan, including uploaded steps."""
    for step in result["scenario"]["scenario"]:
        if step["device_id"] == "climate" and "temperature_c" in step["values"]:
            step["values"]["temperature_c"] = math.floor(step["values"]["temperature_c"] + 0.5)
    return result


def _defaults(dataset):
    return {
        d["device_id"]: {f["field_id"]: f["default_value"] for f in d["fields"]}
        for d in dataset["devices"]
    }


def _at(steps, instant, dataset):
    state = _defaults(dataset)
    for step in steps:
        if as_time(step["at"]) <= instant:
            state[step["device_id"]].update(step["values"])
    return state


def _sound_text(sound, tracks):
    if not sound["volume"]:
        return "Звук выключен"
    title = next(
        (t["title"] for t in tracks if t["track_id"] == sound["track_id"]), "Выбранный звук"
    )
    return f"{title} · {sound['volume']}%" + (
        f" · {sound['timer_minutes']} мин" if sound.get("timer_minutes") else ""
    )


def _periods(result, dataset, stay):
    scenario = result["scenario"]
    steps = scenario["scenario"]
    bedtime, wake = as_time(scenario["bedtime_at"]), as_time(stay["target_wake_at"])
    evening = max(as_time(stay["check_in_at"]), bedtime - timedelta(hours=1))
    dawn = min(
        as_time(s["at"])
        for s in steps
        if s["device_id"] == "light"
        and bedtime < as_time(s["at"]) < wake
        and s["values"].get("brightness", 0) > 0
    )
    modes = {"light": "светом", "sound": "звуком", "both": "светом и звуком"}
    periods = []
    for key, title, start, end, point in [
        ("evening", "Вечер", evening, bedtime, evening),
        ("night", "Ночь", bedtime, dawn, bedtime + timedelta(minutes=5)),
        ("morning", "Утро", dawn, wake, dawn),
    ]:
        state = _at(steps, point, dataset)
        temp = str(math.floor(state["climate"]["temperature_c"] + 0.5))
        light = state["light"]
        light_text = (
            "свет выключен"
            if not light["brightness"]
            else f"свет {light['brightness']}% · {light['color_temperature_k']} K"
        )
        if key == "morning":
            levels = [
                str(s["values"]["brightness"])
                for s in steps
                if s["device_id"] == "light"
                and dawn <= as_time(s["at"]) < wake
                and "brightness" in s["values"]
            ]
            details = [
                "Плавный рассвет: " + " → ".join(levels) + "%",
                f"Подъём в {wake:%H:%M} · будильник {modes[state['alarm']['mode']]}",
            ]
        else:
            details = [f"{temp} °C · {light_text}", _sound_text(state["sound"], dataset["tracks"])]
            if key == "night":
                details.append("Шторы закрыты · «Не беспокоить» включён")
        periods.append(
            {
                "id": key,
                "title": title,
                "tone": "neutral" if key == "night" else "warm",
                "times": (
                    [f"{start:%H:%M} –", f"{end:%H:%M}"] if key == "morning" else [f"{start:%H:%M}"]
                ),
                "timeLabel": f"С {start:%H:%M} до {end:%H:%M}",
                "details": details,
                "at": point.isoformat(),
                "from": start.isoformat(),
                "until": end.isoformat(),
            }
        )
    return periods


def _short_plan(payload):
    """Точные команды интерфейса; произвольные формулировки идут в общий обработчик."""
    text = payload["utterances"][0]["text"]
    normalized = re.sub(r"[^\w]+", " ", text.lower().replace("ё", "е")).strip()
    if re.search(
        r"\b(?:таблетк\w*|лекарств\w*|врач\w*)\b|что (?:принять|выпить)|сердце (?:колотится|болит)",
        normalized,
    ):
        return {"replies": [{"reason": "medical", "settings": {}}]}
    direct_settings = card_settings(payload)
    if direct_settings is not None:
        return {"replies": [{"reason": "apply", "settings": direct_settings}]}
    params, kind = {}, None
    aliases = {
        "warmer": {"теплее", "холодно", "мне холодно", "сделай теплее", "сделай потеплее"},
        "cooler": {
            "жарко",
            "мне жарко",
            "прохладнее",
            "холоднее",
            "сделай прохладнее",
            "сделай холоднее",
        },
        "brighter": {"ярче", "сделай ярче", "добавь света"},
        "dimmer": {"приглуши свет", "сделай свет тише", "убавь свет"},
        "quieter": {"тише", "потише", "сделай потише"},
        "all_off": {"выключи все", "отключи все"},
        "like_home": {"как дома", "сделай как дома"},
        "like_yesterday": {"как вчера", "сделай как вчера"},
        "alarm_cancel": {"отмени будильник", "выключи будильник", "отключи будильник"},
    }
    simple = simple_intent(payload["utterances"])
    if simple:
        kind = simple["intent"]
    for name, texts in aliases.items():
        if normalized in texts:
            kind = name
    direct = None
    state = payload["initial_state"]
    if normalized in {"выключи свет", "отключи свет", "погаси свет"}:
        direct = {"light": {"brightness": 0}}
    elif normalized in {"включи свет", "зажги свет"}:
        direct = {"light": {"brightness": state["light"]["brightness"] or 20}}
    elif normalized in {"выключи звук", "отключи звук", "выключи музыку"}:
        direct = {"sound": {"volume": 0, "timer_minutes": 0}}
    elif normalized in {"открой шторы", "закрой шторы"}:
        kind, params = "curtains", {"position": 100 if normalized.startswith("открой") else 0}
    elif normalized in {
        "не беспокоить",
        "включи не беспокоить",
        "включи режим не беспокоить",
        "выключи режим не беспокоить",
    }:
        kind, params = "do_not_disturb", {"enabled": not normalized.startswith("выключи")}
    elif normalized == "включи звук":
        kind, params = "sound_on", {"track_id": state["sound"]["track_id"]}
    if direct is not None:
        return {"replies": [{"reason": "apply", "settings": direct}]}
    explicit = re.fullmatch(
        r"(?:поставь|установи|сделай)\s+(?:температуру\s+)?(\d+(?:[.,]\d+)?)\s*(?:°\s*[cс]?|градус\w*)",
        text.strip().lower(),
    )
    if explicit:
        kind, params = "set_temperature", {"value": float(explicit[1].replace(",", "."))}
    if kind is None:
        return model_plan(payload)
    devices = [
        {"device_id": d, "fields": [{"field_id": f, "value_schema": s} for f, s in fields.items()]}
        for d, fields in payload["devices"].items()
    ]
    preferences = {"fields": {k: {"value": v} for k, v in payload["preferences"].items()}}
    try:
        settings = plan_intent(
            {"intent": kind, "parameters": params},
            state,
            devices,
            preferences,
            payload["tracks"],
            payload["at"],
        )
        if kind in ("like_home", "like_yesterday") and "alarm" in settings:
            settings["alarm"].pop("at", None)
            if not settings["alarm"]:
                del settings["alarm"]
        return {"replies": [{"reason": "apply", "settings": settings}]}
    except RequestError:
        return {"replies": [{"reason": "unclear", "settings": {}}]}


class GuestPlans:
    def __init__(self, rooms=interactive_rooms):
        self.rooms = rooms
        self._lock = Lock()
        self._cards = {}
        self._applied = {}
        self._preparing = set()
        self._history = {}
        self._pending = set()
        self._commands = {}

    def guests(self):
        session, dataset, current = self.rooms.context()
        users = {u["user_id"]: i + 1 for i, u in enumerate(dataset["users"])}
        return {
            "current_stay_id": current["record_id"],
            "session": session.public_info(),
            "guests": [
                {
                    "stay_id": s["record_id"],
                    "label": f"Гость №{users[s['user_id']]}",
                    "check_in_at": s["check_in_at"],
                    "target_wake_at": s["target_wake_at"],
                    "hotel_timezone": s["hotel_timezone"],
                }
                for s in dataset["stays"]
            ],
        }

    def _card(self):
        session, dataset, stay = self.rooms.context()
        key = (str(session.run_id), stay["record_id"])
        with self._lock:
            card = self._cards.get(key)
        if card is None:
            result = _whole_temperatures(
                prepare_guest(dataset, stay["record_id"], model_call=unknown_preferences)
            )
            card = {"result": result, "source": "profile", "updated_at": _stamp()}
            with self._lock:
                if len(self._cards) > 50:
                    self._cards.clear()
                    self._history.clear()
                    self._applied.clear()
                    self._commands.clear()
                card = self._cards.setdefault(key, card)
        return session, dataset, stay, key, card

    def view(self):
        session, dataset, stay, key, card = self._card()
        result = card["result"]
        fields = result["preferences"]["fields"]
        guest = next(x for x in self.guests()["guests"] if x["stay_id"] == stay["record_id"])
        return {
            "stay": dict(stay, label=guest["label"]),
            "session": session.public_info(),
            "status": (
                "applied"
                if self._applied.get(key) == _digest(result["scenario"]["scenario"])
                else "draft"
            ),
            "personalization": card["source"],
            "updated_at": card["updated_at"],
            "preferences": {
                name: {"value": f["value"], "source": f["source"]} for name, f in fields.items()
            },
            "assumptions": result["scenario"]["assumptions"],
            "bedtime_at": result["scenario"]["bedtime_at"],
            "timezone_difference_hours": result["scenario"]["timezone_difference_hours"],
            "periods": _periods(result, dataset, stay),
            "steps": result["scenario"]["scenario"],
        }

    def personalize(self):
        session, dataset, stay, key, card = self._card()
        with self._lock:
            if key in self._preparing:
                raise HTTPException(425, "План по истории уже готовится.")
            cached = card["source"] == "history"
            if not cached:
                self._preparing.add(key)
        if cached:
            return self.view()
        try:
            try:
                result = _whole_temperatures(prepare_guest(dataset, stay["record_id"]))
            except MODEL_ERRORS as error:
                logger.warning(
                    "UI guest preparation failed (%s, HTTP %s)",
                    type(error).__name__,
                    getattr(error, "code", None),
                )
                raise HTTPException(
                    503, "Персонализация по истории временно недоступна. План по анкете сохранён."
                ) from error
            current, _, _ = self.rooms.context()
            if current.run_id != session.run_id:
                raise HTTPException(412, "Сеанс изменился. Обновите план.")
            with self._lock:
                self._cards[key] = {"result": result, "source": "history", "updated_at": _stamp()}
            return self.view()
        finally:
            with self._lock:
                self._preparing.discard(key)

    def apply(self, expected_session=None):
        with operation_lock:
            checked_room(expected_session)
            session, _, stay, key, card = self._card()
            session = self.rooms.select_stay(stay["record_id"])
            api = Case2Api(session.base_url, "Bearer " + session.run_token)
            steps = card["result"]["scenario"]["scenario"]
            try:
                api.upload(str(session.session_id), steps)
                log = api.call(f"/room/{session.session_id}/log")
                entries = [
                    entry for entry in log.get("entries", []) if entry.get("kind") == "scenario"
                ]
                recorded = entries[-1]["steps"] if entries else []
                normalize = lambda rows: [
                    (as_time(s["at"]), s["device_id"], s["values"]) for s in rows
                ]
                if log.get("session", {}).get("run_id") != str(session.run_id) or normalize(
                    recorded
                ) != normalize(steps):
                    raise ValueError("Scenario not confirmed by log")
                configured_room().state()
            except SimulatorError as error:
                if error.status == 409:
                    self.rooms.mark_closed(session.session_id)
                    raise HTTPException(
                        409, "Сеанс закрыт. Создайте новый сеанс управления."
                    ) from error
                if error.status in (403, 404, 410):
                    raise HTTPException(
                        410, "Доступ к сеансу истёк. Создайте новый сеанс управления."
                    ) from error
                raise HTTPException(
                    502, "Не удалось подтвердить загрузку плана в симулятор."
                ) from error
            except (ValueError, KeyError, TypeError) as error:
                raise HTTPException(502, "Симулятор не подтвердил загруженный план.") from error
            with self._lock:
                self._applied[key] = _digest(steps)
            return self.view()

    def select(self, stay_id, expected_session=None):
        with operation_lock:
            checked_room(expected_session)
            self.rooms.select_stay(stay_id)
            return self.view()

    def clock(self, at, expected_session=None):
        with operation_lock:
            checked_room(expected_session)
            old, _, stay = self.rooms.context()
            at = (
                at.astimezone(ZoneInfo(stay["hotel_timezone"]))
                if at.utcoffset() is not None
                else at
            )
            self.rooms.set_time(at)
            try:
                configured_room().state()
            except HTTPException:
                self.rooms.set_time(old.at)
                raise
            return self.view()

    def command(self, text, command_id, expected_session=None):
        with operation_lock:
            room = checked_room(expected_session)
            session, dataset, stay, key, card = self._card()
            request_key = (str(session.session_id), str(command_id))
            initial = room.state()
            with self._lock:
                cached = self._commands.get(request_key)
                if cached:
                    return copy.deepcopy(cached)
                if key in self._pending:
                    raise HTTPException(425, "Предыдущая просьба ещё выполняется.")
                self._pending.add(key)
                history = copy.deepcopy(self._history.get(key, []))
        at = session.at.isoformat()
        utterances = [{"role": "user", "at": at, "text": text}]
        try:
            preferences = {
                k: v["value"] for k, v in card["result"]["preferences"]["fields"].items()
            }
            plans = (
                [("help", {})]
                if is_help(text)
                else plan_request(
                    {"at": at, "utterances": utterances},
                    initial,
                    preferences,
                    history,
                    dataset["devices"],
                    dataset["tracks"],
                    planner=_short_plan,
                )
            )
            if any(reason == "unavailable" for reason, _ in plans):
                raise HTTPException(
                    503,
                    "Помощник временно недоступен. Можно изменить настройки в разделе «Управление».",
                )
            with operation_lock:
                current, _, current_stay = self.rooms.context()
                if (
                    current.session_id != session.session_id
                    or current.at != session.at
                    or current_stay["record_id"] != stay["record_id"]
                ):
                    raise HTTPException(
                        412, "За время обработки изменился сеанс или время. Повторите просьбу."
                    )
                room = configured_room()
                if room.state() != initial:
                    raise HTTPException(
                        412, "Настройки изменились во время обработки. Повторите просьбу."
                    )
                confirmed, replies = {}, []
                for reason, settings in plans:
                    if reason == "acknowledge":
                        continue
                    if reason == "apply":
                        try:
                            for device, values in settings.items():
                                if device == "climate" and "temperature_c" in values:
                                    values = dict(
                                        values,
                                        temperature_c=math.floor(values["temperature_c"] + 0.5),
                                    )
                                room.apply(device, values)
                                confirmed.setdefault(device, {}).update(values)
                        except HTTPException as error:
                            if error.status_code in (409, 410):
                                raise
                            reason = "failed"
                    reply = make_reply("apply" if reason == "help" else reason, at)
                    if reason == "help":
                        reply["text"] = HELP_TEXT
                    if reason == "failed":
                        reply["text"] = (
                            "Не удалось подтвердить все изменения. Часть настроек могла измениться."
                        )
                    replies.append(reply)
                answer = {
                    "command_id": str(command_id),
                    "session": current.public_info(),
                    "replies": replies,
                    "confirmed_settings": confirmed,
                }
                with self._lock:
                    self._history.setdefault(key, []).append(
                        {
                            "at": at,
                            "utterances": [text],
                            "replies": [r["response_class"] for r in replies],
                            "reply_texts": [r["text"] for r in replies],
                            "confirmed_settings": confirmed,
                        }
                    )
                    self._commands[request_key] = copy.deepcopy(answer)
                return answer
        finally:
            with self._lock:
                self._pending.discard(key)


guest_plans = GuestPlans()


class GuestSelection(BaseModel):
    stay_id: str = Field(min_length=1, max_length=128)


class ClockSelection(BaseModel):
    at: datetime


class GuestCommand(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    command_id: UUID = Field(default_factory=uuid4)


@router.get("/guests")
def get_guests():
    return guest_plans.guests()


@router.post("/guest")
def select_guest(
    data: GuestSelection,
    expected_session: typing.Optional[str] = Header(default=None, alias="X-Room-Session"),
):
    return guest_plans.select(data.stay_id, expected_session)


@router.get("/plan")
def get_plan():
    return guest_plans.view()


@router.post("/plan/prepare")
def prepare_plan():
    return guest_plans.personalize()


@router.post("/plan/apply")
def apply_plan(
    expected_session: typing.Optional[str] = Header(default=None, alias="X-Room-Session")
):
    return guest_plans.apply(expected_session)


@router.post("/time")
def set_time(
    data: ClockSelection,
    expected_session: typing.Optional[str] = Header(default=None, alias="X-Room-Session"),
):
    return guest_plans.clock(data.at, expected_session)


@router.post("/command")
def send_command(
    data: GuestCommand,
    expected_session: typing.Optional[str] = Header(default=None, alias="X-Room-Session"),
):
    if not data.text.strip():
        raise HTTPException(422, "Напишите просьбу.")
    return guest_plans.command(data.text.strip(), data.command_id, expected_session)
