import copy
import json
import unittest

from case2_contracts import validate_answers, validate_dataset, validate_settings
from extract_preferences import FIELDS, extract_card, validate_result
from make_cards import build_cards


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.devices = [
            {
                "device_id": "climate",
                "fields": [
                    {
                        "field_id": "temperature_c",
                        "value_schema": {"type": "number", "minimum": 16, "maximum": 26},
                    }
                ],
            },
            {
                "device_id": "dnd",
                "fields": [{"field_id": "enabled", "value_schema": {"type": "boolean"}}],
            },
        ]
        self.tracks = [{"track_id": "track_04", "title": "Белый шум"}]
        self.dataset = {
            "users": [
                {
                    "user_id": "u",
                    "sleep_preferences": {
                        "temperature": "cool",
                        "light_sensitive": False,
                        "favorite_track_ids": [],
                        "dislikes": ["резкий звонок"],
                    },
                }
            ],
            "stays": [
                {"record_id": "s1", "user_id": "u", "check_in_at": "2026-11-12T18:00:00+03:00"},
                {"record_id": "s2", "user_id": "u", "check_in_at": "2026-11-13T18:00:00+03:00"},
            ],
            "events": [
                {
                    "event_id": "e1",
                    "user_id": "u",
                    "type": "note",
                    "source": "hotel",
                    "started_at": "2026-11-12T17:30:00+03:00",
                    "payload": {"text": "Предпочитает восемнадцать."},
                },
                {
                    "event_id": "e2",
                    "user_id": "u",
                    "type": "note",
                    "source": "app",
                    "started_at": "2026-11-12T16:00:00+00:00",
                    "payload": {"text": "Поздняя запись."},
                },
                {
                    "event_id": "e1",
                    "user_id": "other",
                    "type": "note",
                    "source": "hotel",
                    "started_at": "2026-11-12T17:30:00+03:00",
                    "payload": {"text": "Чужие настройки."},
                },
            ],
            "chat_history": [
                {
                    "message_id": "a1",
                    "user_id": "u",
                    "role": "agent",
                    "at": "2026-11-12T16:00:00+03:00",
                    "text": "Будить только светом?",
                },
                {
                    "message_id": "m1",
                    "user_id": "u",
                    "role": "user",
                    "at": "2026-11-12T16:01:00+03:00",
                    "text": "Да, именно.",
                },
            ],
            "requests": [{"user_id": "u", "utterances": [{"text": "Поставь 26 градусов"}]}],
        }
        self.card = build_cards(self.dataset)[0]
        self.raw = {field: {"value": None, "source_ids": [], "conflict": False} for field in FIELDS}

    def test_history_context_cutoff_and_scoping(self):
        first, second = build_cards(self.dataset)
        evidence = json.loads(first["evidence_json"])
        self.assertEqual([e["id"] for e in evidence], ["m1", "e1"])
        self.assertEqual(evidence[-1]["text"], "Предпочитает восемнадцать.")
        self.assertEqual([c["id"] for c in json.loads(first["conversation_json"])], ["a1", "m1"])
        self.assertEqual([e["id"] for e in json.loads(second["evidence_json"])], ["m1", "e1", "e2"])
        self.assertNotIn("26 градусов", first["evidence_json"])

    def test_profile_context_and_conflicts(self):
        self.raw["temperature"] = {"value": "warm", "source_ids": ["e1"], "conflict": False}
        self.raw["gentle_alarm"] = {
            "value": True,
            "source_ids": ["profile.sleep_preferences.dislikes"],
            "conflict": False,
        }
        self.raw["home_settings"] = {
            "value": {"climate": {"temperature_c": 22}},
            "source_ids": ["e1"],
            "conflict": True,
        }

        def fake(payload):
            self.assertEqual(payload["profile"]["sleep_preferences"]["temperature"], "cool")
            self.assertEqual(payload["conversation"][0]["source"], "agent")
            self.assertNotIn("reference", payload)
            return self.raw, {}

        result, _ = extract_card(self.card, self.tracks, self.devices, fake)
        self.assertEqual(result["fields"]["temperature"]["value"], "cool")
        self.assertIs(result["fields"]["light_sensitive"]["value"], False)
        self.assertEqual(result["fields"]["favorite_track_ids"]["value"], [])
        self.assertIs(result["fields"]["gentle_alarm"]["value"], True)
        self.assertIsNone(result["fields"]["home_settings"]["value"])

    def test_reject_unsupported_source_track_extra_keys(self):
        evidence = json.loads(self.card["evidence_json"])
        for field, value, sources in [
            ("gentle_alarm", True, ["a1"]),
            ("gentle_alarm", True, ["missing"]),
            ("temperature", "warm", []),
            ("favorite_track_ids", ["fake"], ["e1"]),
            ("favorite_track_ids", ["track_04", "track_04"], ["e1"]),
        ]:
            with self.subTest(field=field, sources=sources):
                raw = copy.deepcopy(self.raw)
                raw[field] = {"value": value, "source_ids": sources, "conflict": False}
                with self.assertRaises(ValueError):
                    validate_result(raw, evidence, self.tracks, self.devices)
        self.raw["temperature"]["unexpected"] = "value"
        with self.assertRaises(ValueError):
            validate_result(self.raw, evidence, self.tracks, self.devices)

    def test_device_values_are_checked(self):
        validate_settings(
            {"climate": {"temperature_c": 19.5}, "dnd": {"enabled": False}}, self.devices
        )
        for settings in [
            {"climate": {"temperature_c": 35}},
            {"climate": {"temperature_c": True}},
            {"dnd": {"enabled": 1}},
            {"sound": {"track_id": "fake"}},
            {"climate": {"unknown": 20}},
            {"sleep_sound": "Белый шум"},
            {},
        ]:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                validate_settings(settings, self.devices)

    def test_answers_contract(self):
        answer = {
            "stays": [{"record_id": "s1", "session_id": "session"}],
            "requests": [
                {
                    "record_id": "r1",
                    "session_id": "reqsession",
                    "replies": [
                        {
                            "role": "agent",
                            "at": "2026-11-12T19:00:00+03:00",
                            "text": "Не могу выполнить просьбу.",
                            "response_class": "refused",
                        }
                    ],
                }
            ],
        }
        validate_answers(answer)
        for key, value in [
            ("at", "2026-11-12T16:00:00Z"),
            ("at", "2026-02-30T12:00:00+03:00"),
            ("response_class", "сделал"),
            ("role", "user"),
        ]:
            invalid = copy.deepcopy(answer)
            invalid["requests"][0]["replies"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_answers(invalid)
        with self.assertRaises(ValueError):
            validate_answers({"result": answer})

    def test_dataset_ids_are_scoped_to_guest(self):
        # Минимальный полный набор по входной схеме, без файлов реального dev-набора.
        from case2_contracts import ROOT

        schema = json.loads((ROOT / "requests.json").read_text(encoding="utf-8"))
        user_fields = schema["properties"]["users"]["items"]["required"]
        users = [{**dict.fromkeys(user_fields), "user_id": uid} for uid in ("u", "v")]
        at = "2026-11-12T18:00:00+03:00"
        dataset = {
            "meta": {
                "schema_version": "0.3.0",
                "dataset_id": "test",
                "case_id": 2,
                "phase": "dev",
                "version": "1",
                "generated_at": at,
                "history_through": "2026-11-11",
            },
            "users": users,
            "stays": [
                {
                    "record_id": "s",
                    "user_id": "u",
                    "check_in_at": at,
                    "target_wake_at": "2026-11-13T07:00:00+03:00",
                    "hotel_timezone": "Europe/Moscow",
                }
            ],
            "events": [
                {
                    "event_id": "same",
                    "user_id": uid,
                    "started_at": at,
                    "ended_at": None,
                    "type": "conversation",
                    "source": "app",
                    "payload": {"message_ids": ["m1"]},
                }
                for uid in ("u", "v")
            ],
            "chat_history": [
                {"message_id": "m1", "user_id": uid, "role": "user", "at": at, "text": "Да."}
                for uid in ("u", "v")
            ],
            "requests": [],
            "devices": [
                {
                    "device_id": "dnd",
                    "title": "Не беспокоить",
                    "fields": [
                        {
                            "field_id": "enabled",
                            "description": "Включён",
                            "value_schema": {"type": "boolean"},
                            "default_value": False,
                            "unit": None,
                        }
                    ],
                }
            ],
            "tracks": [{"track_id": f"t{i}", "title": f"Трек {i}"} for i in range(12)],
            "intents": [
                {"intent_id": entry["const"], "description": entry["const"]}
                for entry in schema["properties"]["intents"]["items"]["properties"]["intent_id"][
                    "anyOf"
                ]
            ],
            "sleep_rules": [
                {"rule_id": f"R{i}", "version": "1", "description": f"Правило {i}"}
                for i in range(1, 9)
            ],
        }
        validate_dataset(dataset)
        dataset["events"][1]["payload"]["message_ids"] = ["missing"]
        with self.assertRaises(ValueError):
            validate_dataset(dataset)


if __name__ == "__main__":
    unittest.main()
