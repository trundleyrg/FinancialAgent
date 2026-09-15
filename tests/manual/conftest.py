"""Live-test conftest.

Adds --live flag and skips live tests by default. Tests in tests/manual/
opt in to live behavior by being in this directory — pytest collects them
only when explicitly invoked (`pytest tests/manual/...`).
"""
import os

import pytest


LIVE_DIR = os.path.dirname(os.path.abspath(__file__))


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run live integration tests that hit akshare + DuckDB",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip_live = pytest.mark.skip(reason="needs --live flag and network access")
    for item in items:
        # Only skip items collected from this conftest's directory (tests/manual/).
        # pytest invokes every conftest.py it finds under the testpaths root, so
        # without this filter the regular suite would also be skipped.
        item_path = os.path.abspath(str(item.fspath))
        if item_path.startswith(LIVE_DIR):
            item.add_marker(skip_live)
