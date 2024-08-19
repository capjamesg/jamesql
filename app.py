from nosql import NoSQL
import json

with open("tests/fixtures/documents.json") as f:
    documents = json.load(f)

index = NoSQL(
    index_by=["title", "lyric"],
)

for document in documents: # * 200000:
    index.add(document)

query = {
    "query": {},
    "limit": 2
}

index.create_gsi("title")
index.create_gsi("lyric")

result = index.search(query)

# print(result)

print("Showing search results for query: ", query)

for r in result["documents"]:
    print(r["title"])

print("results returned in ", result["query_time"] + "s")