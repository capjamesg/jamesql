import json
import os
from contextlib import ExitStack as DoesNotRaise

import pytest

from jamesql import JameSQL
from jamesql.index import GSI_INDEX_STRATEGIES, INDEX_STORE


def test_save_to_local_index():
    with open("tests/fixtures/documents.json") as f:
        documents = json.load(f)

    index = JameSQL()

    for document in documents:
        index.add(document)

    index.create_gsi("title", strategy=GSI_INDEX_STRATEGIES.CONTAINS)

    index.save("documents")

    expected_index_path = os.path.join(INDEX_STORE, "documents")

    assert os.path.exists(expected_index_path)


def test_load_from_local_index():
    with open("tests/fixtures/documents.json") as f:
        documents = json.load(f)

    index = JameSQL()

    index.load("documents")

    assert len(index.global_index) == len(documents)
    assert index.global_index
    assert len(index.gsis) == 1
    assert index.gsis["title"]
    assert len(index.uuids_to_position_in_global_index) == len(documents)

    os.remove(os.path.join(INDEX_STORE, "documents"))
