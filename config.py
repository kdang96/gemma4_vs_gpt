"""Settings for the benchmark. Change the values here, not in the scripts."""

from pathlib import Path

ROOT = Path(__file__).parent
PAGES_DIR = ROOT / "selected_pages"
RENDER_DIR = ROOT / "renders"
QA_CSV = ROOT / "eval" / "sources.csv"
RESULTS_DIR = ROOT / "results"
SCORES_DIR = ROOT / "scores"

DEFAULT_DPI = 200
DEFAULT_TOLERANCE = 0.0  # 0 = numeric answers must be exact (26.4 and 26.40 are equal)
DEFAULT_CONCURRENCY = 4
MAX_ATTEMPTS = 6  # attempts per call when the API gives a rate limit or server error

# USD per 1 million tokens: (input, output).
# Prices are from third-party summaries, not from OpenAI. Make sure that they
# agree with https://openai.com/api/pricing before you report a cost.
# A model that is not in this table gets cost "n/a".
# The local vLLM backend always costs 0 USD (hardware cost is not included).
PRICES_PER_1M_TOKENS = {
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
}

# Unit spellings that mean the same unit. Keys and values are lowercase with no
# spaces, because score.normalise_units() does that before the lookup.
# A unit that is not a key stays as it is.
UNIT_ALIASES = {
    "inch": "in",
    "inches": "in",
    "in.": "in",
    "foot": "ft",
    "feet": "ft",
    "pound": "lb",
    "pounds": "lb",
    "lbs": "lb",
    "lbs/in": "lb/in",
    "pounds/in": "lb/in",
    "lb/inch": "lb/in",
    "poundsperinch": "lb/in",
    "hertz": "hz",
    "percent": "%",
    "pct": "%",
    "usd": "$",
    "dollars": "$",
    "us$": "$",
    "n-m2": "n*m^2",
    "n-m^2": "n*m^2",
    "nm2": "n*m^2",
    "nm^2": "n*m^2",
    "n.m2": "n*m^2",
    "n·m2": "n*m^2",
    "n·m²": "n*m^2",
    "n-m²": "n*m^2",
}
