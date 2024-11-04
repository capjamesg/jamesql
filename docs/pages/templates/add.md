---
layout: default
title: Add a Document
permalink: /add/
---

To add documents to a database, use the following code:

```python
index.add({"title": "tolerate it", "artist": "Taylor Swift"})
index.insert({"title": "betty", "artist": "Taylor Swift"})
```

Values within documents can have the following data types:

- String
- Integer
- Float
- List

You cannot currently index a document whose value is a dictionary.

When documents are added, a `uuid` key is added for use in uniquely identifying the document.