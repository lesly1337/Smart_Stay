"""HTTP API SmartStay: управление номером, планы гостей и проверка кейса 2."""

import logging
import os
from typing import Optional

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from case2_run import SimulatorError, solve_case2
from room_simulator import router as room_simulator
from interactive_guests import router as interactive_guests
from speech_api import router as speech_router
from deployment_settings import client_origins

TEAM = os.environ.get("TEAM", "unknown")

app = FastAPI(title=f"hackathon {TEAM}")
app.include_router(room_simulator)
app.include_router(interactive_guests)
app.include_router(speech_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=client_origins(),
    allow_methods=["GET", "PATCH", "POST"],
    allow_headers=["Content-Type", "X-Room-Session"],
)


@app.get("/")
def root() -> dict[str, str]:
    """Главная: показывает, какой команде принадлежит сервис."""
    return {"team": TEAM, "status": "ok"}


@app.get("/health")
def health() -> dict[str, str]:
    """Проверка живости для организаторов и мониторинга."""
    return {"team": TEAM, "status": "ok"}


class RunRequest(BaseModel):
    """Что стенд присылает в теле POST /run."""

    case: int = Field(ge=1, le=4)  # номер кейса, 1..4
    dataset_code: str = Field(min_length=1, max_length=128)  # код набора этапа (online или final)


@app.post("/run")
def run(
    req: RunRequest,
    authorization: Optional[str] = Header(default=None),
) -> JSONResponse:
    """Онлайн-проверка 20.11 и финал 22.11: этот метод вызывает сам стенд, без участия команды.

    Что придёт:
      - тело {"case": N, "dataset_code": "<код набора>"};
      - заголовок Authorization: Bearer <токен проверки>. Это не HACK_TEAM_TOKEN: токен действует
        только на время проверки и только для наборов этого этапа.

    Что сделать:
      1. Взять данные: GET {HACK_API_URL}/case/{case}/getData?dataset_code={dataset_code}
         с тем же заголовком Authorization, что пришёл сюда. Один раз, весь набор целиком.
      2. Посчитать ответ кейса (нейросеть — через LLM_BASE_URL, LLM_API_KEY, LLM_MODEL из env).

    Что вернуть: сам ответ кейса в теле этого ответа — HTTP 200, JSON в том же формате, что принимает
    POST {HACK_API_URL}/case/{case}/validate. В API ответ не сдавайте: стенд сохранит его сам.
    Стенд ждёт до 45 минут, потом попытка засчитывается как таймаут. В online одна попытка на кейс.

    Не печатайте токен, данные набора и ответы в логи и не возвращайте их в ответе.
    """
    if (
        not authorization
        or not authorization.startswith("Bearer ")
        or not authorization[7:].strip()
    ):
        return JSONResponse(
            status_code=401, content={"status": "error", "error": "нет Authorization: Bearer"}
        )
    if req.case != 2:
        return JSONResponse(
            status_code=501, content={"status": "not_implemented", "case": req.case}
        )
    try:
        answer = solve_case2(req.dataset_code, authorization)
    except SimulatorError as error:
        operation = (
            "getData"
            if error.endpoint.startswith("/case/2/getData")
            else error.endpoint.split("?")[0].rsplit("/", 1)[-1]
        )
        logging.getLogger(__name__).warning(
            "Case 2 API operation failed (%s, HTTP %s)", operation, error.status or "no response"
        )
        if error.endpoint.startswith("/case/2/getData") and error.status in (400, 401, 403, 404):
            status = error.status
        else:
            status = 502
        return JSONResponse(
            status_code=status,
            content={"detail": "API хакатона отклонил запрос или не вернул результат."},
        )
    except (ValueError, KeyError, TypeError) as error:
        logging.getLogger(__name__).warning(
            "Case 2 data or response rejected (%s)", type(error).__name__
        )
        return JSONResponse(
            status_code=502, content={"detail": "Не удалось подготовить корректный ответ кейса 2."}
        )
    return JSONResponse(content=answer)
