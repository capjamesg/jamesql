---
layout: default
title: JameSQL
permalink: /
---

An in-memory, NoSQL database implemented in Python, with support for building custom ranking algorithms.

You can run full text search queries on thousands of documents with multiple fields in < 1ms.

## Demo

[Try a site search engine built with JameSQL](https://jamesg.blog/search-pages/).

<video autoplay loop muted playsinline>
    <source src="https://private-user-images.githubusercontent.com/37276661/377151826-f1bf931d-6601-4fc8-b43c-d284853bce8f.mov?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3MzA4MTA0MTUsIm5iZiI6MTczMDgxMDExNSwicGF0aCI6Ii8zNzI3NjY2MS8zNzcxNTE4MjYtZjFiZjkzMWQtNjYwMS00ZmM4LWI0M2MtZDI4NDg1M2JjZThmLm1vdj9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNDExMDUlMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjQxMTA1VDEyMzUxNVomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPWQxOTU1ZThlNjhjYjVmNTYwYmUyODdjOTQ3MzU5OGFiOGI1MWU1ODE0OWRlMDRmOTM1M2I5YzJmMTQxZWI5ZmUmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0In0.2GBymAKR-6lGJskHKo7CslvuiR8jaDfR4hn2EA56MVQ" type="video/mp4">
</video>

## Ideal use case

JameSQL is designed for small-scale search projects where objects can easily be loaded into and stored in memory.

James uses it for his [personal website search engine](https://jamesg.blog/search-pages/), which indexes 1,000+ documents (500,000+ words).

On James' search engine, are computed in < 10ms and returned to a client in < 70ms.