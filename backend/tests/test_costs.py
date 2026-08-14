from costs import calculate_llm_cost
from config import settings


def test_calculates_input_and_output_cost(monkeypatch):
    monkeypatch.setattr(settings, 'LLM_COST_CURRENCY', 'CNY')
    monkeypatch.setattr(settings, 'LLM_PRICING', {
        'test-model': {'input_per_million': 2, 'output_per_million': 4}
    })

    result = calculate_llm_cost('test-model', prompt_tokens=500_000, completion_tokens=250_000)

    assert result['pricing_configured'] is True
    assert result['input_cost'] == 1.0
    assert result['output_cost'] == 1.0
    assert result['total_cost'] == 2.0


def test_does_not_present_missing_price_as_free(monkeypatch):
    monkeypatch.setattr(settings, 'LLM_PRICING', {})

    result = calculate_llm_cost('unknown-model', prompt_tokens=100, completion_tokens=100)

    assert result['pricing_configured'] is False
    assert result['total_cost'] is None
