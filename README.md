# Gemma vs GPT: numeric extraction from technical PDF pages

This benchmark compares two kinds of vision-language model (VLM):

- a frontier model from the OpenAI API, and
- an open-weight model (Gemma) on a local vLLM server.

Each model gets one page image and one question. The model must find one value
on the page and give it as a JSON object. The benchmark measures how many answers
are correct, how often the output does not agree with the schema, the latency
and the cost.

## What the benchmark tests

The pages are scans of old NASA technical reports. The data on them is dense:
tables with many conditions, charts, figure labels, key-value lists and body text.
The scans have noise, small fonts and old typography. The questions test these
skills (the `Category` column in the QA file):

| Category | Skill |
|---|---|
| `table_multi_condition` | Find one cell in a table from two or more conditions (row and column). |
| `chart_read` | Read a value from a plot. |
| `figure_annotation` | Read a value from a label on a figure or diagram. |
| `keyvalue_lookup` | Find a value from a key-value list. |
| `text` | Find a value in body text or a reference list. |

## Data

- `selected_pages/nasa_qa_all_100_pages/`: 80 single-page PDFs. The file name is the page ID:
  `<NTRS citation number>_p<page number, 3 digits>.pdf`, for example `19750006673_p010.pdf`.
- `eval/nasa_qa_all_100.xlsx`: the answer key, one row per question (100 rows).
  Columns: `Title`, `Pages`, `Link` (NTRS citation), `Category`, `User query`,
  `Expected Answer`, `Units`, `Page file`, `Source evidence (review only)`, `Batch`.
  The benchmark does not send `Source evidence` to a model.

The paths are `QA_FILE` and `PAGES_DIR` in `config.py`.

### How the data was chosen

The pages come from public reports on the NASA Technical Reports Server (NTRS).
We chose each page because it has complex numeric content. A page can have more than one question.

<!-- TODO: say who wrote the questions and how the expected answers were checked. -->

The model names in the examples below (for example `google/gemma-4-27b-it`) are examples.
Use the name that your vLLM server reports at `/v1/models`.

## Scoring rules

Each question gets one outcome. Only `correct` counts as correct.
The accuracy denominator is all questions in the QA file (100). Schema failures,
"not found" answers, API errors and missing records count as incorrect.

| Outcome | Meaning |
|---|---|
| `correct` | The value matches and the units match. |
| `wrong_value` | The value does not match. |
| `wrong_units` | The value matches, but the units do not match. |
| `not_found` | The model said that the page does not contain the answer. |
| `schema_failure` | The model output is not a valid JSON object for the schema. |
| `api_error` | The API call failed after all retries. |
| `missing` | The results file has no record for the question. |

**Numeric or text.** If the expected answer is a plain number (for example
`39477`, `26.40`, `+13` or `1.15E+06`), the question is numeric. If not, it is text.

**Numeric answers.** The model value must also be a plain number. Thousands
separators (`39,477`) are permitted. The number must be **exactly** equal to the
expected number. There is no tolerance. The scorer compares the values, not the text, so `26.4` matches `26.40`,
`13` matches `+13` and `1150000` matches `1.15E+06`. But `39476` does not match `39477`,
and `1960` does not match `1961`.

**Text answers.** Normalised exact match. Both strings are changed to lowercase,
and all whitespace and punctuation is removed. Then they must be equal.
For example, `Hysol 5189 / 3538.` matches `Hysol 5189/3538`.

**Units.** If the `Units` cell is blank, the units are not checked. If not, the
units must be equal after normalisation: lowercase, no whitespace, then the
alias table `UNIT_ALIASES` in `config.py` (for example `inches` → `in`,
`pounds` → `lb`, `N-m2` → `n*m^2`). To accept another spelling, add it to that table.

**Schema.** The model must return this JSON object (see `ModelAnswer` in `common.py`):

```json
{"found": true, "value": "39477", "units": "ft", "confidence": "high"}
```

The schema is enforced at decode time on both backends (OpenAI structured outputs and
vLLM guided decoding). Pydantic then validates the output. It also checks one rule that
decode-time enforcement cannot check: `value` is empty if and only if `found` is false.
An output that fails validation counts as `schema_failure`. It is not discarded.
`score.py` validates the raw response again, so you can change the rule and score again
without new model calls.

**Latency** is the wall time of one successful API call, without retry waits.
The p95 latency uses the nearest-rank method.

**Cost** = uncached input tokens × input price + cached input tokens × cached input
price + output tokens × output price. The token counts come from the API response of
each call. The prices are in `PRICES` in `config.py`. Make sure that these prices are current
before you report a cost. The local vLLM model costs 0 USD. This does not include the cost
of the hardware.

### Known limits

- The data set is small (100 questions). One question is 1 % of the accuracy.
- Each question is asked one time. The benchmark does not measure run-to-run variation.

## How to run

You need Python 3.11 or later.

```bash
pip install -r requirements.txt
```

1. Render the pages to PNG (200 DPI by default). `run.py` also does this step.
   PNG files that exist are not rendered again.

   ```bash
   python render.py --dpi 200
   ```

2. Run the OpenAI model. Set the API key in the environment first.

   ```bash
   export OPENAI_API_KEY=...        # PowerShell: $env:OPENAI_API_KEY = "..."
   python run.py --backend openai --model gpt-5
   ```

3. Start vLLM with the Gemma model, then run it. Use `--temperature 0` for
   repeatable output, because vLLM can use the sampling settings of the model.

   ```bash
   vllm serve google/gemma-4-27b-it --port 8000
   python run.py --backend vllm --model google/gemma-4-27b-it --base-url http://localhost:8000/v1 --temperature 0
   ```

   Each run writes `results/<model>_<time>.jsonl`. Each line is one call with the raw
   response, the parsed answer, the latency, the token counts and the cost.

4. If a run stops, continue it. Completed questions are not asked again.
   Questions that had an API error are asked again.

   ```bash
   python run.py --backend openai --model gpt-5 --resume results/gpt-5_20261027-120000.jsonl
   ```

5. Score all runs in `results/`, or give the files:

   ```bash
   python score.py
   python score.py results/a.jsonl results/b.jsonl
   ```

   The Markdown summary goes to the terminal and to `scores/summary_<time>.md`.
   The per-item scoring goes to `scores/<run>_items.csv`. Use it to examine each failure.

Other options:

| Option | Script | Default | Meaning |
|---|---|---|---|
| `--dpi` | `render.py`, `run.py` | 200 | Render resolution. |
| `--concurrency` | `run.py` | 4 | Number of calls at the same time. |
| `--temperature` | `run.py` | not sent | Sampling temperature. Some OpenAI reasoning models accept only the default. |
| `--limit N` | `run.py` | all | Ask only the first N questions (for a test). |

Rate limits and server errors get up to 6 attempts with exponential backoff.
All prompts are in `prompts.py`.

## Tests

```bash
ruff check .
pytest
```

The GitHub Actions workflow runs the same commands on each pull request. It does not call a model.

## Results

<!-- Paste the output of score.py here. -->

| Run | Model | N | Accuracy | Schema failure rate | Mean latency (s) | p95 latency (s) | Total cost (USD) |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

### Observations

<!-- Write your observations here. -->
