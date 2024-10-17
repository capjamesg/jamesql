import json
import sys
from contextlib import ExitStack as DoesNotRaise

import pytest

from jamesql import JameSQL
from jamesql.index import GSI_INDEX_STRATEGIES
from jamesql.rewriter import simplify_string_query, grammar
from lark import   Lark


def pytest_addoption(parser):
    parser.addoption("--benchmark", action="store")


@pytest.fixture(scope="session")
def create_indices(request):
    with open("tests/fixtures/documents.json") as f:
        documents = json.load(f)

    index = JameSQL()

    for document in documents:
        index.add(document)

    with open("tests/fixtures/documents.json") as f:
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
    "query, simplified_form, number_of_documents_expected, top_result_value, raises_exception",
    [
        (
            "sky -sky",
            "",
            0,
            "",
            DoesNotRaise(),
        ),  # test negation simplification with empty string result
        (
            "screaming -sky",
            "screaming -sky",
            0,
            "",
            DoesNotRaise(),
        ),  # test negation with no simplification required
        (
            "sky sky",
            "sky",
            2,
            ["my tears ricochet", "tolerate it"],
            DoesNotRaise(),
        ),  # test duplication of single word term simplification
        (
            "sky OR mural sky",
            "sky mural",
            2,
            "tolerate it",
            DoesNotRaise(),
        ),  # test redundant single term in or query simplification
        (
            "sky OR sky OR sky",
            "sky",
            2,
            ["my tears ricochet", "tolerate it"],
            DoesNotRaise(),
        ),  # test redundant term in multiple ORs
        (
            "-lyric:sky lyric:sky",
            "",
            0,
            "",
            DoesNotRaise(),
        ),  # test double negation of in clause
    ]
)
@pytest.mark.timeout(20)
def test_simplification_then_search(
    create_indices,
    query,
    simplified_form,
    number_of_documents_expected,
    top_result_value,
    raises_exception,
):
    with raises_exception:
        parser = Lark(grammar)
        index, large_index = create_indices

        simplified_query, _ = simplify_string_query(parser, query)

        assert simplified_query == simplified_form

        response = index.string_query_search(query)

        assert len(response["documents"]) == number_of_documents_expected

        if number_of_documents_expected > 0:
            if isinstance(top_result_value, list):
                assert response["documents"][0]["title"] in top_result_value
            else:
                assert response["documents"][0]["title"] == top_result_value

        assert float(response["query_time"]) < 0.1

        # run if --benchmark is passed
        if "--benchmark" in sys.argv:
            response = large_index.string_query_search(query)

            assert float(response["query_time"]) < 0.1
