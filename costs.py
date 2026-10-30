from dataclasses import dataclass


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float
    cached_input_per_million: float


def calculate_cost(
    usage: TokenUsage,
    price: ModelPrice,
) -> float:
    uncached_input = usage.input_tokens - usage.cached_input_tokens

    if not 0 <= usage.cached_input_tokens <= usage.input_tokens:
        raise ValueError("Invalid cached input token count")

    return (
        uncached_input * price.input_per_million
        + usage.cached_input_tokens * price.cached_input_per_million
        + usage.output_tokens * price.output_per_million
    ) / 1_000_000
