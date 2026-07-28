"""Configuration-backed LLM cost calculations.

Prices are intentionally not embedded in source code.  API gateways can use
different rates for the same model ID, so a missing rate is reported as
"unconfigured" rather than incorrectly displayed as free.
"""

from typing import Any, Dict

from config import settings


def calculate_llm_cost(
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> Dict[str, Any]:
    """Return an auditable actual-cost breakdown for provider-reported usage."""
    pricing = getattr(settings, 'LLM_PRICING', {}) or {}
    rate = pricing.get(model, {}) if isinstance(pricing, dict) else {}
    try:
        input_rate = float(rate['input_per_million'])
        output_rate = float(rate['output_per_million'])
        configured = input_rate >= 0 and output_rate >= 0
    except (KeyError, TypeError, ValueError):
        input_rate = output_rate = 0.0
        configured = False

    prompt_tokens = max(0, int(prompt_tokens or 0))
    completion_tokens = max(0, int(completion_tokens or 0))
    input_cost = prompt_tokens * input_rate / 1_000_000 if configured else None
    output_cost = completion_tokens * output_rate / 1_000_000 if configured else None
    total_cost = input_cost + output_cost if configured else None
    return {
        'pricing_configured': configured,
        'currency': getattr(settings, 'LLM_COST_CURRENCY', 'CNY'),
        'model': model,
        'input_price_per_million': input_rate if configured else None,
        'output_price_per_million': output_rate if configured else None,
        'input_cost': round(input_cost, 6) if input_cost is not None else None,
        'output_cost': round(output_cost, 6) if output_cost is not None else None,
        'total_cost': round(total_cost, 6) if total_cost is not None else None,
    }
