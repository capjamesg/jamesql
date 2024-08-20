import json
from contextlib import ExitStack as DoesNotRaise

import pytest

from jamesql import JameSQL

@pytest.fixture
def example_stub_and_query():
    with open("tests/fixtures/example_stub_and_query.json") as f:
        query = json.load(f)

    return query

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
                "query": {"lyric": {"contains": "my mural", "strict": True}},
                "limit": 1,
                "sort_by": "title",
            },
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test strict
        (
            {
                "query": {"lyric": {"contains": "my murap", "strict": True, "fuzzy": True}},
                "limit": 1,
                "sort_by": "title",
            },
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test fuzzy and strict
        (
            {
                "query": {"title": {"wildcard": "tolerat*"}},
                "limit": 1,
                "sort_by": "title",
            },
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test wildcard
        (
            {
                "query": {"lyric": {"wildcard": "my mura*", "strict": True}},
                "limit": 1,
                "sort_by": "title",
            },
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test wildcard and strict
        (
            {
                "query": {"title": {"contains": "it tolerate", "strict": True}},
                "limit": 10,
                "sort_by": "title",
            },
            0,
            "",
            DoesNotRaise(),
        ),  # test an invalid query
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
                "query": {"lyric": {"contains": "Startee with", "fuzzy": True}},
                "limit": 10,
                "sort_by": "title",
            },
            1,
            "The Bolter",
            DoesNotRaise(),
        ),  # test fuzzy on contains
        (
            {
                "query": {"lyric": {"starts_with": "Startee with", "fuzzy": True}},
                "limit": 10,
                "sort_by": "title",
            },
            1,
            "The Bolter",
            DoesNotRaise(),
        ),  # test fuzzy on starts_with
        (
            {
                "query": {"lyric": {"equals": "Startee with", "fuzzy": True}},
                "limit": 10,
                "sort_by": "title",
            },
            0,
            "",
            DoesNotRaise(),
        ),  # fuzzy doesn't work on equals
        (
            {
                "query": {"lyric": {"contains": "sky"}},
                "limit": 10,
                "sort_by": "lyric",
            },
            2,
            "my tears ricochet",
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
            DoesNotRaise(),
        ),  # the query is missing the query key; this returns an "error" key but doesn't raise an error
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
                "skip": 2,
                "limit": 1,
                "sort_by": "title",
            },
            1,
            "tolerate it",
            DoesNotRaise(),
        ),  # test start query
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

@pytest.mark.parametrize(
    "query, top_document_name, top_document_score, raises_exception",
    [
        (
            {
                "query":{"title": {"contains": "tolerate"}},
                "limit": 2,
                "query_score": "(_score + 2)",
            },
            "tolerate it",
            3.0,
            DoesNotRaise(),
        ),
        (
            {
                "query":{"title": {"contains": "tolerate"}},
                "limit": 2,
                "query_score": "(_score * 2)",
            },
            "tolerate it",
            2.0,
            DoesNotRaise(),
        ),
        (
            {
                "query": {"lyric": {"contains": "sky", "boost": 56}},
                "limit": 10,
                "sort_by": "title",
            },
            "my tears ricochet",
            56.0,
            DoesNotRaise(),
        ),
    ]
)
def test_query_score_and_boost(
    create_index,
    query,
    top_document_name,
    top_document_score,
    raises_exception,
):
    with raises_exception:
        index = create_index
        response = index.search(query)

        assert response["documents"][0]["title"] == top_document_name
        assert response["documents"][0]["_score"] == top_document_score

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

def test_query_exceeding_maximum_subqueries(example_stub_and_query, create_index):
    for i in range(0, 25):
        example_stub_and_query["query"]["and"].append({"lyric" + str(i): {"contains": "kiss"}})

    index = create_index

    response = index.search(example_stub_and_query)

    assert len(response["documents"]) == 0
    assert response["error"].startswith("Too many query conditions.")