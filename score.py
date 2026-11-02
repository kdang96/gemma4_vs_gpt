"""Score results files against the expected answers in the QA file.

Usage:
  python score.py                                  (score every file in results/)
  python score.py results/gpt-5_20261027-120000.jsonl results/google_gemma-4_20261027-130000.jsonl

Writes a Markdown summary to scores/summary_<time>.md and the per-item scoring
to scores/<results file name>_items.csv.
"""

import argparse
import csv
import json
import math
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import config
from common import load_questions, parse_answer

# The possible outcomes for one question. Only CORRECT counts as a correct answer.
CORRECT = "correct"
WRONG_VALUE = "wrong_value"
WRONG_UNITS = "wrong_units"
NOT_FOUND = "not_found"  # the model said that the page does not contain the answer
SCHEMA_FAILURE = "schema_failure"  # the model output did not agree with the JSON schema
API_ERROR = "api_error"  # the call failed after all retries
MISSING = "missing"  # the results file has no record for this question
OUTCOMES = [CORRECT, WRONG_VALUE, WRONG_UNITS, NOT_FOUND, SCHEMA_FAILURE, API_ERROR, MISSING]


# ---------------------------------------------------------------------------
# Rules for one answer
# ---------------------------------------------------------------------------


# Words that multiply a number, in the value ("7.9 million") or in the units ("$ billion").
SCALE_WORDS = {
    "thousand": Decimal(10**3),
    "million": Decimal(10**6),
    "billion": Decimal(10**9),
    "trillion": Decimal(10**12),
}

# Words after a number that mean US dollars ("560 billion dollars").
CURRENCY_WORDS = {"$", "us$", "usd", "dollar", "dollars"}

# A model can write a small whole number as a word, for example "five" when the page says "five".
NUMBER_WORDS = {
    word: Decimal(n)
    for n, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
        "sixteen seventeen eighteen nineteen twenty".split()
    )
}

PLUS_MINUS_SIGNS = ("±", "+/-", "+-")


def parse_number(text: str | None) -> Decimal | None:
    """Return text as a Decimal, or None if text is not a plain number.

    Accepts "39477", "39,477", "+13", "26.40", ".028", "1.15E+06" and number words from "zero" to "twenty".
    Rejects "87 in", "about 3", "NaN" and "Infinity".
    """
    if text is None:
        return None
    cleaned = text.strip().replace(",", "")  # remove thousands separators
    if cleaned.lower() in NUMBER_WORDS:
        return NUMBER_WORDS[cleaned.lower()]
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return number


def split_plus_minus(text: str | None) -> tuple[bool, str]:
    """Remove a leading plus-minus sign. Return (True if there was one, the remaining text)."""
    stripped = (text or "").strip()
    for sign in PLUS_MINUS_SIGNS:
        if stripped.startswith(sign):
            return True, stripped[len(sign) :].strip()
    return False, stripped


def strip_restatement(text: str) -> str:
    """Remove a part in brackets at the end that contains a number, for example the "(100.3 ft)" in "m (100.3 ft)".

    Pages often give a value in two units, for example "30.6 m (100.3 ft)". A model can copy the
    second value into "units" or "value". We ignore that part and do not check it.
    """
    return re.sub(r"\s+\([^()]*\d[^()]*\)$", "", text.strip())


def units_key(units: str | None) -> str:
    """Lowercase the units, remove a restatement in brackets, all whitespace and the dots at the end.

    Examples: "lb/sq in." becomes "lb/sqin", "m (100.3 ft)" becomes "m".
    """
    if units is None:
        return ""
    return "".join(strip_restatement(units).lower().split()).rstrip(".")


def normalise_units(units: str | None) -> str:
    """Make units_key(), then apply the alias table in config."""
    key = units_key(units)
    return config.UNIT_ALIASES.get(key, key)


def parse_amount(value: str | None, units: str | None) -> tuple[Decimal | None, str]:
    """Read a numeric answer. Return (the number or None, the normalised units).

    Scale words in the value or in the units multiply the number. A currency sign or word
    in the value becomes the units when the units are empty. Examples:
      ("7.9 million", "dollars") gives (7900000, "$")
      ("560", "$ billion") gives (560000000000, "$")
      ("$60 million", None) gives (60000000, "$")
      ("30.6 (100.3 ft)", "m") gives (30.6, "m")
    """
    text = strip_restatement(value or "").lower()
    scale = Decimal(1)
    currency = False
    for sign in ("us$", "$"):
        if text.startswith(sign):
            text = text[len(sign) :]
            currency = True
            break
    number_text, *other_words = text.split() or [""]
    number = parse_number(number_text)
    for word in other_words:
        if word in SCALE_WORDS:
            scale *= SCALE_WORDS[word]
        elif word in CURRENCY_WORDS:
            currency = True
        else:
            number = None  # for example "12 to 18" or "87 in": not a plain number

    key = units_key(units)
    for word, factor in SCALE_WORDS.items():
        if word in key:
            scale *= factor
            key = key.replace(word, "")
    if key == "" and currency:
        key = "$"
    key = config.UNIT_ALIASES.get(key, key)
    return (None if number is None else number * scale), key


def text_words(text: str | None) -> set[str]:
    """Return the set of words in text, lowercase, with unit spellings changed by the alias table.

    A word is a sequence of letters and digits. A decimal point in a number stays ("10.35").
    "_" is removed ("v_P" is "vp"), "√" is the word "sqrt" and '"' after a digit is the word "in".
    """
    cleaned = (text or "").lower().replace("_", "").replace("√", " sqrt ")
    cleaned = re.sub(r'(?<=\d)\s*["″]', " in ", cleaned)
    return {config.UNIT_ALIASES.get(word, word) for word in re.findall(r"\w+(?:\.\w+)*", cleaned)}


def judge_answer(
    expected_value: str,
    expected_units: str,
    value: str | None,
    units: str | None,
    accept_min: str = "",
    accept_max: str = "",
) -> str:
    """Compare one model answer with the expected answer. Return CORRECT, WRONG_VALUE or WRONG_UNITS.

    Numeric expected value: the answer must be a number that is exactly equal. Decimal compares
    values, not text, so 26.4 equals 26.40 and 1150000 equals 1.15E+06. If the QA file gives
    accept_min and accept_max (chart readings), each number in that range, edges included, is correct.
    A plus-minus sign must be in both answers or in neither.
    Text expected value: the answer must contain all the words of the expected value (see text_words()).
    Units: if the QA file gives no units, we do not check them.
    The value is checked first, so an answer with a wrong value and wrong units is WRONG_VALUE.
    """
    expected_plus_minus, expected_text = split_plus_minus(expected_value)
    expected_number, expected_key = parse_amount(expected_text, expected_units)

    if expected_number is not None:
        plus_minus, predicted_text = split_plus_minus(value)
        predicted_number, predicted_key = parse_amount(predicted_text, units)
        if predicted_number is None or plus_minus != expected_plus_minus:
            value_ok = False
        elif accept_min and accept_max:
            value_ok = parse_number(accept_min) <= predicted_number <= parse_number(accept_max)
        else:
            value_ok = predicted_number == expected_number
    else:
        expected_words = text_words(expected_value)
        value_ok = bool(expected_words) and expected_words <= text_words(value)
        expected_key, predicted_key = normalise_units(expected_units), normalise_units(units)

    if not value_ok:
        return WRONG_VALUE
    if expected_key != "" and expected_key != predicted_key:
        return WRONG_UNITS
    return CORRECT


def score_item(question: dict, record: dict | None) -> dict:
    """Score one question. Return one row for the per-item CSV file.

    We validate raw_response again here, so the score does not depend on what run.py decided.
    """
    row = {
        "qid": question["qid"],
        "category": question["category"],
        "question": question["question"],
        "expected_value": question["expected_value"],
        "expected_units": question["units"],
        "accepted_range": f"{question['accept_min']} to {question['accept_max']}" if question["accept_min"] else "",
        "alt_answer": f"{question['alt_value']} {question['alt_units']}".strip(),
        "predicted_value": None,
        "predicted_units": None,
        "confidence": None,
        "outcome": None,
        "detail": "",
    }

    if record is None:
        row["outcome"] = MISSING
        return row
    # The qid is the page plus a counter, so a new or moved row in the QA file can give a qid
    # to a different question. Records from older runs have no "question", so we cannot check them.
    if record.get("question") not in (None, question["question"]):
        row["outcome"] = MISSING
        row["detail"] = "the question in the QA file changed after this run"
        return row
    if record["error_type"] == "api":
        row["outcome"] = API_ERROR
        row["detail"] = record["error"]
        return row

    answer, error = parse_answer(record["raw_response"])
    if answer is None:
        row["outcome"] = SCHEMA_FAILURE
        row["detail"] = error
        return row

    row["predicted_value"] = answer.value
    row["predicted_units"] = answer.units
    row["confidence"] = answer.confidence
    if not answer.found:
        row["outcome"] = NOT_FOUND
        return row

    row["outcome"] = judge_answer(
        question["expected_value"],
        question["units"],
        answer.value,
        answer.units,
        question["accept_min"],
        question["accept_max"],
    )
    # The alternative answer is the same value in other units, as the page prints it
    # (for example 100.3 ft for 30.6 m). If both comparisons fail, report the closer one.
    if row["outcome"] != CORRECT and question["alt_value"]:
        alt_outcome = judge_answer(question["alt_value"], question["alt_units"], answer.value, answer.units)
        row["outcome"] = min(row["outcome"], alt_outcome, key=[CORRECT, WRONG_UNITS, WRONG_VALUE].index)
    return row


# ---------------------------------------------------------------------------
# Totals for one run
# ---------------------------------------------------------------------------


def load_results(path: Path) -> dict[str, dict]:
    """Read a results file. Return {qid: record}. If a qid occurs again (after --resume), the last record wins."""
    records = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            print(f"WARNING: {path.name} line {line_number} is not valid JSON. It is ignored.")
            continue
        records[record["qid"]] = record
    return records


def percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile: the smallest value that has pct % of the values at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(pct / 100 * len(ordered))  # 1-based rank
    return ordered[max(rank, 1) - 1]


def summarise(rows: list[dict], records: dict[str, dict]) -> dict:
    """Calculate the totals for one run from its scored rows and its records."""
    total = len(rows)
    counts = {outcome: 0 for outcome in OUTCOMES}
    for row in rows:
        counts[row["outcome"]] += 1

    per_category = {}  # {category: (correct, total)}
    for row in rows:
        correct, seen = per_category.get(row["category"], (0, 0))
        per_category[row["category"]] = (correct + (row["outcome"] == CORRECT), seen + 1)

    # Latency and cost come only from calls that got a response from the API.
    answered = [r for r in records.values() if r["error_type"] != "api"]
    latencies = [r["latency_s"] for r in answered if r["latency_s"] is not None]
    costs = [r["cost_usd"] for r in answered]
    total_cost = None if None in costs else sum(costs)  # None if a model has no price

    return {
        "total": total,
        "counts": counts,
        "accuracy": counts[CORRECT] / total if total else 0.0,
        "schema_failure_rate": counts[SCHEMA_FAILURE] / total if total else 0.0,
        "per_category": per_category,
        "mean_latency_s": sum(latencies) / len(latencies) if latencies else None,
        "p95_latency_s": percentile(latencies, 95),
        "total_cost_usd": total_cost,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def fmt(number: float | None, digits: int) -> str:
    return "n/a" if number is None else f"{number:.{digits}f}"


def markdown_report(runs: list[tuple[str, str, dict]]) -> str:
    """runs is a list of (run name, model, summary)."""
    lines = ["Numeric answers: exact match.", ""]

    header = [
        "Run",
        "Model",
        "N",
        "Accuracy",
        "Schema failure rate",
        "Mean latency (s)",
        "p95 latency (s)",
        "Total cost (USD)",
    ]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|---" * len(header) + "|")
    for name, model, s in runs:
        lines.append(
            f"| {name} | {model} | {s['total']} | {s['accuracy']:.1%} | {s['schema_failure_rate']:.1%} "
            f"| {fmt(s['mean_latency_s'], 2)} | {fmt(s['p95_latency_s'], 2)} | {fmt(s['total_cost_usd'], 4)} |"
        )

    lines += ["", "Accuracy per category (correct / total):", ""]
    lines.append("| Category | " + " | ".join(name for name, _, _ in runs) + " |")
    lines.append("|---|" + "---|" * len(runs))
    categories = sorted({c for _, _, s in runs for c in s["per_category"]})
    for category in categories:
        cells = []
        for _, _, s in runs:
            correct, seen = s["per_category"].get(category, (0, 0))
            cells.append(f"{correct}/{seen} ({correct / seen:.0%})" if seen else "-")
        lines.append(f"| {category} | " + " | ".join(cells) + " |")

    lines += ["", "Outcome counts:", ""]
    lines.append("| Outcome | " + " | ".join(name for name, _, _ in runs) + " |")
    lines.append("|---|" + "---|" * len(runs))
    for outcome in OUTCOMES:
        lines.append(f"| {outcome} | " + " | ".join(str(s["counts"][outcome]) for _, _, s in runs) + " |")

    return "\n".join(lines) + "\n"


def write_items_csv(path: Path, rows: list[dict]) -> None:
    # "utf-8-sig" adds a byte-order mark. Without it, Excel reads the file as ANSI and shows
    # characters such as σ, ° and Δ as "?" or "�". The file content is correct in both cases.
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", nargs="*", type=Path, help="results files (default: all in results/)")
    args = parser.parse_args()

    paths = args.results or sorted(config.RESULTS_DIR.glob("*.jsonl"))
    if not paths:
        raise SystemExit("No results files found.")

    questions = load_questions()
    config.SCORES_DIR.mkdir(exist_ok=True)
    runs = []
    for path in paths:
        records = load_results(path)
        rows = [score_item(q, records.get(q["qid"])) for q in questions]
        write_items_csv(config.SCORES_DIR / f"{path.stem}_items.csv", rows)
        model = next(iter(records.values()))["model"] if records else "?"
        runs.append((path.stem, model, summarise(rows, records)))

    report = markdown_report(runs)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (config.SCORES_DIR / f"summary_{stamp}.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
