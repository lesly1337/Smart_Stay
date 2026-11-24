"""Public client origins and opt-in local speech settings."""

import os


def client_origins():
    configured = os.getenv("SMARTSTAY_CLIENT_ORIGINS", "").strip()
    if configured:
        return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]


def local_speech_enabled():
    return os.getenv("SMARTSTAY_LOCAL_SPEECH", "0") == "1"
