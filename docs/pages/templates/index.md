---
layout: default
title: JameSQL
permalink: /
---

An in-memory, NoSQL database implemented in Python, with support for building custom ranking algorithms.

You can run full text search queries on thousands of documents with multiple fields in < 1ms.

[Try a site search engine built with JameSQL](https://jamesg.blog/search-pages/).

## Ideal use case

JameSQL is designed for small-scale search projects where objects can easily be loaded into and stored in memory.

James uses it for his [personal website search engine](https://jamesg.blog/search-pages/), which indexes 1,000+ documents (500,000+ words).

On James' search engine, are computed in < 10ms and returned to a client in < 70ms.