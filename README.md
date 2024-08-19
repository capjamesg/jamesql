[![test workflow](https://github.com/capjamesg/jamesql/actions/workflows/test.yml/badge.svg)](https://github.com/capjamesg/jamesql/actions/workflows/test.yml)

# JameSQL

A JameSQL database implemented in Python.

This project has support for:

- Inserting records
- Deleting records
- Searching for records that match a query
- Searching for records that match multiple query conditions

This database does not enforce a schema, so you can insert records with different fields.

## Installation

To install this project, run:

```
git clone https://github.com/capjamesg/jamesql
cd jamesql
pip3 install -e .
```

## Usage

### Create a database

To create a database, use the following code:

```python
from nosql import NoSQL

index = JameSQL()
```

### Add documents to a database

To add documents to a database, use the following code:

```python
index.add({"title": "tolerate it", "artist": "Taylor Swift"})
index.insert({"title": "betty", "artist": "Taylor Swift"})
```

When documents are added, a `uuid` key is added for use in uniquely identifying the document.

### Search for documents

A query has the following format:

```python
{
    "query": {},
    "limit": 2,
    "sort_by": "song",
    "skip": 1
}
```

- `query` is a dictionary that contains the fields to search for.
- `limit` is the maximum number of documents to return. (default 10)
- `sort_by` is the field to sort by. (default None)
- `skip` is the number of documents to skip. This is useful for implementing pagination. (default 0)

`limit`, `sort_by`, and `skip` are optional.

Within the `query` key you can query for documents that match one or more conditions.

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

To search for documents that match a query, use the following code:

```python
result = index.search(query)
```

This will return a list of documents that match the query.

### Update documents

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

### Delete documents

You need a document UUID to delete a document. You can retrieve a UUID by searching for a document.

Here is an example showing how to delete a document:

```python
response = index.search(
    {
        "query": {"title": {"equals": "tolerate it"}},
        "limit": 10,
        "sort_by": "title",
    }
)

uuid = response["documents"][0]["uuid"]

index.remove(uuid)
```

You can validate the document has been deleted using this code:

```python
response = index.search(
    {
        "query": {"title": {"equals": "tolerate it"}},
        "limit": 10,
        "sort_by": "title",
    }
)

assert len(response["documents"]) == 0
```

## Testing

This project comes with two test suites:

- Unit tests
- A benchmarking test

You can run the unit tests using:

```
pytest tests/test.py
```

You can run the benchmark test using:

```
pytest tests/stress.py
```

The benchmark test evaluates how long it takes to run a query in a database with 300,000 records.

## License

This project is licensed under an [MIT license](LICENSE).
