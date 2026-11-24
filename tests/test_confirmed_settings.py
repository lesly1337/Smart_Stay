import copy
import json
import unittest
from pathlib import Path

from confirmed_settings import apply_confirmed_settings
from guest_service import prepare_guest

ROOT = Path(__file__).resolve().parents[1]


def message(role, identifier, at, text):
    return {"kind": "chat", "source": role, "id": identifier, "at": at, "text": text}


class ConfirmedSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads((ROOT / "examples/guest_input.json").read_text(encoding="utf-8"))[
            "dataset"
        ]
        cls.devices = cls.dataset["devices"]
        cls.tracks = cls.dataset["tracks"]
        cls.raw = json.loads(
            (ROOT / "examples/guest_model_response.json").read_text(encoding="utf-8")
        )

    def fields(self):
        return {
            "home_settings": {
                "value": {"light": {"brightness": 33}},
                "source": "model",
                "model_suggestion": {"source_ids": ["u"], "conflict": False},
            },
            "previous_evening_settings": {
                "value": None,
                "source": "unknown",
                "model_suggestion": {"source_ids": [], "conflict": False},
            },
        }

    def apply(self, fields, conversation, evidence=None):
        return apply_confirmed_settings(
            fields,
            conversation,
            evidence or [],
            self.tracks,
            self.devices,
            "2026-11-12T18:30:00+03:00",
        )

    def test_home_color_added_only_from_matching_confirmation(self):
        guest = message(
            "user", "u", "2026-10-28T21:30:00+03:00", "Дома поставила тёплую лампу и убавила свет."
        )
        reply = message(
            "agent",
            "a",
            "2026-10-28T21:31:00+03:00",
            "Обновила домашние настройки: тёплый свет около 2700 K.",
        )
        fields = self.apply(self.fields(), [guest, reply])
        self.assertEqual(
            fields["home_settings"]["value"]["light"],
            {"brightness": 33, "color_temperature_k": 2700},
        )
        self.assertEqual(
            fields["home_settings"]["confirmed_sources"]["light.color_temperature_k"],
            {"user_message_id": "u", "agent_message_id": "a"},
        )

    def test_home_rejects_unconfirmed_unrelated_or_contradicting_claims(self):
        guest = message("user", "u", "2026-10-28T21:30:00+03:00", "Дома поставила тёплую лампу.")
        reply = message(
            "agent",
            "a",
            "2026-10-28T21:31:00+03:00",
            "Обновила домашние настройки: тёплый свет около 2700 K.",
        )
        cases = [
            ([guest], "missing"),
            ([guest, {**reply, "text": "Могу включить свет около 2700 K?"}], "suggestion"),
            ([{**guest, "id": "other"}, reply], "unrelated source"),
            (
                [guest, {**reply, "text": "Обновила домашние настройки: свет 6500 K."}],
                "contradiction",
            ),
            ([{**guest, "text": "Дома поставила не тёплую лампу."}, reply], "negation"),
            ([guest, {**reply, "at": "2026-10-28T21:33:00+03:00"}], "late"),
        ]
        for conversation, label in cases:
            with self.subTest(label=label):
                result = self.apply(self.fields(), conversation)
                self.assertNotIn("color_temperature_k", result["home_settings"]["value"]["light"])
        uncertain = {
            **reply,
            "text": "Обновила домашние настройки, но не удалось установить свет 2700 K.",
        }
        result = self.apply(self.fields(), [guest, uncertain])
        self.assertNotIn("color_temperature_k", result["home_settings"]["value"]["light"])
        fields = self.fields()
        fields["home_settings"]["model_suggestion"]["conflict"] = True
        self.assertNotIn(
            "color_temperature_k",
            self.apply(fields, [guest, reply])["home_settings"]["value"]["light"],
        )

    def test_confirmed_evening_settings_and_source_ids(self):
        guest = message(
            "user",
            "u",
            "2026-11-11T23:05:00+03:00",
            "Включи белый шум на двадцать и таймер на сорок минут. И сделай двадцать градусов.",
        )
        reply = message(
            "agent",
            "a",
            "2026-11-11T23:05:30+03:00",
            "Готово: «Белый шум» на громкости 20, таймер 40 минут, температура 20 °C.",
        )
        result = self.apply(self.fields(), [guest, reply])["previous_evening_settings"]
        self.assertEqual(
            result["value"],
            {
                "climate": {"temperature_c": 20},
                "sound": {"track_id": "track_04", "volume": 20, "timer_minutes": 40},
            },
        )
        self.assertEqual(result["source"], "confirmed_dialogue")
        self.assertEqual(
            result["confirmed_sources"], {"user_message_id": "u", "agent_message_id": "a"}
        )

    def test_evening_does_not_accept_unrequested_or_contradicting_values(self):
        guest = message(
            "user",
            "u",
            "2026-11-11T23:05:00+03:00",
            "Включи белый шум на двадцать и сделай двадцать градусов.",
        )
        reply = message(
            "agent",
            "a",
            "2026-11-11T23:05:30+03:00",
            "Готово: «Белый шум» на громкости 30, таймер 40 минут, температура 20 °C.",
        )
        result = self.apply(self.fields(), [guest, reply])["previous_evening_settings"]["value"]
        self.assertEqual(
            result, {"climate": {"temperature_c": 20}, "sound": {"track_id": "track_04"}}
        )
        later = message("user", "new", "2026-11-12T10:00:00+03:00", "Поменяла температуру на 19.")
        self.assertIsNone(
            self.apply(self.fields(), [guest, reply], [later])["previous_evening_settings"]["value"]
        )
        failed = {**reply, "text": "Готово, но не удалось включить белый шум на громкости 20."}
        self.assertIsNone(
            self.apply(self.fields(), [guest, failed])["previous_evening_settings"]["value"]
        )
        off = {**guest, "text": "Выключи белый шум и поставь двадцать градусов."}
        result = self.apply(self.fields(), [off, reply])["previous_evening_settings"]["value"]
        self.assertNotIn("sound", result)

    def test_recent_evening_cannot_override_model_value_or_conflict(self):
        guest = message("user", "u", "2026-11-11T23:05:00+03:00", "Сделай двадцать градусов.")
        reply = message("agent", "a", "2026-11-11T23:05:30+03:00", "Готово, температура 20 °C.")
        fields = self.fields()
        fields["previous_evening_settings"]["value"] = {"climate": {"temperature_c": 18}}
        self.assertEqual(
            self.apply(fields, [guest, reply])["previous_evening_settings"]["value"],
            {"climate": {"temperature_c": 18}},
        )
        fields = self.fields()
        fields["previous_evening_settings"]["model_suggestion"]["conflict"] = True
        self.assertIsNone(self.apply(fields, [guest, reply])["previous_evening_settings"]["value"])
        midday_guest = {**guest, "at": "2026-11-11T13:05:00+03:00"}
        midday_reply = {**reply, "at": "2026-11-11T13:05:30+03:00"}
        self.assertIsNone(
            self.apply(self.fields(), [midday_guest, midday_reply])["previous_evening_settings"][
                "value"
            ]
        )

    def test_prepare_guest_integrates_confirmed_home_without_new_model_call(self):
        dataset = copy.deepcopy(self.dataset)
        dataset["chat_history"].append(
            {
                "message_id": "confirmation",
                "user_id": "u_k3m9x2",
                "role": "agent",
                "at": "2026-10-28T21:30:40+03:00",
                "text": "Обновила домашние настройки: тёплый свет около 2700 K.",
            }
        )
        result = prepare_guest(
            dataset, "stay_m7k2", model_call=lambda payload: (copy.deepcopy(self.raw), {})
        )
        home = result["preferences"]["fields"]["home_settings"]
        self.assertEqual(home["value"]["light"]["color_temperature_k"], 2700)
        self.assertEqual(
            home["confirmed_sources"]["light.color_temperature_k"]["agent_message_id"],
            "confirmation",
        )


if __name__ == "__main__":
    unittest.main()
