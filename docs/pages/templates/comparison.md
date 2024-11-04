You can find documents where a field is less than, greater than, less than or equal to, or greater than or equal to a value with a range query. Here is an example of a query that looks for documents where the `year` field is greater than `2010`:

```python
query = {
    "query": {
        "year": {
            "greater_than": 2010
        }
    }
}
```

The following operators are supported:

- `greater_than`
- `less_than`
- `greater_than_or_equal`
- `less_than_or_equal`