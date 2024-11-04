---
layout: default
title: Highlight Results
permalink: /highlight/
---

You can extract context around results. This data can be used to show a snippet of the document that contains the query term.

Here is an example of a query that highlights context around all instances of the term "sky" in the `lyric` field:

```python
query = {
    "query": {
        "lyric": {
            "contains": "sky",
            "highlight": True,
            "highlight_stride": 3
        }
    }
}
```

`highlight_stride` states how many words to retrieve before and after the match.

All documents returned by this query will have a `_context` key that contains the context around all instances of the term "sky".