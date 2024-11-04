---
layout: default
title: Update a Document
permalink: /update/
---


You need a document UUID to update a document. You can retrieve a UUID by searching for a document.

Here is an example showing how to update a document:

```python
response = index.search(
    {
        "query": {"title": {"equals": "tolerate it"}},
        "limit": 10,
        "sort_by": "title",
    }
)

uuid = response["documents"][0]["uuid"]

index.update(uuid, {"title": "tolerate it (folklore)", "artist": "Taylor Swift"})
```

`update` is an override operation. This means you must provide the full document that you want to save, instead of only the fields you want to update.
