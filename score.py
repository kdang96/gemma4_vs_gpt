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
import unicodedata
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


def parse_number(text: str | None) -> Decimal | None:
    """Return text as a Decimal, or None if text is not a plain number.

    Accepts "39477", "39,477", "+13", "26.40" and "1.15E+06".
    Rejects "87 in", "about 3", "NaN" and "Infinity".
    """
    if text is None:
        return None
    cleaned = text.strip().replace(",", "")  # remove thousands separators
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return number


def normalise_text(text: str | None) -> str:
    """Lowercase the text and remove all whitespace and punctuation.

    Example: "Hysol 5189 / 3538." becomes "hysol51893538".
    Punctuation is every character in a Unicode "P" category (for example . , / - ( ) and the en dash).
    """
    if text is None:
        return ""
    kept = []
    for char in text.lower():
        if char.isspace():
            continue
        if unicodedata.category(char).startswith("P"):
            continue
        kept.append(char)
    return "".join(kept)


def normalise_units(units: str | None) -> str:
    """Lowercase the units, remove all whitespace, then apply the alias table in config."""
    if units is None:
        return ""
    key = "".join(units.lower().split())
    return config.UNIT_ALIASES.get(key, key)


def units_match(expected: str | None, predicted: str | None) -> bool:
    """True if the units agree. If the QA file gives no units, we do not check the units."""
    expected_units = normalise_units(expected)
    if expected_units == "":
        return True
    return expected_units == normalise_units(predicted)


def judge_answer(expected_value: str, expected_units: str, value: str | None, units: str | None) -> str:
    """Compare one model answer with the expected answer. Return CORRECT, WRONG_VALUE or WRONG_UNITS.

    If the expected value is a number, the answer must be a number that is exactly equal.
    Decimal compares values, not text, so 26.4 equals 26.40 and 1150000 equals 1.15E+06.
    If not, the answer must be equal after normalise_text().
    The value is checked first, so an answer with a wrong value and wrong units is WRONG_VALUE.
    """
    expected_number = parse_number(expected_value)
    if expected_number is not None:
        predicted_number = parse_number(value)
        value_ok = predicted_number == expected_number
    else:
        value_ok = normalise_text(expected_value) == normalise_text(value)

    if not value_ok:
        return WRONG_VALUE
    if not units_match(expected_units, units):
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
        "predicted_value": None,
        "predicted_units": None,
        "confidence": None,
        "outcome": None,
        "detail": "",
    }

    if record is None:
        row["outcome"] = MISSING
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

    row["outcome"] = judge_answer(question["expected_value"], question["units"], answer.value, answer.units)
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
    with open(path, "w", newline="", encoding="utf-8") as f:
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
