#!/usr/bin/env bash
# Точка входа контейнера: сервер должен слушать 0.0.0.0 и порт из переменной PORT.
set -euo pipefail
# Local Whisper is never enabled on the competition stand.
export SMARTSTAY_LOCAL_SPEECH=0
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
