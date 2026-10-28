## Purpose
Compare Gemma 4 against OpenAI GPT models on extracting
numeric data from dense scanned technical documents.

## Objective
Compare the models on how many of the `eval/sources.csv` questions
each model answers correctly.

## Data
20 single pages from NASA technical reports, chosen for difficult
numeric content: key-value lists, grid tables, figure callouts,
chart reads and prose. Questions and expected answers are in
`eval/sources.csv`. `eval/sources.xlsx` is a copy of the CSV file.

## Scoring
- Numeric values and numbers: exact match.
- Units are a separate field and are scored separately.
  The units can be in a different form (for example "ft" or "feet"),
  but they must be the correct units. A correct number with missing
  or wrong units counts as wrong.
- Record the model's actual answer for every item, not only
  pass or fail.

## Rules
- `eval/sources.csv` is the hand-checked answer key. Never edit it
  to make a result pass. If an expected value looks wrong, stop and
  tell me.
- The OpenAI key comes from the environment only.

## Preferences
- Write all comments, documentation and communication with me in
  ASD-STE100 (Simplified Technical English).