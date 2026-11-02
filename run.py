"""Ask a model each question in the QA file, with the page image. Record the answers.

Usage:
  python run.py --backend openai --model gpt-5
  python run.py --backend vllm --model google/gemma-4-27b-it --base-url http://localhost:8000/v1
  python run.py --backend openai --model gpt-5 --resume results/gpt-5_20261027-120000.jsonl
  python run.py --backend openai --model gpt-5 --resume results/gpt-5_20261027-120000.jsonl --only "19630002367_p018#2"

The OpenAI backend reads the API key from OPENAI_API_KEY.
The vLLM backend reads an optional key from VLLM_API_KEY.
"""

import argparse
import base64
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import openai
from openai import OpenAI

import config
import prompts
import render
from common import ModelAnswer, load_questions, parse_answer
from costs import TokenUsage, calculate_cost

# Errors that can go away if we wait and try again.
RETRY_ERRORS = (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "answer", "schema": ModelAnswer.model_json_schema(), "strict": True},
}


def make_client(backend: str, base_url: str | None) -> OpenAI:
    # max_retries=0: we do the retries in call_model(), so that the latency
    # we record is for one successful attempt only.
    if backend == "openai":
        return OpenAI(max_retries=0)  # the key comes from OPENAI_API_KEY
    if base_url is None:
        raise SystemExit("--base-url is necessary for the vllm backend")
    return OpenAI(base_url=base_url, api_key=os.environ.get("VLLM_API_KEY", "EMPTY"), max_retries=0)


def image_data_url(png: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode("ascii")


def estimate_cost(backend: str, model: str, usage: TokenUsage) -> float | None:
    if backend == "vllm":
        return 0.0
    if model not in config.PRICES:
        return None
    return calculate_cost(usage, config.PRICES[model])


def call_model(client: OpenAI, args, question: dict) -> dict:
    """Send one question. Return one result record. Do not raise on API errors."""
    png = render.png_path(question["page_id"], args.dpi)
    messages = [
        {"role": "system", "content": prompts.SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompts.USER_TEMPLATE.format(question=question["question"])},
                {"type": "image_url", "image_url": {"url": image_data_url(png), "detail": "high"}},
            ],
        },
    ]
    request = {"model": args.model, "messages": messages, "response_format": RESPONSE_FORMAT}
    if args.temperature is not None:
        request["temperature"] = args.temperature

    record = {
        "qid": question["qid"],
        "page_id": question["page_id"],
        "question": question["question"],  # score.py uses it to find records for a changed question
        "model": args.model,
        "backend": args.backend,
        "dpi": args.dpi,
        "timestamp": datetime.now(UTC).isoformat(),
        "raw_response": None,
        "finish_reason": None,
        "parsed": None,
        "error_type": None,  # None, "schema" or "api"
        "error": None,
        "latency_s": None,
        "input_tokens": None,
        "output_tokens": None,
        "cached_input_tokens": None,
        "cost_usd": None,
    }

    for attempt in range(1, config.MAX_ATTEMPTS + 1):
        try:
            start = time.perf_counter()
            response = client.chat.completions.create(**request)
            record["latency_s"] = time.perf_counter() - start
            break
        except RETRY_ERRORS as e:
            if attempt == config.MAX_ATTEMPTS:
                record["error_type"] = "api"
                record["error"] = f"{type(e).__name__}: {e}"
                return record
            wait = min(60, 2**attempt) + random.random()
            print(f"  {question['qid']}: {type(e).__name__}, retry in {wait:.0f} s")
            time.sleep(wait)
        except openai.APIError as e:
            # For example a bad request or an unknown model. A retry does not help.
            record["error_type"] = "api"
            record["error"] = f"{type(e).__name__}: {e}"
            return record

    choice = response.choices[0]
    record["raw_response"] = choice.message.content
    record["finish_reason"] = choice.finish_reason
    if response.usage is not None:
        # The output tokens include the reasoning tokens. OpenAI bills them as output.
        # vLLM can send no prompt_tokens_details.
        details = response.usage.prompt_tokens_details
        usage = TokenUsage(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            cached_input_tokens=(details.cached_tokens or 0) if details else 0,
        )
        record["input_tokens"] = usage.input_tokens
        record["output_tokens"] = usage.output_tokens
        record["cached_input_tokens"] = usage.cached_input_tokens
        record["cost_usd"] = estimate_cost(args.backend, args.model, usage)

    answer, error = parse_answer(choice.message.content)
    if answer is None:
        record["error_type"] = "schema"
        record["error"] = error
    else:
        record["parsed"] = answer.model_dump()
    return record


def completed_qids(results_path: Path) -> set[str]:
    """Return the qids that have a final record. A record with an API error is not final."""
    done = set()
    for line in results_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # a line that was cut when the last run stopped
        if record["error_type"] == "api":
            done.discard(record["qid"])
        else:
            done.add(record["qid"])
    return done


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend", choices=["openai", "vllm"], required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", help="vLLM server URL, for example http://localhost:8000/v1")
    parser.add_argument("--dpi", type=int, default=config.DEFAULT_DPI)
    parser.add_argument("--concurrency", type=int, default=config.DEFAULT_CONCURRENCY)
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="not sent if not set (some OpenAI reasoning models accept only the default)",
    )
    parser.add_argument("--resume", type=Path, help="results file of a run that stopped")
    parser.add_argument("--limit", type=int, help="ask only the first N questions (for a test)")
    parser.add_argument(
        "--only",
        nargs="+",
        default=[],
        metavar="QID",
        help="ask only these questions, also if the --resume file has them (score.py uses the last record of a qid)",
    )
    args = parser.parse_args()

    questions = load_questions()
    if args.only:
        unknown = set(args.only) - {q["qid"] for q in questions}
        if unknown:
            parser.error(f"qids not in the QA file: {', '.join(sorted(unknown))}")
        questions = [q for q in questions if q["qid"] in args.only]
    if args.limit:
        questions = questions[: args.limit]

    if args.resume:
        results_path = args.resume
        done = completed_qids(results_path) - set(args.only)
        # If the last run stopped during a write, start on a new line.
        text = results_path.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            with open(results_path, "a", encoding="utf-8") as f:
                f.write("\n")
    else:
        config.RESULTS_DIR.mkdir(exist_ok=True)
        safe_model = re.sub(r"[^A-Za-z0-9._-]", "_", args.model)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        results_path = config.RESULTS_DIR / f"{safe_model}_{stamp}.jsonl"
        done = set()

    todo = [q for q in questions if q["qid"] not in done]
    print(f"{len(todo)} questions to ask, {len(done)} already done. Output: {results_path}")

    # Render before the threads start, so that two threads never write the same PNG.
    render.render_all(args.dpi)

    client = make_client(args.backend, args.base_url)
    with open(results_path, "a", encoding="utf-8") as out, ThreadPoolExecutor(args.concurrency) as pool:
        futures = [pool.submit(call_model, client, args, q) for q in todo]
        # Only this loop (the main thread) writes to the file.
        for future in as_completed(futures):
            record = future.result()
            # Write and flush each record at once, so a stop loses no completed call.
            out.write(json.dumps(record) + "\n")
            out.flush()
            status = record["error_type"] or "ok"
            latency = f"{record['latency_s']:.1f} s" if record["latency_s"] else "-"
            print(f"  {record['qid']}: {status} ({latency})")


if __name__ == "__main__":
    main()
