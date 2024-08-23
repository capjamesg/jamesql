import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--benchmark", action="store_true", default=False, help="Enable benchmarking"
    )
    parser.addoption(
        "--long-benchmark",
        action="store_true",
        default=False,
        help="Enable long benchmark",
    )
