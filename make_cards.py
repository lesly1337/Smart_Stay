"""Создать карточку фактов и кандидатов для каждого заезда, без использования эталона."""

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path


def as_time(value):
    """Сравнивать моменты с их смещениями, а не строки или местное время."""
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError(f"Время без часового пояса: {value}")
    return result


def json_cell(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_cards(dataset):
    users = {user["user_id"]: user for user in dataset["users"]}
    if len(users) != len(dataset["users"]):
        raise ValueError("Повторяющийся user_id")
    if len({stay["record_id"] for stay in dataset["stays"]}) != len(dataset["stays"]):
        raise ValueError("Повторяющийся record_id заезда")
    cards = []
    for stay in dataset["stays"]:
        user = users[stay["user_id"]]
        cutoff = as_time(stay["check_in_at"])
        preferences = user.get("sleep_preferences") or {}
        evidence = []
        conversation = []
        for event in dataset.get("events", []):
            if event.get("user_id") != user["user_id"] or event.get("type") != "note":
                continue
            text = (event.get("payload") or {}).get("text") or ""
            if as_time(event["started_at"]) <= cutoff:
                evidence.append(
                    {
                        "kind": "note",
                        "source": event.get("source"),
                        "id": event.get("event_id"),
                        "at": event["started_at"],
                        "text": text,
                    }
                )
        for message in dataset.get("chat_history", []):
            if message.get("user_id") != user["user_id"]:
                continue
            text = message.get("text") or ""
            if as_time(message["at"]) <= cutoff:
                entry = {
                    "kind": "chat",
                    "source": message["role"],
                    "id": message.get("message_id"),
                    "at": message["at"],
                    "text": text,
                }
                conversation.append(entry)
                # Слова агента нужны для понимания «да, так», но не являются фактом о госте.
                if message["role"] == "user":
                    evidence.append(entry)
        evidence.sort(key=lambda item: as_time(item["at"]))
        conversation.sort(key=lambda item: as_time(item["at"]))
        cards.append(
            {
                "user_id": user["user_id"],
                "stay_id": stay["record_id"],
                "check_in_at": stay["check_in_at"],
                "home_timezone": user.get("timezone"),
                "hotel_timezone": stay.get("hotel_timezone"),
                "target_wake_at": stay.get("target_wake_at"),
                "chronotype": user.get("chronotype"),
                "weekday_bedtime": user.get("weekday_bedtime"),
                "weekday_wake_time": user.get("weekday_wake_time"),
                "goal": json_cell(user.get("goal")),
                # None, false и пустые списки различаются: они записываются как JSON.
                "temp_category": json_cell(preferences.get("temperature")),
                "light_sensitive": json_cell(preferences.get("light_sensitive")),
                "favorite_tracks": json_cell(preferences.get("favorite_track_ids")),
                "dislikes": json_cell(preferences.get("dislikes")),
                "alarm_attitude": json_cell(None),
                "like_home_settings": json_cell(None),
                "profile_source": "users.sleep_preferences",
                "evidence_json": json_cell(evidence),
                "conversation_json": json_cell(conversation),
            }
        )
    return cards


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("/tmp/smartstay-case2-dev.json"))
    parser.add_argument("--output", type=Path, default=Path("6_preference_cards.csv"))
    args = parser.parse_args()
    with args.input.open(encoding="utf-8") as file:
        response = json.load(file)
    cards = build_cards(response["dataset"])
    with args.output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file, fieldnames=list(cards[0]) if cards else ["user_id", "stay_id"]
        )
        writer.writeheader()
        writer.writerows(cards)
    print(f"Карточек: {len(cards)}; файл: {args.output}")
    print(
        "evidence_json — заметки и слова гостя; conversation_json — контекст диалогов, не выводы."
    )


if __name__ == "__main__":
    main()
