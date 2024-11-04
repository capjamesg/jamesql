---
layout: default
permalink: /ranking/
title: Document Ranking
---

By default, documents are ranked in no order. If you provide a `sort_by` field, documents are sorted by that field.

For more advanced ranking, you can use the `boost` feature. This feature lets you boost the value of a field in a document to calculate a final score.

The default score for each field is `1`.

To use this feature, you must use `boost` on fields that have an index.

Here is an example of a query that uses the `boost` feature:

```python
{
    "query": {
        "or": {
            "post": {
                "contains": "taylor swift",
                "strict": False,
                "boost": 1
            },
            "title": {
                "contains": "desk",
                "strict": True,
                "boost": 25
            }
        }
    },
    "limit": 4,
    "sort_by": "_score",
}
```

This query would search for documents whose `post` field contains `taylor swift` or whose `title` field contains `desk`. The `title` field is boosted by 25, so documents that match the `title` field are ranked higher.

The score for each document before boosting is equal to the number of times the query condition is satisfied. For example, if a post contains `taylor swift` twice, the score for that document is `2`; if a title contains `desk` once, the score for that document is `1`.

Documents are then ranked in decreasing order of score.