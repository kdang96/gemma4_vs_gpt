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

We curated the questions in two steps:

1. **Selection and writing.** We used manual work together with Claude (an AI model from Anthropic)
   to select the pages and to write the questions and the expected answers.
2. **Manual verification.** A person then compared each question, expected answer and unit
   with the page by hand. The person corrected or removed each item that was not correct or not clear.

Claude is not one of the models that this benchmark compares.

The model names in the examples below (for example `google/gemma-4-27b-it`) are examples.
Use the name that your vLLM server reports at `/v1/models`. The name is case-sensitive
(`gemma-4-31b-it` is not `gemma-4-31B-it`). Before the first question, `run.py` makes sure that
the server has the model. If not, it stops and shows the close names.

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
`39477`, `26.40`, `+13` or `1.15E+06`), the question is numeric. If not, it is text.

**Numeric answers.** The model value must also be a number. Thousands
separators (`39,477`) are permitted. The number must be **exactly** equal to the
expected number. There is no tolerance. The scorer compares the values, not the text, so `26.4` matches `26.40`,
`.028` matches `0.028`, `13` matches `+13` and `1150000` matches `1.15E+06`. But `39476` does not match `39477`,
and `1.15E+06` does not match `1148000`.

- **Powers of ten.** `1.148X10^6`, `1.148 x 10^6`, `1.148*10**6` and `1.148×10⁶` all match `1148000`.
  The exponent must have `^`, `**` or superscript digits, so `2 x 105` is not a number.

- **Chart readings.** If the row has `Accept min` and `Accept max`, each number from
  min to max (edges included) is correct. Other rows have no range.
- **Number words.** `zero` to `twenty` count as numbers, so `five` matches `5`.
- **Scale words and money.** `thousand`, `million`, `billion` and `trillion` in the value or
  in the units multiply the number. `$`, `US$`, `USD`, `dollar` and `dollars` mean US dollars.
  So `7.9 million` with units `dollars`, `7.9` with units `$ million` and `$7.9 million`
  all match `7900000` `USD`. A money answer without a currency (`7.9 million` and no units) is `wrong_units`.
- **Plus-minus.** A `±`, `+/-` or `+-` at the start of the value is ignored, so `±1`, `+/-1`
  and `1` all match `1`. A minus sign is not ignored: `-4` does not match `4`.
- **Value in two units.** If the row has `Alt answer` and `Alt units`, that answer is also
  correct. For `30.6` `m` with the alternative `100.3` `ft`, both `30.6 m` and `100.3 ft` are correct.
  A second value in brackets at the end of the value or the units is ignored and not checked,
  so units `m (100.3 ft)` count as `m`. The prompt tells the model to give one value only.

**Text answers.** The model answer must contain all the words of the expected answer.
Case, punctuation and extra words are ignored. A word is a sequence of letters and digits;
a decimal point in a number stays in the word (`10.35`). Unit spellings in the words use
the alias table, `"` after a digit is `in`, `√` is `sqrt` and `_` is removed. Subscript and
superscript characters become plain characters (Unicode NFKC), so `Vₚ` is `vp`. For example,
`Hysol 5189 / 3538.` matches `Hysol 5189/3538`, and `3/8" x 3/8" on 2" centers` matches
`3/8 in x 3/8 in on 2 in centers`.

**Units.** If the `Units` cell is blank, the units are not checked. If not, the
units must be equal after normalisation: lowercase, no whitespace, no dot at the end, then the
alias table `UNIT_ALIASES` in `config.py` (for example `inches` → `in`, `"` → `in`,
`pounds` → `lb`, `N-m2` → `n*m^2`, `F` → `degf`, and the look-alikes `º` and `˚` → `deg`). To accept another spelling, add it to that table.
A `unit -` label at the start is removed before the lookup, because some axis labels print the
units as `(UNIT - G²)`. So `UNIT - G^2` matches `G^2`.

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

**Mean input tokens** is the mean of the input tokens of each call. Most of these tokens are
image tokens, so the value shows how much of the page image the model gets. The system prompt
and the question use approximately 300 tokens. If the mean is near 600 for Gemma, the image got
only approximately 280 visual tokens, and the run is not valid (see step 3 of "How to run").

**Cost** = uncached input tokens × input price + cached input tokens × cached input
price + output tokens × output price. The token counts come from the API response of
each call. The prices are in `PRICES` in `config.py`. Make sure that these prices are current
before you report a cost. The local vLLM model costs 0 USD. This does not include the cost
of the hardware.

### Known limits

- The data set is small (100 questions). One question is 1 % of the accuracy.
- Each question is asked one time. The benchmark does not measure run-to-run variation.
  Before you report a difference of a few points between two models, run each model 2 or 3 times.
- The `confidence` field is not a useful signal for most models. In the final runs, Gemma and
  gpt-4.1-mini gave `high` for all 100 answers, also for their 9 and 7 wrong answers. gpt-5-nano
  gave `high` for 16 of its 26 wrong answers. gpt-5-mini is the exception: 8 of its 11 `medium`
  answers were wrong.
- A text answer is correct if it contains all the expected words, so a long answer with
  extra words is also correct.
- A second value in brackets (for example the `(100.3 ft)` in `m (100.3 ft)`) is not checked.
- Results files from before 2 November 2026 are not comparable with new runs. Since then,
  8 questions were reworded, 6 more rows got a new expected answer or new units,
  3 page files changed and the prompt changed. Run the models again.
- The second review of 2 November 2026 (after the first gpt-4.1-mini and Gemma runs) changed
  the answer key again:
  - 3 questions were reworded, because a correct answer could fail or the question was not clear:
    `19750006673_p016#1` (asked for an "intensity", but the answer is a count),
    `19750002862_p012#1` (now names the "Airplane 1 & 2" column) and
    `19620000016_p006#1` (now asks for the table number, not "which table").
  - 2 questions were reworded so that a plain number is the correct answer, and their expected
    answers have no plus-minus sign now: `19750006673_p020#1` (now `2.0` `g`, was `±2.0`) and
    `19630002367_p018#2` (now `1` `deg`, was `±1`).
  - `19640000612_p049#1` has no units now (was `mph`). The answer is an equation, and the
    label on the figure prints no units.
  - `19750006674_p038#1` was reworded after the first full results. The table in Figure 19 has
    two "AIR MANEUVER" columns for VTOL (`0.4%` and `1.2%`), and the old question did not tell
    which one. The question now asks for the second air maneuver, after the descent. The expected
    answer is still `1.2` `%`.

  Results files from before this change show the 6 reworded items as `missing`. Run the models
  again for these items with `--only`.
  For the first 3 rows, `19640000612_p049#1` and `19750006674_p038#1`, the `Source evidence`
  column tells what changed and why.
  The same review added the `F` unit alias, the `unit -` label rule and the Gemma image token budget.
  The scorer then also got the power-of-ten rule and the `º` and `˚` unit aliases.
  Gemma results files that have no `max_soft_tokens` field used the default budget of 280 tokens.
  They are not comparable with new runs.

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

   **Image token budget.** Gemma 4 converts each image to a fixed maximum number of visual tokens
   (70, 140, 280, 560 or 1120). The default is 280. At 280 tokens, the model cannot read the digits
   in a dense table. `run.py` sends `VLLM_MAX_SOFT_TOKENS` from `config.py` (1120) with each request,
   and the results file records it in `max_soft_tokens`. You do not have to restart the server
   to change the budget. Use `--max-soft-tokens` to try a different budget.
   After the first questions, look at `input_tokens` in the results file. It must be much more
   than 600. If it is approximately 600, the server did not use the budget. Then start the server
   with `--mm-processor-kwargs '{"max_soft_tokens": 1120}'` and run again.
   See the [vLLM recipe for Gemma 4](https://recipes.vllm.ai/Google/gemma-4-31B-it).

   Each run writes `results/<model>_<time>.jsonl`. Each line is one call with the raw
   response, the parsed answer, the latency, the token counts, the image token budget and the cost.

4. If a run stops, continue it. Completed questions are not asked again.
   Questions that had an API error are asked again.

   ```bash
   python run.py --backend openai --model gpt-5 --resume results/gpt-5_20261027-120000.jsonl
   ```

   To ask some questions again (for example after a change to the QA file), give their qids
   with `--only`. The new records are added to the end of the file. `score.py` uses the last
   record of each qid, so the new answer replaces the old one. The cost and latency of the old
   call are then not in the summary.

   ```bash
   python run.py --backend openai --model gpt-5 --resume results/gpt-5_20261027-120000.jsonl --only "19750006673_p020#1" "19630002367_p018#2"
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
| `--max-soft-tokens` | `run.py` | 1120 | vLLM backend only: maximum visual tokens for one image (Gemma 4). |
| `--limit N` | `run.py` | all | Ask only the first N questions (for a test). |
| `--only QID ...` | `run.py` | all | Ask only these questions. With `--resume`, ask them again also if they are done. |

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

These are the results of 2 November 2026 for the final answer key. The source is
`scores/summary_20261102-184816.md`. The per-item scoring of each run is in `scores/<run>_items.csv`.

Run settings: 200 DPI for all runs. Gemma ran on a local vLLM server with an image token budget
of 1120 (`max_soft_tokens`). Each model answered each question one time. For the items that
were asked again after the answer key changed, the summary uses only the last call.

The table is sorted by accuracy.

| Run | Model | N | Accuracy | Schema failure rate | Mean latency (s) | p95 latency (s) | Mean input tokens | Total cost (USD) |
|---|---|---|---|---|---|---|---|---|
| gpt-6.1-terra_20261102-172050 | gpt-6.1-terra | 100 | 100.0% | 0.0% | 1.99 | 3.02 | 3392 | 0.3573 |
| gpt-6-astra_20261102-171615 | gpt-6-astra | 100 | 100.0% | 0.0% | 2.35 | 3.24 | 3392 | 3.5433 |
| gpt-4.1-mini_20261102-165614 | gpt-4.1-mini | 100 | 93.0% | 0.0% | 1.40 | 2.08 | 5511 | 0.2235 |
| google_gemma-4-31B-it_20261102-164606 | google/gemma-4-31B-it | 100 | 91.0% | 0.0% | 1.43 | 1.87 | 1437 | 0.0000 |
| gpt-5-mini_20261102-170042 | gpt-5-mini | 100 | 90.0% | 0.0% | 5.48 | 11.62 | 4204 | 0.1679 |
| gpt-5-nano_20261102-165017 | gpt-5-nano | 100 | 74.0% | 0.0% | 7.88 | 15.92 | 5137 | 0.0664 |

Accuracy per category (correct / total):

| Category | gpt-6.1-terra | gpt-6-astra | gpt-4.1-mini | Gemma 4 31B | gpt-5-mini | gpt-5-nano |
|---|---|---|---|---|---|---|
| chart_read | 13/13 (100%) | 13/13 (100%) | 7/13 (54%) | 10/13 (77%) | 6/13 (46%) | 3/13 (23%) |
| figure_annotation | 19/19 (100%) | 19/19 (100%) | 19/19 (100%) | 18/19 (95%) | 18/19 (95%) | 16/19 (84%) |
| keyvalue_lookup | 14/14 (100%) | 14/14 (100%) | 14/14 (100%) | 13/14 (93%) | 14/14 (100%) | 13/14 (93%) |
| table_multi_condition | 29/29 (100%) | 29/29 (100%) | 28/29 (97%) | 25/29 (86%) | 28/29 (97%) | 19/29 (66%) |
| text | 25/25 (100%) | 25/25 (100%) | 25/25 (100%) | 25/25 (100%) | 24/25 (96%) | 23/25 (92%) |

Outcome counts:

| Outcome | gpt-6.1-terra | gpt-6-astra | gpt-4.1-mini | Gemma 4 31B | gpt-5-mini | gpt-5-nano |
|---|---|---|---|---|---|---|
| correct | 100 | 100 | 93 | 91 | 90 | 74 |
| wrong_value | 0 | 0 | 7 | 7 | 8 | 23 |
| wrong_units | 0 | 0 | 0 | 0 | 2 | 2 |
| not_found | 0 | 0 | 0 | 2 | 0 | 1 |
| schema_failure | 0 | 0 | 0 | 0 | 0 | 0 |
| api_error | 0 | 0 | 0 | 0 | 0 | 0 |
| missing | 0 | 0 | 0 | 0 | 0 | 0 |

### Observations

- **Gemma against the GPT models.** Gemma 4 31B answered 91 of 100 questions correctly.
  This is 2 questions fewer than gpt-4.1-mini (93) and 9 fewer than gpt-6.1-terra and
  gpt-6-astra (100). It is 1 question more than gpt-5-mini (90) and 17 more than gpt-5-nano (74).
  Each model ran one time, so a difference of 1 or 2 questions is not a reliable result
  (see "Known limits").
- **Strengths and weaknesses of Gemma.** Gemma read charts better than the small GPT models
  (10 of 13, against 7, 6 and 3). But it got fewer table items correct than gpt-4.1-mini and
  gpt-5-mini (25 of 29, against 28). Of the 9 Gemma failures, 4 were table cells (2 of them in
  Table 1(a) of `19620000016_p010`), 3 were chart readings, 1 was a key-value item and 1 was a
  figure label. Two failures were `not_found` answers for values that are on the page, and one
  was a misread digit (`70,395` for `73395`).
- **The gpt-6 models.** gpt-6.1-terra and gpt-6-astra answered all 100 questions correctly.
  gpt-6-astra cost approximately 10 times more (3.54 USD against 0.36 USD) and was a little slower.
- **Cost.** Gemma on the local server costs 0 USD, without the cost of the hardware. Of the GPT
  models, gpt-5-nano cost the least (0.07 USD) but had the lowest accuracy.
- **Latency.** Gemma (1.43 s) and gpt-4.1-mini (1.40 s) had the lowest mean latency.
  gpt-5-mini and gpt-5-nano were approximately 4 to 6 times slower (p95 of 12 s and 16 s)
  and less accurate.
- **Input tokens.** Gemma used approximately 1440 input tokens for each question, which is
  less than half of the input tokens of the GPT models.
- **Schema.** No model had a schema failure. Decode-time enforcement of the schema works on
  both backends.
- **Chart readings are the most difficult category.** For the 4 models below the gpt-6 models,
  chart readings had the lowest accuracy. Two chart items failed for 4 of the 6 models:
  `19750016645_p019#1` and `19640000612_p028#2`. All 4 answers were outside the accepted range.
- **Correct value, format not accepted.** Some failures have the correct value in a format that
  the scorer does not accept. gpt-5-mini gave the units `° above horizontal` and the value
  `over 22,000`. gpt-5-nano gave the values `±1°` (with no units), `about 26 percent` and
  `nine-point`, and the units `WT-LB`. The scorer rejects these on purpose: a qualifier such as
  "over" or "about" is not a plain number, and the units must be in the units field. If the
  scorer accepted them, gpt-5-mini would have 92 correct answers (1 more than Gemma) and
  gpt-5-nano 78.
