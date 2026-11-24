"""Запустить и проверить один изолированный dev-прогон через локальный /run."""

import argparse
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from case2_run import Case2Api, SimulatorError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("token_file", type=Path, help="путь к api.token команды")
    parser.add_argument(
        "--server-url", default="http://127.0.0.1:8000", help="адрес проверяемого FastAPI-сервера"
    )
    parser.add_argument("--output", type=Path, default=None, help="папка результатов dev-проверки")
    args = parser.parse_args()
    base = os.getenv("HACK_API_URL", "https://hack-api.be-healthy.tech").rstrip("/")
    try:
        token = args.token_file.read_text(encoding="utf-8").strip()
    except OSError:
        print("Не удалось прочитать файл api.token.", file=sys.stderr)
        return 1
    if not token:
        print("Файл api.token пуст.", file=sys.stderr)
        return 1
    client = Case2Api(base, f"Bearer {token}")
    directory = args.output or Path("/tmp") / (
        "smartstay-dev-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    )
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        run = client.call("/runs", {"case": 2}, attempts=1)
        if run["stage"] != "dev":
            print("API не создал dev-прогон.", file=sys.stderr)
            return 1
        metadata = {key: run[key] for key in ("run_id", "dataset_id", "stage", "expires_at")}
        metadata["server_url"] = args.server_url.rstrip("/")
        (directory / "run.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"Dev-прогон {run['run_id']} создан. Сервер обрабатывает заезды и просьбы.", flush=True
        )
        started = monotonic()
        request = Request(
            args.server_url.rstrip("/") + "/run",
            headers={
                "Authorization": f"Bearer {run['run_token']}",
                "Content-Type": "application/json",
            },
            data=json.dumps({"case": 2, "dataset_code": run["dataset_id"]}).encode(),
        )
        with urlopen(request, timeout=44 * 60) as response:
            answer = json.load(response)
        metadata["elapsed_seconds"] = round(monotonic() - started, 2)
        (directory / "run.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (directory / "answer.json").write_text(
            json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"Ответ /run. Заездов: {len(answer['stays'])}. Просьб: {len(answer['requests'])}.",
            flush=True,
        )
        validation = client.call("/case/2/validate", answer)
        (directory / "validation.json").write_text(
            json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except SimulatorError as error:
        print(
            f"Ошибка API при вызове {error.endpoint}. HTTP: {error.status or 'нет ответа'}.",
            file=sys.stderr,
        )
        return 1
    except HTTPError as error:
        print(f"Локальный /run вернул HTTP {error.code}.", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, ValueError, KeyError, TypeError):
        print(
            "Не удалось получить ответ локального /run. Проверьте запущенный сервер.",
            file=sys.stderr,
        )
        return 1
    if not validation.get("valid"):
        print("API отклонил ответ.", file=sys.stderr)
        for error in validation.get("errors", [])[:8]:
            print(error.get("path"), error.get("code"), file=sys.stderr)
        return 1
    print("API подтвердил формат и ссылки на сеансы.")
    print(f"Результаты сохранены в {directory.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
