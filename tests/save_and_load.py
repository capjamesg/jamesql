import json
import os
from contextlib import ExitStack as DoesNotRaise

import pytest

from jamesql import JameSQL
from jamesql.index import GSI_INDEX_STRATEGIES, INDEX_STORE



def test_load_from_local_index():
    with open("tests/fixtures/documents.json") as f:
        documents = json.load(f)

    index = JameSQL.load()

    assert len(index.global_index) == len(documents)
    assert index.global_index
    assert len(index.gsis) == 2 # indexing two fields
    assert index.gsis["title"]
    assert len(index.uuids_to_position_in_global_index) == len(documents)
