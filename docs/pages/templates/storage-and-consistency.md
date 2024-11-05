---
layout: default
title: Data Storage and Consistency
permalink: /storage-and-consistency/
---

JameSQL indices are stored in memory and on disk.

When you call the `add()` method, the document is appended to an `index.jamesql` file in the directory in which your program is running. This file is serialized as JSONL.

When you load an index, all entries in the `index.jamesql` file will be read back into memory.

_Note: You will need to manually reconstruct your indices using the `create_gsi()` method after loading an index._

## Data Consistency

When you call `add()`, a `journal.jamesql` file is created. This is used to store the contents of the `add()` operation you are executing. If JameSQL terminates during an `add()` call for any reason (i.e. system crash, program termination), this journal will be used to reconcile the database.

Next time you initialize a JameSQL instance, your documents in `index.jamesql` will be read into memory. Then, the transactions in `journal.jamesql` will be replayed to ensure the index is consistent. Finally, the `journal.jamesql` file will be deleted.

You can access the JSON of the last transaction issued, sans the `uuid`, by calling `index.last_transaction`.

If you were in the middle of ingesting data, this could be used to resume the ingestion process from where you left off by allowing you to skip records that were already ingested.

## Reducing Precision for Large Results Pages

By default, JameSQL assigns scores to the top 1,000 documents in each clause in a query. Consider the following query;

<pre><code class="language-python">
query = {
    "query": {
        "and": [
            {
                "artist": {
                    "equals": "Taylor Swift"
                }
            },
            {
                "title": {
                    "equals": "tolerate it"
                }
            }
        ]
    },
    "limit": 10
}
</code></pre>

The `{ "artist": { "equals": "Taylor Swift" } }` clause will return the top 1,000 documents that match the query. The `{ "title": { "equals": "tolerate it" } }` clause will return the top 1,000 documents that match the query.

These will then be combine and sorted to return the 10 documents of the 2,000 processed that have the highest score.

This means that if you have a large number of documents that match a query, you may not get precisely the most relevant documents in the top 10 results, rather an approximation of the most relevant documents.

You can override the number of documents to consider with:

<pre><code class="language-python">
index.match_limit_for_large_result_pages = 10_000
</code></pre>

The higher this number, the longer it will take to process results with a large number of matching documents.