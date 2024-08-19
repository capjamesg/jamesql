# test query speeds on an index with 300,000 documents
# each title is 10x longer than the original
# this allows us to test:
# - whether the index can handle a larger number of documents
# - whether the index can handle larger documents

from jamesql import JameSQL
import json
import time
from tqdm import tqdm

with open("tests/fixtures/documents.json") as f:
    documents = json.load(f)

index = JameSQL()

for document in tqdm(documents * 100000):
    document = document.copy()
    document["title"] = "".join(
        [word + " " for word in document["title"].split() for _ in range(100)]
    )
    index.add(document)

query = {
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
}
print("Creating GSI")
index.create_gsi("title")
index.create_gsi("lyric")

times = []

for i in tqdm(range(100)):
    result = index.search(query)
    times.append(float(result["query_time"]))

average_query_time = sum(times) / len(times)

print("Tests run across 100,000 queries")

if average_query_time < 0.0001:
    print("Average query time is less than 0.0001s")
else:
    print("Average query time is ", average_query_time)
