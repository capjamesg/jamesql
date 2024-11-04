---
layout: default
permalink: /script-scores/
title: Script Scores
---

The script score feature lets you write custom scripts to calculate the score for each document. This is useful if you want to calculate a score based on multiple fields, including numeric fields.

Script scores are applied after all documents are retrieved.

The script score feature supports the following mathematical operations:

- `+` (addition)
- `-` (subtraction)
- `*` (multiplication)
- `/` (division)
- `log` (logarithm)
- `decay` (timeseries decay)

You can apply a script score at the top level of your query:

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
    "script_score": "((post + title) * 2)"
}
```

The above example will calculate the score of documents by adding the score of the `post` field and the `title` field, then multiplying the result by `2`.

A script score is made up of terms. A term is a field name or number (float or int), followed by an operator, followed by another term or number. Terms can be nested.

All terms must be enclosed within parentheses.

To compute a score that adds the `post` score to `title` and multiplies the result by `2`, use the following code:

```text
((post + title) * 2)
```

Invalid forms of this query include:

- `post + title * 2` (missing parentheses)
- `(post + title * 2)` (terms can only include one operator)

The `decay` function lets you decay a value by `0.9 ** days_since_post / 30`. This is useful for gradually decreasing the rank for older documents as time passes. This may be particularly useful if you are working with data where you want more recent documents to be ranked higher. `decay` only works with timeseries.

Here is an example of `decay` in use:

```
(_score * decay published)
```

This will apply the `decay` function to the `published` field.

Data must be stored as a Python `datetime` object for the `decay` function to work.