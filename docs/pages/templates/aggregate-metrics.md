
You can find the total number of unique values for the fields returned by a query using an `aggregate` query. This is useful for presenting the total number of options available in a search space to a user.

You can use the following query to find the total number of unique values for all fields whose `lyric` field contains the term "sky":

```python
query = {
    "query": {
        "lyric": {
            "contains": "sky"
        }
    },
    "metrics": ["aggregate"]
}
```

The aggregate results are presented in an `unique_record_values` key with the following structure:

```python
{
    "documents": [...],
    "query_time": 0.0001,
    {'unique_record_values': {'title': 2, 'lyric': 2, 'listens': 2, 'categories': 3}}
}
```