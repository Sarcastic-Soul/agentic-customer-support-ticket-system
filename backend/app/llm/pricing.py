"""Rough cost estimation for agent_runs.est_cost_usd. Paid-tier prices as of
2026-09-08 (docs/02-tech-stack.md); the seeded/dev traffic actually runs on
free tiers, so this is a "what would this have cost" estimate, not a bill.
"""

from decimal import Decimal

# (input $ / 1M tokens, output $ / 1M tokens)
_PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "gemini-3.8-flash": (Decimal("0.75"), Decimal("3.75")),
    "gemini-3.5-flash-lite": (Decimal("0.30"), Decimal("2.50")),
    "openai/gpt-oss-120b": (Decimal("0.15"), Decimal("0.60")),
    "openai/gpt-oss-20b": (Decimal("0.075"), Decimal("0.30")),
}

_MILLION = Decimal(1_000_000)


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> Decimal:
    prices = _PRICES.get(model)
    if prices is None:
        return Decimal(0)
    price_in, price_out = prices
    return (Decimal(tokens_in) * price_in + Decimal(tokens_out) * price_out) / _MILLION
