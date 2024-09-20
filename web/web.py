from flask import Flask, request, render_template, send_from_directory
from jamesql import JameSQL
from jamesql.index import GSI_INDEX_STRATEGIES
import json
from tqdm import tqdm
from datetime import datetime
import requests
import time

import os
import pyromark
import frontmatter
from bs4 import BeautifulSoup

app = Flask(__name__)

index = JameSQL()

link_graph = {}
records = []

blog_posts = os.listdir("../../pages/posts")

for post_name in blog_posts:
    with open(f"../../pages/posts/{post_name}") as f:
        post = frontmatter.load(f)
        category = post.get("categories", [])[0]
        description = "<br>".join(post.content.split("\n")[:2])
        post["description"] = description

        post[
            "published"
        ] = f"{post_name.split('-')[0]}-{post_name.split('-')[1]}-{post_name.split('-')[2]}"
        post[
            "url"
        ] = f"https://jamesg.blog/{post_name.split('-')[0]}/{post_name.split('-')[1]}/{post_name.split('-')[2]}/{'-'.join(post_name.split('-')[3:]).replace('.md', '').strip('/')}"

        # stem the content
        # post.content = " ".join([stemmer.stem(word) for word in post.content.split()])
        # post["title"] = " ".join([stemmer.stem(word) for word in post["title"].split()])
        # parse markdown
        # post.content = pyromark.markdown(post.content)
        # exit()
        links = BeautifulSoup(pyromark.markdown(post.content), "html.parser").find_all(
            "a"
        )

        links = [link.get("href") for link in links]

        for link in links:
            if not link:
                continue

            # if link starts with /, add jamesg.blog
            if link.startswith("/"):
                link = f"https://jamesg.blog{link}"

            link = link.rstrip("/")

            if link not in link_graph:
                link_graph[link] = []

            link_graph[link].append(post["url"].strip("/"))

        html = pyromark.markdown(post["description"])

        if post.content and post["title"]:
            records.append(
                {
                    "title": post["title"],
                    "title_lower": post["title"].lower(),
                    "post": post.content.lower(),
                    "category": category,
                    "description": html,
                    "published": datetime.strptime(post["published"], "%Y-%m-%d"),
                    "url": post["url"],
                    "type": "blog",
                }
            )

for record in records:
    record["inlinks"] = len(link_graph.get(record["url"], []))
    index.add(record)

index.create_gsi("title_lower", strategy=GSI_INDEX_STRATEGIES.CONTAINS)
index.create_gsi("post", strategy=GSI_INDEX_STRATEGIES.CONTAINS)


@app.route("/", methods=["GET", "POST"])
def search():
    field_names = index.gsis

    field_names_to_index_types = {
        name: index.gsis[name]["strategy"] for name in field_names.keys()
    }
    if request.method == "POST":
        query = request.json
        if query["type"] == "string_query":
            query_parsed = index._compute_string_query(
                query["raw_query"], query_keys=query["fields"], boosts=query["boosts"]
            )
            query_parsed["query_score"] = query["query_score"]
            query_parsed["sort_by"] = "_score"
            result = index.search(query_parsed)
        else:
            result = index.search(query)
        return result

    return render_template("search.html", field_names=field_names_to_index_types)


@app.route("/json", methods=["GET", "POST"])
def json_search():
    if request.method == "POST":
        query = request.json
        result = index.search(query)
        return result

    return render_template("index.html")


# serve ./ace-builds
@app.route("/ace-builds/<path:path>")
def ace(path):
    return send_from_directory("ace-builds", path)


if __name__ == "__main__":
    app.run(debug=True)
