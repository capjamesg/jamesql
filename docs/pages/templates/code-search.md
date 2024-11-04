---
layout: default
title: Code Search
permalink: /code-search/
---

You can use JameSQL to efficiently search through code.

To do so, first create a `TRIGRAM_CODE` index on the field you want to search.

When you add documents, include at least the following two fields:

- `file_name`: The name of the file the code is in.
- `code`: The code you want to index.

When you search for code, all matching documents will have a `_context` key with the following structure:

```python
{
    "line": "1",
    "code": "..."
}
```

This tells you on what line your search matched, and the code that matched. This information is ideal to highlight specific lines relevant to your query.