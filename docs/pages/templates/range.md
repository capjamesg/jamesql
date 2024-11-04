---
layout: default
title: Range Queries
permalink: /range/
---

You can find values in a numeric range with a range query. Here is an example of a query that looks for documents where the `year` field is between `2010` and `2020`:

```python
query = {
    "query": {
        "year": {
            "range": [2010, 2020]
        }
    }
}
```

The first value in the range is the lower bound to use in the search, and the second value is the upper bound.