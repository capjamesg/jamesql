---
layout: default
permalink: /autosuggest/
title: Autosuggest
---

You can enable autosuggest using one or more fields in an index. This can be used to efficiently find records that start with a given prefix.

To enable autosuggest on an index, run:

```python
index = JameSQL()

...

index.enable_autosuggest("field")
```

Where `field` is the name of the field on which you want to enable autosuggest.

You can enable autosuggest on multiple fields:

```python
index.enable_autosuggest("field1")
index.enable_autosuggest("field2")
```

When you enable autosuggest on a field, JameSQL will create a trie index for that field. This index is used to efficiently find records that start with a given prefix.

To run an autosuggest query, use the following code:

```python
suggestions = index.autosuggest("started", match_full_record=True, limit = 1)
```

This will automatically return records that start with the prefix `started`.

The `match_full_record` parameter indicates whether to return full record names, or any records starting with a term.

`match_full_record=True` means that the full record name will be returned. This is ideal to enable selection between full records.

`match_full_record=False` means that any records starting with the term will be returned. This is ideal for autosuggesting single words.

For example, given the query `start`, matching against full records with `match_full_record=True` would return:

- `Started with a kiss`

This is the content of a full document.

`match_full_record=False`, on the other hand, would return:

- `started`
- `started with a kiss`

This contains both a root word starting with `start` and full documents starting with `start`.

This feature is case insensitive.

The `limit` argument limits the number of results returned.