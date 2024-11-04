---
layout: default
title: Quickstart
permalink: /quickstart/
---

<p>You can create a JameSQL database in five lines of code.</p>

First, install JameSQL:

<pre>
pip install jamesql
</pre>

Then, create a new Python file and add the following code:

<pre><code class="language-python">
from jamesql import JameSQL

index = JameSQL.load()

index.add({"title": "tolerate it", "lyric": "Use my best colors for your portrait"})

results = index.string_query_search("title:'tolerate it' colors")

print(results)
</code></pre>

This code creates a new JameSQL database, adds a document, and searches the database.

The code searches for a document whose title contains "tolerate it" and any field contains "colors".

Here are the results:

<pre><code class="language-python">
{"documents": [{"title": "tolerate it", "lyric": "Use my best colors for your portrait" …}]}
</code></pre>

We have successfully built a database!

<footer>
Next up: <a href="/index/">Learn how to create indices →</a>
</footer>