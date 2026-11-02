## Purpose
Compare Gemma 4 against OpenAI GPT models on extracting
numeric data from dense scanned technical documents.

## Objective
Compare the models on how many of the `eval/nasa_qa_all_100.xlsx` questions
each model answers correctly.

## Data
100 questions on 79 single pages from NASA technical reports, chosen for difficult
numeric content: key-value lists, grid tables, figure callouts,
chart reads and prose. Questions and expected answers are in
`eval/nasa_qa_all_100.xlsx`. The pages are in
`selected_pages/nasa_qa_all_100_pages/`.

## Scoring
- Numeric values and numbers: exact match. Exception: a chart reading
  that has `Accept min` and `Accept max` in the answer key is correct
  for each value in that range.
- If the answer key gives an `Alt answer` and `Alt units` (the same
  value in other units, as the page prints it), that answer is also correct.
- Units are a separate field and are scored separately.
  The units can be in a different form (for example "ft" or "feet"),
  but they must be the correct units. A correct number with missing
  or wrong units counts as wrong.
- Record the model's actual answer for every item, not only
  pass or fail.

## Rules
- `eval/nasa_qa_all_100.xlsx` is the hand-checked answer key. Never edit it
  to make a result pass. If an expected value looks wrong, stop and
  tell me.
- The OpenAI key comes from the environment only.

## Preferences
- Write all comments, documentation and communication with me in
  ASD-STE100 (Simplified Technical English).