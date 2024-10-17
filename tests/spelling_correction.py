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
    "query, corrected_query",
    [
        ("tolerat", "tolerate"),
        ("tolerateit", "tolerate it"),  # test segmentation
        (
            "startedwith",
            "started with",
        ),  # query word that appears uppercase in corpus of text
        ("toleratt", "tolerate"),
        ("toleratt", "tolerate"),
        ("tolerate", "tolerate"),
        ("toler", "toler"),  # not in index
        ("cod", "cod"),  # not in index
    ],
)
def test_spelling_correction(create_indices, query, corrected_query):
    index = create_indices[0]
    large_index = create_indices[1]

    assert index.spelling_correction(query) == corrected_query

    if large_index:
        assert large_index.spelling_correction(query) == corrected_query
