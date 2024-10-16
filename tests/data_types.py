import json
import sys
from contextlib import ExitStack as DoesNotRaise

import pytest
from deepdiff import DeepDiff

from jamesql import JameSQL
from jamesql.index import GSI_INDEX_STRATEGIES


def pytest_addoption(parser):
    parser.addoption("--benchmark", action="store")


@pytest.fixture
def example_stub_and_query():
    with open("tests/fixtures/example_stub_and_query.json") as f:
        query = json.load(f)

    return query


@pytest.fixture(scope="session")
def create_indices(request):
    with open("tests/fixtures/documents_with_varied_data_types.json") as f:
        documents = json.load(f)

    index = JameSQL()

    for document in documents:
        index.add(document)

    with open("tests/fixtures/documents_with_varied_data_types.json") as f:
        documents = json.load(f)

    if request.config.getoption("--benchmark") or request.config.getoption(
        "--long-benchmark"
    ):
        large_index = JameSQL()

        for document in documents * 100000:
            if request.config.getoption("--long-benchmark"):
                document = document.copy()
                document["title"] = "".join(
                    [
                        word + " "
                        for word in document["title"].split()
                        for _ in range(10)
                    ]
                )
            large_index.add(document)
    else:
        large_index = None

    return index, large_index


@pytest.mark.parametrize(
    "query, number_of_documents_expected, top_result_value, raises_exception",
    [
        (
            {
                "query": {
                    "album_in_stock": {"equals": True},
                },
                "limit": 2,
                "sort_by": "title",
            },
            2,
            "tolerate it",
            DoesNotRaise(),
        ),  # test equals with boolean
        (
            {
                "query": {
                    "rating": {"greater_than": 4.8},
                },
                "limit": 2,
                "sort_by": "title",
            },
            1,
            "The Bolter",
            DoesNotRaise(),
        ),  # test greater than with floating point
        (
            {
                "query": {
                    "metadata": {"contains": "version"},
                },
                "limit": 2,
                "sort_by": "title",
            },
            0,
            "",
            DoesNotRaise(),
        ),  # dictionaries are not indexable, so this will return a 0 result
        (
            {
                "query": {
                    "record_last_updated": {"greater_than": "2024-03-01"},
                },
                "limit": 2,
                "sort_by": "title",
            },
            1,
            "The Bolter",
            DoesNotRaise(),
        ),  # test greater than with date
        (
            {
                "query": {
                    "record_last_updated": {"less_than": "2024-03-01"},
                },
                "limit": 2,
                "sort_by": "title",
            },
            2,
            "tolerate it",
            DoesNotRaise(),
        ),  # test greater than with date
    ],
)
@pytest.mark.timeout(20)
def test_search(
    create_indices,
    query,
    number_of_documents_expected,
    top_result_value,
    raises_exception,
):
    with raises_exception:
        index, large_index = create_indices

        response = index.search(query)

        assert len(response["documents"]) == number_of_documents_expected

        if number_of_documents_expected > 0:
            assert response["documents"][0]["title"] == top_result_value

        assert float(response["query_time"]) < 0.1

        # run if --benchmark is passed
        if "--benchmark" in sys.argv:
            response = large_index.string_query_search(query)

            assert float(response["query_time"]) < 0.1
