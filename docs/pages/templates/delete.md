---
layout: default
title: Delete a Document
permalink: /delete/
---

You need a document UUID to delete a document. You can retrieve a UUID by searching for a document.

Here is an example showing how to delete a document:

<pre><code class="language-python">
response = index.search(
    {
        "query": {"title": {"equals": "tolerate it"}},
        "limit": 10,
        "sort_by": "title",
    }
)

uuid = response["documents"][0]["uuid"]

index.remove(uuid)
</code></pre>

You can validate the document has been deleted using this code:

```python
response = index.search(
    {
        "query": {"title": {"equals": "tolerate it"}},
        "limit": 10,
        "sort_by": "title",
    }
)

assert len(response["documents"]) == 0
```