import json
from decimal import Decimal

import pytest

import score


def make_question(
    expected_value,
    units="",
    category="table_multi_condition",
    accept_min="",
    accept_max="",
    alt_value="",
    alt_units="",
):
    return {
        "qid": "page#1",
        "page_id": "page",
        "category": category,
        "question": "What is it?",
        "expected_value": expected_value,
        "units": units,
        "accept_min": accept_min,
        "accept_max": accept_max,
        "alt_value": alt_value,
        "alt_units": alt_units,
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
        (".028", Decimal("0.028")),
        ("five", Decimal("5")),
        ("Five", Decimal("5")),
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
    assert score.judge_answer("18", "s", "12 to 18", "s") == score.WRONG_VALUE


def test_number_word_matches_digits():
    assert score.judge_answer("5", "", "five", None) == score.CORRECT
    assert score.judge_answer("5", "", "four", None) == score.WRONG_VALUE


# --- accepted range (chart readings) ----------------------------------------


@pytest.mark.parametrize(
    "predicted, is_match",
    [
        ("195", True),  # the edges count as a match
        ("200", True),
        ("205", True),
        ("194.9", False),
        ("205.1", False),
    ],
)
def test_accepted_range(predicted, is_match):
    outcome = score.judge_answer("202", "", predicted, None, "195", "205")
    assert (outcome == score.CORRECT) == is_match


def test_accepted_range_still_checks_units():
    assert score.judge_answer("90", "knots", "90", "kt", "85", "95") == score.CORRECT
    assert score.judge_answer("90", "knots", "90", "mph", "85", "95") == score.WRONG_UNITS


def test_no_range_means_exact():
    assert score.judge_answer("202", "", "200", None) == score.WRONG_VALUE


# --- money and scale words --------------------------------------------------


@pytest.mark.parametrize(
    "value, units, outcome",
    [
        ("7.9 million", "dollars", score.CORRECT),
        ("7.9", "$ million", score.CORRECT),
        ("7.9", "million USD", score.CORRECT),
        ("$7.9 million", None, score.CORRECT),
        ("7900000", "$", score.CORRECT),
        ("7.9 million", None, score.WRONG_UNITS),  # no currency
        ("7.9", "million", score.WRONG_UNITS),  # no currency
        ("7.9", "$", score.WRONG_VALUE),  # the "million" is missing
        ("7.9 billion", "$", score.WRONG_VALUE),
    ],
)
def test_money_amounts(value, units, outcome):
    assert score.judge_answer("7900000", "USD", value, units) == outcome


# --- plus-minus -------------------------------------------------------------


@pytest.mark.parametrize("value", ["1", "±1", "+/-1", "+- 1", "± 1.0"])
def test_plus_minus_sign_is_ignored(value):
    assert score.judge_answer("1", "deg", value, "°") == score.CORRECT


def test_minus_sign_is_not_ignored():
    assert score.judge_answer("4", "", "-4", None) == score.WRONG_VALUE
    assert score.judge_answer("-4", "", "4", None) == score.WRONG_VALUE
    assert score.judge_answer("1", "deg", "±-1", "deg") == score.WRONG_VALUE


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
    assert score.judge_answer("25.2", "in", "25.2", '"') == score.CORRECT
    assert score.judge_answer("350", "lb/sq in", "350", "lb/sq in.") == score.CORRECT
    assert score.judge_answer("12", "s", "12", "sec.") == score.CORRECT


def test_blank_expected_units_are_not_checked():
    assert score.judge_answer("39477", "", "39477", "ft") == score.CORRECT


def test_wrong_value_has_priority_over_wrong_units():
    assert score.judge_answer("87", "IN", "90", "ft") == score.WRONG_VALUE


# --- text answers -----------------------------------------------------------


def test_text_answer_must_contain_all_expected_words():
    assert score.judge_answer("Hysol 5189/3538", "", "hysol 5189 / 3538.", None) == score.CORRECT
    assert score.judge_answer("Hysol 5189/3538", "", "Hysol 5189/3538 adhesive", None) == score.CORRECT
    assert score.judge_answer("Hysol 5189/3538", "", "Hysol 5189", None) == score.WRONG_VALUE
    assert score.judge_answer("1925Z-0014Z/15", "", "1925Z–0014Z/15", None) == score.CORRECT  # en dash
    assert score.judge_answer("1925Z-0014Z/15", "", "0259z-0014z/15", None) == score.WRONG_VALUE


def test_text_words_use_unit_aliases_and_symbols():
    grooves = "3/8 in x 3/8 in on 2 in centers"
    assert score.judge_answer(grooves, "", "3/8 x 3/8 on 2 inches centers", None) == score.CORRECT
    assert score.judge_answer(grooves, "", '3/8" x 3/8" on 2" centers', None) == score.CORRECT
    assert score.judge_answer(grooves, "", "3/8 x 3/8", None) == score.WRONG_VALUE
    equation = "VP = 10.35 sqrt(p)"
    assert score.judge_answer(equation, "", "v_P = 10.35 sqrt(p)", None) == score.CORRECT
    assert score.judge_answer(equation, "", "V_P = 10.35√P", None) == score.CORRECT
    assert score.judge_answer(equation, "", "Vₚ = 10.35√p", None) == score.CORRECT  # subscript p
    assert score.judge_answer(equation, "", "VP = 9 sqrt(p)", None) == score.WRONG_VALUE


def test_text_answer_units_are_checked():
    assert score.judge_answer("VP = 10.35 sqrt(p)", "mph", "VP = 10.35 sqrt(p)", None) == score.WRONG_UNITS


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
    row = score.score_item(make_question("82", "%"), make_record(answer_json("82", "percentage")))
    assert row["outcome"] == score.CORRECT


def test_not_found():
    row = score.score_item(make_question("3"), make_record(answer_json(None, found=False, confidence="low")))
    assert row["outcome"] == score.NOT_FOUND


@pytest.mark.parametrize(
    "value, units, outcome",
    [
        ("30.6", "m", score.CORRECT),
        ("100.3", "ft", score.CORRECT),  # the alternative answer
        ("100.3", "feet", score.CORRECT),
        ("30.6", "m (100.3 ft)", score.CORRECT),  # the restatement in brackets is ignored
        ("30.6 (100.3 ft)", "m", score.CORRECT),
        ("100.3", "m", score.WRONG_UNITS),  # the value of the alternative with the wrong units
        ("30.6", "ft", score.WRONG_UNITS),
        ("31", "m", score.WRONG_VALUE),
    ],
)
def test_alternative_answer_in_other_units(value, units, outcome):
    question = make_question("30.6", "m", alt_value="100.3", alt_units="ft")
    assert score.score_item(question, make_record(answer_json(value, units)))["outcome"] == outcome


def test_restatement_needs_a_number_in_brackets():
    assert score.units_key("m (100.3 ft)") == "m"
    assert score.units_key("lb/(in)") == "lb/(in)"
    assert score.judge_answer("4.4", "lbf/ft2", "4.4", "psf") == score.CORRECT


def test_record_for_a_changed_question_is_missing():
    record = make_record(answer_json("3"))
    record["question"] = "An older question?"
    row = score.score_item(make_question("3"), record)
    assert row["outcome"] == score.MISSING
    assert row["detail"] != ""
    record["question"] = "What is it?"
    assert score.score_item(make_question("3"), record)["outcome"] == score.CORRECT


def test_items_csv_opens_in_excel_with_special_characters(tmp_path):
    path = tmp_path / "items.csv"
    score.write_items_csv(path, [{"question": "What was the 3σ error at 15°?"}])
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # byte-order mark
    assert "3σ error at 15°" in raw.decode("utf-8-sig")


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
