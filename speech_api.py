"""Local speech recognition, adapted from the team's speech_agent.py."""

import io
import array
import os
import tempfile
import threading
import wave
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from deployment_settings import local_speech_enabled

router = APIRouter(prefix="/api/speech")
_model = None
_lock = threading.Lock()
MAX_BYTES = 4 * 1024 * 1024


@router.get("/status")
def speech_status():
    return {"enabled": local_speech_enabled()}


def transcribe(data):
    global _model
    try:
        with wave.open(io.BytesIO(data)) as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                raise ValueError()
            if not 0 < audio.getnframes() <= 16000 * 120:
                raise ValueError()
            samples = array.array("h", audio.readframes(audio.getnframes()))
            if not samples or max(abs(value) for value in samples) < 100:
                raise HTTPException(422, "В записи не слышно голоса. Проверьте микрофон.")
    except (wave.Error, EOFError, ValueError):
        raise HTTPException(422, "Нужна запись WAV, mono, 16 kHz, до 2 минут.")
    if not _lock.acquire(blocking=False):
        raise HTTPException(429, "Предыдущая запись ещё распознаётся. Попробуйте позже.")
    try:
        try:
            from pywhispercpp.model import Model
        except ImportError:
            raise HTTPException(
                503,
                "На бэкенде не установлен Whisper. Установите requirements-speech.txt и перезапустите сервер.",
            )
        with tempfile.TemporaryDirectory(prefix="smartstay-speech-") as folder:
            path = Path(folder) / "voice.wav"
            # Preserve complete words and give the decoder context around short utterances.
            with wave.open(str(path), "wb") as prepared:
                prepared.setnchannels(1)
                prepared.setsampwidth(2)
                prepared.setframerate(16000)
                prepared.writeframes(b"\0" * 8000 + samples.tobytes() + b"\0" * 16000)
            if _model is None:
                _model = Model(
                    os.getenv("WHISPER_MODEL", "small"),
                    n_threads=6,
                    print_realtime=False,
                    print_progress=False,
                )
            segments = _model.transcribe(str(path), language="ru")
            text = " ".join(segment.text.strip() for segment in segments).strip()
            if not text:
                raise HTTPException(422, "Не удалось разобрать речь. Попробуйте сказать ещё раз.")
            return {"text": text}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            503,
            "Распознавание недоступно. Проверьте установку Whisper и загрузку модели на сервере.",
        )
    finally:
        _lock.release()


@router.post("/transcribe")
async def recognize(request: Request):
    if not local_speech_enabled():
        raise HTTPException(
            503, "Голосовой ввод на этом сервере отключён. Напишите сообщение текстом."
        )
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "Запись слишком большая. Максимум — 2 минуты.")
    return await run_in_threadpool(transcribe, bytes(data))
