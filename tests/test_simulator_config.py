import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from simulator_config import simulator_settings


class ConfigTests(unittest.TestCase):
    def test_local_settings_and_token_file(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / "api.token").write_text(" sample-token\n", encoding="utf-8")
            config = root / "simulator.local.json"
            config.write_text(
                json.dumps(
                    {"HACK_ROOM_SESSION_ID": "local-session", "HACK_TEAM_TOKEN_FILE": "api.token"}
                ),
                encoding="utf-8",
            )
            settings = simulator_settings(config)
            self.assertEqual(settings["HACK_TEAM_TOKEN"], "sample-token")
            self.assertEqual(settings["HACK_ROOM_SESSION_ID"], "local-session")
            with patch.dict(
                os.environ, {"HACK_ROOM_SESSION_ID": "env-session", "HACK_TEAM_TOKEN": "env-token"}
            ):
                settings = simulator_settings(config)
                self.assertEqual(settings["HACK_ROOM_SESSION_ID"], "env-session")
                self.assertEqual(settings["HACK_TEAM_TOKEN"], "env-token")

    def test_missing_config_allows_environment(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"HACK_TEAM_TOKEN": "env-token"}, clear=True),
        ):
            self.assertEqual(
                simulator_settings(Path(directory) / "absent.json")["HACK_TEAM_TOKEN"], "env-token"
            )

    def test_bad_config_and_missing_token_file(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            config = Path(directory) / "simulator.local.json"
            for content in (
                "{bad",
                "[]",
                '{"HACK_ROOM_AT": 12}',
                '{"HACK_TEAM_TOKEN_FILE": "missing.token"}',
            ):
                config.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    simulator_settings(config)


if __name__ == "__main__":
    unittest.main()
