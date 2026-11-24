import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from deployment_settings import client_origins, local_speech_enabled
from main import app


class DeploymentSettingsTests(unittest.TestCase):
    def test_default_origins_allow_local_client_with_stand_backend(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertIn("http://127.0.0.1:5173", client_origins())
            self.assertIn("http://localhost:4173", client_origins())
            self.assertFalse(local_speech_enabled())

    def test_custom_origins_replace_defaults(self):
        with patch.dict(
            "os.environ",
            {"SMARTSTAY_CLIENT_ORIGINS": " https://app.example.com/, https://demo.example.com "},
        ):
            self.assertEqual(
                client_origins(), ["https://app.example.com", "https://demo.example.com"]
            )

    def test_disabled_speech_does_not_call_recognizer(self):
        with (
            patch.dict("os.environ", {"SMARTSTAY_LOCAL_SPEECH": "0"}),
            patch("speech_api.transcribe") as recognize,
        ):
            client = TestClient(app)
            self.assertEqual(client.get("/api/speech/status").json(), {"enabled": False})
            response = client.post("/api/speech/transcribe", content=b"audio")
            self.assertEqual(response.status_code, 503)
            recognize.assert_not_called()

    def test_local_speech_requires_explicit_opt_in(self):
        with patch.dict("os.environ", {"SMARTSTAY_LOCAL_SPEECH": "1"}):
            self.assertEqual(TestClient(app).get("/api/speech/status").json(), {"enabled": True})

    def test_browser_preflight_for_stand_client(self):
        response = TestClient(app).options(
            "/api/room/light",
            headers={
                "Origin": "http://localhost:4173",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "content-type,x-room-session",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:4173")
