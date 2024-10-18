import json
import random
import threading

from jamesql import JameSQL
from jamesql.index import GSI_INDEX_STRATEGIES


def test_threading():
    with open("tests/fixtures/documents.json") as f:
        documents = json.load(f)

    index = JameSQL()

    index.create_gsi("title", strategy=GSI_INDEX_STRATEGIES.CONTAINS)
    index.create_gsi("lyric", strategy=GSI_INDEX_STRATEGIES.CONTAINS)

    for document in documents * 100:
        document = document.copy()
        index.add(document, doc_id=str(random.randint(0, 1000000)))

    def query(i):
        if i == 0:
            document = documents[0].copy()
            document["title"] = "teal"
            index.add(document, "xyz")
            index.create_gsi("title", strategy=GSI_INDEX_STRATEGIES.CONTAINS)

        assert len(index.string_query_search("teal")["documents"]) == 1

    threads = []

    for i in range(2500):
        t = threading.Thread(target=query, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(index.global_index) == 301
    assert index.global_index["xyz"]["title"] == "teal"
