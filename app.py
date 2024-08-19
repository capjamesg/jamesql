from jamesql import JameSQL
from jamesql.index import GSI_INDEX_STRATEGIES
import json

with open("tests/fixtures/documents.json") as f:
    documents = json.load(f)

index = JameSQL()

for document in documents: # * 200000:
    index.add(document)

query = {
    "query":{"title": {"contains": "tolerate"}},
    "limit": 2,
    "sort_by": "title",
}

# index.create_gsi("title", strategy=GSI_INDEX_STRATEGIES.PREFIX)

result = index.search(query)
# print(result)

print("Showing search results for query: ", query)

for r in result["documents"]:
    print(r["title"])

print("results returned in ", result["query_time"] + "s")