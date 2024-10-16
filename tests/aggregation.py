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
    with open("tests/fixtures/documents.json") as f:
        documents = json.load(f)

    index = JameSQL()

    for document in documents:
        index.add(document)

    index.create_gsi("title", strategy=GSI_INDEX_STRATEGIES.CONTAINS)
    index.create_gsi("lyric", strategy=GSI_INDEX_STRATEGIES.CONTAINS)

    with open("tests/fixtures/documents.json") as f:
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

        large_index.create_gsi("title", strategy=GSI_INDEX_STRATEGIES.CONTAINS)
        large_index.create_gsi("lyric", strategy=GSI_INDEX_STRATEGIES.CONTAINS)
    else:
        large_index = None

    return index, large_index


@pytest.mark.parametrize(
    "query, introspection_results, number_of_documents_expected, top_result_value, raises_exception",
    [
        (
            {
                "query": {
                    "and": [
                        {
                            "lyric": {
                                "contains": "my",
                            }
                        },
                    ]
                },
                "metrics": ["aggregate"],
                "limit": 10,
                "sort_by": "title",
            },
            {"unique_record_values": {"title": 1, "lyric": 1}},
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test query with introspection
        (
            {
                "query": {},
                "metrics": ["aggregate"],
                "limit": 10,
                "sort_by": "title",
            },
            {},
            0,
            "",
            DoesNotRaise(),
        ),  # test blank query with introspection
        (
            {
                "query": "*",
                "metrics": ["aggregate"],
                "limit": 10,
                "sort_by": "title",
            },
            {"unique_record_values": {"title": 3, "lyric": 3}},
            3,
            "tolerate it",
            DoesNotRaise(),
        ),  # test all (*) query with introspection
    ],
)
@pytest.mark.timeout(20)
def test_search(
    create_indices,
    query,
    introspection_results,
    number_of_documents_expected,
    top_result_value,
    raises_exception,
):
    with raises_exception:
        index, large_index = create_indices

        response = index.search(query)

        assert len(response["documents"]) == number_of_documents_expected

        # allow items to be in different orders; order doesn't matter
        result = DeepDiff(
            response.get("metrics", {}), introspection_results, ignore_order=True
        )

        assert result == {}

        if number_of_documents_expected > 0:
            assert response["documents"][0]["title"] == top_result_value

        assert float(response["query_time"]) < 0.1

        # run if --benchmark is passed
        if "--benchmark" in sys.argv:
            response = large_index.search(query)

            assert float(response["query_time"]) < 0.1
