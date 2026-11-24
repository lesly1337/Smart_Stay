"""Планирование и ответы на одну просьбу гостя."""

import json
import copy
import logging
import re
from urllib.error import URLError

from case2_contracts import validate_settings
from extract_preferences import call_model
from make_cards import as_time
from request_handler import PROMPT as INTENT_PROMPT, RequestError
from request_handler import recognize_request, plan_request as plan_intent

REPLY_TEXT = {
    "apply": "Настройки номера подтверждены.",
    "acknowledge": "Понял.",
    "medical": "Я управляю настройками номера. За медицинской консультацией обратитесь к врачу.",
    "outside_room": "Я могу помочь с настройками номера. С этим вопросом обратитесь на стойку регистрации.",
    "out_of_range": "Такое значение выходит за допустимый диапазон устройства.",
    "unclear": "Уточните, какое устройство и какую настройку нужно изменить.",
    "unavailable": "Не удалось обработать просьбу. Попробуйте ещё раз.",
    "failed": "Симулятор не подтвердил эту настройку. Попробуйте ещё раз.",
}
DONE = {"apply", "acknowledge"}
PLANNED = DONE | {"medical", "outside_room", "out_of_range", "unclear"}
MODEL_ERRORS = (URLError, TimeoutError, ValueError, KeyError, TypeError, IndexError)


INTENT_REPLY_PROMPT = (
    INTENT_PROMPT
    + """
Вместо одного объекта верни {"replies":[{"intent":"...","parameters":{}}]}:
ровно по одному результату на каждую utterance, в исходном порядке.
Если первая реплика сообщает контекст, а вторая уточняет её, используй
intent acknowledge с parameters {} на первой, окончательное намерение на второй.
acknowledge допустим только перед следующей репликой; независимые просьбы
нужно обработать раздельно. Слова «только светом» уточняют предыдущий будильник.
Учитывай at как request_at. initial_state — текущее состояние.
preferences содержит готовые значения предпочтений, history — подтверждённые
настройки и предыдущие ответы. Если нужен обычный звук и известно несколько
любимых треков, выбери подходящий из favorite_track_ids, не выдумывай новый.
"""
)


def simple_intent(utterances):
    """Точные короткие команды сна; дополнительные слова требуют распознавания.

    Например, «проснулась» — управление номером, а жалоба после этого слова
    должна пройти обычную проверку медицинского содержания.
    """
    if len(utterances) != 1:
        return None
    text = re.sub(r"[^\w]+", " ", utterances[0]["text"].lower().replace("ё", "е")).strip()
    if text in {
        "ложусь",
        "я ложусь",
        "иду спать",
        "я иду спать",
        "я спать",
        "отбой",
        "все отбой",
        "все сплю",
        "все ложусь",
        "сплю",
    }:
        return {"intent": "going_to_bed", "parameters": {}}
    if text in {
        "встал",
        "встала",
        "я встал",
        "я встала",
        "проснулся",
        "проснулась",
        "я проснулся",
        "я проснулась",
    }:
        return {"intent": "woke_up", "parameters": {}}
    return None


def model_plan(payload):
    """Модель распознаёт смысл, код Лёши рассчитывает и проверяет настройки.

    Сохраняем отдельный результат каждой реплики и общий ограничитель частоты
    LLM-вызовов с подготовкой гостя. Команды отправляет только case2_run.
    """
    simple = simple_intent(payload["utterances"])
    result = (
        {"replies": [simple]}
        if simple
        else call_model(
            payload,
            prompt=INTENT_REPLY_PROMPT,
            max_tokens=1800,
            timeout=120,
        )[0]
    )
    decisions = result.get("replies") if isinstance(result, dict) else None
    if not isinstance(decisions, list) or len(decisions) != len(payload["utterances"]):
        raise ValueError("Неверное число распознанных реплик")
    devices = [
        {
            "device_id": device,
            "fields": [
                {"field_id": field, "value_schema": schema} for field, schema in fields.items()
            ],
        }
        for device, fields in payload["devices"].items()
    ]
    preferences = {
        "fields": {key: {"value": value} for key, value in payload["preferences"].items()}
    }
    state, replies = copy.deepcopy(payload["initial_state"]), []
    for index, decision in enumerate(decisions):
        reason, settings = "unclear", {}
        if decision == {"intent": "acknowledge", "parameters": {}} and index < len(decisions) - 1:
            reason = "acknowledge"
        else:
            try:
                recognized = recognize_request(
                    payload["utterances"][: index + 1],
                    state,
                    payload["history"],
                    preferences,
                    [],
                    request_at=payload["at"],
                    tracks=payload["tracks"],
                    model_call=lambda _: decision,
                )
                kind = recognized["intent"]
                if kind == "sound_on":
                    # Любимый трек можно восстановить из предпочтений, но его
                    # прежний таймер и громкость не являются новой командой.
                    text = " ".join(turn["text"] for turn in payload["utterances"][: index + 1])
                    if not re.search(r"таймер|минут|полчас|\bчас|timer|minute|hour", text, re.I):
                        recognized["parameters"].pop("timer_minutes", None)
                    if not re.search(
                        r"громк|тише|тихо|процент|%|volume|louder|quieter", text, re.I
                    ):
                        recognized["parameters"].pop("volume", None)
                if kind in ("medical", "out_of_scope", "invalid_value"):
                    reason = {
                        "medical": "medical",
                        "out_of_scope": "outside_room",
                        "invalid_value": "out_of_range",
                    }[kind]
                else:
                    # Каждая новая просьба имеет initial_state. Только явный сдвиг
                    # будильника может ссылаться на ранее подтверждённое время.
                    if kind == "alarm_shift" and not state.get("alarm", {}).get("at"):
                        for item in reversed(payload["history"]):
                            alarm = item.get("confirmed_settings", {}).get("alarm", {})
                            if "at" in alarm:
                                state.setdefault("alarm", {}).update(alarm)
                                break
                    settings = plan_intent(
                        recognized, state, devices, preferences, payload["tracks"], payload["at"]
                    )
                    if kind in ("like_home", "like_yesterday") and "alarm" in settings:
                        # Сохранённый режим может быть полезен, абсолютная дата
                        # будильника прошлого заезда не переносится в новый.
                        settings["alarm"].pop("at", None)
                        if not settings["alarm"]:
                            del settings["alarm"]
                        if not settings:
                            raise RequestError("Нет настроек для повторения.")
                    reason = "apply"
                    for device, values in settings.items():
                        state.setdefault(device, {}).update(values)
            except RequestError:
                reason, settings = "unclear", {}
        replies.append({"reason": reason, "settings": settings})
    return {"replies": replies}


def plan_request(record, initial, preferences, history, devices, tracks, planner=model_plan):
    utterances = record["utterances"]
    payload = {
        "at": record["at"],
        "utterances": utterances,
        "initial_state": initial,
        "preferences": preferences,
        "history": history,
        "devices": {
            device["device_id"]: {
                field["field_id"]: field["value_schema"] for field in device["fields"]
            }
            for device in devices
        },
        "tracks": tracks,
    }
    try:
        result = planner(payload)
        plans = result["replies"]
        if not isinstance(plans, list) or len(plans) != len(utterances):
            raise ValueError("Неверное число команд")
    except MODEL_ERRORS as error:
        logging.getLogger(__name__).warning(
            "Case 2 request model failed (%s, HTTP %s)",
            type(error).__name__,
            getattr(error, "code", None) or "n/a",
        )
        return [("unavailable", {}) for _ in utterances]

    decisions = []
    for plan in plans:
        try:
            reason, settings = plan["reason"], plan["settings"]
            if reason not in PLANNED or not isinstance(settings, dict):
                raise ValueError("Неверная команда")
            if reason == "apply":
                validate_settings(settings, devices)
                json.dumps(settings, allow_nan=False)
                alarm_at = settings.get("alarm", {}).get("at")
                if alarm_at is not None and as_time(alarm_at) <= as_time(record["at"]):
                    raise ValueError("Будильник должен быть в будущем")
            elif settings or (reason == "acknowledge" and len(plans) < 2):
                raise ValueError("Противоречивый ответ модели")
        except (ValueError, KeyError, TypeError):
            reason, settings = "out_of_range", {}
        decisions.append((reason, settings))
    return decisions


def make_reply(reason, at):
    return {
        "role": "agent",
        "at": at,
        "text": REPLY_TEXT[reason],
        "response_class": "done" if reason in DONE else "refused",
    }
