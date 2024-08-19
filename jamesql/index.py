import time
import uuid
from collections import defaultdict
from typing import Dict, List
from enum import Enum

import pybmoore

import pygtrie

KEYW0RDS = ["and", "or"]

METHODS = {"and": set.intersection, "or": set.union}

class GSI_INDEX_STRATEGIES(Enum):
    PREFIX = "prefix"
    CONTAINS = "contains"
    FLAT = "flat"

class JameSQL:
    def __init__(self) -> None:
        self.global_index = {}
        self.uuids_to_position_in_global_index = {}
        self.gsis = {}

    def _create_reverse_index(self, document: str) -> Dict[str, List[int]]:
        """
        Accepts a document and returns a reverse index of the document in the form:

        {word: word_count}

        Where `word` is every word in the document and `word_count` is the number of times it appears.
        """
        index = defaultdict(int)

        for word in document.split():
            index[word] += 1

        return index

    def add(self, document: list, partition_key=None) -> Dict[str, dict]:
        """
        This function accepts a list of documents and turns them into a dictionary with the structure:

        {
            partition_key: document
        }

        Every document is assigned a UUID.
        """

        document["uuid"] = uuid.uuid4()

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

    def create_gsi(self, index_by: str | List[str], strategy: GSI_INDEX_STRATEGIES = "flat", prefix_limit = 20) -> Dict[str, dict]:
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
            gsi = self._create_reverse_index(index_by)
        elif strategy == GSI_INDEX_STRATEGIES.FLAT:
            gsi = defaultdict(list)

            for item in self.global_index.values():
                gsi[item.get(index_by)].append(item.get("uuid"))

        self.gsis[index_by] = {"gsi": gsi, "strategy": strategy}

        return gsi

    def search(self, query: dict) -> List[str]:
        start_time = time.time()

        results_limit = query.get("limit", 10)

        if query["query"] == {}:  # empty query
            documents = []
        elif query["query"] == "*":  # all query
            documents = list(self.global_index)[:results_limit]
        else:
            documents = self._recursively_parse_query(query["query"])

        results = list(documents)[:results_limit]

        end_time = time.time()

        results = [self.global_index.get(doc_id) for doc_id in results]

        if query.get("sort_by") is not None:
            results_sort_by = query["sort_by"]

            results = sorted(results, key=lambda x: x[results_sort_by])

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
        first_key = list(query_tree.keys())[0]

        if first_key in KEYW0RDS:
            values = []

            method = METHODS[first_key]

            if isinstance(query_tree[first_key], dict):
                for key, query in query_tree[first_key].items():
                    values.append(self._recursively_parse_query({key: query}))
            else:
                for query in query_tree[first_key]:
                    values.append(self._recursively_parse_query(query))

            values = method(*values)

            return values
        else:
            results = set(
                [
                    doc.get("uuid")
                    for doc in self._run(
                        {"query": query_tree}, list(query_tree.keys())[0]
                    )["documents"]
                ]
            )

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
        start_time = time.time()

        matching_documents = []

        query_type = list(query["query"][query_field].keys())[0]
        query_term = query["query"][query_field][query_type]

        if not self.gsis.get(query_field):
            # print("GSI does not exist on query field ", query_field, ". Creating GSI now.")
            self.create_gsi(query_field, GSI_INDEX_STRATEGIES.FLAT)

        gsi_type = self.gsis[query_field]["strategy"]
        gsi = self.gsis[query_field]["gsi"]

        if gsi_type != GSI_INDEX_STRATEGIES.FLAT:
            if query_type == "starts_with" and gsi_type == GSI_INDEX_STRATEGIES.PREFIX:
                matches = gsi.keys(prefix=query_term)
                matching_documents.extend([gsi[match] for match in matches])

            if query_type == "contains" and gsi_type == GSI_INDEX_STRATEGIES.CONTAINS:
                for word in query_term.split():
                    if gsi.get(word) is not None:
                        matching_documents.extend(gsi[word])
            if query_type == "equals":
                matching_documents.extend(gsi.get(query_term, []))
        elif query_type == "equals":
            matching_documents.extend(gsi.get(query_term, []))
        else:
            for key, value in gsi.items():
                matches = pybmoore.search(query_term, key)

                if query_type == "contains" and len(matches) > 0:
                    matching_documents.extend(value)
                elif query_type == "starts_with" and len(matches) > 0:
                    for match in matches:
                        # this indicates that the query term is a prefix of the sort key
                        if match[0] == 0:
                            matching_documents.extend(value)
                            break

        print(matching_documents)

        end_time = time.time()

        response = {
            "documents": [
                self.global_index.get(doc_id) for doc_id in matching_documents
            ],
            "query_time": str(round(end_time - start_time, 4)),
        }

        # documents may be none if they have been removed from the index but not the GSI
        response["documents"] = [
            doc for doc in response["documents"] if doc is not None
        ]

        return response
