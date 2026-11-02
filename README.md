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

- `selected_pages/nasa_qa_all_100_pages/`: 79 single-page PDFs. The file name is the page ID:
  `<NTRS citation number>_p<page number, 3 digits>.pdf`, for example `19750006673_p010.pdf`.
- `eval/nasa_qa_all_100.xlsx`: the answer key, one row per question (100 rows).
  Columns: `Title`, `Pages`, `Link` (NTRS citation), `Category`, `User query`,
  `Expected Answer`, `Units`, `Page file`, `Source evidence (review only)`, `Batch`,
  `Accept min`, `Accept max`, `Alt answer`, `Alt units`. The benchmark does not send
  `Source evidence` to a model.
  `Accept min` and `Accept max` are filled only for chart readings that are approximate.
  `Alt answer` and `Alt units` are filled only where the page prints the value in two units,
  for example "30.6 m (100.3 ft)".
  Money amounts are plain US dollar amounts with the units `USD` (for example `7900000`).
  A row has units only if the page prints them.
- All pages are upright. Three pages were printed sideways: `19750002863_p014` was
  replaced with an upright copy, and `19750004869_p012` and `19750004869_p016` have
  a PDF rotation of 90° clockwise. The renderer uses the PDF rotation.

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
| `missing` | The results file has no record for the question, or the question changed after the run. |

**Numeric or text.** If the expected answer is a plain number (for example
`39477`, `26.40`, `+13`, `±2.0` or `1.15E+06`), the question is numeric. If not, it is text.

**Numeric answers.** The model value must also be a number. Thousands
separators (`39,477`) are permitted. The number must be **exactly** equal to the
expected number. There is no tolerance. The scorer compares the values, not the text, so `26.4` matches `26.40`,
`.028` matches `0.028`, `13` matches `+13` and `1150000` matches `1.15E+06`. But `39476` does not match `39477`,
and `1.15E+06` does not match `1148000`.

- **Chart readings.** If the row has `Accept min` and `Accept max`, each number from
  min to max (edges included) is correct. Other rows have no range.
- **Number words.** `zero` to `twenty` count as numbers, so `five` matches `5`.
- **Scale words and money.** `thousand`, `million`, `billion` and `trillion` in the value or
  in the units multiply the number. `$`, `US$`, `USD`, `dollar` and `dollars` mean US dollars.
  So `7.9 million` with units `dollars`, `7.9` with units `$ million` and `$7.9 million`
  all match `7900000` `USD`. A money answer without a currency (`7.9 million` and no units) is `wrong_units`.
- **Plus-minus.** `±`, `+/-` and `+-` must be in both values or in neither.
  `±2` matches `±2.0`, but `2.0` does not.
- **Value in two units.** If the row has `Alt answer` and `Alt units`, that answer is also
  correct. For `30.6` `m` with the alternative `100.3` `ft`, both `30.6 m` and `100.3 ft` are correct.
  A second value in brackets at the end of the value or the units is ignored and not checked,
  so units `m (100.3 ft)` count as `m`. The prompt tells the model to give one value only.

**Text answers.** The model answer must contain all the words of the expected answer.
Case, punctuation and extra words are ignored. A word is a sequence of letters and digits;
a decimal point in a number stays in the word (`10.35`). Unit spellings in the words use
the alias table, `"` after a digit is `in`, `√` is `sqrt` and `_` is removed. For example,
`Hysol 5189 / 3538.` matches `Hysol 5189/3538`, and `3/8" x 3/8" on 2" centers` matches
`3/8 in x 3/8 in on 2 in centers`.

**Units.** If the `Units` cell is blank, the units are not checked. If not, the
units must be equal after normalisation: lowercase, no whitespace, no dot at the end, then the
alias table `UNIT_ALIASES` in `config.py` (for example `inches` → `in`, `"` → `in`,
`pounds` → `lb`, `N-m2` → `n*m^2`). To accept another spelling, add it to that table.

**Changed questions.** Each record in a results file has the question text. If the QA file
has a different question for that qid, the item is `missing`. Run the model again for it.
Records from runs before this check have no question text and are not checked.

**Per-item CSV.** `scores/<run>_items.csv` is UTF-8 with a byte-order mark, so Excel shows
characters such as `σ`, `°` and `Δ` correctly. If you save the file again from Excel as
"CSV" (not "CSV UTF-8"), Excel changes these characters to `?`.

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
- A text answer is correct if it contains all the expected words, so a long answer with
  extra words is also correct.
- A second value in brackets (for example the `(100.3 ft)` in `m (100.3 ft)`) is not checked.
- Results files from before 2 November 2026 are not comparable with new runs. Since then,
  8 questions were reworded, 6 more rows got a new expected answer or new units,
  3 page files changed and the prompt changed. Run the models again.

## How to run

You need Python 3.11 or later.

```bash
pip install -r requirements.txt
```

1. Render the pages to PNG (200 DPI by default). `run.py` also does this step.
   A page is rendered again only if its PDF is newer than its PNG.

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
ruff format --check .
pytest
```

`tests/test_score.py` tests the scoring rules. `tests/test_data.py` checks that the answer key
and the page folder agree, and that each range and alternative answer is complete.
The GitHub Actions workflow runs the same commands on each pull request. It does not call a model.

## Results

<!-- Paste the output of score.py here. -->

| Run | Model | N | Accuracy | Schema failure rate | Mean latency (s) | p95 latency (s) | Total cost (USD) |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

### Observations

<!-- Write your observations here. -->
