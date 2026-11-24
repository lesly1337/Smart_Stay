"""Отдельный dev-прогон для интерактивного управления номером."""

import typing
import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import Lock
from uuid import UUID

from fastapi import HTTPException

from case2_run import Case2Api, SimulatorError
from simulator_config import simulator_settings


@dataclass(frozen=True)
class InteractiveSession:
    base_url: str
    run_token: str
    run_id: UUID
    session_id: UUID
    at: datetime
    expires_at: datetime
    kind: str = "request"
    stay_id: typing.Optional[str] = None
    room_id: typing.Optional[str] = None

    def public_info(self):
        return {
            "run_id": str(self.run_id),
            "session_id": str(self.session_id),
            "at": self.at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "kind": self.kind,
            "stay_id": self.stay_id,
            "context_id": f"{self.session_id}|{self.at.isoformat()}",
        }


class InteractiveRooms:
    def __init__(self):
        self._lock = Lock()
        self._session = None
        self._closed = False
        self._dataset = None
        self._stay_id = None
        self._stay_sessions = {}

    def _active(self):
        if self._session is None:
            raise HTTPException(409, "Откройте сеанс управления номером.")
        if datetime.now(timezone.utc) >= self._session.expires_at:
            raise HTTPException(
                410, "45 минут dev-сеанса истекли. Создайте новый сеанс управления."
            )
        if self._closed:
            raise HTTPException(
                409, "Симулятор закрыл сеанс для изменений. Создайте новый сеанс управления."
            )
        return self._session

    def get(self):
        with self._lock:
            return self._active()

    def mark_closed(self, session_id):
        with self._lock:
            if self._session and self._session.session_id == session_id:
                self._closed = True

    def context(self):
        """Данные текущего UI-прогона остаются на сервере."""
        with self._lock:
            session = self._active()
            dataset = self._dataset
            if not dataset or not dataset.get("stays"):
                raise HTTPException(503, "Данные гостя пока недоступны.")
            stay = next((s for s in dataset["stays"] if s["record_id"] == self._stay_id), None)
            if stay is None:
                raise HTTPException(503, "Заезд гостя не найден.")
            return session, dataset, stay

    def select_stay(self, stay_id):
        session, dataset, _ = self.context()
        stay = next((s for s in dataset["stays"] if s["record_id"] == stay_id), None)
        if stay is None:
            raise HTTPException(404, "Заезд гостя не найден.")
        with self._lock:
            if self._session.kind == "stay" and self._stay_id == stay_id:
                return self._active()
            cached = self._stay_sessions.get(stay_id)
        if cached is None:
            try:
                opened = Case2Api(session.base_url, "Bearer " + session.run_token).open_session(
                    stay_id, "stay"
                )
                if opened["run_id"] != str(session.run_id):
                    raise ValueError("Unexpected run")
                cached = replace(
                    session,
                    session_id=UUID(opened["session_id"]),
                    at=datetime.fromisoformat(stay["check_in_at"]),
                    kind="stay",
                    stay_id=stay_id,
                    room_id=opened.get("room_id"),
                )
            except (SimulatorError, KeyError, ValueError, TypeError) as error:
                raise HTTPException(502, "Не удалось открыть сеанс плана отдыха.") from error
        with self._lock:
            if self._active().run_id != session.run_id:
                raise HTTPException(412, "Сеанс изменился. Обновите настройки номера.")
            self._stay_sessions[stay_id] = cached
            self._stay_id = stay_id
            self._session = cached
            return cached

    def set_time(self, at):
        session, _, stay = self.context()
        if session.kind != "stay":
            raise HTTPException(400, "Сначала примените план отдыха или выберите гостя.")
        if at.utcoffset() is None or not datetime.fromisoformat(
            stay["check_in_at"]
        ) <= at <= datetime.fromisoformat(stay["target_wake_at"]):
            raise HTTPException(400, "Время должно лежать между заселением и подъёмом.")
        with self._lock:
            self._session = replace(self._active(), at=at)
            self._stay_sessions[stay["record_id"]] = self._session
            return self._session

    def create(self, renew=False):
        with self._lock:
            if self._session is not None and not renew:
                return self._active()
            try:
                settings = simulator_settings()
            except ValueError as error:
                raise HTTPException(503, str(error)) from error
            base_url = (settings["HACK_API_URL"] or "https://hack-api.be-healthy.tech").rstrip("/")
            team_token = settings["HACK_TEAM_TOKEN"]
            if not team_token:
                raise HTTPException(
                    503, "На сервере не задан HACK_TEAM_TOKEN для управления номером."
                )
            api = Case2Api(base_url, f"Bearer {team_token}")
            try:
                # Командный токен открывает отдельный dev-прогон, независимый от /run.
                run = api.call("/runs", {"case": 2}, attempts=1)
                if run["stage"] != "dev":
                    raise ValueError("Expected a dev run")
                client = Case2Api(base_url, f"Bearer {run['run_token']}")
                dataset = client.call("/case/2/getData")["dataset"]
                records = dataset["requests"]
                configured_record = os.getenv("HACK_UI_RECORD_ID", "").strip()
                record = next(
                    (
                        row
                        for row in records
                        if not configured_record or row["record_id"] == configured_record
                    ),
                    None,
                )
                if record is None:
                    raise HTTPException(
                        503, "В dev-наборе не найдена запись для управления номером."
                    )
                session = client.open_session(record["record_id"], "request")
                if session["run_id"] != run["run_id"]:
                    raise ValueError("Unexpected session run")
                expiry = datetime.fromisoformat(run["expires_at"])
                instant = datetime.fromisoformat(session["at"])
                if expiry.utcoffset() is None or instant.utcoffset() is None:
                    raise ValueError("Expected timezone offsets")
                self._session = InteractiveSession(
                    base_url,
                    run["run_token"],
                    UUID(run["run_id"]),
                    UUID(session["session_id"]),
                    instant,
                    expiry,
                    stay_id=record.get("stay_id"),
                    room_id=session.get("room_id"),
                )
                self._dataset = dataset
                self._stay_id = record.get("stay_id") or next(
                    (s["record_id"] for s in dataset.get("stays", [])), None
                )
                self._stay_sessions = {}
                self._closed = False
                return self._active()
            except SimulatorError as error:
                raise HTTPException(
                    502, "Не удалось открыть dev-сеанс. Проверьте доступность API и токен команды."
                ) from error
            except (KeyError, ValueError, TypeError) as error:
                raise HTTPException(502, "API вернул некорректные данные dev-сеанса.") from error


interactive_rooms = InteractiveRooms()
