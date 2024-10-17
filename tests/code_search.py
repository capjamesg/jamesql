import json
import os
import sys
from contextlib import ExitStack as DoesNotRaise

import pytest
from deepdiff import DeepDiff

from jamesql import JameSQL
from jamesql.index import GSI_INDEX_STRATEGIES

CODE_BASE_DIR = "tests/fixtures/code"


def pytest_addoption(parser):
    parser.addoption("--benchmark", action="store")


@pytest.fixture(scope="session")
def create_indices(request):
    # open all files in code/*
    documents = []

    for file in os.listdir("tests/fixtures/code"):
        with open(os.path.join("tests/fixtures/code", file)) as f:
            documents.append({"file_name": file, "code": f.read()})

    index = JameSQL()

    index.create_gsi("file_name", strategy=GSI_INDEX_STRATEGIES.PREFIX)
    index.create_gsi("code", strategy=GSI_INDEX_STRATEGIES.TRIGRAM_CODE)

    for document in documents:
        index.add(document)

    if request.config.getoption("--benchmark") or request.config.getoption(
        "--long-benchmark"
    ):
        large_index = JameSQL()

        for document in documents * 100000:
            if request.config.getoption("--long-benchmark"):
                document = document.copy()

            large_index.add(document)

        large_index.create_gsi("file_name", strategy=GSI_INDEX_STRATEGIES.PREFIX)
        large_index.create_gsi("code", strategy=GSI_INDEX_STRATEGIES.TRIGRAM_CODE)
    else:
        large_index = None

    return index, large_index


@pytest.mark.parametrize(
    "query, number_of_documents_expected, top_result_value, raises_exception",
    [
        (
            {"query": {"and": [{"code": {"contains": "def"}}]}, "limit": 10},
            3,
            "index.py",
            DoesNotRaise(),
        ),  # test code search for valid query
        (
            {"query": {"and": [{"code": {"contains": "ef "}}]}, "limit": 10},
            3,
            "index.py",
            DoesNotRaise(),
        ),  # test code search for valid query with space
        (
            {"query": {"and": [{"code": {"contains": "banana"}}]}, "limit": 10},
            0,
            "",
            DoesNotRaise(),
        ),  # test code search with toekn not in documents
        (
            {"query": {"and": [{"code": {"contains": "return "}}]}, "limit": 10},
            3,
            "index.py",
            DoesNotRaise(),
        ),  # test code search with > 3 char token
    ],
)
@pytest.mark.timeout(20)
def test_code_search(
    create_indices,
    query,
    number_of_documents_expected,
    top_result_value,
    raises_exception,
):
    with raises_exception:
        index, large_index = create_indices

        response = index.search(query)

        # sort response by documents[0]["title"] to make it easier to compare
        response["documents"] = sorted(
            response["documents"], key=lambda x: x["file_name"]
        )

        assert len(response["documents"]) == number_of_documents_expected

        if number_of_documents_expected > 0:
            assert response["documents"][0]["file_name"] == top_result_value

        assert float(response["query_time"]) < 0.06

        # run if --benchmark is passed
        if "--benchmark" in sys.argv:
            response = large_index.search(query)

            assert float(response["query_time"]) < 0.06
