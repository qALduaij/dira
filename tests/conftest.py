"""Tests must never inherit operator credentials, live feeds or production stores."""

import os

import pytest

from dira.config import Settings


@pytest.fixture(autouse=True)
def isolate_operator_configuration(monkeypatch):
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key in list(os.environ):
        if key.startswith("DIRA_"):
            monkeypatch.delenv(key)
