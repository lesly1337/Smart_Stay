"""Консервативное восстановление настроек из подтверждённых пар реплик.

Здесь не определяется постоянное предпочтение: добавляются только отдельные
настройки дома и прошлой ночи. Каждое значение проверяется по каталогу устройств.
"""

import copy
import re
from datetime import timedelta

from case2_contracts import validate_settings
from make_cards import as_time


_UNITS = {
    "ноль": 0,
    "один": 1,
    "одна": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
    "одиннадцать": 11,
    "двенадцать": 12,
    "тринадцать": 13,
    "четырнадцать": 14,
    "пятнадцать": 15,
    "шестнадцать": 16,
    "семнадцать": 17,
    "восемнадцать": 18,
    "девятнадцать": 19,
    "двадцать": 20,
    "тридцать": 30,
    "сорок": 40,
    "пятьдесят": 50,
    "шестьдесят": 60,
    "семьдесят": 70,
    "восемьдесят": 80,
    "девяносто": 90,
    "сто": 100,
}
_TENS = (
    "двадцать",
    "тридцать",
    "сорок",
    "пятьдесят",
    "шестьдесят",
    "семьдесят",
    "восемьдесят",
    "девяносто",
)
_SMALL = "|".join(sorted((word for word, n in _UNITS.items() if 0 < n < 10), key=len, reverse=True))
_COMPOUND = "|".join(t + r"\s+(?:" + _SMALL + ")" for t in _TENS)
_WORDS = "|".join(sorted(_UNITS, key=len, reverse=True))
_NUMBER = r"(?:\d+(?:[.,]\d+)?|" + _COMPOUND + "|" + _WORDS + r")\b"


def _number(text):
    text = text.strip().lower().replace(",", ".")
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        parts = text.split()
        if not parts or any(part not in _UNITS for part in parts):
            return None
        return sum(_UNITS[part] for part in parts)


def _capture(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE)
    return _number(match.group("number")) if match else None


def _uncertain(text):
    return bool(
        re.search(
            r"\b(?:не\s+(?:удалось|смог\w*|могу|получил\w*|установил\w*|включил\w*|сделал\w*|тепл\w*)|"
            r"ошибк\w*|попробу\w*|возможно|кажется|если)\b",
            text,
            re.IGNORECASE,
        )
    )


def _add_if_valid(settings, device, field, value, devices):
    try:
        validate_settings({device: {field: value}}, devices)
    except ValueError:
        return
    settings.setdefault(device, {})[field] = value


def _pairs(conversation):
    """Только соседние реплики одного диалога, без удалённых подтверждений."""
    for user, agent in zip(conversation, conversation[1:]):
        if (
            user.get("source") != "user"
            or agent.get("source") != "agent"
            or not user.get("id")
            or not agent.get("id")
        ):
            continue
        try:
            delta = as_time(agent["at"]) - as_time(user["at"])
        except (KeyError, TypeError, ValueError):
            continue
        if timedelta(0) <= delta <= timedelta(minutes=2):
            yield user, agent


def _confirmed_home_color(user, agent, devices):
    guest = user.get("text", "").lower().replace("ё", "е")
    reply = agent.get("text", "").lower().replace("ё", "е")
    # Агент должен явно сообщить, что записал именно домашнюю настройку;
    # вопрос, предложение и неподтверждённая реплика не считаются фактом.
    if not re.search(r"\b(?:обновил[аио]?|запомнил[аио]?|сохранил[аио]?)\s+домашн", reply):
        return None
    if (
        "?" in guest
        or "?" in reply
        or _uncertain(guest)
        or _uncertain(reply)
        or not re.search(r"дом(?:а|ашн|е|у|ой)", guest)
        or not re.search(r"свет|ламп|торшер|ночник", guest)
        or not re.search(r"тепл", guest)
        or re.search(r"не\s+тепл", guest)
        or not re.search(r"свет|ламп|торшер|ночник", reply)
    ):
        return None
    match = re.search(r"\b(\d{4})\s*(?:k|к|кельвин)", reply, re.IGNORECASE)
    if not match:
        return None
    value = int(match.group(1))
    # Противоречие явному значению или смыслу «тёплый» не принимаем.
    explicit = re.search(r"\b(\d{4})\s*(?:k|к|кельвин)", guest, re.IGNORECASE)
    if (explicit and int(explicit.group(1)) != value) or not 2200 <= value <= 3500:
        return None
    settings = {}
    _add_if_valid(settings, "light", "color_temperature_k", value, devices)
    return value if settings else None


def _confirmed_evening(user, agent, tracks, devices):
    guest, reply = user.get("text", "").lower(), agent.get("text", "").lower()
    if (
        "?" in guest
        or "?" in reply
        or _uncertain(guest)
        or _uncertain(reply)
        or not re.match(r"^\s*(?:готово|выполнено|сделано)\b", reply)
        or not re.search(r"\b(?:включи|поставь|установи|сделай|выставь)\b", guest)
        or re.search(r"\b(?:не|отмен\w*|откаж\w*)\s+(?:включ|став|дела|выполн)", guest)
    ):
        return {}
    plan = {}
    guest_temp = _capture(
        r"(?:сделай|поставь|установи|выставь)\s+(?P<number>" + _NUMBER + r")\s*(?:градус|°)", guest
    )
    agent_temp = _capture(
        r"(?:температур\w*\s*)?(?P<number>" + _NUMBER + r")\s*(?:°\s*c|градус)", reply
    )
    if guest_temp is not None and guest_temp == agent_temp:
        _add_if_valid(plan, "climate", "temperature_c", guest_temp, devices)
    guest_timer = _capture(r"таймер\s+(?:на\s+)?(?P<number>" + _NUMBER + r")\s*(?:минут)?", guest)
    agent_timer = _capture(r"таймер\s+(?:на\s+)?(?P<number>" + _NUMBER + r")\s*(?:минут)?", reply)
    if guest_timer is not None and guest_timer == agent_timer:
        _add_if_valid(plan, "sound", "timer_minutes", guest_timer, devices)
    matching_tracks = [
        track
        for track in tracks
        if isinstance(track.get("title"), str)
        and track["title"]
        and re.search(
            r"\b(?:включи|поставь|воспроизведи)\s+(?:мне\s+)?" + re.escape(track["title"].lower()),
            guest,
        )
        and track["title"].lower() in reply
    ]
    if len(matching_tracks) == 1:
        track = matching_tracks[0]
        _add_if_valid(plan, "sound", "track_id", track["track_id"], devices)
        title = re.escape(track["title"].lower())
        guest_volume = _capture(
            r"(?:" + title + r"|громкост\w*)\s+(?:на\s+)?(?P<number>" + _NUMBER + r")", guest
        )
        agent_volume = _capture(r"громкост\w*\s+(?:на\s+)?(?P<number>" + _NUMBER + r")", reply)
        if guest_volume is not None and guest_volume == agent_volume:
            _add_if_valid(plan, "sound", "volume", guest_volume, devices)
    return plan


def apply_confirmed_settings(fields, conversation, evidence, tracks, devices, check_in_at):
    """Добавить подтверждённые отсутствующие настройки, сохранив оба ID источников."""
    pairs = list(_pairs(conversation))
    home = fields.get("home_settings", {})
    suggestion = home.get("model_suggestion", {})
    current = home.get("value")
    if isinstance(current, dict) and not suggestion.get("conflict"):
        current = copy.deepcopy(current)
        if "color_temperature_k" not in current.get("light", {}):
            # Не примешиваем другую, потенциально устаревшую домашнюю запись.
            sources = suggestion.get("source_ids", [])
            for user, agent in reversed(pairs):
                if user["id"] not in sources:
                    continue
                color = _confirmed_home_color(user, agent, devices)
                if color is not None:
                    current.setdefault("light", {})["color_temperature_k"] = color
                    home["value"] = current
                    home["source"] = "model+confirmed_dialogue"
                    home["confirmed_sources"] = {
                        "light.color_temperature_k": {
                            "user_message_id": user["id"],
                            "agent_message_id": agent["id"],
                        }
                    }
                    break
    previous = fields.get("previous_evening_settings", {})
    if previous.get("value") is None and not previous.get("model_suggestion", {}).get("conflict"):
        check_in = as_time(check_in_at)
        for user, agent in reversed(pairs):
            at = as_time(user["at"])
            # Подтверждённая разовая команда — не привычка, но может описывать
            # последние настройки прошлой ночи для режима «как вчера».
            if not (at.hour >= 18 or at.hour < 4) or not timedelta(0) <= check_in - at <= timedelta(
                hours=36
            ):
                continue
            plan = _confirmed_evening(user, agent, tracks, devices)
            if not plan:
                continue
            # Более поздние сведения об этих устройствах требуют повторной оценки.
            if any(
                as_time(item["at"]) > as_time(agent["at"])
                and re.search(
                    r"температур|градус|°|зву[кч]|шум|громк|таймер|трек", item.get("text", ""), re.I
                )
                for item in evidence
            ):
                continue
            previous["value"] = plan
            previous["source"] = "confirmed_dialogue"
            previous["confirmed_sources"] = {
                "user_message_id": user["id"],
                "agent_message_id": agent["id"],
            }
            break
    return fields
