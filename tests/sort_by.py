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
    "query, top_result_title, number_of_documents_expected, raises_exception",
    [
        (
            {
                "query": {
                    "or": [
                        {
                            "lyric": {
                                "contains": "kiss",
                            }
                        },
                        {
                            "lyric": {
                                "contains": "sky",
                            }
                        },
                    ]
                },
                "limit": 10,
                "sort_by": "title",
            },
            "tolerate it",
            3,
            DoesNotRaise(),
        ),  # test with text field sort
        (
            {
                "query": {
                    "or": [
                        {
                            "lyric": {
                                "contains": "kiss",
                            }
                        },
                        {
                            "lyric": {
                                "contains": "sky",
                            }
                        },
                    ]
                },
                "limit": 10,
                "sort_by": "_score",
            },
            "The Bolter",
            3,
            DoesNotRaise(),
        ),  # test with text field score sort
        (
            {
                "query": {
                    "or": [
                        {
                            "lyric": {
                                "contains": "kiss",
                            }
                        },
                        {
                            "lyric": {
                                "contains": "sky",
                            }
                        },
                    ]
                },
                "limit": 10,
                "sort_by": "_score",
                "sort_order": "asc",
            },
            "my tears ricochet",
            3,
            DoesNotRaise(),
        ),  # test with text field score sort
        (
            {
                "query": {
                    "or": [
                        {
                            "lyric": {
                                "contains": "kiss",
                            }
                        },
                        {
                            "lyric": {
                                "contains": "sky",
                            }
                        },
                    ]
                },
                "limit": 10,
                "sort_by": "_score",
                "sort_order": "desc",
            },
            "The Bolter",
            3,
            DoesNotRaise(),
        ),  # test with text field score sort
    ],
)
@pytest.mark.timeout(20)
def test_search(
    create_indices,
    query,
    top_result_title,
    number_of_documents_expected,
    raises_exception,
):
    with raises_exception:
        index, large_index = create_indices

        response = index.search(query)

        # print(response)

        # assert False

        assert len(response["documents"]) == number_of_documents_expected
        assert response["documents"][0]["title"] == top_result_title

        if number_of_documents_expected > 0:
            assert response["documents"][0]["title"] == top_result_title

        assert float(response["query_time"]) < 0.06

        # run if --benchmark is passed
        if "--benchmark" in sys.argv:
            response = large_index.search(query)

            assert float(response["query_time"]) < 0.06
