"""Code that run.py and score.py both use: the question loader and the answer schema."""

import csv
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

import config


def load_questions(csv_path: Path = config.QA_CSV) -> list[dict]:
    """Read the QA file. Return one dict per question with the benchmark field names.

    Each question gets a "qid". The qid is the page_id plus a counter, so a page
    can have more than one question (for example "ntrs19750006673_p010#1").
    """
    questions = []
    count_per_page: dict[str, int] = {}
    # "utf-8-sig" removes the byte-order mark that Excel adds to CSV files.
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            page_id = row["page_id"].strip()
            count_per_page[page_id] = count_per_page.get(page_id, 0) + 1
            questions.append(
                {
                    "qid": f"{page_id}#{count_per_page[page_id]}",
                    "page_id": page_id,
                    "category": row["Category"].strip(),
                    "question": row["User query"].strip(),
                    "expected_value": row["Expected Answer"].strip(),
                    "units": row["Units"].strip(),
                }
            )
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
