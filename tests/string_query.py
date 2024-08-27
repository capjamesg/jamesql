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
    "query, rewritten_query, number_of_documents_expected, top_result_value, raises_exception",
    [
        (
            "tolerate it",
            {
                "query": {
                    "and": [
                        {
                            "or": [
                                {"lyric": {"contains": "tolerate"}},
                                {"title": {"contains": "tolerate"}},
                            ]
                        },
                        {
                            "or": [
                                {"lyric": {"contains": "it"}},
                                {"title": {"contains": "it"}},
                            ]
                        },
                    ]
                },
                "limit": 10,
            },
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test query with no special operators
        (
            "title:tolerate",
            {"query": {"and": [{"title": {"contains": "tolerate"}}]}, "limit": 10},
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test one word field search
        (
            "title:'tolerate it'",
            {"query": {"and": [{"title": {"contains": "tolerate it"}}]}, "limit": 10},
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test multi-word field search
        (
            "'tolerate'",
            {
                "query": {
                    "and": [
                        {
                            "or": {
                                "lyric": {"contains": "tolerate", "strict": True},
                                "title": {"contains": "tolerate", "strict": True},
                            }
                        }
                    ]
                },
                "limit": 10,
            },
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test multi-word search
        (
            "St*rted",
            {
                "query": {
                    "and": [
                        {
                            "or": [
                                {"lyric": {"wildcard": "St*rted"}},
                                {"title": {"wildcard": "St*rted"}},
                            ]
                        }
                    ]
                },
                "limit": 10,
            },
            1,
            "The Bolter",
            DoesNotRaise(),
        ),  # test multi-word search
        (
            "St*rted",
            {
                "query": {
                    "and": [
                        {
                            "or": [
                                {"lyric": {"wildcard": "St*rted"}},
                                {"title": {"wildcard": "St*rted"}},
                            ]
                        }
                    ]
                },
                "limit": 10,
            },
            1,
            "The Bolter",
            DoesNotRaise(),
        ),  # test multi-word search
        (
            "-started -with mural",
            {'query': {'and': [{'not': {'or': [{'title': {'contains': 'started'}}, {'lyric': {'contains': 'started'}}]}}, {'not': {'or': [{'title': {'contains': 'with'}}, {'lyric': {'contains': 'with'}}]}}, {'or': [{'title': {'contains': 'mural'}}, {'lyric': {'contains': 'mural'}}]}]}, 'limit': 10},
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # two negation queries
        (
            "title:tolerate lyric:I",
            {'query': {'and': [{'title': {'contains': 'tolerate'}}, {'lyric': {'contains': 'I'}}]}, 'limit': 10},
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # two field queries
        (
            "",
            {'query': {}},
            0,
            "",
            DoesNotRaise(),
        ),  # blank query
        (
            "Started or sky",
            {'query': {'or': [{'and': [{'or': [{'title': {'contains': 'Started'}}, {'lyric': {'contains': 'Started'}}]}]}, {'and': [{'or': [{'title': {'contains': 'sky'}}, {'lyric': {'contains': 'sky'}}]}]}]}, 'limit': 10, 'sort_by': 'title'},
            3,
            "tolerate it",
            DoesNotRaise(),
        ),  # test OR argument
        (
            "I -still",
            {
                "query": {
                    "and": [
                        {
                            "or": [
                                {"lyric": {"contains": "I"}},
                                {"title": {"contains": "I"}},
                            ]
                        },
                        {
                            "not": {
                                "or": [
                                    {"lyric": {"contains": "still"}},
                                    {"title": {"contains": "still"}},
                                ]
                            }
                        },
                    ]
                },
                "limit": 10,
            },
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test negation argument
        (
            "-started -mural -title:'The'",
            {'query': {'and': [{'not': {'or': [{'title': {'contains': 'started'}}, {'lyric': {'contains': 'started'}}]}}, {'not': {'or': [{'title': {'contains': 'mural'}}, {'lyric': {'contains': 'mural'}}]}}, {'not': {'title': {'contains': 'The'}}}]}, 'limit': 10},
            1,
            "my tears ricochet",
            DoesNotRaise(),
        ),  # test negation on field
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

        internal_query = index._compute_string_query(query)
        response = index.string_query_search(query)

        assert len(response["documents"]) == number_of_documents_expected

        # allow items to be in different orders; order doesn't matter, ignore sort_by
        result = DeepDiff(internal_query, rewritten_query, ignore_order=True, exclude_regex_paths=["root\['sort_by'\]"])

        assert result == {}

        if number_of_documents_expected > 0:
            assert response["documents"][0]["title"] == top_result_value

        assert float(response["query_time"]) < 0.1

        # run if --benchmark is passed
        if "--benchmark" in sys.argv:
            response = large_index.string_query_search(query)

            assert float(response["query_time"]) < 0.1
