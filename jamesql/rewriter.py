from lark import Lark, Transformer
import re

grammar = """
start: query

or_query: (query "OR" query)*
query: or_query | query_component
query_component: (negate_query | range_query | strict_search_query | word_query | field_query | comparison)+

strict_search_query: "'" MULTI_WORD "'"
comparison: TERM OPERATOR WORD
range_query: TERM "[" WORD "," WORD "]"
word_query: WORD 
field_query: TERM ":" "'" MULTI_WORD "'" | TERM ":" WORD | TERM ":" DOUBLE_QUOTE MULTI_WORD DOUBLE_QUOTE
negate_query: "-" (strict_search_query | word_query | field_query | comparison | range_query)
OPERATOR: ">" | "<" | ">=" | "<="
DOUBLE_QUOTE: "\\""
WORD: /[a-zA-Z0-9_.!?*-]+/
MULTI_WORD: /[a-zA-Z0-9 ]+/
TERM: /[a-zA-Z0-9_]+/

%import common.WS
%ignore WS
"""

OPERATOR_MAP = {
    ">": "greater_than",
    "<": "less_than",
    ">=": "greater_than_or_equal",
    "<=": "less_than_or_equal",
}

class QueryRewriter(Transformer):
    def __init__(self, default_strategies=None, query_keys=None):
        self.indexing_strategies = default_strategies
        self.query_keys = query_keys

    def get_query_strategy(self, key="", value=""):
        default = "contains"

        if isinstance(value, str) and "*" in value:
            return "wildcard"

        return default
    
    def or_query(self, items):
        return {"or": items}

    def negate_query(self, items):
        return {"not": items[0]}
    
    def query(self, items):
        return items[0]

    def query_component(self, items):
        return {"and": items}

    def start(self, items):
        items = {k: v for item in items for k, v in item.items()}

        return {"query": items, "limit": 10}
    
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

            if self.indexing_strategies.get(field) == "NUMERIC":
                continue

            result.append({field: {self.get_query_strategy(field, value): value}})

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
            return int(items.value)
        
        return items.value


def string_query_to_jamesql(query, query_keys, default_strategies={}):
    if query.strip() == "":
        return {"query": {}}
    
    # remove punctuation not in grammar
    query = re.sub(r"[^a-zA-Z0-9_.,!?*:\-'<>=\[\] ]", "", query)
    
    tree = Lark(grammar).parse(query)

    rewritten_query = QueryRewriter(
        default_strategies=default_strategies, query_keys=query_keys
    ).transform(tree)

    return rewritten_query