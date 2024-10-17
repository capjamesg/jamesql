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
    with open("tests/fixtures/documents_with_categorical_values.json") as f:
        documents = json.load(f)

    index = JameSQL()

    for document in documents:
        index.add(document)

    with open("tests/fixtures/documents_with_categorical_values.json") as f:
        documents = json.load(f)

    index.create_gsi("title", strategy=GSI_INDEX_STRATEGIES.CONTAINS)
    index.create_gsi("lyric", strategy=GSI_INDEX_STRATEGIES.CONTAINS)
    index.create_gsi("listens", strategy=GSI_INDEX_STRATEGIES.NUMERIC)

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
        large_index.create_gsi("listens", strategy=GSI_INDEX_STRATEGIES.NUMERIC)
    else:
        large_index = None

    return index, large_index


@pytest.mark.parametrize(
    "query, group_by_result, number_of_documents_expected, top_result_value, raises_exception",
    [
        (
            {
                "query": {"and": [{"lyric": {"contains": "with"}}]},
                "limit": 10,
                "group_by": "title",
                "sort_by": "title",
            },
            {
                "The Bolter": [
                    {
                        "title": "The Bolter",
                        "lyric": "Started with a kiss",
                        "category": ["pop", "acoustic"],
                        "uuid": "18fbe44e19a24153b0a22841261db61c",
                        "_score": 1,
                    }
                ]
            },
            1,
            "The Bolter",
            DoesNotRaise(),
        ),  # test group by on string field
        (
            {
                "query": {"and": [{"lyric": {"contains": "kiss"}}]},
                "group_by": "category",
                "limit": 10,
                "sort_by": "title",
            },
            {
                "pop": [
                    {
                        "title": "The Bolter",
                        "lyric": "Started with a kiss",
                        "category": ["pop", "acoustic"],
                        "uuid": "eb11180b16e34467a5d457f7115fda38",
                        "_score": 1,
                    }
                ],
                "acoustic": [
                    {
                        "title": "The Bolter",
                        "lyric": "Started with a kiss",
                        "category": ["pop", "acoustic"],
                        "uuid": "eb11180b16e34467a5d457f7115fda38",
                        "_score": 1,
                    }
                ],
            },
            1,
            "The Bolter",
            DoesNotRaise(),
        ),  # test group by on categorical field
    ],
)
@pytest.mark.timeout(20)
def test_search(
    create_indices,
    query,
    group_by_result,
    number_of_documents_expected,
    top_result_value,
    raises_exception,
):
    with raises_exception:
        index, large_index = create_indices

        response = index.search(query)

        assert len(response["documents"]) == number_of_documents_expected

        # exclude uuids since they are randomly assigned on indexing in this configuration

        assert (
            DeepDiff(
                dict(response["groups"]),
                group_by_result,
                ignore_order=True,
                # ignore "score"
                exclude_regex_paths=["root\[.*\]\['uuid'\]", "root\[.*\]\['_score'\]"],
            )
            == {}
        )

        if number_of_documents_expected > 0:
            assert response["documents"][0]["title"] == top_result_value

        assert float(response["query_time"]) < 0.06

        # run if --benchmark is passed
        if "--benchmark" in sys.argv:
            response = large_index.search(query)

            assert float(response["query_time"]) < 0.06
