import json
import os
import string
import time
import uuid
from collections import defaultdict
from enum import Enum
from typing import Dict, List

import orjson
import pybmoore
import pygtrie

INDEX_STORE = os.path.join(os.path.expanduser("~"), ".jamesql")

if not os.path.exists(INDEX_STORE):
    os.makedirs(INDEX_STORE)

KEYW0RDS = ["and", "or"]

METHODS = {"and": set.intersection, "or": set.union}

RESERVED_QUERY_TERMS = ["strict"]


class GSI_INDEX_STRATEGIES(Enum):
    PREFIX = "prefix"
    CONTAINS = "contains"
    FLAT = "flat"


class RANKING_STRATEGIES(Enum):
    BOOST = "BOOST"


class JameSQL:
    def __init__(self) -> None:
        self.global_index = {}
        self.uuids_to_position_in_global_index = {}
        self.gsis = {}

    def _create_reverse_index(
        self, documents: str, index_by: str
    ) -> Dict[str, List[int]]:
        """
        Accepts a document and returns a reverse index of the document in the form:

        {word: word_count}

        Where `word` is every word in the document and `word_count` is the number of times it appears.
        """

        index = defaultdict(dict)

        for document in documents:
            doc_pos = 0

            for pos, word in enumerate(document[index_by].split()):
                if not index.get(word):
                    index[word] = {
                        "count": 0,
                        "documents": {
                            "uuid": defaultdict(list),
                            "count": defaultdict(int),
                        },
                    }

                index[word]["count"] += 1
                index[word]["documents"]["uuid"][document["uuid"]].append(doc_pos)
                index[word]["documents"]["count"][document["uuid"]] += 1

                doc_pos += len(word) + 1

        return index

    def save(self, index_name: str) -> None:
        """
        This function saves the index to disk.
        """

        structure = {
            "global_index": self.global_index,
            "uuids_to_position_in_global_index": self.uuids_to_position_in_global_index,
            "gsis": self.gsis,
        }

        os.makedirs(INDEX_STORE, exist_ok=True)

        with open(os.path.join(INDEX_STORE, index_name), "w") as f:
            f.write(json.dumps(structure))

    def load(self, index_name: str) -> None:
        """
        This function reads the index from disk.
        """

        with open(os.path.join(INDEX_STORE, index_name), "r") as f:
            structure = orjson.loads(f.read())

            self.global_index = structure["global_index"]
            self.uuids_to_position_in_global_index = structure[
                "uuids_to_position_in_global_index"
            ]
            self.gsis = structure["gsis"]

    def add(self, document: list, partition_key=None) -> Dict[str, dict]:
        """
        This function accepts a list of documents and turns them into a dictionary with the structure:

        {
            partition_key: document
        }

        Every document is assigned a UUID.
        """

        document["uuid"] = uuid.uuid4().hex

        if partition_key is None:
            partition_key = document["uuid"]

        self.global_index[partition_key] = document

        self.uuids_to_position_in_global_index[document["uuid"]] = (
            len(self.global_index) - 1
        )

    def update(self, uuid: str, document: dict) -> Dict[str, dict]:
        """
        Accepts a UUID and a Tdocument and updates the document associated with that key.
        """
        if uuid not in self.uuids_to_position_in_global_index:
            return {"error": "Document not found"}

        position_in_global_index = self.uuids_to_position_in_global_index[uuid]

        self.global_index[position_in_global_index] = document

        return document

    def remove(self, uuid: str) -> None:
        """
        Accepts a UUID and removes the document associated with that key.
        """

        del self.global_index[uuid]

    def create_gsi(
        self,
        index_by: str | List[str],
        strategy: GSI_INDEX_STRATEGIES = "flat",
        prefix_limit=20,
    ) -> Dict[str, dict]:
        """
        The raw index returned by create_index is not optimized for querying. Instead, it is designed as
        a single source of truth for all data.

        A Global Secondary Index (GSI) is a data structure that allows for more efficient querying of data.

        This function accepts an index and creates a GSI with the following structure:

        { "index_by": "doc_id" }

        This allows for more efficient querying of data by the index_by field.

        This function can work with individual and composite keys.

        A composite key is a key that is made up of multiple fields. This is useful if you want to be able to
        query across different search fields.

        Of note, GSIs are not kept in sync with the main index. This means that if the main index is updated,
        the GSI needs to be updated (keys that no longer satisfy the GSI criteria will need to be
        removed, new keys that satisfy the GSI criteria will need to be added, and deleted keys will need to
        be removed).

        A GSI has three types:

        - Prefix
        - Contains (reverse index)
        - Flat
        """

        if strategy == GSI_INDEX_STRATEGIES.PREFIX:
            gsi = pygtrie.CharTrie()

            for item in self.global_index.values():
                gsi[item.get(index_by)[:prefix_limit]] = item.get("uuid")
        elif strategy == GSI_INDEX_STRATEGIES.CONTAINS:
            gsi = self._create_reverse_index(
                [item for item in self.global_index.values()], index_by
            )
        elif strategy == GSI_INDEX_STRATEGIES.FLAT:
            gsi = defaultdict(list)

            for item in self.global_index.values():
                gsi[item.get(index_by)].append(item.get("uuid"))
        else:
            raise ValueError(
                "Invalid GSI strategy. Must be one of: "
                + ", ".join([strategy.name for strategy in GSI_INDEX_STRATEGIES])
                + "."
            )

        self.gsis[index_by] = {"gsi": gsi, "strategy": strategy}

        return gsi

    def search(self, query: dict) -> List[str]:
        start_time = time.time()

        results_limit = query.get("limit", 10)

        if not query.get("query"):
            return {
                "documents": [],
                "query_time": str(round(time.time() - start_time, 4)),
            }

        if query["query"] == {}:  # empty query
            results = []
        elif query["query"] == "*":  # all query
            results = list(self.global_index.values())
        else:
            results = self._recursively_parse_query(query["query"])

            if len(results) > 0 and isinstance(results[0], dict):
                final_results = []

                for doc in results:
                    item = self.global_index.get(doc.get("uuid"))
                    item["_score"] = doc.get("_score")
                    item["_context"] = doc.get("_context")

                    final_results.append(item.copy())

                results = final_results
            else:
                results = [self.global_index.get(doc_id) for doc_id in results]

        end_time = time.time()

        if query.get("sort_by") is not None and query.get("sort_by") != "_score":
            results_sort_by = query["sort_by"]

            results = sorted(results, key=lambda x: x[results_sort_by])
        else:
            results = sorted(results, key=lambda x: x.get("_score", 1), reverse=True)

        if query.get("skip"):
            results = results[query["skip"] :]

        if results_limit:
            results = results[:results_limit]

        if results_limit == 0:
            results = []

        return {
            "documents": results,
            "query_time": str(round(end_time - start_time, 4)),
        }

    def _get_query_conditions(self, query_tree):
        # This is not used
        first_key = list(query_tree.keys())[0]

        if first_key in KEYW0RDS:
            values = []

            if isinstance(query_tree[first_key], dict):
                for key, query in query_tree[first_key].items():
                    values.append(self.get_query_conditions({key: query}))
            else:
                for query in query_tree[first_key]:
                    values.append(self.get_query_conditions(query))

            return values
        else:
            return query_tree

    def _recursively_parse_query(self, query_tree: dict) -> set:
        """
        Accepts a query tree and returns a set of matching documents.

        This function implements a depth-first search to parse the query tree.

        If a node is a query, the query is evaluated. If a node is a keyword, the keyword is evaluated
        with the query results from the children nodes.
        """
        first_key = list(
            [key for key in query_tree.keys() if key not in RESERVED_QUERY_TERMS]
        )[0]

        if first_key in KEYW0RDS:
            values = []

            method = METHODS[first_key]

            if isinstance(query_tree[first_key], dict):
                for key, query in query_tree[first_key].items():
                    values.append(self._recursively_parse_query({key: query}))
            else:
                for query in query_tree[first_key]:
                    values.append(self._recursively_parse_query(query))

            uuids = [set([doc.get("uuid") for doc in value]) for value in values]

            uuid_intersection = method(*uuids)

            new_values = defaultdict(int)
            contexts = []

            for value in values:
                for v in value:
                    if v.get("uuid") in uuid_intersection:
                        new_values[v.get("uuid")] += v.get("_score", 0)
                        contexts.extend(v.get("_context"))

            docs = [self.global_index.get(uuid) for uuid in uuid_intersection]

            for doc in docs:
                doc["_score"] = new_values.get(doc.get("uuid"))

            doc["_context"] = contexts

            return docs
        else:
            results = [
                doc
                for doc in self._run({"query": query_tree}, list(query_tree.keys())[0])
            ]

            return results

    def _run(self, query: dict, query_field: str) -> List[str]:
        """
        Accept a query and return a list of matching documents.

        This function should be passed in a GSI that is structured to allow
        for searching the field that a user wants to search by.

        For example, if a user wants to search by title, the GSI should be structured
        so that the title is the key and the partition key is the value.

        This can be done using the transform_index_into_gsi function.
        """

        matching_documents = []
        matching_document_scores = {}

        query_type = list(query["query"][query_field].keys())[0]
        query_term = query["query"][query_field][query_type]

        enforce_strict = query["query"][query_field].get("strict", False)

        if not self.gsis.get(query_field):
            self.create_gsi(query_field, GSI_INDEX_STRATEGIES.FLAT)

        gsi_type = self.gsis[query_field]["strategy"]
        gsi = self.gsis[query_field]["gsi"]

        fuzzy = query["query"][query_field].get("fuzzy", False)

        boost_factor = query["query"][query_field].get("boost", 1)

        query_terms = [query_term]

        if fuzzy:
            query_terms.extend(
                [
                    query_term[:i] + c + query_term[i + 1 :]
                    for i in range(len(query_term))
                    for c in string.ascii_lowercase
                ]
            )

        for query_term in query_terms:
            if gsi_type != GSI_INDEX_STRATEGIES.FLAT:
                if (
                    query_type == "starts_with"
                    and gsi_type == GSI_INDEX_STRATEGIES.PREFIX
                ):
                    matches = gsi.keys(prefix=query_term)
                    matching_documents.extend([gsi[match] for match in matches])

                if (
                    query_type == "contains"
                    and gsi_type == GSI_INDEX_STRATEGIES.CONTAINS
                ):
                    if enforce_strict and len(query_term.split()) > 1:
                        words = query_term.split()

                        all_matches = {}
                        all_match_positions = {}

                        for word_index in range(0, len(words) - 1):
                            current_word = words[word_index]
                            next_word = words[word_index + 1]
                            current_word_positions = (
                                gsi.get(current_word, {})
                                .get("documents", {})
                                .get("uuid", {})
                            )
                            next_word_positions = (
                                gsi.get(next_word, {})
                                .get("documents", {})
                                .get("uuid", {})
                            )

                            matches_for_this_word = []
                            match_positions = defaultdict(list)

                            for doc_id, positions in current_word_positions.items():
                                if doc_id not in next_word_positions:
                                    continue

                                for position in positions:
                                    if (
                                        position + len(current_word) + 1
                                        in next_word_positions[doc_id]
                                    ):
                                        matches_for_this_word.append(doc_id)
                                        match_positions[doc_id].append(position)
                                        break

                            all_matches[current_word + " " + next_word] = (
                                matches_for_this_word
                            )
                            all_match_positions[current_word + " " + next_word] = (
                                match_positions
                            )

                        if all_matches:
                            matching_documents = list(
                                set.intersection(
                                    *[set(matches) for matches in all_matches.values()]
                                )
                            )
                            # score for each matching document is the # of matches
                            matching_document_scores.update(
                                {
                                    doc_id: len(all_matches)
                                    for doc_id in matching_documents
                                }
                            )
                    else:
                        for word in query_term.split():
                            if gsi.get(word) is None:
                                continue

                            uuid_of_documents = gsi[word]["documents"]["uuid"]
                            matching_documents.extend(uuid_of_documents)

                            for uuid_of_document in uuid_of_documents:
                                count = gsi[word]["documents"]["count"][
                                    uuid_of_document
                                ]
                                matching_document_scores.update(
                                    {uuid_of_document: count}
                                )
                if query_type == "equals":
                    matching_documents.extend(gsi.get(query_term, []))
            elif query_type == "equals":
                matching_documents.extend(gsi.get(query_term, []))
            else:
                for key, value in gsi.items():
                    if query_term is None or key is None:
                        continue

                    matches = pybmoore.search(query_term, key)

                    if query_type == "contains" and len(matches) > 0:
                        matching_documents.extend(value)
                    elif query_type == "starts_with" and len(matches) > 0:
                        for match in matches:
                            # this indicates that the query term is a prefix of the sort key
                            if match[0] == 0:
                                matching_documents.extend(value)
                                break

        response = [self.global_index.get(doc_id) for doc_id in matching_documents]

        # documents may be none if they have been removed from the index but not the GSI
        response = [doc for doc in response if doc is not None]

        # assign doc ranks
        for i, doc in enumerate(response):
            doc["_score"] = matching_document_scores.get(doc["uuid"], 0) * boost_factor

        return response