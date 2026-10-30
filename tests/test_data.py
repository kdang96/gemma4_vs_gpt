"""Checks that the QA file and the page folder agree. These tests do not call a model."""

import config
from common import load_questions


def test_each_question_has_a_page_and_each_page_has_a_question():
    questions = load_questions()
    page_ids = {q["page_id"] for q in questions}
    pdf_ids = {pdf.stem for pdf in config.PAGES_DIR.glob("*.pdf")}
    assert page_ids - pdf_ids == set(), "questions with no PDF"
    assert pdf_ids - page_ids == set(), "PDFs with no question"


def test_questions_are_complete_and_qids_are_unique():
    questions = load_questions()
    assert len(questions) == 100
    assert len({q["qid"] for q in questions}) == len(questions)
    for q in questions:
        assert q["question"] != "", q["qid"]
        assert q["expected_value"] != "", q["qid"]
        assert q["category"] in {"table_multi_condition", "chart_read", "figure_annotation", "keyvalue_lookup", "text"}


def test_numbers_from_excel_cells_are_plain_text():
    by_qid = {q["qid"]: q for q in load_questions()}
    assert by_qid["19750006673_p010#1"]["expected_value"] == "0.5"
    assert by_qid["19630002367_p013#2"]["expected_value"] == "8.3"
    assert by_qid["19750002863_p011#1"]["expected_value"] == "1148000"
