import json
import os
import string
import time
import uuid
from collections import defaultdict
from enum import Enum
from typing import Dict, List
from functools import lru_cache
from copy import deepcopy

import orjson
import pybmoore
import pygtrie
import hashlib
from BTrees.OOBTree import OOBTree
from lark import Lark
import nltk
from nltk.corpus import stopwords
import math

from jamesql.rewriter import string_query_to_jamesql, grammar as rewriter_grammar

from .script_lang import JameSQLScriptTransformer, grammar

nltk.download('stopwords')

INDEX_STORE = os.path.join(os.path.expanduser("~"), ".jamesql")
JOURNAL_FILE = os.path.join(os.getcwd(), "journal.jamesql")
INDEX_DATA_FILE = os.path.join(os.getcwd(), "index.jamesql")

if not os.path.exists(INDEX_STORE):
    os.makedirs(INDEX_STORE)

KEYW0RDS = ["and", "or", "not"]

METHODS = {"and": set.intersection, "or": set.union, "not": set.difference}

RESERVED_QUERY_TERMS = ["strict", "boost", "highlight", "highlight_stride"]

# this is the maximum number of individual sub-queries
# that can be run in a single query
MAXIMUM_QUERY_STATEMENTS = 20

stop_words = set(stopwords.words("english"))

class GSI_INDEX_STRATEGIES(Enum):
    PREFIX = "prefix"
    CONTAINS = "contains"
    FLAT = "flat"
    NUMERIC = "numeric"
    INFER = "infer"
    DATE = "date"
    NOT_INDEXABLE = "not_indexable"
    TRIGRAM_CODE = "trigram_code"


class RANKING_STRATEGIES(Enum):
    BOOST = "BOOST"


JAMESQL_SCRIPT_SCORE_PARSER = Lark(grammar)

@lru_cache()
def parse_script_score(query: str) -> dict:
    return JAMESQL_SCRIPT_SCORE_PARSER.parse(query)

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
    ],
}


def get_trigrams(line):
    return [line[i : i + 3] for i in range(len(line) - 2)]


class JameSQL:
    SELF_METHODS = {"close_to": "_close_to"}

    def __init__(self) -> None:
        self.global_index = {}
        self.uuids_to_position_in_global_index = {}
        self.gsis = {}
        self.last_transaction_after_recovery = None
        self.autosuggest_index = {}
        self.doc_lengths = defaultdict(dict)
        self.autosuggest_on = None
        self.word_counts = defaultdict(int)
        self.string_query_parser = Lark(rewriter_grammar, parser="earley", propagate_positions=False, maybe_placeholders=False)

    def __len__(self):
        return len(self.global_index)

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

        index = defaultdict(
            lambda: {
                "count": 0,
                "documents": {"uuid": defaultdict(list), "count": defaultdict(int)},
            }
        )

        for document in documents:
            for pos, word in enumerate(document[index_by].split()):
                index[word]["count"] += 1
                index[word]["documents"]["uuid"][document["uuid"]].append(pos)
                index[word]["documents"]["count"][document["uuid"]] += 1
                self.word_counts[word.lower()] += 1
                self.word_counts[word] += 1

                index[document[index_by]]["count"] += 1
                index[document[index_by]]["documents"]["uuid"][document["uuid"]].append(pos)
                index[document[index_by]]["documents"]["count"][document["uuid"]] += 1

        return index

    @classmethod
    def load(cls) -> "JameSQL":
        """
        This function reads the index from disk.
        """

        instance = cls()

        if os.path.exists(INDEX_DATA_FILE):
            with open(INDEX_DATA_FILE) as f:
                file = f.read().splitlines().copy()
        else:
            file = []

        for line in file:
            document = json.loads(line)
            # records are not written to the index using write_to_journal=False
            # this flag also ensures that records aren't saved in the index
            # if write_to_journal was True, the records would be saved in the index again
            # leading to duplicate records and thus data inconsistency
            instance.add(document.copy(), doc_id=None, write_to_journal=False)

        # at this step, the database is reconciling its history from the journal
        # no other writes can happen until this is done
        # the write_to_journal flag ensures that the current journal is not overwritten while
        # the database is being reconciled
        if os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE, "r") as f:
                records = f.read().splitlines().copy()

            with open(INDEX_DATA_FILE, "a") as f:
                for idx, line in enumerate(records):
                    op_record = json.loads(line)
                    if op_record["operation"] == "add":
                        document = instance.add(
                            op_record["document"], write_to_journal=False
                        )
                    elif op_record["operation"] == "remove":
                        document = instance.remove(
                            op_record["document"]["uuid"], write_to_journal=False
                        )

                    f.write(json.dumps(document) + "\n")

                    if idx == len(records) - 1:
                        instance.last_transaction_after_recovery = hashlib.sha1(
                            orjson.dumps(records).hex()
                        ).hexdigest()

            if os.path.exists(JOURNAL_FILE):
                os.remove(JOURNAL_FILE)

        return instance

    def enable_autosuggest(self, field):
        """
        Accepts a field and adds it to the auto suggest index.
        """

        if not self.autosuggest_index:
            self.autosuggest_index = pygtrie.CharTrie()

        for document in self.gsis[field]["gsi"]:
            self.autosuggest_index[document.lower()] = document

        self.autosuggest_on = field

    def autosuggest(self, query: str, match_full_record=False, limit=5) -> List[str]:
        """
        Accepts a query and returns a list of suggestions.
        """
        if not self.autosuggest_index or not query:
            return []

        if match_full_record:
            results = []

            for i in self.autosuggest_index.itervalues(
                prefix=query.lower(), shallow=False
            ):
                if self.autosuggest_index.has_subtrie(i.lower()):
                    continue
                results.append(i)

            return results[0:limit]
        else:
            try:
                return self.autosuggest_index.keys(prefix=query.lower())[0:limit]
            except KeyError:
                return []

    def _compute_string_query(
        self, query: str, query_keys: list = [], boosts={}, fuzzy = False, highlight_keys = []
    ) -> List[str]:
        """
        Accepts a string query and returns a list of matching documents.
        """

        if query == "":
            return {"query": {}}, {}

        if not query_keys:
            query_keys = list(self.gsis.keys())

        indexing_strategies = {name: gsi["strategy"] for name, gsi in self.gsis.items()}

        query, spelling_substitutions = string_query_to_jamesql(
            self.string_query_parser,
            query,
            query_keys=query_keys,
            default_strategies=indexing_strategies,
            boosts=boosts,
            fuzzy=fuzzy,
            correct_spelling_index=self,
            highlight_keys=highlight_keys
        )

        return query, spelling_substitutions

    def string_query_search(
        self, query: str, query_keys: list = [], start: int = 0, fuzzy = False, highlight_keys = []
    ) -> List[str]:
        """
        Accepts a string query and returns a list of matching documents.
        """

        if query == "":
            return {"documents": []}

        query, spelling_substitutions = self._compute_string_query(query, query_keys, fuzzy=fuzzy, highlight_keys=highlight_keys)

        if start:
            query["skip"] = start

        result = self.search(query)

        if spelling_substitutions:
            result["spelling_substitutions"] = spelling_substitutions

        return result

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

        counts = {
            key: len(value)
            for key, value in counts.items()
            if not key.startswith("_") and key != "uuid"
        }

        return counts

    def scroll(self, query: dict, scroll_size: int = 10):
        for i in range(0, len(self.global_index), scroll_size):
            query["skip"] = i
            yield self.search(query)

    def add(
        self, document: dict, doc_id=None, write_to_journal=False
    ) -> Dict[str, dict]:
        """
        This function accepts a document and indexes it.

        {
            partition_key: document
        }

        Every document is assigned a UUID.
        """

        if write_to_journal:
            with open(JOURNAL_FILE, "a") as f:
                op_record = {"operation": "add", "document": document}
                f.write(json.dumps(op_record) + "\n")

        if doc_id is not None:
            document["uuid"] = doc_id
        elif document.get("uuid"):
            doc_id = document["uuid"]
        else:
            document["uuid"] = uuid.uuid4().hex

        self.global_index[document["uuid"]] = document

        self.uuids_to_position_in_global_index[document["uuid"]] = (
            len(self.global_index) - 1
        )

        if self.autosuggest_on and document.get(self.autosuggest_on):
            self.autosuggest_index[document[self.autosuggest_on].lower()] = document[
                self.autosuggest_on
            ]

        # add to GSI
        for key, value in document.items():
            if isinstance(value, str):
                self.doc_lengths[document["uuid"]][key] = len(value.split(" "))

            if key not in self.gsis:
                if key == "uuid":
                    continue
                self.create_gsi(key, strategy=GSI_INDEX_STRATEGIES.INFER)

            if self.gsis[key]["strategy"] == GSI_INDEX_STRATEGIES.CONTAINS.name:
                if not self.gsis[key]["gsi"].get(value):
                    self.gsis[key]["gsi"][value] = {
                        "documents": {
                            "uuid": defaultdict(list),
                            "count": defaultdict(int),
                        }
                    }
                self.gsis[key]["gsi"][value]["length"] = len(value)
                self.gsis[key]["gsi"][value]["documents"]["uuid"][
                    document["uuid"]
                ].append(0)
                self.gsis[key]["gsi"][value]["documents"]["count"][
                    document["uuid"]
                ] += 1
            elif self.gsis[key]["strategy"] == GSI_INDEX_STRATEGIES.PREFIX.name:
                if not self.gsis[key]["gsi"].get(value[:20]):
                    self.gsis[key]["gsi"][value[:20]] = {
                        "documents": {
                            "uuid": defaultdict(list),
                            "count": defaultdict(int),
                        }
                    }

                self.gsis[key]["gsi"][value]["documents"]["length"] = len(value)
                self.gsis[key]["gsi"][value[:20]]["documents"]["uuid"][
                    document["uuid"]
                ].append(0)
                self.gsis[key]["gsi"][value[:20]]["documents"]["count"][
                    document["uuid"]
                ] += 1
            elif self.gsis[key]["strategy"] == GSI_INDEX_STRATEGIES.FLAT.name:
                if isinstance(value, list):
                    for inner in value:
                        if not self.gsis[key]["gsi"].get(inner):
                            self.gsis[key]["gsi"][inner] = []

                        self.gsis[key]["gsi"][inner].append(document["uuid"])
                else:
                    if not self.gsis[key]["gsi"].get(value):
                        self.gsis[key]["gsi"][value] = []

                    self.gsis[key]["gsi"][value].append(document["uuid"])
            elif (
                self.gsis[key]["strategy"] == GSI_INDEX_STRATEGIES.NUMERIC.name
                or self.gsis[key]["strategy"] == GSI_INDEX_STRATEGIES.DATE.name
            ):
                if not self.gsis[key]["gsi"].get(value):
                    self.gsis[key]["gsi"][value] = []

                self.gsis[key]["gsi"][value].append(document["uuid"])
            elif self.gsis[key]["strategy"] == GSI_INDEX_STRATEGIES.TRIGRAM_CODE.name:
                code_lines = value.split("\n")
                total_lines = len(code_lines)
                file_name = document.get("file_name")

                for line_num, line in enumerate(code_lines):
                    trigrams = get_trigrams(line)

                    if len(trigrams) == 0:
                        self.gsis[key]["id2line"][f"{file_name}:{line_num}"] = line

                    for trigram in trigrams:
                        if not self.gsis[key]["gsi"].get(trigram):
                            self.gsis[key]["gsi"][trigram] = []

                        self.gsis[key]["gsi"][trigram].append(
                            (file_name, line_num, document["uuid"])
                        )
                        self.gsis[key]["id2line"][f"{file_name}:{line_num}"] = line
                self.gsis[key]["doc_lengths"][file_name] = total_lines
            elif self.gsis[key]["strategy"] == GSI_INDEX_STRATEGIES.NOT_INDEXABLE.name:
                pass
            else:
                raise ValueError(
                    "Invalid GSI strategy. Must be one of: "
                    + ", ".join([strategy.name for strategy in GSI_INDEX_STRATEGIES])
                    + "."
                )

        if write_to_journal:
            with open(INDEX_DATA_FILE, "a") as f:
                f.write(json.dumps(document) + "\n")

            os.remove(JOURNAL_FILE)

        return document

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

        with open(JOURNAL_FILE, "a") as f:
            op_record = {"operation": "remove", "document": {"uuid": uuid}}
            f.write(json.dumps(op_record) + "\n")

        del self.global_index[uuid]

        with open(JOURNAL_FILE, "w") as f:
            f.write("")

    @lru_cache()
    def spelling_correction(self, query: str) -> str:
        """
        Accepts a query and returns a spelling corrected query.
        """

        if query in self.word_counts and self.word_counts[query] > 1:
            return query
        
        # generate all possible segmentations
        # like "coffeeis" -> "coffee is"

        all_possibilities = {}

        segmentations = {}

        for i in range(1, len(query)):
            left_word = query[:i]
            right_word = query[i:]

            if left_word in self.word_counts and right_word in self.word_counts:
                segmentations[left_word + " " + right_word] = self.word_counts[left_word] + self.word_counts[right_word]

        if segmentations:
            all_possibilities.update(segmentations)

        fuzzy_suggestions = self._turn_query_into_fuzzy_options(query)
        
        fuzzy_suggestions = [word for word in fuzzy_suggestions if word in self.word_counts]

        if fuzzy_suggestions:
            all_possibilities.update({word: self.word_counts[word] for word in fuzzy_suggestions})

        fuzzy_suggestions_2_edits = []

        for word in fuzzy_suggestions:
            fuzzy_suggestions_2_edits.extend(self._turn_query_into_fuzzy_options(word))

        fuzzy_suggestions_2_edits = [word for word in fuzzy_suggestions_2_edits if word in self.word_counts]

        for word in fuzzy_suggestions_2_edits:
            if word in self.word_counts:
                # make these less exponentially weighted
                all_possibilities[word] = math.exp(-1) * self.word_counts[word]

        if len(all_possibilities) == 0:
            return query
        
        return max(all_possibilities, key=all_possibilities.get)

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

        documents_in_indexed_by = [
            item.get(index_by) for item in self.global_index.values()
        ]

        if strategy == GSI_INDEX_STRATEGIES.INFER:
            if all([isinstance(item, list) for item in documents_in_indexed_by]):
                strategy = GSI_INDEX_STRATEGIES.FLAT
            # if bool, set to flat
            elif all([isinstance(item, bool) for item in documents_in_indexed_by]):
                strategy = GSI_INDEX_STRATEGIES.FLAT
            elif all(
                [
                    isinstance(item, int) or (isinstance(item, str) and item.isdigit())
                    for item in documents_in_indexed_by[:25]
                ]
            ):
                strategy = GSI_INDEX_STRATEGIES.NUMERIC
            elif all([isinstance(item, float) for item in documents_in_indexed_by]):
                strategy = GSI_INDEX_STRATEGIES.NUMERIC
            elif all(
                [
                    isinstance(item, str) and len(item.split("-")) == 3
                    for item in documents_in_indexed_by[:25]
                ]
            ):
                strategy = GSI_INDEX_STRATEGIES.DATE
            # if word count < 10, use prefix
            # elif isinstance(index_by, str) and sum([len(item.split(" ")) for item in documents_in_indexed_by]) / len(documents_in_indexed_by) < 10:
            #     strategy = GSI_INDEX_STRATEGIES.PREFIX
            # if average contains more than one word, use contains
            elif (
                isinstance(documents_in_indexed_by[0], str)
                and sum([len(item.split(" ")) for item in documents_in_indexed_by]) / len(documents_in_indexed_by)
            ):
                strategy = GSI_INDEX_STRATEGIES.CONTAINS
            # if strings are less than 10 letters, use prefix
            elif (
                isinstance(documents_in_indexed_by[0], str)
                and sum([len(item) for item in documents_in_indexed_by]) / len(documents_in_indexed_by)
                < 10
            ):
                strategy = GSI_INDEX_STRATEGIES.PREFIX
            elif index_by == "file_name":
                strategy = GSI_INDEX_STRATEGIES.TRIGRAM_CODE
            elif all([isinstance(item, dict) for item in documents_in_indexed_by]):
                strategy = GSI_INDEX_STRATEGIES.NOT_INDEXABLE
            else:
                print(documents_in_indexed_by)
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
        elif (
            strategy == GSI_INDEX_STRATEGIES.NUMERIC
            or strategy == GSI_INDEX_STRATEGIES.DATE
        ):
            gsi = OOBTree()

            for item in self.global_index.values():
                if gsi.get(item.get(index_by)) is None:
                    gsi[item.get(index_by)] = []

                if isinstance(item.get(index_by), list):
                    for inner in item.get(index_by):
                        gsi[inner].append(item.get("uuid"))

                gsi[item.get(index_by)].append(item.get("uuid"))
        elif strategy == GSI_INDEX_STRATEGIES.TRIGRAM_CODE:
            gsi = {}
        elif strategy == GSI_INDEX_STRATEGIES.NOT_INDEXABLE:
            gsi = {}
        else:
            raise ValueError(
                "Invalid GSI strategy. Must be one of: "
                + ", ".join([strategy.name for strategy in GSI_INDEX_STRATEGIES])
                + "."
            )

        self.gsis[index_by] = {"gsi": gsi, "strategy": strategy.name}

        if strategy == GSI_INDEX_STRATEGIES.TRIGRAM_CODE:
            self.gsis[index_by]["id2line"] = {}
            self.gsis[index_by]["doc_lengths"] = {}

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

            results = [
                self.global_index.get(doc_id)
                for doc_id in results
                if doc_id in self.global_index
            ]

        end_time = time.time()
        
        if query.get("sort_by") is None:
            query["sort_by"] = "_score"

        results_sort_by = query["sort_by"]

        if query.get("sort_order") == "asc":
            results = sorted(results, key=lambda x: x[results_sort_by])
        else:
            results = sorted(
                results, key=lambda x: x[results_sort_by], reverse=True
            )

        if query.get("query_score"):
            tree = parse_script_score(query["query_score"])

            for document in results:
                if document.get("_score") is None:
                    document["_score"] = 1

                transformer = JameSQLScriptTransformer(document)

                document["_score"] = transformer.transform(tree)

                print(document["_score"])
            results = sorted(results, key=lambda x: x.get("_score", 1), reverse=True)

        if query.get("skip"):
            results = results[int(query["skip"]) :]

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

        # reset highlights and scores
        # this is done because highlights and scores are adjusted for each query
        # in the long term, this should be replaced with logic that
        # recursively returns scores and highlights in a `metadata`-type field
        # in _recursively_parse_query

        response = deepcopy(result)

        for doc in results:
            doc["_context"] = []
            doc["_score"] = 0

        return response

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

                # uuids = [set(value.get("uuid") for value in value) for value in values]
                uuids = values

                if first_key == "not":
                    uuid_intersection = set(self.global_index.keys()).difference(
                        method(*uuids)
                    )
                else:
                    uuid_intersection = method(*uuids)

                # new_values = defaultdict(int)

                # for value in values:
                #     for v in value:
                #         if v.get("uuid") in uuid_intersection:
                #             new_values[v.get("uuid")] += v.get("_score", 1)

                acc = set.union(acc, uuid_intersection)
            elif first_key in self.SELF_METHODS:
                func = self.SELF_METHODS[first_key]

                acc = set.union(getattr(self, func)(query_tree[first_key]))
            else:
                results, result_uuids = self._run(
                    {"query": query_tree}, list(query_tree.keys())[0]
                )
                acc = set.union(acc, result_uuids)

        return acc

    def _turn_query_into_fuzzy_options(self, query_term: str) -> dict:
        query_term = str(query_term)

        query_terms = []

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

        # add letter to end of query
        query_terms.extend([query_term + c for c in string.ascii_lowercase])

        # remove a letter from every possible position
        query_terms.extend(
            [query_term[:i] + query_term[i + 1 :] for i in range(len(query_term))]
        )

        # swap every letter with the next letter
        query_terms.extend(
            [
                query_term[:i] + query_term[i + 1] + query_term[i] + query_term[i + 2 :]
                for i in range(len(query_term) - 1)
            ]
        )

        return query_terms

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

        query_type = list(
            [
                key
                for key in query["query"][query_field].keys()
                if key not in RESERVED_QUERY_TERMS
            ]
        )[0]

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
            final_query_terms = []

            for query_term in query_terms:
                final_query_terms.extend(self._turn_query_into_fuzzy_options(query_term))

            query_terms = final_query_terms

        if query_type == "wildcard":
            # replace * with every possible character
            query_terms = [query_term.replace("*", c) for c in string.ascii_lowercase]

        for query_term in query_terms:
            if gsi_type not in (
                GSI_INDEX_STRATEGIES.FLAT,
                GSI_INDEX_STRATEGIES.NUMERIC,
                GSI_INDEX_STRATEGIES.DATE,
            ):
                if gsi_type == GSI_INDEX_STRATEGIES.TRIGRAM_CODE:
                    trigrams = get_trigrams(query_term)

                    contexts = []

                    candidates = set(self.gsis[query_field]["gsi"].get(trigrams[0], []))

                    for trigram in trigrams:
                        candidates = candidates.intersection(
                            set(self.gsis[query_field]["gsi"].get(trigram, []))
                        )

                    # candidate[2] is the document uuid
                    matching_documents.extend(
                        [candidate[2] for candidate in candidates]
                    )

                    # get line numbers
                    for candidate in candidates:
                        contexts.append(
                            {
                                "line": candidate[1],
                                "code": self.gsis[query_field]["id2line"][
                                    f"{candidate[0]}:{candidate[1]}"
                                ],
                            }
                        )
                        matching_highlights[candidate[2]] = contexts
                if (
                    query_type == "starts_with"
                    and gsi_type == GSI_INDEX_STRATEGIES.PREFIX
                ):
                    matches = gsi.keys(prefix=query_term)
                    matching_documents.extend([gsi[match] for match in matches])
                elif query_type == "starts_with":
                    for document in self.global_index.values():
                        if document.get(query_field).startswith(query_term):
                            matching_documents.append(document["uuid"])
                if (
                    query_type in {"contains", "wildcard"}
                    and gsi_type == GSI_INDEX_STRATEGIES.CONTAINS
                ):
                    if enforce_strict:
                        words = query_term.split()

                        all_matches = {}
                        all_match_positions = {}

                        if len(words) == 1:
                            all_matches[words[0]] = list(
                                set(
                                    gsi.get(words[0], {})
                                    .get("documents", {})
                                    .get("uuid", [])
                                )
                            )
                            all_match_positions[words[0]] = (
                                gsi.get(words[0], {})
                                .get("documents", {})
                                .get("uuid", {})
                            )

                        for word_index in range(0, len(words)):
                            current_word = words[word_index]
                            if word_index + 1 == len(words):
                                next_word = current_word
                            else:
                                next_word = words[word_index + 1]

                            # break if on last word
                            if word_index + 1 == len(words):
                                break

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
                                        position + 1 in next_word_positions[doc_id]
                                    ) or len(words) == 1:
                                        matches_for_this_word.append(doc_id)
                                        match_positions[doc_id].append(position)
                                        break

                            if word_index + 1 == len(words) and len(words) == 1:
                                all_matches[current_word] = matches_for_this_word
                                all_match_positions[current_word] = match_positions
                            else:
                                all_matches[
                                    current_word + " " + next_word
                                ] = matches_for_this_word
                                all_match_positions[
                                    current_word + " " + next_word
                                ] = match_positions

                        if all_matches:
                            matching_documents.extend(
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
                                            end = min(
                                                position + highlight_stride,
                                                len(
                                                    self.global_index[doc_id][
                                                        highlight_terms
                                                    ].split()
                                                ),
                                            )
                                            matches_with_context[doc_id].append(
                                                " ".join(
                                                    self.global_index[doc_id][
                                                        highlight_terms
                                                    ].split()[start:end]
                                                )
                                            )

                                matching_highlights.update(matches_with_context)
                    else:
                        for word in query_term.split(" "):
                            if gsi.get(word) is None:
                                continue

                            uuid_of_documents = gsi[word]["documents"]["uuid"]
                            if len(matching_documents) == 0:
                                matching_documents.extend(uuid_of_documents)
                            else:
                                matching_documents.extend(
                                    list(
                                        set(matching_documents).intersection(
                                            set(uuid_of_documents)
                                        )
                                    )
                                )
                            
                            matching_documents_count = len(uuid_of_documents)
                            index_length =  len(self.global_index)
                            for uuid_of_document in uuid_of_documents:
                                document_term_frequency = (
                                    gsi[word]["documents"]["count"][uuid_of_document]
                                    / self.doc_lengths[uuid_of_document][query_field]
                                )

                                inverse_document_frequency = math.log(
                                    index_length / 1 + matching_documents_count
                                )

                                tf_idf = (
                                    document_term_frequency * inverse_document_frequency
                                )

                                matching_document_scores.update(
                                    {uuid_of_document: tf_idf}
                                )

                elif query_type == "equals":
                    matching_documents.extend(
                        [
                            doc_uuid
                            for doc_uuid in gsi.get(query_term, {})
                            .get("documents", {})
                            .get("uuid", [])
                        ]
                    )
                elif (
                    query_type == "contains" and gsi_type == GSI_INDEX_STRATEGIES.PREFIX
                ):
                    results = [
                        list(doc["documents"]["uuid"].keys())
                        for key, doc in gsi.items()
                        if pybmoore.search(query_term, key)
                    ]
                    # flatten
                    matching_documents.extend([item for sublist in results for item in sublist])
            elif query_type == "equals":
                matching_documents.extend([doc_uuid for doc_uuid in gsi.get(query_term, [])])
            elif query_type == "range":
                lower_bound, upper_bound = query_term
                results = gsi.values(min=lower_bound, max=upper_bound)
                for result in results:
                    matching_documents.extend(result)
            elif query_type in QUERY_TYPE_COMPARISON_METHODS and gsi_type in {
                GSI_INDEX_STRATEGIES.DATE,
                GSI_INDEX_STRATEGIES.NUMERIC,
            }:
                result = QUERY_TYPE_COMPARISON_METHODS[query_type](query_term, gsi)
                if isinstance(result[0], list):
                    for item in result:
                        matching_documents.extend(item)
                else:
                    matching_documents.extend(result)

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
                            
        for doc in matching_documents:
            doc = self.global_index.get(doc)
            if doc is None:
                continue

            doc["_score"] = (matching_document_scores.get(doc["uuid"], 0) * float(
                boost_factor
            )) + doc.get("_score", 0)

            if doc.get("_context") is None:
                doc["_context"] = []

            doc["_context"] = matching_highlights.get(doc["uuid"], {})

        return {}, matching_documents
