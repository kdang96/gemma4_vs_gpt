"""Code that run.py and score.py both use: the question loader and the answer schema."""

from pathlib import Path
from typing import Literal

import openpyxl
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

import config


def cell_text(value) -> str:
    """Return a cell value as text. A blank cell gives "".

    Excel keeps numbers as numbers, so 3 comes back as int 3 and 0.5 as float 0.5.
    str() gives "3" and "0.5", which score.parse_number() reads correctly.
    """
    if value is None:
        return ""
    return str(value).strip()


def load_questions(qa_path: Path = config.QA_FILE) -> list[dict]:
    """Read the QA workbook (first sheet). Return one dict per question with the benchmark field names.

    The page_id is the "Page file" name without ".pdf" (for example "19750006673_p010").
    Each question gets a "qid". The qid is the page_id plus a counter, so a page
    can have more than one question (for example "19750006673_p010#1").
    "Accept min" and "Accept max" are optional. They give the accepted range for a chart reading.
    "Alt answer" and "Alt units" are optional. They give the same value in other units, as the page prints it.
    The "Source evidence (review only)" column is for people. We do not send it to a model.
    """
    workbook = openpyxl.load_workbook(qa_path, read_only=True, data_only=True)
    try:
        rows = workbook.worksheets[0].iter_rows(values_only=True)
        header = [cell_text(name) for name in next(rows)]
        questions = []
        count_per_page: dict[str, int] = {}
        for values in rows:
            row = dict(zip(header, (cell_text(v) for v in values), strict=False))
            if not any(row.values()):
                continue  # an empty row at the end of the sheet
            page_id = Path(row["Page file"]).stem
            count_per_page[page_id] = count_per_page.get(page_id, 0) + 1
            questions.append(
                {
                    "qid": f"{page_id}#{count_per_page[page_id]}",
                    "page_id": page_id,
                    "category": row["Category"],
                    "question": row["User query"],
                    "expected_value": row["Expected Answer"],
                    "units": row["Units"],
                    "accept_min": row.get("Accept min", ""),
                    "accept_max": row.get("Accept max", ""),
                    "alt_value": row.get("Alt answer", ""),
                    "alt_units": row.get("Alt units", ""),
                }
            )
    finally:
        workbook.close()
    return questions


class ModelAnswer(BaseModel):
    """The JSON object that the model must return."""

    # "forbid" makes extra keys an error. It also gives additionalProperties=false
    # in the JSON schema, which OpenAI strict mode needs.
    model_config = ConfigDict(extra="forbid")

    found: bool = Field(description="false if the page does not contain the answer")
    value: str | None = Field(description="the answer; a plain number or text; null if not found")
    units: str | None = Field(description="units as shown on the page; null if none")
    confidence: Literal["high", "medium", "low"]

    @model_validator(mode="after")
    def value_agrees_with_found(self):
        # Decode-time schema enforcement cannot check this rule, so we check it here.
        has_value = self.value is not None and self.value.strip() != ""
        if self.found and not has_value:
            raise ValueError("found is true but value is empty")
        if not self.found and has_value:
            raise ValueError("found is false but value is not empty")
        return self


def parse_answer(raw: str | None) -> tuple[ModelAnswer | None, str | None]:
    """Validate the raw model text. Return (answer, None) or (None, error message)."""
    if raw is None or raw.strip() == "":
        return None, "empty response"
    try:
        return ModelAnswer.model_validate_json(raw), None
    except ValidationError as e:
        return None, str(e)
