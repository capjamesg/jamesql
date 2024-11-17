import hashlib
import json
import math
import os
import string
import time
import uuid
from collections import defaultdict
from copy import deepcopy
from enum import Enum
from functools import lru_cache
from typing import Dict, List
from sortedcontainers import SortedDict
import threading

from operator import itemgetter
import orjson
import pybmoore
import pygtrie
from BTrees.OOBTree import OOBTree
from lark import Lark
from nltk.corpus import stopwords
from nltk import download

from jamesql.rewriter import grammar as rewriter_grammar
from jamesql.rewriter import string_query_to_jamesql

from .script_lang import JameSQLScriptTransformer, grammar

download("stopwords")

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

    def __init__(self, match_limit_for_large_result_pages = 1000) -> None:
        self.global_index = {}
        self.uuids_to_position_in_global_index = {}
        self.gsis = {}
        self.last_transaction_after_recovery = None
        self.autosuggest_index = {}
        self.doc_lengths = defaultdict(dict)
        self.document_length_words = defaultdict(int)
        self.autosuggest_on = None
        self.word_counts = defaultdict(int)
        self.string_query_parser = Lark(
            rewriter_grammar,
            parser="earley",
            propagate_positions=False,
            maybe_placeholders=False,
        )
        self.match_limit_for_large_result_pages = match_limit_for_large_result_pages
        self.tf = defaultdict(dict)
        self.idf = {}
        self.tf_idf = defaultdict(lambda: SortedDict())
        self.bm25 = defaultdict(lambda: SortedDict())
        self.reverse_tf_idf = defaultdict(lambda: SortedDict())
        self.write_lock = threading.Lock()

        self.k1 = 1.5
        self.b = 0.75

        self.enable_experimental_bm25_ranker = False

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

        total_documents = len(documents)
        document_frequencies = defaultdict(int)

        for document in documents:
            word_count = defaultdict(int)  # Track word counts in this document
            words = document[index_by].split()  # Tokenize the document

            unique_words_in_document = set()

            index[document[index_by]]["documents"]["uuid"][document["uuid"]].append(0)

            for pos, word in enumerate(document[index_by].split()):
                word_lower = word.lower()

                # Update index
                index[word_lower]["count"] += 1
                index[word_lower]["documents"]["uuid"][document["uuid"]].append(pos)
                index[word_lower]["documents"]["count"][document["uuid"]] += 1

                self.word_counts[word_lower] += 1
                self.word_counts[word] += 1
                word_count[word_lower] += 1

                # Track first occurrence of the word in the document for document frequencies
                if word_lower not in unique_words_in_document:
                    document_frequencies[word_lower] += 1
                    unique_words_in_document.add(word_lower)

            # Compute term frequency (TF) for each word in the document
            total_words_in_document = len(words)
            for word, count in word_count.items():
                self.tf[document["uuid"]][word] = count # / total_words_in_document

        # Compute inverse document frequency (IDF) for each word in the corpus
        for word, doc_count in document_frequencies.items():
            self.idf[word] =math.log((total_documents - doc_count + 0.5) / (doc_count + 0.5) + 1)

        # Compute TF-IDF for each document
        for document in documents:
            for word, tf_value in self.tf[document["uuid"]].items():
                score = tf_value * self.idf[word]
                if self.tf_idf[word].get(score):
                    self.tf_idf[word][score].append(document["uuid"])
                else:
                    self.tf_idf[word][score] = [document["uuid"]]
                    
            for w in document[index_by].split(" "):
                if self.reverse_tf_idf[w].get(index_by) is None:
                    self.reverse_tf_idf[w][index_by] = {}

                self.reverse_tf_idf[w][index_by][document["uuid"]] = score

                if self.reverse_tf_idf[w.lower()].get(index_by) is None:
                    self.reverse_tf_idf[w.lower()][index_by] = {}

                self.reverse_tf_idf[w.lower()][index_by][document["uuid"]] = score

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
        self,
        query: str,
        query_keys: list = [],
        boosts={},
        fuzzy=False,
        highlight_keys=[],
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
            highlight_keys=highlight_keys,
        )

        return query, spelling_substitutions

    def string_query_search(
        self,
        query: str,
        query_keys: list = [],
        start: int = 0,
        fuzzy=False,
        highlight_keys=[],
    ) -> List[str]:
        """
        Accepts a string query and returns a list of matching documents.
        """

        if query == "":
            return {"documents": []}

        query, spelling_substitutions = self._compute_string_query(
            query, query_keys, fuzzy=fuzzy, highlight_keys=highlight_keys
        )

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

        with self.write_lock:
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
                    self.document_length_words[document["uuid"]] += len(value.split(" "))

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
        Accepts a UUID and a document and updates the document associated with that key.
        """
        
        with self.write_lock:
            if uuid not in self.uuids_to_position_in_global_index:
                return {"error": "Document not found"}

            position_in_global_index = self.uuids_to_position_in_global_index[uuid]

            self.global_index[position_in_global_index] = document

            return document

    def remove(self, uuid: str) -> None:
        """
        Accepts a UUID and removes the document associated with that key.
        """

        with self.write_lock:
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
                segmentations[left_word + " " + right_word] = (
                    self.word_counts[left_word] + self.word_counts[right_word]
                )

        if segmentations:
            all_possibilities.update(segmentations)

        fuzzy_suggestions = self._turn_query_into_fuzzy_options(query)

        fuzzy_suggestions = [
            word for word in fuzzy_suggestions if word in self.word_counts
        ]

        if fuzzy_suggestions:
            all_possibilities.update(
                {word: self.word_counts[word] for word in fuzzy_suggestions}
            )

        fuzzy_suggestions_2_edits = []

        for word in fuzzy_suggestions:
            fuzzy_suggestions_2_edits.extend(self._turn_query_into_fuzzy_options(word))

        fuzzy_suggestions_2_edits = [
            word for word in fuzzy_suggestions_2_edits if word in self.word_counts
        ]

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
            elif isinstance(documents_in_indexed_by[0], str) and sum(
                [len(item.split(" ")) for item in documents_in_indexed_by]
            ) / len(documents_in_indexed_by):
                strategy = GSI_INDEX_STRATEGIES.CONTAINS
            # if strings are less than 10 letters, use prefix
            elif (
                isinstance(documents_in_indexed_by[0], str)
                and sum([len(item) for item in documents_in_indexed_by])
                / len(documents_in_indexed_by)
                < 10
            ):
                strategy = GSI_INDEX_STRATEGIES.PREFIX
            elif index_by == "file_name":
                strategy = GSI_INDEX_STRATEGIES.TRIGRAM_CODE
            elif all([isinstance(item, dict) for item in documents_in_indexed_by]):
                strategy = GSI_INDEX_STRATEGIES.NOT_INDEXABLE
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
        with self.write_lock:
            start_time = time.time()

            results_limit = query.get("limit", 10)

            metadata = {}

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

                metadata, result_ids = self._recursively_parse_query(query["query"])

                results = [self.global_index.get(doc_id) for doc_id in result_ids if doc_id in self.global_index]

                results = orjson.loads(orjson.dumps(results))

                for r in results:
                    r["_score"] = 0
                    if r["uuid"] in metadata.get("scores", {}):
                        r["_score"] = metadata["scores"][r["uuid"]]
                    if r["uuid"] in metadata.get("highlights", {}):
                        r["_context"] = metadata["highlights"][r["uuid"]]

            end_time = time.time()

            if query.get("sort_by") is None:
                query["sort_by"] = "_score"

            results_sort_by = query["sort_by"]

            if query.get("sort_order") == "asc":
                results = sorted(
                    results, key=itemgetter(results_sort_by), reverse=False
                )
            else:
                results = sorted(
                    results, key=itemgetter(results_sort_by), reverse=True
                )

            if self.enable_experimental_bm25_ranker:
                # TODO: Make sure this code can process boosts.

                self.avgdl = sum(self.document_length_words.values()) / len(self.document_length_words)

                if query["query"].get("or"):
                    term_queries = [term.get("or")[0][list(term.get("or")[0].keys())[0]]["contains"] for term in query["query"]["or"]]
                else:
                    term_queries = [term.get("and")[0][list(term.get("and")[0].keys())[0]]["contains"] for term in query["query"]["and"]]
                    
                fields = [list(term.get("or")[0].keys()) for term in query["query"]["or"]]
                fields = [field for sublist in fields for field in sublist]

                for doc in results:
                    word_pos = defaultdict(list)
                    for i, word in enumerate(doc["post"].lower().split(" ")):
                        word_pos[word].append(i)
                    word_pos_title = defaultdict(list)
                    for i, word in enumerate(doc["title"].lower().split(" ")):
                        word_pos_title[word].append(i)

                    doc["_score"] = 0

                    for term in term_queries:
                        tf = self.tf.get(doc["uuid"], {}).get(term, 0)
                        idf = self.idf.get(term, 0)

                        # bm25
                        term_score = (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * (self.document_length_words[doc["uuid"]] / self.avgdl)))
                        term_score *= idf

                        doc["_score"] += term_score

                    for field in fields:
                        # give a boost if all terms are within 1 word of each other
                        # so a doc with "all too well" would do btter than "all well too"
                        if all([word_pos.get(w) for w in term_queries]):
                            first_word_pos = set(word_pos[query["query"]["or"][0]["or"][0][field]["contains"]])
                            total = first_word_pos.copy()
                            for i, term in enumerate(term_queries):
                                positions = set([x - i for x in word_pos[term]])
                                first_word_pos = first_word_pos.intersection(positions)
                                total = total.union(positions)

                            if first_word_pos:
                                doc["_score"] += (len(first_word_pos) + 1) * len(total)

                        if field != "title_lower":
                            # TODO: Run only if query len > 1 word
                            if all([word_pos.get(w) for w in term_queries]):
                                first_word_pos = set(word_pos_title[query["query"]["or"][0]["or"][0][field]["contains"]])
                                for i, term in enumerate(term_queries):
                                    positions = set([x - i for x in word_pos_title[term]])
                                    first_word_pos = first_word_pos.intersection(positions)

                                if first_word_pos:
                                    doc["_score"] *= 2 + len(first_word_pos)

                    if "title_lower" in fields:
                        # TODO: Make this more dynamic
                        doc["_score"] *= len([term.get("or")[0].get("title_lower", {}).get("contains") in doc["title"].lower() for term in query["query"]["or"] if str(term.get("or")[0].get("title_lower", {}).get("contains")).lower() in doc["title"].lower()]) + 1

            # sort by doc score
            results = sorted(
                results, key=lambda x: x.get("_score", 0), reverse=True
            )

            if query.get("query_score"):
                tree = parse_script_score(query["query_score"])

                for document in results:
                    if document.get("_score") is None:
                        document["_score"] = 0

                    transformer = JameSQLScriptTransformer(document)

                    document["_score"] = transformer.transform(tree)

                results = sorted(results, key=lambda x: x.get("_score", 0), reverse=True)

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

        first_key = list(query_tree.keys())[0]

        if first_key in RESERVED_QUERY_TERMS:
            return {}, set()

        if first_key in KEYW0RDS:
            values = []
            metadata = []

            method = METHODS[first_key]

            if isinstance(query_tree[first_key], dict):
                for key, query in query_tree[first_key].items():
                    query_metadata, query_values = self._recursively_parse_query({key: query})
                    metadata.append(query_metadata)
                    values.append(query_values)
            else:
                for query in query_tree[first_key]:
                    query_metadata, query_values = self._recursively_parse_query(query)
                    metadata.append(query_metadata)
                    values.append(query_values)

            # uuids = [set(value.get("uuid") for value in value) for value in values]
            uuids = values

            if first_key == "not":
                uuid_intersection = set(self.global_index.keys()).difference(
                    method(*uuids)
                )
            else:
                uuid_intersection = method(*uuids)

            acc = set.union(acc, uuid_intersection)

            # for each item in metadata, update the scores and highlights
            final_highlights = defaultdict(list)
            final_scores = defaultdict(float)

            for item in metadata:
                for key in list(acc):
                    highlights = item.get("highlights", {}).get(key)
                    if highlights:
                        final_highlights[key].extend(highlights)

                    score_record = item.get("scores", {}).get(key)
                    if score_record:
                        final_scores[key] += score_record

            scores = {
                "scores": final_scores,
                "highlights": final_highlights,
            }

        elif first_key in self.SELF_METHODS:
            func = self.SELF_METHODS[first_key]

            acc = set.union(getattr(self, func)(query_tree[first_key]))
        else:
            scores, result_uuids = self._run(
                {"query": query_tree}, first_key
            )
            acc = set.union(acc, result_uuids)

        return scores, acc

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

        query_term = str(query["query"][query_field][query_type])

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
                final_query_terms.extend(
                    self._turn_query_into_fuzzy_options(query_term)
                )

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
                        for word in str(query_term).split(" "):
                            word = word.lower()
                            
                            if gsi.get(word) is None:
                                continue

                            results = self.reverse_tf_idf[word].get(query_field, {})

                            matching_document_scores = results
                            matching_documents.extend(results.keys())

                elif query_type == "equals":
                    matching_documents.extend(
                        gsi.get(query_term, {}).get("documents", {}).get("uuid", [])
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
                    matching_documents.extend(
                        [item for sublist in results for item in sublist]
                    )
            elif query_type == "equals":
                matching_documents.extend(
                    [doc_uuid for doc_uuid in gsi.get(query_term, [])]
                )
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

        advanced_query_information = {
            "scores": defaultdict(dict),
            "highlights": defaultdict(dict),
        }
        
        for doc in matching_documents[:self.match_limit_for_large_result_pages]:
            advanced_query_information["scores"][doc] = matching_document_scores.get(doc, 0) * float(
                boost_factor
            )

            if matching_highlights:
                advanced_query_information["highlights"][doc] = matching_highlights.get(doc, {})

        return advanced_query_information, matching_documents[:self.match_limit_for_large_result_pages]
