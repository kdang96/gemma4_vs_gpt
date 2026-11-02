"""Tests for the checks in run.py. These tests do not call a model."""

from types import SimpleNamespace

import pytest

import run


def fake_client(*names):
    models = [SimpleNamespace(id=name) for name in names]
    return SimpleNamespace(models=SimpleNamespace(list=lambda: models))


def test_check_model_accepts_a_served_model():
    run.check_model(fake_client("google/gemma-4-31B-it"), "google/gemma-4-31B-it")


def test_check_model_stops_for_a_wrong_name_and_gives_the_close_name():
    with pytest.raises(SystemExit, match="Close names: google/gemma-4-31B-it"):
        run.check_model(fake_client("google/gemma-4-31B-it"), "google/gemma-4-31b-it")
