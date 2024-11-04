---
layout: default
title: Search for Documents
permalink: /search/
---

There are two ways you can run a search:

- Using a natural language query with JameSQL operators, or;
- Using a JSON DSL.

## Using the JSON DSL

A query has the following format:

<pre><code class="language-python">
{
    "query": {
        "field": "value"
    },
    "limit": 10,
    "sort_by": "field",
    "skip": 0
}
</code></pre>

- `query` is a dictionary that contains the fields to search for.
- `limit` is the maximum number of documents to return. (default 10)
- `sort_by` is the field to sort by. (default None)
- `skip` is the number of documents to skip. This is useful for implementing pagination. (default 0)

`limit`, `sort_by`, and `skip` are optional.

Within the `query` key you can query for documents that match one or more conditions.

An empty query returns no documents.

### Running a search

To search for documents that match a query, use the following code:

<pre><code class="language-python">
result = index.search(query)
</code></pre>

This returns a JSON payload with the following structure:
<pre><code class="language-python">

{
    "documents": [
        {"uuid": "1", ...}
        {"uuid": "2", ...}
        ...
    ],
    "query_time": 0.0001,
    "total_results": 200
}
</code></pre>

You can search through multiple pages with the `scroll()` method:

<pre><code class="language-python">
result = index.scroll(query)
</code></pre>

`scroll()` returns a generator that yields documents in the same format as `search()`.

## Retrieve All Documents

You can retrieve all documents by using a catch-all query, which uses the following syntax:

<pre><code class="language-python">
{
    "query": "*",
    "limit": 2,
    "sort_by": "song",
    "skip": 1
}
</code></pre>

This is useful if you want to page through documents. You should supply a `sort_by` field to ensure the order of documents is consistent.

### Response

All valid queries return responses in the following form:

<pre><code class="language-python">
{
    "documents": [
        {"uuid": "1", "title": "test", "artist": "..."},
        {"uuid": "2", "title": "test", "artist": "..."},
        ...
    ],
    "query_time": 0.0001,
    "total_results": 200
}
</code></pre>

`documents` is a list of documents that match the query. `query_time` is the amount of time it took to execute the query. `total_results` is the total number of documents that match the query before applying any `limit`.

`total_results` is useful for implementing pagination.

If an error was encountered, the response will be in the following form:

<pre><code class="language-python">
{
    "documents": [],
    "query_time": 0.0001,
    "error": "Invalid query"
}
</code></pre>

The `error` key contains a message describing the exact error encountered.