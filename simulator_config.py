"""Local simulator settings; process environment takes precedence."""

import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("simulator.local.json")


def simulator_settings(config_path=None):
    path = Path(config_path) if config_path is not None else CONFIG_PATH
    local = {}
    if path.exists():
        try:
            local = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            raise ValueError(
                "Не удалось прочитать simulator.local.json: проверьте формат JSON."
            ) from error
        if not isinstance(local, dict) or any(
            not isinstance(value, str) for value in local.values()
        ):
            raise ValueError("В simulator.local.json значения должны быть строками.")
    names = (
        "HACK_API_URL",
        "HACK_ROOM_SESSION_ID",
        "HACK_ROOM_AT",
        "HACK_ROOM_RUN_ID",
        "HACK_TEAM_TOKEN",
        "HACK_TEAM_TOKEN_FILE",
    )
    settings = {
        name: (os.environ.get(name, "").strip() or local.get(name, "").strip()) for name in names
    }
    if not settings["HACK_TEAM_TOKEN"] and settings["HACK_TEAM_TOKEN_FILE"]:
        token_path = Path(settings["HACK_TEAM_TOKEN_FILE"])
        if not token_path.is_absolute():
            token_path = path.parent / token_path
        try:
            settings["HACK_TEAM_TOKEN"] = token_path.read_text(encoding="utf-8-sig").strip()
        except OSError as error:
            raise ValueError(
                "Не удалось прочитать api.token: проверьте HACK_TEAM_TOKEN_FILE."
            ) from error
    return settings
