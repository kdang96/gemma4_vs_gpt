"""Settings for the benchmark. Change the values here, not in the scripts."""

from pathlib import Path

from costs import ModelPrice

ROOT = Path(__file__).parent
PAGES_DIR = ROOT / "selected_pages" / "nasa_qa_all_100_pages"
RENDER_DIR = ROOT / "renders"
QA_FILE = ROOT / "eval" / "nasa_qa_all_100.xlsx"
RESULTS_DIR = ROOT / "results"
SCORES_DIR = ROOT / "scores"

DEFAULT_DPI = 200
DEFAULT_CONCURRENCY = 4
MAX_ATTEMPTS = 6  # attempts per call when the API gives a rate limit or server error

# USD per 1 million tokens: input, output and cached input.
# Prices are from third-party summaries, not from OpenAI. Make sure that they
# agree with https://openai.com/api/pricing before you report a cost.
# A model that is not in this table gets cost "n/a".
# The local vLLM backend always costs 0 USD (hardware cost is not included).
PRICES = {
    "gpt-5.5": ModelPrice(input_per_million=5.00, output_per_million=30.00, cached_input_per_million=0.50),
    "gpt-5.4": ModelPrice(input_per_million=2.50, output_per_million=15.00, cached_input_per_million=0.25),
    "gpt-5.4-mini": ModelPrice(input_per_million=0.75, output_per_million=4.50, cached_input_per_million=0.075),
    "gpt-5": ModelPrice(input_per_million=1.25, output_per_million=10.00, cached_input_per_million=0.125),
    "gpt-5-mini": ModelPrice(input_per_million=0.25, output_per_million=2.00, cached_input_per_million=0.025),
    "gpt-5-nano": ModelPrice(input_per_million=0.05, output_per_million=0.40, cached_input_per_million=0.005),
    "gpt-4.1": ModelPrice(input_per_million=2.00, output_per_million=8.00, cached_input_per_million=0.50),
    "gpt-4.1-mini": ModelPrice(input_per_million=0.40, output_per_million=1.60, cached_input_per_million=0.10),
}

# Unit spellings that mean the same unit. Keys and values are lowercase with no
# spaces and no dot at the end, because score.units_key() does that before the lookup.
# score.text_words() also uses this table for the words in a text answer.
# A unit that is not a key stays as it is.
UNIT_ALIASES = {
    "inch": "in",
    "inches": "in",
    '"': "in",
    "″": "in",
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
    "percentage": "%",
    "pct": "%",
    "usd": "$",
    "dollar": "$",
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
    "newton": "n",
    "newtons": "n",
    "lbf": "lb",
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",
    "centimeter": "cm",
    "centimeters": "cm",
    "centimetre": "cm",
    "centimetres": "cm",
    "n.mi": "nmi",
    "nauticalmile": "nmi",
    "nauticalmiles": "nmi",
    "m2": "m^2",
    "m²": "m^2",
    "sqm": "m^2",
    "sqft": "ft^2",
    "lbf/ft2": "lb/ft^2",
    "lbf/ft^2": "lb/ft^2",
    "lbf/ft²": "lb/ft^2",
    "lb/ft2": "lb/ft^2",
    "lb/ft²": "lb/ft^2",
    "lb/sqft": "lb/ft^2",
    "psf": "lb/ft^2",
    "sq.ft": "ft^2",
    "ft2": "ft^2",
    "ft²": "ft^2",
    "squarefeet": "ft^2",
    "sec": "s",
    "second": "s",
    "seconds": "s",
    "minute": "min",
    "minutes": "min",
    "mins": "min",
    "gigahertz": "ghz",
    "°": "deg",
    "degree": "deg",
    "degrees": "deg",
    "°f": "degf",
    "degreesf": "degf",
    "degreesfahrenheit": "degf",
    "knots": "kt",
    "knot": "kt",
    "kts": "kt",
    "kn": "kt",
    "mi/h": "mph",
    "mi/hr": "mph",
    "milesperhour": "mph",
    "ft/sec": "ft/s",
    "fps": "ft/s",
    "feetpersecond": "ft/s",
    "m/sec": "m/s",
    "meterspersecond": "m/s",
    "fpm": "ft/min",
    "feetperminute": "ft/min",
    "rad/sec2": "rad/s^2",
    "rad/sec^2": "rad/s^2",
    "rad/sec²": "rad/s^2",
    "rad/s2": "rad/s^2",
    "rad/s²": "rad/s^2",
    "g2": "g^2",
    "g²": "g^2",
    "n/m2": "n/m^2",
    "n/m²": "n/m^2",
    "pa": "n/m^2",
    "lb/sqin": "psi",
    "lb/sq.in": "psi",
    "lb/in2": "psi",
    "lb/in^2": "psi",
    "lb/in²": "psi",
    "lbf/in2": "psi",
    "lbf/in^2": "psi",
    "lbf/in²": "psi",
}
