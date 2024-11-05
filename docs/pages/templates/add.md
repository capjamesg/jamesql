---
layout: default
title: Add a Document
permalink: /add/
---

To add documents to a database, use the following code:

<pre><code class="language-python">
index.add({"title": "tolerate it", "artist": "Taylor Swift"})
index.add({"title": "betty", "artist": "Taylor Swift"})
</code></pre>

Values within documents can have the following data types:

- String
- Integer
- Float
- List
- Dictionary

When documents are added, a `uuid` key is added for use in uniquely identifying the document.

<div class="warning">
    Dictionaries are not indexable. You can store dictionaries and they will be returned in payloads, but you cannot run search operations on them.
</div>