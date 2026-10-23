import importlib.util
import pathlib
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name):
    """Import ROOT/<name>.py by path, so a folder or package of the same name elsewhere
    (e.g. a records/ directory in the repo) can't shadow the script under test."""
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeResponse:
    def __init__(self, text):
        self.text = text
        self.encoding = None

    def raise_for_status(self):
        pass


class FakeSession:
    """session.get(...) answers come from handler(params) -> html, or raise if handler returns an Exception."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []
