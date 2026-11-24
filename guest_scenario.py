"""Построение чернового сценария на основе извлечённой карточки гостя.

Это внутренний формат; загрузка в симулятор и ответ Case2Answers — задача сервера.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from case2_contracts import validate_settings


def local_bedtime(context):
    """Вариант R8: перевести домашний отбой в пояс отеля и сдвинуть на час к местному."""
    if not context.get("weekday_bedtime") or not context.get("home_timezone"):
        raise ValueError("Для сценария нужны привычный отбой и домашний часовой пояс")
    home = ZoneInfo(context["home_timezone"])
    hotel = ZoneInfo(context["hotel_timezone"])
    wake = datetime.fromisoformat(context["target_wake_at"])
    if wake.utcoffset() is None:
        raise ValueError("Время подъёма должно содержать смещение")
    home_wake = wake.astimezone(home)
    clock = time.fromisoformat(context["weekday_bedtime"])
    if clock.tzinfo is not None or clock.second or clock.microsecond:
        raise ValueError("Время отбоя должно быть в формате HH:MM")
    bedtime = datetime.combine(home_wake.date(), clock, tzinfo=home)
    if bedtime >= home_wake:
        bedtime -= timedelta(days=1)
    bedtime = bedtime.astimezone(hotel)
    offset = (bedtime.utcoffset() - bedtime.astimezone(home).utcoffset()).total_seconds() / 3600
    if offset >= 3:
        bedtime -= timedelta(hours=1)
    elif offset <= -3:
        bedtime += timedelta(hours=1)
    return bedtime, offset


def build_scenario(card, devices, tracks):
    """Вернуть шаги и допущения; каждый шаг содержит at, device_id и values."""
    context, fields = card["context"], card["fields"]
    check_in = datetime.fromisoformat(context["check_in_at"])
    wake = datetime.fromisoformat(context["target_wake_at"])
    if check_in.utcoffset() is None or wake.utcoffset() is None:
        raise ValueError("Время заселения и подъёма должно содержать смещение")
    hotel = ZoneInfo(context["hotel_timezone"])
    check_in, wake = check_in.astimezone(hotel), wake.astimezone(hotel)
    bedtime, offset = local_bedtime(context)
    if not check_in < bedtime or not bedtime < wake - timedelta(minutes=30):
        raise ValueError("Невозможно построить вечер, сон и рассвет в интервале заезда")

    category = fields["temperature"]["value"]
    if category not in (None, "cool", "normal", "warm"):
        raise ValueError("Неизвестная категория температуры")
    temp = {"cool": 17.5, "normal": 19.5, "warm": 21.5, None: 19.5}[category]
    preferred_tracks = fields["favorite_track_ids"]["value"]
    if preferred_tracks is not None and not isinstance(preferred_tracks, list):
        raise ValueError("Любимые треки должны быть списком или null")
    track_ids = {track["track_id"] for track in tracks}
    if preferred_tracks and any(track not in track_ids for track in preferred_tracks):
        raise ValueError("Неизвестный трек")
    gentle = fields["gentle_alarm"]["value"]
    if gentle is not None and type(gentle) is not bool:
        raise ValueError("gentle_alarm должен быть boolean или null")
    assumptions = []
    if category is None:
        assumptions.append("Температура сна неизвестна: выбран стандарт R3 19,5 °C.")
    if preferred_tracks is None:
        assumptions.append("Любимые звуки неизвестны: звук выключен; R4 требует уточнения.")
    if gentle is None:
        assumptions.append("Отношение к резкому будильнику неизвестно: выбран режим света и звука.")

    scenario = []

    def add(at, device, values):
        if not check_in <= at <= wake:
            raise ValueError("Шаг вне интервала заезда")
        validate_settings({device: values}, devices)
        scenario.append(
            {"at": at.isoformat(timespec="seconds"), "device_id": device, "values": values}
        )

    add(check_in, "climate", {"temperature_c": temp})
    add(check_in, "curtains", {"position": 0})
    add(
        check_in,
        "alarm",
        {
            "at": wake.isoformat(timespec="seconds"),
            "mode": "light" if gentle is True else "both",
            "window_minutes": 0,
        },
    )
    add(check_in, "sound", {"volume": 0})
    wind_down = max(check_in, bedtime - timedelta(minutes=60))
    if check_in < wind_down:
        add(check_in, "light", {"brightness": 50, "color_temperature_k": 3000})
    add(wind_down, "light", {"brightness": 20, "color_temperature_k": 2700})
    add(bedtime, "light", {"brightness": 0})
    add(bedtime, "dnd", {"enabled": True})
    if preferred_tracks:
        add(bedtime, "sound", {"track_id": preferred_tracks[0], "volume": 15, "timer_minutes": 30})
    else:
        add(bedtime, "sound", {"volume": 0})
    for minutes, brightness in ((25, 10), (20, 30), (15, 50)):
        add(wake - timedelta(minutes=minutes), "light", {"brightness": brightness})
    # Пожелание открыть шторы учитывается только после подъёма; сон защищён до рассвета.
    add(wake, "dnd", {"enabled": False})
    scenario.sort(key=lambda step: datetime.fromisoformat(step["at"]))
    return {
        "user_id": card["user_id"],
        "stay_id": card["stay_id"],
        "bedtime_at": bedtime.isoformat(timespec="seconds"),
        "timezone_difference_hours": offset,
        "scenario": scenario,
        "assumptions": assumptions,
    }
