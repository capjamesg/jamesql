---
layout: default
title: Group By
permalink: /group-by/
---

You can group results by a single key. This is useful for presenting aggregate views of data.

To group results by a key, use the following code:

```python
query = {
    "query": {
        "lyric": {
            "contains": "sky"
        }
    },
    "group_by": "title"
}
```

This query will search for all `lyric` fields that contain the term "sky" and group the results by the `title` field.