from flask import Flask, request, render_template, send_from_directory
from jamesql import JameSQL
from jamesql.index import GSI_INDEX_STRATEGIES
import json
from tqdm import tqdm

app = Flask(__name__)

index = JameSQL()

with open("tests/fixtures/documents.json") as f:
    documents = json.load(f)

for document in tqdm(documents):
    document = document.copy()
    index.add(document)

@app.route("/", methods=["GET", "POST"])
def search():
    if request.method == "POST":
        query = request.json
        # convert to a python dictionary
        result = index.search(query)
        return result
    
    return render_template("index.html")

# serve ./ace-builds
@app.route("/ace-builds/<path:path>")
def ace(path):
    return send_from_directory("ace-builds", path)

if __name__ == "__main__":
    app.run(debug=True)