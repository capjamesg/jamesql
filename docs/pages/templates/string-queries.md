---
layout: default
title: String Queries
permalink: /string-query/
---

JameSQL supports string queries. String queries are single strings that use special syntax to assert the meaning of parts of a string.

For example, you could use the following query to find documents where the `title` field contains `tolerate it` and any field contains `mural`:

<pre>
title:"tolerate it" mural
</pre>

The following operators are supported:

<table>
    <thead>
        <tr>
            <th>Operator</th>
            <th>Description</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td><code>-term</code></td>
            <td>Search for documents that do not contain <code>term</code>.</td>
        </tr>
        <tr>
            <td><code>term</code></td>
            <td>Search for documents that contain <code>term</code>.</td>
        </tr>
        <tr>
            <td><code>term1 term2</code></td>
            <td>Search for documents that contain <code>term1</code> and <code>term2</code>.</td>
        </tr>
        <tr>
            <td><code>'term1 term2'</code></td>
            <td>Search for the literal phrase <code>term1 term2</code> in documents.</td>
        </tr>
        <tr>
            <td><code>field:'term'</code></td>
            <td>Search for documents where the <code>field</code> field contains <code>term</code> (i.e. <code>title:"tolerate it"</code>).</td>
        </tr>
        <tr>
            <td><code>field^2 term</code></td>
            <td>Boost the score of documents where the <code>field</code> field matches the query <code>term</code> by <code>2</code>.</td>
        </tr>
    </tbody>
</table>

This feature turns a string query into a JameSQL query, which is then executed and the results returned.

To run a string query, use the following code:

```python
results = index.string_query_search("title:'tolerate it' mural")
```

When you run a string query, JameSQL will attempt to simplify the query to make it more efficient. For example, if you search for `-sky sky mural`, the query will be `mural` because `-sky` negates the `sky` mention.
