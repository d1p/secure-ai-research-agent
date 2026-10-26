"""Ensure the repo's pure modules are importable without installing services."""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("POLICY_FILE", os.path.join(REPO_ROOT, "gateway", "policy.yaml"))
for _path in (
    REPO_ROOT,
    os.path.join(REPO_ROOT, "gateway"),
    os.path.join(REPO_ROOT, "orchestrator"),
):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def pytest_addoption(parser):
    parser.addoption("--run-network", action="store_true", help="run network tests")
    parser.addoption("--run-llm", action="store_true", help="run LLM-graded tests")
    parser.addoption("--run-slow", action="store_true", help="run slow offline tests")


def pytest_collection_modifyitems(config, items):
    import pytest

    for mark, option in (
        ("network", "--run-network"),
        ("llm", "--run-llm"),
        ("slow", "--run-slow"),
    ):
        if config.getoption(option):
            continue
        skip = pytest.mark.skip(reason=f"needs {option}")
        for item in items:
            if mark in item.keywords:
                item.add_marker(skip)
