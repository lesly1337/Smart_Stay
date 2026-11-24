"""Интерфейс извлечения и построения сценария для серверной части.

prepare_guest вызывает LLM, если не передать model_call. Модуль не обращается к /room.
"""

from case2_contracts import validate_dataset
from extract_preferences import call_model, extract_card
from guest_scenario import build_scenario
from make_cards import build_cards


def prepare_guest(dataset, stay_id, *, model_call=None):
    """dataset из getData['dataset']; вернуть предпочтения и шаги для одного заезда."""
    validate_dataset(dataset)
    card = next((c for c in build_cards(dataset) if c["stay_id"] == stay_id), None)
    if card is None:
        raise ValueError("Заезд не найден в наборе")
    preferences, usage = extract_card(
        card, dataset["tracks"], dataset["devices"], model_call=model_call or call_model
    )
    scenario = build_scenario(preferences, dataset["devices"], dataset["tracks"])
    return {"preferences": preferences, "scenario": scenario, "llm_usage": usage}
