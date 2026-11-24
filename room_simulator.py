"""Веб-интерфейс одного настроенного dev-сеанса симулятора номера."""

import typing
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from threading import Lock, RLock
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, StrictBool, ValidationError
from interactive_room import interactive_rooms

router = APIRouter(prefix="/api/room")
operation_lock = RLock()
device_locks = {
    device: Lock() for device in ("light", "climate", "curtains", "sound", "alarm", "dnd")
}
device_names = {
    "light": "настройки света",
    "climate": "температуру",
    "curtains": "положение штор",
    "sound": "настройки звука",
    "alarm": "настройки будильника",
    "dnd": "режим «Не беспокоить»",
}


class InteractiveSessionRequest(BaseModel):
    renew: StrictBool = False


class LightUpdate(BaseModel):
    brightness: int = Field(ge=0, le=100, strict=True)
    color_temperature_k: typing.Optional[int] = Field(default=None, ge=2200, le=6500, strict=True)


class TemperatureUpdate(BaseModel):
    temperature: float = Field(ge=16, le=26, strict=True)


class CurtainsUpdate(BaseModel):
    position: int = Field(ge=0, le=100, strict=True)


class SoundUpdate(BaseModel):
    track_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    volume: int = Field(ge=0, le=100, strict=True)
    timer_minutes: typing.Optional[int] = Field(default=None, ge=0, le=1440, strict=True)


class AlarmUpdate(BaseModel):
    enabled: StrictBool
    time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    mode: Literal["light", "sound", "both"]


class DndUpdate(BaseModel):
    enabled: StrictBool


class Track(BaseModel):
    track_id: str
    title: str


@dataclass(frozen=True)
class SimulatorRoom:
    base_url: str
    token: str
    session_id: UUID
    at: datetime

    def request(self, path: str, body: typing.Optional[dict] = None, **query: str) -> dict:
        url = self.base_url + path
        if query:
            url += "?" + urlencode(query)
        headers = {"Authorization": f"Bearer {self.token}"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        try:
            with urlopen(Request(url, data=data, headers=headers), timeout=30) as response:
                result = json.load(response)
                if not isinstance(result, dict):
                    raise ValueError("Expected a JSON object")
                return result
        except HTTPError as error:
            if error.code == 401:
                detail = "Симулятор отклонил токен команды. Проверьте api.token."
            elif error.code in (404, 410):
                detail = "Сеанс симулятора не найден или истёк. Подключите свежий сеанс."
            elif error.code == 403:
                detail = "Доступ к dev-сеансу закрыт. Создайте новый сеанс управления."
            elif error.code == 409:
                interactive_rooms.mark_closed(self.session_id)
                raise HTTPException(
                    409, "Сеанс закрыт для изменений. Создайте новый сеанс управления."
                ) from error
            else:
                detail = f"Симулятор вернул HTTP {error.code}."
            status = 410 if error.code in (403, 404, 410) else 502
            raise HTTPException(status, detail) from error
        except (URLError, TimeoutError) as error:
            raise HTTPException(502, "Симулятор недоступен.") from error
        except ValueError as error:
            raise HTTPException(502, "Симулятор вернул некорректный ответ.") from error

    def state(self) -> dict:
        result = self.request(f"/room/{self.session_id}/state", at=self.at.isoformat())
        state = result.get("state")
        if not isinstance(state, dict):
            raise HTTPException(502, "Симулятор не вернул состояние номера.")
        return state

    def apply(self, device: str, values: dict) -> dict:
        with device_locks[device]:
            self.request(
                f"/room/{self.session_id}/action",
                {
                    "device_id": device,
                    "values": values,
                    "at": self.at.isoformat(),
                },
            )
            state = self.state()
        actual = state.get(device)
        if not isinstance(actual, dict) or any(
            key not in actual or actual[key] != expected for key, expected in values.items()
        ):
            raise HTTPException(502, f"Симулятор не подтвердил {device_names[device]}.")
        return actual


def configured_room() -> SimulatorRoom:
    session = interactive_rooms.get()
    return SimulatorRoom(session.base_url, session.run_token, session.session_id, session.at)


def checked_room(expected_session=None):
    room = configured_room()
    actual_context = (
        f"{room.session_id}|{room.at.isoformat()}"
        if expected_session and "|" in expected_session
        else str(room.session_id)
    )
    if expected_session and actual_context != expected_session:
        raise HTTPException(412, "Выбран другой сеанс. Обновите настройки номера.")
    return room


def apply_current(device, values, expected_session=None):
    with operation_lock:
        return checked_room(expected_session).apply(device, values)


@router.post("/session")
def open_interactive_session(data: InteractiveSessionRequest):
    with operation_lock:
        return interactive_rooms.create(renew=data.renew).public_info()


def light_settings(values):
    result = {"brightness": values["brightness"], "lightOn": values["brightness"] > 0}
    if "color_temperature_k" in values:
        result["color_temperature_k"] = values["color_temperature_k"]
    return result


@router.get("")
def get_room():
    values = configured_room().state()["light"]
    return light_settings(values)


@router.patch("/light")
def set_light(
    data: LightUpdate,
    expected_session: typing.Optional[str] = Header(default=None, alias="X-Room-Session"),
):
    actual = apply_current("light", data.model_dump(exclude_none=True), expected_session)
    return light_settings(actual)


def alarm_settings(state: dict, at: datetime) -> dict:
    alarm_at = state["at"]
    time = None
    if alarm_at is not None:
        alarm_time = datetime.fromisoformat(alarm_at)
        if alarm_time.utcoffset() is None:
            raise ValueError("Expected an alarm time with an offset")
        time = alarm_time.astimezone(at.tzinfo).strftime("%H:%M")
    return {"enabled": alarm_at is not None, "time": time, "mode": state["mode"]}


@router.get("/devices")
def get_device_settings():
    room = configured_room()
    state = room.state()
    try:
        return {
            "light": LightUpdate(**state["light"]),
            "climate": TemperatureUpdate(temperature=state["climate"]["temperature_c"]),
            "curtains": CurtainsUpdate(**state["curtains"]),
            "sound": SoundUpdate(**state["sound"]),
            "alarm": alarm_settings(state["alarm"], room.at),
            "dnd": DndUpdate(**state["dnd"]),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(502, "Симулятор вернул некорректные настройки номера.") from error


@lru_cache(maxsize=16)
def read_tracks(room: SimulatorRoom, run_id: str) -> tuple[Track, ...]:
    if not run_id:
        log = room.request(f"/room/{room.session_id}/log")
        try:
            run_id = log["session"]["run_id"]
        except (KeyError, TypeError) as error:
            raise HTTPException(502, "Симулятор не вернул идентификатор прогона.") from error
    catalog = room.request("/room/devices", run_id=run_id)
    try:
        tracks = tuple(Track.model_validate(track) for track in catalog["tracks"])
        if not tracks:
            raise ValueError("Empty track catalog")
        return tracks
    except (KeyError, TypeError, ValidationError, ValueError) as error:
        raise HTTPException(502, "Симулятор не вернул список треков.") from error


@router.get("/tracks")
def get_tracks():
    session = interactive_rooms.get()
    return read_tracks(configured_room(), str(session.run_id))


@router.get("/temperature")
def get_temperature():
    try:
        temperature = configured_room().state()["climate"]["temperature_c"]
        return TemperatureUpdate(temperature=temperature)
    except (KeyError, TypeError, ValidationError) as error:
        raise HTTPException(502, "Симулятор не вернул температуру.") from error


@router.patch("/temperature")
def set_temperature(
    data: TemperatureUpdate,
    expected_session: typing.Optional[str] = Header(default=None, alias="X-Room-Session"),
):
    actual = apply_current(
        "climate", {"temperature_c": math.floor(data.temperature + 0.5)}, expected_session
    )
    return {"temperature": actual["temperature_c"]}


@router.patch("/curtains")
def set_curtains(
    data: CurtainsUpdate,
    expected_session: typing.Optional[str] = Header(default=None, alias="X-Room-Session"),
):
    actual = apply_current("curtains", data.model_dump(), expected_session)
    return {"position": actual["position"]}


@router.patch("/sound")
def set_sound(
    data: SoundUpdate,
    expected_session: typing.Optional[str] = Header(default=None, alias="X-Room-Session"),
):
    actual = apply_current("sound", data.model_dump(exclude_none=True), expected_session)
    return {
        "track_id": actual["track_id"],
        "volume": actual["volume"],
        "timer_minutes": actual.get("timer_minutes", 0),
    }


@router.patch("/alarm")
def set_alarm(
    data: AlarmUpdate,
    expected_session: typing.Optional[str] = Header(default=None, alias="X-Room-Session"),
):
    with operation_lock:
        room = checked_room(expected_session)
        alarm_at = None
        if data.enabled:
            hour, minute = map(int, data.time.split(":"))
            occurrence = room.at.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if occurrence <= room.at:
                occurrence += timedelta(days=1)
            alarm_at = occurrence.isoformat()
        actual = room.apply("alarm", {"at": alarm_at, "mode": data.mode})
        return alarm_settings(actual, room.at)


@router.patch("/dnd")
def set_dnd(
    data: DndUpdate,
    expected_session: typing.Optional[str] = Header(default=None, alias="X-Room-Session"),
):
    actual = apply_current("dnd", data.model_dump(), expected_session)
    return {"enabled": actual["enabled"]}
