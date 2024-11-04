---
layout: default
title: Search Matching
permalink: /matching/
---

### Strict matching

By default, a search query on a text field will find any document where the field contains any word in the query string. For example, a query for `tolerate it` on a `title` field will match any document whose `title` that contains `tolerate` or `it`. This is called a non-strict match.

Non-strict matches are the default because they are faster to compute than strict matches.

If you want to find documents where terms appear next to each other in a field, you can do so with a strict match. Here is an example of a strict match:

```python
query = {
    "query": {
        "title": {
            "contains": "tolerate it",
            "strict": True
        }
    }
}
```

This will return documents whose title contains `tolerate it` as a single phrase.

### Fuzzy matching

By default, search queries look for the exact string provided. This means that if a query contains a typo (i.e. searching for `tolerate ip` instead of `tolerate it`), no documents will be returned.

JameSQL implements a limited form of fuzzy matching. This means that if a query contains a typo, JameSQL will still return documents that match the query.

The fuzzy matching feature matches documents that contain one typo. If a document contains more than one typo, it will not be returned. A typo is an incorrectly typed character. JameSQL does not support fuzzy matching that accounts for missing or additional characters (i.e. `tolerate itt` will not match `tolerate it`).

You can enable fuzzy matching by setting the `fuzzy` key to `True` in the query. Here is an example of a query that uses fuzzy matching:

```python
query = {
    "query": {
        "title": {
            "contains": "tolerate ip",
            "fuzzy": True
        }
    }
}
```

### Wildcard matching

You can match documents using a single wildcard character. This character is represented by an asterisk `*`.

```python
query = {
    "query": {
        "title": {
            "contains": "tolerat* it",
            "fuzzy": True
        }
    }
}
```

This query will look for all words that match the pattern `tolerat* it`, where the `*` character can be any single character.