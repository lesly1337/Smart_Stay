import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from guest_service import prepare_guest

example_dir = ROOT / "examples"
with (example_dir / "guest_input.json").open(encoding="utf-8") as file:
    dataset = json.load(file)["dataset"]
with (example_dir / "guest_model_response.json").open(encoding="utf-8") as file:
    saved_model_response = json.load(file)

result = prepare_guest(
    dataset, "stay_m7k2", model_call=lambda payload: (saved_model_response, {"cached": True})
)
(example_dir / "guest_result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print("Готово: examples/guest_result.json; запросов к модели: 0")
