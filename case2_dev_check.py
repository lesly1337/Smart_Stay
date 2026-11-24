"""Отдельная dev-проверка фактических состояний; не вызывается из /run."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from case2_run import Case2Api


def request_errors(reference, initial, actual, replies):
    errors = []
    classes = [reply["response_class"] for reply in replies]
    if classes != reference["expected_reply_classes"]:
        errors.append("reply_classes")
    checked = set()
    for expectation in reference["expectations"]:
        device, field = expectation["device_id"], expectation["field_id"]
        checked.add((device, field))
        value = actual.get(device, {}).get(field)
        old = initial.get(device, {}).get(field)
        comparison = expectation["comparison"]
        expected = expectation.get("value")
        try:
            if comparison == "exact":
                valid = value == expected
            elif comparison == "unchanged":
                valid = value == old
            elif comparison in ("increase", "decrease"):
                valid = value > old if comparison == "increase" else value < old
            elif comparison == "within":
                if expectation.get("unit") == "minutes":
                    delta = (
                        datetime.fromisoformat(value) - datetime.fromisoformat(expected)
                    ).total_seconds() / 60
                else:
                    delta = value - expected
                valid = abs(delta) <= expectation["tolerance"]
            else:
                raise ValueError("Неизвестное сравнение dev-эталона")
        except (TypeError, ValueError):
            valid = False
        if not valid:
            errors.append(device + "." + field)
    if reference.get("preserve_other_fields"):
        for device, fields in initial.items():
            for field, value in fields.items():
                if (device, field) not in checked and actual.get(device, {}).get(field) != value:
                    errors.append("preserve:" + device + "." + field)
    return errors


def check_requests(api, directory):
    metadata = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    answers = json.loads((directory / "answer.json").read_text(encoding="utf-8"))
    data = api.call("/case/2/getData?" + urlencode({"dataset_code": metadata["dataset_id"]}))
    reference = data.get("reference")
    if not isinstance(reference, dict):
        raise ValueError("Эта проверка требует dev-набор с эталоном")
    records = {record["record_id"]: record for record in data["dataset"]["requests"]}
    expected = {record["record_id"]: record for record in reference["requests"]}
    ids = [answer["record_id"] for answer in answers["requests"]]
    if len(ids) != len(set(ids)) or set(ids) != set(records):
        raise ValueError("Ответ должен содержать каждую просьбу набора ровно один раз")

    def inspect(answer):
        record_id = answer["record_id"]
        log = api.call("/room/" + answer["session_id"] + "/log")
        if log.get("session", {}).get("run_id") != metadata["run_id"]:
            raise ValueError("Журнал относится к другому прогону")
        errors = request_errors(
            expected[record_id],
            records[record_id]["initial_state"],
            log["final_state"],
            answer["replies"],
        )
        return {"record_id": record_id, "passed": not errors, "errors": errors}

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(inspect, answers["requests"]))
    report = {
        "run_id": metadata["run_id"],
        "requests_checked": len(results),
        "requests_passed": sum(result["passed"] for result in results),
        "requests": results,
    }
    (directory / "quality.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("token_file", type=Path)
    parser.add_argument("results_directory", type=Path)
    args = parser.parse_args()
    api = Case2Api(
        os.getenv("HACK_API_URL", "https://hack-api.be-healthy.tech").rstrip("/"),
        "Bearer " + args.token_file.read_text(encoding="utf-8").strip(),
    )
    report = check_requests(api, args.results_directory)
    print(
        f"Фактические настройки и ответы: {report['requests_passed']}/{report['requests_checked']} просьб совпали с dev-эталоном."
    )
    for record in report["requests"]:
        if record["errors"]:
            print(record["record_id"] + ": " + ", ".join(record["errors"]))
    return 0 if report["requests_passed"] == report["requests_checked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
