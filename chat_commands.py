"""Exact UI phrases; ambiguous requests stay with the contextual planner."""

import re
from datetime import datetime, timedelta

HELP_TEXT = (
    "Можно менять свет, температуру, шторы, звук, таймер, будильник и режим «Не беспокоить». "
    "Например: «яркость света 60 процентов», «температура 22 градуса», «включи шум дождя», "
    "«поставь таймер звука на 15 минут», «поставь будильник на 07:30»."
)


def is_help(text):
    return re.fullmatch(r"(?:помощь|команды|что ты умеешь)[?.!\s]*", text.strip(), re.I) is not None


def card_settings(payload):
    text = payload["utterances"][0]["text"].lower().replace("ё", "е").strip()
    text = re.sub(r"[.!?«»]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^пожалуйста | пожалуйста$", "", text)
    state = payload["initial_state"]

    if text in {"выключи не беспокоить", "отключи не беспокоить"}:
        return {"dnd": {"enabled": False}}
    if re.search(r"\b(?:не|нельзя)\b", text):
        return None

    match = re.fullmatch(
        r"(?:поставь |установи |сделай )?(яркость(?: света)?|громкость(?: звука)?|температур[ау]) (-?\d+(?:[.,]\d+)?)\s*(?:%|процентов|градуса?|градусов)?",
        text,
    )
    if match:
        name, number = match.groups()
        value = float(number.replace(",", "."))
        if name.startswith("температур"):
            return {"climate": {"temperature_c": value}}
        device, field = (
            ("light", "brightness") if name.startswith("яркость") else ("sound", "volume")
        )
        return {device: {field: int(value) if value.is_integer() else value}}

    if text in {"теплый свет", "сделай теплый свет", "холодный свет", "сделай холодный свет"}:
        return {"light": {"color_temperature_k": 2700 if "теплый" in text else 6500}}
    if text in {"громче", "сделай громче", "погромче", "сделай погромче"}:
        return {"sound": {"volume": min(100, state["sound"]["volume"] + 10)}}

    if text in {"отмени таймер", "отмени таймер звука", "выключи таймер звука"}:
        return {"sound": {"timer_minutes": 0}}
    match = re.fullmatch(
        r"(?:поставь|установи|запусти|ставь) таймер(?: звука| звуку)? на (\d+) (минут\w*|час\w*)",
        text,
    )
    if match:
        return {
            "sound": {"timer_minutes": int(match[1]) * (60 if match[2].startswith("час") else 1)}
        }
    if text in {"поставь таймер на полчаса", "поставь таймер звука на полчаса"}:
        return {"sound": {"timer_minutes": 30}}

    match = re.fullmatch(
        r"(?:поставь|поставить|установи|включи|ставь|разбуди(?: меня)?) (?:будильник )?(?:на |в )?(\d{1,2})[:\- ](\d{2})",
        text,
    )
    if match and int(match[1]) < 24 and int(match[2]) < 60:
        now = datetime.fromisoformat(payload["at"])
        at = now.replace(hour=int(match[1]), minute=int(match[2]), second=0, microsecond=0)
        if at <= now:
            at += timedelta(days=1)
        return {"alarm": {"at": at.isoformat()}}
    modes = {
        "будильник только светом": "light",
        "будильник светом": "light",
        "будильник только звуком": "sound",
        "будильник звуком": "sound",
        "будильник свет и звук": "both",
        "будильник вместе": "both",
    }
    if text in modes:
        return {"alarm": {"mode": modes[text]}}

    match = re.fullmatch(r"(?:включи|запусти|вруби) (?:звук )?(.+)", text)
    if match:
        query = match[1]
        aliases = {
            "дождь": "шум дождя",
            "костер": "камин",
            "океан": "морской прибой",
            "лес": "лесные птицы",
        }
        query = aliases.get(query, query)
        track = next(
            (
                track
                for track in payload["tracks"]
                if track["title"].lower().replace("ё", "е") == query
            ),
            None,
        )
        if track:
            return {
                "sound": {"track_id": track["track_id"], "volume": state["sound"]["volume"] or 20}
            }
    return None
