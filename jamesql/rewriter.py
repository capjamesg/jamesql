import re

from lark import   Lark, Transformer
from lark.visitors import Visitor, Interpreter

from .query_simplifier import simplifier

grammar = """
start: (query)+ sort_component?

or_query: (query ("OR ") query)*
query:  or_query | query_component
query_component: (negate_query | range_query | strict_search_query | word_query | field_query | comparison)+

sort_component: "sort:" TERM (ORDER)?
strict_search_query: "'" MULTI_WORD "'"
comparison: TERM OPERATOR WORD
range_query: TERM "[" WORD "," WORD "]"
word_query: WORD ("^" FLOAT)?
field_query: TERM ":" ("'" MULTI_WORD "'" | WORD | DOUBLE_QUOTE MULTI_WORD DOUBLE_QUOTE)
negate_query: "-" (strict_search_query | word_query | field_query | comparison | range_query)
OPERATOR: ">" | "<" | ">=" | "<="
DOUBLE_QUOTE: "\\""
WORD: /[a-zA-Z0-9_.!?*-]+/
FLOAT: /[0-9]+(\.[0-9]+)?/
MULTI_WORD: /[a-zA-Z0-9 ]+/
TERM: /[a-zA-Z0-9_]+/
ORDER: "ASC" | "DESC" | "asc" | "desc"

%import common.WS
%ignore WS
"""

OPERATOR_MAP = {
    ">": "greater_than",
    "<": "less_than",
    ">=": "greater_than_or_equal",
    "<=": "less_than_or_equal",
}


class QuerySimplifier(Transformer):
    def __init__(self):
        self.terms = []

    def WORD(self, items):
        return items.value
    
    def FLOAT(self, items):
        return items.value

    def word_query(self, items):
        self.terms.append("^".join(items))
        return "^".join(items)

    def field_query(self, items):
        return items[0]

    def query_component(self, items):
        return items[0]

    def query(self, items):
        return items[0]

    def or_query(self, items):
        self.terms.append([items[0], "OR", items[1]])
        return items[0]

    def start(self, items):
        return items[0]

    def field_query(self, items):
        self.terms.append(items[0] + ":" + "'" + items[1] + "'")
        return items[0] + ":" + "'" + items[1] + "'"

    def TERM(self, items):
        return items.value

    def negate_query(self, items):
        if items[0] in self.terms:
            self.terms.remove(items[0])

        self.terms.append(["NOT", items[0]])

        return items[0]
    
    def range_query(self, items):
        self.terms.append(items[0] + "[" + items[1] + "," + items[2] + "]")
        return items[0] + "[" + items[1] + "," + items[2] + "]"
    
    def comparison(self, items):
        self.terms.append(items[0] + items[1] + items[2])
        return items[0] + items[1] + items[2]
    
    def strict_search_query(self, items):
        self.terms.append("'" + items[0] + "'")
        return "'" + items[0] + "'"
    
    def MULTI_WORD(self, items):
        return items.value

class QueryRewriter(Transformer):
    def __init__(self, default_strategies=None, query_keys=None, boosts={}, fuzzy = False, highlight_keys = []):
        self.indexing_strategies = default_strategies
        self.query_keys = query_keys
        self.boosts = boosts
        self.fuzzy = fuzzy
        self.highlight_keys = highlight_keys

    def get_query_strategy(self, key="", value=""):
        default = "contains"

        if isinstance(value, str) and "*" in value:
            return "wildcard"

        return default

    def ORDER(self, items):
        return items.value
    
    def FLOAT(self, items):
        return items.value

    def or_query(self, items):
        return {"or": items}

    def negate_query(self, items):
        return {"not": items[0]}

    def query(self, items):
        return items[0]

    def query_component(self, items):
        # if all child keys are OR, return as OR
        all_are_or = False

        for item in items:
            if not isinstance(item, dict) or "or" not in item:
                all_are_or = False
                break

            all_are_or = True

        return {"and": items} if not all_are_or else {"or": items}

    def sort_component(self, items):
        result = {"sort_by": items[0]}

        if len(items) > 1:
            result["sort_order"] = items[1]

        return result

    def start(self, items):
        items = {k: v for item in items for k, v in item.items()}

        response = {"query": items, "limit": 10}

        if "sort_by" in items:
            response["sort_by"] = items["sort_by"]
            response["sort_order"] = items.get("sort_order", "asc")
            del items["sort_by"]
            del items["sort_order"]

        return response

    def OPERATOR(self, items):
        return items.value

    def strict_search_query(self, items):
        return {
            "or": {
                field: {
                    self.get_query_strategy(value=items[0]): items[0],
                    "strict": True,
                }
                for field in self.query_keys
                if self.indexing_strategies.get(field) not in {"NUMERIC", "DATE"}
            }
        }

    def TERM(self, items):
        return items.value

    def MULTI_WORD(self, items):
        return items.value

    def comparison(self, items):
        field = items[0]
        operator = items[1]
        value = items[2]

        if field not in self.query_keys:
            return {}

        return {field: {OPERATOR_MAP[operator]: value}}

    def range_query(self, items):
        field = items[0]
        start = items[1]
        end = items[2]

        if field not in self.query_keys:
            return {}

        return {field: {"range": [start, end]}}

    def word_query(self, items):
        result = []

        for key in self.query_keys:
            field = key
            value = items[0]
            if len(items) > 1:
                boost = items[1]
            else:
                boost = 1

            if self.indexing_strategies.get(field) == "NUMERIC":
                continue

            results = {
                field: {
                    self.get_query_strategy(field, value): value,
                }
            }

            if self.boosts.get(field):
                results[field]["boost"] = self.boosts.get(field, boost)

            if self.fuzzy:
                results[field]["fuzzy"] = self.fuzzy if self.get_query_strategy(field, value) == "contains" else False

            if field in self.highlight_keys:
                results[field]["highlight"] = True

            result.append(results)

        return {"or": result}

    def field_query(self, items):
        # remove negation
        field = items[0].lstrip("-")
        value = items[1]

        if field not in self.query_keys:
            return {}

        return {field: {self.get_query_strategy(field, value): value}}

    def WORD(self, items):
        if items.value.isdigit():
            return float(items.value)
        
        return items.value


def simplify_string_query(parser, query, correct_spelling_index = None):
    # remove punctuation not in grammar
    query = re.sub(r"[^a-zA-Z0-9_,!?^*:\-'<>=\[\] ]", "", query)

    tree = parser.parse(query)

    result = QuerySimplifier()
    result.transform(tree.copy())

    query = simplifier(result.terms)
    query = " ".join(query).strip()

    if len(query.strip()) == 0:
        return query, {}

    spelling_substitutions = {}

    if correct_spelling_index is not None:
        final_query = ""

        for word in query.split():
            # if word starts with -, skip
            # ' and " are used to indicate strict strings, so we need to skip words that start or end with the character
            if word.startswith("-") or correct_spelling_index.word_counts.get(word) or word.startswith("'") or word.startswith('"') or word.endswith("'") or word.endswith('"') or "*" in word:
                final_query += word + " "
                continue

            final_query += correct_spelling_index.spelling_correction(word) + " "

        spelling_substitutions = {
            word: correct_spelling_index.spelling_correction(word)
            for word in query.split()
            if word != correct_spelling_index.spelling_correction(word)
        }

        query = final_query.strip()

    return query, spelling_substitutions


def string_query_to_jamesql(parser, query, query_keys, default_strategies={}, boosts={}, fuzzy = False, correct_spelling_index = None, highlight_keys = False):
    query, spelling_substitutions = simplify_string_query(parser, query, correct_spelling_index)

    if query.strip() == "":
        return {"query": {}}, []

    tree = parser.parse(query)

    rewritten_query = QueryRewriter(
        default_strategies=default_strategies, query_keys=query_keys, boosts=boosts, fuzzy=fuzzy, highlight_keys=highlight_keys
    ).transform(tree)

    return rewritten_query, spelling_substitutions
