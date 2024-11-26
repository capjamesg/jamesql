---
layout: default
title: Quickstart
permalink: /quickstart/
---

<p>You can create a JameSQL database in five lines of code.</p>

<h2>Install JameSQL</h2>

First, install JameSQL:

<pre>
pip install jamesql
</pre>

<h2>Insert Records</h2>

Then, create a new Python file and add the following code:

<pre><code class="language-python">
from jamesql import JameSQL, GSI_INDEX_STRATEGIES

index = JameSQL.load()

index.add({"title": "tolerate it", "lyric": "Use my best colors for your portrait"})
</code></pre>

<h2>Create an Index</h2>

For efficient data retrieval for longer pieces of text in the `lyric` key, we are going to use the `CONTAINS` index type. This creates a reverse index for each word in the text.

<pre><code class="language-python">
index.create_gsi("lyric", GSI_INDEX_STRATEGIES.CONTAINS)
</code></pre>

<h3>Search the Database</h3>

We can search the database using the following code:

<pre><code class="language-python">
results = index.string_query_search("title:'tolerate it' colors")

print(results)
</code></pre>

Our code returns:

<pre><code class="language-python">
{"documents": [{"title": "tolerate it", "lyric": "Use my best colors for your portrait" …}]}
</code></pre>

We have successfully built a database!

<footer>
Next up: <a href="{{ site.root_url }}/index/">Learn how to create indices →</a>
</footer>