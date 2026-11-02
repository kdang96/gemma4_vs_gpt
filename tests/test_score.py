import json
from decimal import Decimal

import pytest

import score


def make_question(expected_value, units="", category="table_multi_condition"):
    return {
        "qid": "page#1",
        "page_id": "page",
        "category": category,
        "question": "What is it?",
        "expected_value": expected_value,
        "units": units,
    }


def make_record(raw_response, error_type=None, error=None):
    return {
        "qid": "page#1",
        "model": "test-model",
        "raw_response": raw_response,
        "error_type": error_type,
        "error": error,
        "latency_s": 1.0,
        "cost_usd": 0.0,
    }


def answer_json(value, units=None, found=True, confidence="high"):
    return json.dumps({"found": found, "value": value, "units": units, "confidence": confidence})


# --- parse_number -----------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("39477", Decimal("39477")),
        ("39,477", Decimal("39477")),
        ("+13", Decimal("13")),
        (" 26.40 ", Decimal("26.40")),
        ("1.15E+06", Decimal("1150000")),
    ],
)
def test_parse_number_accepts_plain_numbers(text, expected):
    assert score.parse_number(text) == expected


@pytest.mark.parametrize("text", [None, "", "87 in", "about 3", "NaN", "Infinity", "1925Z-0014Z/15"])
def test_parse_number_rejects_non_numbers(text):
    assert score.parse_number(text) is None


# --- exact numeric match ----------------------------------------------------


@pytest.mark.parametrize(
    "expected, predicted, is_match",
    [
        ("1961", "1961", True),
        ("1961", "1960", False),  # a year must be exact
        ("39477", "39476", False),
        ("39477", "39,477", True),
        ("26.40", "26.4", True),  # same value, different text
        ("+13", "13", True),
        ("1.15E+06", "1150000", True),
        ("0.488", "0.4881", False),
    ],
)
def test_numeric_is_exact_match(expected, predicted, is_match):
    outcome = score.judge_answer(expected, "", predicted, None)
    assert (outcome == score.CORRECT) == is_match


def test_expected_zero_needs_exact_zero():
    assert score.judge_answer("0", "", "0.0", None) == score.CORRECT
    assert score.judge_answer("0", "", "0.0001", None) == score.WRONG_VALUE


def test_numeric_expected_with_text_answer_is_wrong():
    assert score.judge_answer("87", "IN", "87 in", "IN") == score.WRONG_VALUE


# --- units ------------------------------------------------------------------


def test_unit_mismatch():
    assert score.judge_answer("87", "IN", "87", "ft") == score.WRONG_UNITS


def test_missing_units_when_units_are_expected():
    assert score.judge_answer("87", "IN", "87", None) == score.WRONG_UNITS


def test_unit_aliases_and_case():
    assert score.judge_answer("87", "IN", "87", "inches") == score.CORRECT
    assert score.judge_answer("110020", "pounds", "110020", "lb") == score.CORRECT
    assert score.judge_answer("1.15E+06", "N-m2", "1.15E+06", "N·m²") == score.CORRECT
    assert score.judge_answer("337", "LB/IN", "337", "lb / in") == score.CORRECT
    assert score.judge_answer("168", "knots", "168", "kt") == score.CORRECT
    assert score.judge_answer("0.3", "n. mi.", "0.3", "nmi") == score.CORRECT
    assert score.judge_answer("350", "lb/sq in", "350", "psi") == score.CORRECT
    assert score.judge_answer("195", "fps", "195", "ft/sec") == score.CORRECT
    assert score.judge_answer("790", "sq ft", "790", "ft²") == score.CORRECT
    assert score.judge_answer("250", "°F", "250", "deg F") == score.CORRECT
    assert score.judge_answer("15", "deg", "15", "°") == score.CORRECT
    assert score.judge_answer("15", "deg", "15", "°F") == score.WRONG_UNITS


def test_blank_expected_units_are_not_checked():
    assert score.judge_answer("39477", "", "39477", "ft") == score.CORRECT


def test_wrong_value_has_priority_over_wrong_units():
    assert score.judge_answer("87", "IN", "90", "ft") == score.WRONG_VALUE


# --- text answers -----------------------------------------------------------


def test_text_normalised_exact_match():
    assert score.judge_answer("Hysol 5189/3538", "", "hysol 5189 / 3538.", None) == score.CORRECT
    assert score.judge_answer("1925Z-0014Z/15", "", "1925Z–0014Z/15", None) == score.CORRECT  # en dash
    assert score.judge_answer("Hysol 5189/3538", "", "Hysol 5189", None) == score.WRONG_VALUE


# --- whole records ----------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        None,  # no content (for example a refusal)
        "",
        "The answer is 3.",  # prose, not JSON
        '{"found": true, "value": "3", "units": null',  # JSON cut short
        '{"found": true, "value": "3", "units": null}',  # "confidence" is missing
        '{"found": true, "value": "3", "units": null, "confidence": "sure"}',  # not an allowed value
        '{"found": true, "value": "3", "units": null, "confidence": "high", "page": 10}',  # extra key
        answer_json(None, found=True),  # found but no value
        answer_json("3", found=False),  # not found but a value
    ],
)
def test_malformed_response_is_schema_failure(raw):
    row = score.score_item(make_question("3"), make_record(raw))
    assert row["outcome"] == score.SCHEMA_FAILURE
    assert row["detail"] != ""


def test_valid_response_is_scored():
    row = score.score_item(make_question("43", "%"), make_record(answer_json("43.0", "percent")))
    assert row["outcome"] == score.CORRECT
    assert row["predicted_value"] == "43.0"


def test_not_found():
    row = score.score_item(make_question("3"), make_record(answer_json(None, found=False, confidence="low")))
    assert row["outcome"] == score.NOT_FOUND


def test_api_error_and_missing_record():
    api_record = make_record(None, error_type="api", error="RateLimitError")
    assert score.score_item(make_question("3"), api_record)["outcome"] == score.API_ERROR
    assert score.score_item(make_question("3"), None)["outcome"] == score.MISSING


# --- totals -----------------------------------------------------------------


def test_percentile_nearest_rank():
    values = [float(v) for v in range(1, 21)]  # 1 to 20
    assert score.percentile(values, 95) == 19.0
    assert score.percentile(values, 50) == 10.0
    assert score.percentile([], 95) is None


def test_summarise_counts_schema_failures_in_accuracy_denominator():
    questions = [make_question("3"), make_question("4")]
    questions[1]["qid"] = "page#2"
    rows = [
        score.score_item(questions[0], make_record(answer_json("3"))),
        score.score_item(questions[1], make_record("not json")),
    ]
    summary = score.summarise(rows, {"page#1": make_record(answer_json("3"))})
    assert summary["accuracy"] == 0.5
    assert summary["schema_failure_rate"] == 0.5
    assert summary["per_category"] == {"table_multi_condition": (1, 2)}
