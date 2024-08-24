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
from lark import Lark
from BTrees.OOBTree import OOBTree

from jamesql.rewriter import string_query_to_jamesql

from .script_lang import JameSQLScriptTransformer, grammar

INDEX_STORE = os.path.join(os.path.expanduser("~"), ".jamesql")

if not os.path.exists(INDEX_STORE):
    os.makedirs(INDEX_STORE)

KEYW0RDS = ["and", "or", "not"]

METHODS = {"and": set.intersection, "or": set.union, "not": set.difference}

RESERVED_QUERY_TERMS = ["strict", "boost", "highlight", "highlight_stride"]

# this is the maximum number of individual sub-queries
# that can be run in a single query
MAXIMUM_QUERY_STATEMENTS = 20


class GSI_INDEX_STRATEGIES(Enum):
    PREFIX = "prefix"
    CONTAINS = "contains"
    FLAT = "flat"
    NUMERIC = "numeric"
    INFER = "infer"


class RANKING_STRATEGIES(Enum):
    BOOST = "BOOST"


JAMESQL_SCRIPT_SCORE_PARSER = Lark(grammar)

QUERY_TYPE_COMPARISON_METHODS = {
    "greater_than": lambda query_term, gsi: [
        doc_uuid for doc_uuid in gsi.values(min=query_term, excludemin=True)
    ],
    "less_than": lambda query_term, gsi: [
        doc_uuid for doc_uuid in gsi.values(max=query_term, excludemax=True)
    ],
    "greater_than_or_equal": lambda query_term, gsi: [
        doc_uuid for doc_uuid in gsi.values(min=query_term)
    ],
    "less_than_or_equal": lambda query_term, gsi: [
        doc_uuid for doc_uuid in gsi.values(max=query_term)
    ]
}

class JameSQL:
    SELF_METHODS = {"close_to": "_close_to"}

    def __init__(self) -> None:
        self.global_index = {}
        self.uuids_to_position_in_global_index = {}
        self.gsis = {}

    def _close_to(self, query: list) -> dict:
        """
        Accepts a query and returns a query that is close to the original query.

        This is useful for finding documents that are similar to the original query.
        """
        matching_documents = set()

        positions = defaultdict(int)

        stride = query[0].get("distance", 3)

        for i, item in enumerate(query):
            if i == 0:
                continue

            field = list(item.keys())[0]
            value = item[field]

            previous_word = (
                query[i - 1][list(query[i - 1].keys())[0]] if i > 0 else None
            )

            if not self.gsis.get(field):
                self.create_gsi(field, GSI_INDEX_STRATEGIES.INFER)

            gsi = self.gsis[field]
            gsi_index = gsi["gsi"]

            previous_word_positions = gsi_index.get(previous_word)["documents"]["uuid"]
            current_word_positions = gsi_index.get(value)["documents"]["uuid"]

            stride_range = range(-stride, stride + 1)

            if gsi["strategy"] == GSI_INDEX_STRATEGIES.CONTAINS.name:
                for doc_id, positions in current_word_positions.items():
                    if doc_id not in previous_word_positions:
                        continue

                    if matching_documents and doc_id not in matching_documents:
                        continue

                    for position in set(positions):
                        for stride_value in stride_range:
                            if (
                                position + stride_value
                                in previous_word_positions[doc_id]
                            ):
                                matching_documents.add(doc_id)

        documents = [self.global_index.get(doc_id) for doc_id in matching_documents]

        return documents

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
                index[word]["documents"]["uuid"][document["uuid"]].append(pos)
                index[word]["documents"]["count"][document["uuid"]] += 1

            # allow equals lookup
            if not index.get(document[index_by]):
                index[document[index_by]] = {
                    "count": 0,
                    "documents": {"uuid": defaultdict(list), "count": defaultdict(int)},
                }
            index[document[index_by]]["count"] += 1
            index[document[index_by]]["documents"]["uuid"][document["uuid"]].append(pos)
            index[document[index_by]]["documents"]["count"][document["uuid"]] += 1

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

    def _compute_string_query(self, query: str, query_keys: list = []) -> List[str]:
        """
        Accepts a string query and returns a list of matching documents.
        """

        if not query_keys:
            query_keys = list(self.gsis.keys())

        indexing_strategies = {
            name: gsi["strategy"].lower() for name, gsi in self.gsis.items()
        }

        query = string_query_to_jamesql(
            query, query_keys=query_keys, default_strategies=indexing_strategies
        )

        return query

    def string_query_search(self, query: str, query_keys: list = []) -> List[str]:
        """
        Accepts a string query and returns a list of matching documents.
        """

        query = self._compute_string_query(query, query_keys)

        return self.search(query)
    
    def _get_unique_record_count(self, documents: list) -> int:
        """
        Accepts a GSI name and returns the number of unique record values in the GSI.

        Uniqueness is enforced by the fact that GSIs are dictionaries.
        """
        
        counts = {}

        for document in documents:
            for key, value in document.items():
                if key not in counts:
                    counts[key] = set()

                if key.startswith("_"):
                    continue

                if isinstance(value, list):
                    for item in value:
                        counts[key].add(item)
                else:
                    counts[key].add(value)

        counts = {key: len(value) for key, value in counts.items() if not key.startswith("_") and key != "uuid"}
                
        return counts

    def add(self, document: list, doc_id=None) -> Dict[str, dict]:
        """
        This function accepts a list of documents and turns them into a dictionary with the structure:

        {
            partition_key: document
        }

        Every document is assigned a UUID.
        """

        if doc_id:
            document["uuid"] = doc_id
        else:
            document["uuid"] = uuid.uuid4().hex

        self.global_index[document["uuid"]] = document

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
        strategy: GSI_INDEX_STRATEGIES = "infer",
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

        documents_in_indexed_by = [item.get(index_by) for item in self.global_index.values()]
        if strategy == GSI_INDEX_STRATEGIES.INFER:
            if isinstance(index_by, list):
                strategy = GSI_INDEX_STRATEGIES.FLAT
            elif all([isinstance(item, int) or item.isdigit() for item in documents_in_indexed_by]):
                strategy = GSI_INDEX_STRATEGIES.NUMERIC
            # if word count < 10, use prefix
            # elif isinstance(index_by, str) and sum([len(item.split(" ")) for item in documents_in_indexed_by]) / len(documents_in_indexed_by) < 10:
            #     strategy = GSI_INDEX_STRATEGIES.PREFIX
            elif isinstance(index_by, str) and sum([len(item.split(" ")) for item in documents_in_indexed_by]) / len(documents_in_indexed_by) > 20:
                strategy = GSI_INDEX_STRATEGIES.CONTAINS
            else:
                strategy = GSI_INDEX_STRATEGIES.FLAT

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
                if isinstance(item.get(index_by), list):
                    for inner in item.get(index_by):
                        gsi[inner].append(item.get("uuid"))
                else:
                    gsi[item.get(index_by)].append(item.get("uuid"))
        elif strategy == GSI_INDEX_STRATEGIES.NUMERIC:
            gsi = OOBTree()

            gsi.update({item.get(index_by): item.get("uuid") for item in self.global_index.values()})
        else:
            raise ValueError(
                "Invalid GSI strategy. Must be one of: "
                + ", ".join([strategy.name for strategy in GSI_INDEX_STRATEGIES])
                + "."
            )

        self.gsis[index_by] = {"gsi": gsi, "strategy": strategy.name}

        return gsi

    def search(self, query: dict) -> List[str]:
        start_time = time.time()

        results_limit = query.get("limit", 10)

        if not query.get("query"):
            return {
                "documents": [],
                "error": "No query provided",
                "query_time": str(round(time.time() - start_time, 4)),
            }

        if query["query"] == {}:  # empty query
            results = []
        elif query["query"] == "*":  # all query
            results = list(self.global_index.values())
        else:
            number_of_query_conditions = self._get_query_conditions(query["query"])

            if len(number_of_query_conditions) > MAXIMUM_QUERY_STATEMENTS:
                return {
                    "documents": [],
                    "error": "Too many query conditions. Maximum is "
                    + str(MAXIMUM_QUERY_STATEMENTS)
                    + ".",
                    "query_time": str(round(time.time() - start_time, 4)),
                }

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

        if query.get("query_score"):
            tree = JAMESQL_SCRIPT_SCORE_PARSER.parse(query["query_score"])

            for document in results:
                if document.get("_score") is None:
                    document["_score"] = 1

                transformer = JameSQLScriptTransformer(document)

                document["_score"] = transformer.transform(tree)

            results = sorted(results, key=lambda x: x.get("_score", 1), reverse=True)

        if query.get("skip"):
            results = results[query["skip"] :]

        total_results = len(results)

        if results_limit:
            results = results[:results_limit]

        if results_limit == 0:
            results = []

        result = {
            "documents": results,
            "query_time": str(round(end_time - start_time, 4)),
            "total_results": total_results,
        }

        if query.get("metrics") and "aggregate" in query["metrics"]:
            result["metrics"] = {
                "unique_record_values": self._get_unique_record_count(results),
            }

        if query.get("group_by"):
            result["groups"] = defaultdict(list)

            for doc in results:
                if isinstance(doc.get(query["group_by"]), list):
                    for item in doc.get(query["group_by"]):
                        result["groups"][item].append(doc)
                else:
                    result["groups"][doc.get(query["group_by"])].append(doc)

        return result

    def _get_query_conditions(self, query_tree):
        first_key = list(query_tree.keys())[0]

        if first_key in KEYW0RDS:
            values = []

            if isinstance(query_tree[first_key], dict):
                for key, query in query_tree[first_key].items():
                    values.append(self._get_query_conditions({key: query}))
            else:
                for query in query_tree[first_key]:
                    values.append(self._get_query_conditions(query))

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
        acc = set()

        for first_key in query_tree.keys():
            if first_key in RESERVED_QUERY_TERMS:
                continue

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

                if len(uuids) == 0:
                    uuids = [set()]

                if first_key == "not":
                    uuid_intersection = set(self.global_index.keys()).difference(
                        uuids[0]
                    )
                else:
                    uuid_intersection = method(*uuids)

                new_values = defaultdict(int)

                for value in values:
                    for v in value:
                        if v.get("uuid") in uuid_intersection:
                            new_values[v.get("uuid")] += v.get("_score", 1)

                docs = [self.global_index.get(uuid) for uuid in uuid_intersection]

                for doc in docs:
                    doc["_score"] = new_values.get(doc.get("uuid"), 1)

                acc = set.union(acc, uuid_intersection)
            elif first_key in self.SELF_METHODS:
                func = self.SELF_METHODS[first_key]

                acc = set.union(getattr(self, func)(query_tree[first_key]))
            else:
                results = [
                    doc
                    for doc in self._run(
                        {"query": query_tree}, list(query_tree.keys())[0]
                    )
                ]
                acc = set.union(acc, set([doc.get("uuid") for doc in results]))

        return [self.global_index.get(doc_id) for doc_id in acc]

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
        matching_highlights = {}

        query_type = list([key for key in query["query"][query_field].keys() if key not in RESERVED_QUERY_TERMS])[0]
        query_term = query["query"][query_field][query_type]

        enforce_strict = query["query"][query_field].get("strict", False)
        highlight_terms = query["query"][query_field].get("highlight", False)
        highlight_stride = query["query"][query_field].get("highlight_stride", 10)

        if not self.gsis.get(query_field):
            self.create_gsi(query_field, GSI_INDEX_STRATEGIES.INFER)

        gsi_type = GSI_INDEX_STRATEGIES[self.gsis[query_field]["strategy"]]

        gsi = self.gsis[query_field]["gsi"]

        fuzzy = query["query"][query_field].get("fuzzy", False)

        boost_factor = query["query"][query_field].get("boost", 1)

        query_terms = [query_term]

        if fuzzy:
            # create versions of query where a letter is replaced in every possible position
            query_terms.extend(
                [
                    query_term[:i] + c + query_term[i + 1 :]
                    for i in range(len(query_term))
                    for c in string.ascii_lowercase
                ]
            )
            # create versions of query where a letter is added in every possible position
            query_terms.extend(
                [
                    query_term[:i] + c + query_term[i:]
                    for i in range(len(query_term))
                    for c in string.ascii_lowercase
                ]
            )
            # remove a letter from every possible position
            query_terms.extend(
                [query_term[:i] + query_term[i + 1 :] for i in range(len(query_term))]
            )

        # remove query terms whose words are not in index
        if gsi_type == GSI_INDEX_STRATEGIES.CONTAINS:
            query_terms = [term for term in query_terms if term in gsi]

        if query_type == "wildcard":
            # replace * with every possible character
            query_terms = [query_term.replace("*", c) for c in string.ascii_lowercase]
        
        for query_term in query_terms:
            if gsi_type not in (GSI_INDEX_STRATEGIES.FLAT, GSI_INDEX_STRATEGIES.NUMERIC):
                if (
                    query_type == "starts_with"
                    and gsi_type == GSI_INDEX_STRATEGIES.PREFIX
                ):
                    matches = gsi.keys(prefix=query_term)
                    matching_documents.extend([gsi[match] for match in matches])
                    

                if (
                    query_type in {"contains", "wildcard"}
                    and gsi_type == GSI_INDEX_STRATEGIES.CONTAINS
                ):
                    if enforce_strict:
                        words = query_term.split()

                        all_matches = {}
                        all_match_positions = {}

                        for word_index in range(0, len(words)):
                            current_word = words[word_index]
                            if word_index + 1 == len(words):
                                next_word = current_word
                            else:
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

                                for position in set(positions):
                                    if (
                                        position + len(current_word) + 1
                                        in next_word_positions[doc_id]
                                    ) or len(words) == 1:
                                        matches_for_this_word.append(doc_id)
                                        match_positions[doc_id].append(position)
                                        break

                            if word_index + 1 == len(words) and len(words) == 1:
                                all_matches[current_word] = matches_for_this_word
                                all_match_positions[current_word] = match_positions
                            else:
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
                            if highlight_terms:
                                matches_with_context = defaultdict(list)

                                for doc_occurrences in all_match_positions.values():
                                    for doc_id, positions in doc_occurrences.items():
                                        for position in positions:
                                            start = max(0, position - highlight_stride)
                                            end = min(position + highlight_stride, len(self.global_index[doc_id]["lyric"].split()))
                                            matches_with_context[doc_id].append(
                                                " ".join(self.global_index[doc_id]["lyric"].split()[start:end])
                                            )
                                
                                matching_highlights.update(matches_with_context)
                    else:
                        for word in query_term.split(" "):
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
                    matching_documents.extend(
                        [
                            doc_uuid
                            for doc_uuid in gsi.get(query_term, {})
                            .get("documents", {})
                            .get("uuid", [])
                        ]
                    )
                if query_type == "contains" and gsi_type == GSI_INDEX_STRATEGIES.PREFIX:
                    matching_documents.extend(
                        [
                            doc_uuid
                            for key, doc_uuid in gsi.items()
                            if pybmoore.search(query_term, key)
                        ]
                    )
            elif query_type == "equals":
                matching_documents.extend(gsi.get(query_term, []))
            elif query_type == "range":
                lower_bound, upper_bound = query_term
                matching_documents.extend(
                    [
                        doc_uuid
                        for doc_uuid in gsi.values(min=lower_bound, max=upper_bound)
                    ]
                )
            elif query_type in QUERY_TYPE_COMPARISON_METHODS:
                matching_documents.extend(
                    QUERY_TYPE_COMPARISON_METHODS[query_type](query_term, gsi)
                )
            else:
                for key, value in gsi.items():
                    if query_term is None or key is None:
                        continue

                    matches = pybmoore.search(query_term, key)

                    if query_type in {"contains", "wildcard"} and len(matches) > 0:
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
            doc["_score"] = matching_document_scores.get(doc["uuid"], 1) * boost_factor
            doc["_context"] = matching_highlights.get(doc["uuid"], {})

        return response
