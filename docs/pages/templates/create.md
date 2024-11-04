---
layout: default
permalink: /create
title: Create an Index
---

JameSQL supports several index types.

To achieve the best performance, you should carefully choose the index type to use for each field in your data.

If you don't choose an index, JameSQL will automatically create an index for you when you run a query on a field for the first time. This is inferred from the types of data in the first record you add.

## Set an Index Strategy

To create an index, use the following code:

<pre><code class="language-python">
index.create_gsi("title", strategy=GSI_INDEX_STRATEGIES.PREFIX)
</code></pre>

See the table below for a list of available index strategies.

## Indexing strategies

The following index strategies are available:

<table>
    <thead>
        <tr>
            <th>Index Strategy</th>
            <th>Description</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>
                <code>GSI_INDEX_STRATEGIES.CONTAINS</code>
            </td>
            <td>
                Creates a reverse index for the field. This is useful for fields that contain longer strings (i.e. body text in a blog post). TF-IDF is used to search fields structured with the <code>CONTAINS</code> type.
            </td>
        </tr>
        <tr>
            <td>
                <code>GSI_INDEX_STRATEGIES.NUMERIC</code>
            </td>
            <td>
                Creates several buckets to allow for efficient search of numeric values, especially values with high cardinality.
            </td>
        </tr>
        <tr>
            <td>
                <code>GSI_INDEX_STRATEGIES.FLAT</code>
            </td>
            <td>
                Stores the field as the data type it is. A flat index is created of values that are not strings or numbers. This is the default. For example, if you are indexing document titles and don't need to do a <code>starts_with</code> query, you may choose a flat index to allow for efficient <code>equals</code> and <code>contains</code> queries.
            </td>
        </tr>
        <tr>
            <td>
                <code>GSI_INDEX_STRATEGIES.PREFIX</code>
            </td>
            <td>
                Creates a trie index for the field. This is useful for fields that contain short strings (i.e. titles).
            </td>
        </tr>
        <tr>
            <td>
                <code>GSI_INDEX_STRATEGIES.CATEGORICAL</code>
            </td>
            <td>
                Creates a categorical index for the field. This is useful for fields that contain specific categories (i.e. genres).
            </td>
        </tr>
        <tr>
            <td>
                <code>GSI_INDEX_STRATEGIES.TRIGRAM_CODE</code>
            </td>
            <td>
                Creates a character-level trigram index for the field. This is useful for efficient code search. See the "Code Search" documentation later in this README for more information about using code search with JameSQL.
            </td>
        </tr>
    </tbody>
</table>