import json
from contextlib import ExitStack as DoesNotRaise

import pytest
from pytest import raises

from jamesql import JameSQL


@pytest.fixture
def create_index():
    with open("tests/fixtures/documents.json") as f:
        documents = json.load(f)

    index = JameSQL()

    for document in documents:
        index.add(document)

    return index


@pytest.mark.parametrize(
    "query, number_of_documents_expected, top_result_value, raises_exception",
    [
        (
            {
                "query": {"title": {"contains": "tolerate"}},
                "limit": 10,
                "sort_by": "title",
            },
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test contains
        (
            {
                "query": {"title": {"contains": "tolerats"}},
                "limit": 10,
                "sort_by": "title",
            },
            0,
            "",
            DoesNotRaise(),
        ),  # test contains
        (
            {
                "query": {"title": {"equals": "tolerate it"}},
                "limit": 10,
                "sort_by": "title",
            },
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test equals
        (
            {
                "query": {"title": {"equals": "tolerate it"}},
                "limit": 0,
                "sort_by": "title",
            },
            0,
            "",
            DoesNotRaise(),
        ),  # test limit
        (
            {
                "query": {"title": {"starts_with": "toler"}},
                "limit": 10,
                "sort_by": "title",
            },
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test starts_with
        (
            {
                "query": {"lyric": {"starts_with": "Started with"}},
                "limit": 10,
                "sort_by": "title",
            },
            1,
            "The Bolter",
            DoesNotRaise(),
        ),  # test starts_with
        (
            {
                "query": {"lyric": {"starts_with": "started with"}},
                "limit": 10,
                "sort_by": "title",
            },
            0,
            "",
            DoesNotRaise(),
        ),  # the query is case-sensitive
        (
            {
                "query": {"lyric": {"starts_with": "started with"}},
                "limit": 10,
                "sort_by": "title",
            },
            0,
            "",
            DoesNotRaise(),
        ),  # the query contains a key that doesn't exist; this shouldn't fail
        (
            {"lyric": {"starts_with": "started with"}, "limit": 10, "sort_by": "title"},
            0,
            "",
            raises(KeyError),
        ),  # the query is missing the query key
        (
            {
                "query": {
                    "and": [
                        {"title": {"starts_with": "tolerate"}},
                        {"title": {"contains": "it"}},
                    ]
                },
                "limit": 2,
                "sort_by": "title",
            },
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test complex query with single query
        (
            {
                "query": {
                    "or": {
                        "and": [
                            {"title": {"starts_with": "tolerate"}},
                            {"title": {"contains": "it"}},
                        ],
                        "lyric": {"contains": "kiss"},
                    }
                },
                "limit": 2,
                "sort_by": "title",
            },
            2,
            "The Bolter",
            DoesNotRaise(),
        ),  # test complex query with multiple queries
        (
            {
                "query": {},
                "limit": 10,
                "sort_by": "title",
            },
            0,
            "",
            DoesNotRaise(),
        ),  # test empty query
        (
            {
                "query": "*",
                "limit": 10,
                "sort_by": "title",
            },
            3,
            "The Bolter",
            DoesNotRaise(),
        ),  # test all query
    ],
)
def test_search(
    create_index,
    query,
    number_of_documents_expected,
    top_result_value,
    raises_exception,
):
    with raises_exception:
        index = create_index
        response = index.search(query)

        assert len(response["documents"]) == number_of_documents_expected

        if number_of_documents_expected > 0:
            assert response["documents"][0]["title"] == top_result_value

        assert float(response["query_time"]) < 0.1


def test_add_item(
    create_index,
):
    index = create_index

    index.add({"title": "shake it off", "lyric": "I stay out too late"})

    response = index.search(
        {
            "query": {"title": {"contains": "shake it off"}},
            "limit": 10,
            "sort_by": "title",
        }
    )

    print(response)

    assert len(response["documents"]) == 1


def test_remove_item(
    create_index,
):
    index = create_index

    response = index.search(
        {
            "query": {"title": {"contains": "tolerate"}},
            "limit": 10,
            "sort_by": "title",
        }
    )

    uuid = response["documents"][0]["uuid"]

    index.remove(uuid)

    response = index.search(
        {
            "query": {"title": {"contains": "tolerate"}},
            "limit": 10,
            "sort_by": "title",
        }
    )

    assert len(response["documents"]) == 0
