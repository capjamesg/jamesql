import json

import pytest

from jamesql import JameSQL
from jamesql.index import GSI_INDEX_STRATEGIES


def pytest_addoption(parser):
    parser.addoption("--benchmark", action="store")


@pytest.mark.timeout(20)
def test_gsi_type_inference(request):
    with open("tests/fixtures/documents_with_varied_data_types.json") as f:
        documents = json.load(f)

    index = JameSQL()

    for document in documents:
        index.add(document)

    # check gsi type
    assert index.gsis["title"]["strategy"] == GSI_INDEX_STRATEGIES.CONTAINS.name
    assert index.gsis["lyric"]["strategy"] == GSI_INDEX_STRATEGIES.CONTAINS.name
    assert index.gsis["listens"]["strategy"] == GSI_INDEX_STRATEGIES.NUMERIC.name
    assert index.gsis["album_in_stock"]["strategy"] == GSI_INDEX_STRATEGIES.FLAT.name
    assert index.gsis["rating"]["strategy"] == GSI_INDEX_STRATEGIES.NUMERIC.name
    assert index.gsis["metadata"]["strategy"] == GSI_INDEX_STRATEGIES.NOT_INDEXABLE.name
    assert (
        index.gsis["record_last_updated"]["strategy"] == GSI_INDEX_STRATEGIES.DATE.name
    )

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

        assert (
            large_index.gsis["title"]["strategy"] == GSI_INDEX_STRATEGIES.CONTAINS.name
        )
        assert (
            large_index.gsis["lyric"]["strategy"] == GSI_INDEX_STRATEGIES.CONTAINS.name
        )
        assert (
            large_index.gsis["listens"]["strategy"] == GSI_INDEX_STRATEGIES.NUMERIC.name
        )
        assert (
            large_index.gsis["album_in_stock"]["strategy"]
            == GSI_INDEX_STRATEGIES.FLAT.name
        )
        assert (
            large_index.gsis["rating"]["strategy"] == GSI_INDEX_STRATEGIES.NUMERIC.name
        )
        assert (
            large_index.gsis["metadata"]["strategy"]
            == GSI_INDEX_STRATEGIES.NOT_INDEXABLE.name
        )
        assert (
            large_index.gsis["record_last_updated"]["strategy"]
            == GSI_INDEX_STRATEGIES.DATE.name
        )
