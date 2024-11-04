---
title: Operators
layout: default
permalink: /conditions/operators
---

There are three operators you can use for condition matching:

- `equals`
- `contains`
- `starts_with`

Here is an example of a query that searches for documents that have the `artist` field set to `Taylor Swift`:

```python
query = {
    "query": {
        "artist": {
            "equals": "Taylor Swift"
        }
    }
}
```

These operators can be used with three query types:

- `and`
- `or`
- `not`

### and

You can also search for documents that have the `artist` field set to `Taylor Swift` and the `title` field set to `tolerate it`:

```python
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
    }
}
```

### or

You can nest conditions to create complex queries, like:

```python
query = {
    "query": {
        "or": {
            "and": [
                {"title": {"starts_with": "tolerate"}},
                {"title": {"contains": "it"}},
            ],
            "lyric": {"contains": "kiss"},
        }
    },
    "limit": 2,
    "sort_by": "title",
}
```

This will return a list of documents that match the query.

### not

You can search for documents that do not match a query by using the `not` operator. Here is an example of a query that searches for lyrics that contain `sky` but not `kiss`:

```python
query = {
    "query": {
        "and": {
            "or": [
                {"lyric": {"contains": "sky", "boost": 3}},
            ],
            "not": {"lyric": {"contains": "kiss"}},
        }
    },
    "limit": 10,
    "sort_by": "title",
}
```