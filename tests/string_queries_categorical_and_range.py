import json
import sys
from contextlib import ExitStack as DoesNotRaise

import pytest
from deepdiff import DeepDiff

from jamesql import JameSQL
from jamesql.index import GSI_INDEX_STRATEGIES


def pytest_addoption(parser):
    parser.addoption("--benchmark", action="store")


@pytest.fixture(scope="session")
def create_indices(request):
    with open("tests/fixtures/documents_with_categorical_and_numeric_values.json") as f:
        documents = json.load(f)

    index = JameSQL()

    for document in documents:
        index.add(document)

    index.create_gsi("title", strategy=GSI_INDEX_STRATEGIES.PREFIX)
    index.create_gsi("lyric", strategy=GSI_INDEX_STRATEGIES.CONTAINS)
    index.create_gsi("category", strategy=GSI_INDEX_STRATEGIES.FLAT)
    index.create_gsi("listens", strategy=GSI_INDEX_STRATEGIES.NUMERIC)

    with open("tests/fixtures/documents_with_categorical_and_numeric_values.json") as f:
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

        large_index.create_gsi("title", strategy=GSI_INDEX_STRATEGIES.PREFIX)
        large_index.create_gsi("lyric", strategy=GSI_INDEX_STRATEGIES.CONTAINS)
        large_index.create_gsi("category", strategy=GSI_INDEX_STRATEGIES.FLAT)
        large_index.create_gsi("listens", strategy=GSI_INDEX_STRATEGIES.NUMERIC)
    else:
        large_index = None

    return index, large_index


@pytest.mark.parametrize(
    "query, rewritten_query, number_of_documents_expected, top_result_value, raises_exception",
    [
        (
            "listens>100",
            {"query": {"and": [{"listens": {"greater_than": 100}}]}, "limit": 10},
            2,
            "The Bolter",
            DoesNotRaise(),
        ),  # test > operator
        (
            "listens<101",
            {"query": {"and": [{"listens": {"less_than": 101}}]}, "limit": 10},
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test < operator
        (
            "listens<=101",
            {"query": {"and": [{"listens": {"less_than_or_equal": 101}}]}, "limit": 10},
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test <= operator
        (
            "listens>=101",
            {
                "query": {"and": [{"listens": {"greater_than_or_equal": 101}}]},
                "limit": 10,
            },
            2,
            "The Bolter",
            DoesNotRaise(),
        ),  # test >= operator
        (
            "listens[200, 300] category:'pop'",
            {
                "query": {
                    "and": [
                        {"listens": {"range": [200, 300]}},
                        {"category": {"contains": "pop"}},
                    ]
                },
                "limit": 10,
            },
            1,
            "my tears ricochet",
            DoesNotRaise(),
        ),  # test range operator with a single categorical data query
        (
            "listens[200, 300]",
            {"query": {"and": [{"listens": {"range": [200, 300]}}]}, "limit": 10},
            2,
            "The Bolter",
            DoesNotRaise(),
        ),  # test range operator
        (
            "listens>=101 sky",
            {
                "query": {
                    "and": [
                        {"listens": {"greater_than_or_equal": 101}},
                        {
                            "or": [
                                {"title": {"contains": "sky"}},
                                {"lyric": {"contains": "sky"}},
                                {"category": {"contains": "sky"}},
                            ]
                        },
                    ]
                },
                "limit": 10,
            },
            1,
            "my tears ricochet",
            DoesNotRaise(),
        ),  # test >= operator with a single word query
        (
            "category:'pop' sky",
            {
                "query": {
                    "and": [
                        {"category": {"contains": "pop"}},
                        {
                            "or": [
                                {"title": {"contains": "sky"}},
                                {"lyric": {"contains": "sky"}},
                                {"category": {"contains": "sky"}},
                            ]
                        },
                    ]
                },
                "limit": 10,
            },
            2,
            "my tears ricochet",
            DoesNotRaise(),
        ),  # test a single categorical data query with a single word query
        (
            "category:'pop' category:'acoustic'",
            {
                "query": {
                    "and": [
                        {"category": {"contains": "pop"}},
                        {"category": {"contains": "acoustic"}},
                    ]
                },
                "limit": 10,
            },
            1,
            "my tears ricochet",
            DoesNotRaise(),
        ),  # test two categorical data queries
    ],
)
@pytest.mark.timeout(20)
def test_search(
    create_indices,
    query,
    rewritten_query,
    number_of_documents_expected,
    top_result_value,
    raises_exception,
):
    with raises_exception:
        index, large_index = create_indices

        internal_query, _ = index._compute_string_query(query)
        response = index.string_query_search(query)

        # sort response by documents[0]["title"] to make it easier to compare
        response["documents"] = sorted(response["documents"], key=lambda x: x["title"])

        assert len(response["documents"]) == number_of_documents_expected

        # allow items to be in different orders; order doesn't matter
        result = DeepDiff(internal_query, rewritten_query, ignore_order=True)

        assert result == {}

        # order documents alphabetically by title
    
        response["documents"] = sorted(response["documents"], key=lambda x: x["title"])

        if number_of_documents_expected > 0:
            assert response["documents"][0]["title"] == top_result_value

        assert float(response["query_time"]) < 0.1

        # run if --benchmark is passed
        if "--benchmark" in sys.argv:
            response = large_index.string_query_search(query)

            assert float(response["query_time"]) < 0.1
