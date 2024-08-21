import math

from lark import Transformer

grammar = """
start: query

query: "(" query OPERATOR query ")" | logarithm | WORD
logarithm: LOGARITHM query
OPERATOR: "+" | "-" | "*" | "/"
LOGARITHM: "log"

WORD: /[a-zA-Z0-9_]+/

%import common.WS
%ignore WS
"""

OPERATOR_METHODS = {
    "+": lambda x, y: x + y,
    "-": lambda x, y: x - y,
    "*": lambda x, y: x * y,
    "/": lambda x, y: x / y,
}


class JameSQLScriptTransformer(Transformer):
    def __init__(self, document):
        self.document = document

    def query(self, items):
        if len(items) == 1:
            return items[0]

        left = items[0]
        operator = items[1]
        right = items[2]

        operator_command = OPERATOR_METHODS[operator]

        return operator_command(left, right)

    def logarithm(self, items):
        return math.log(items[1])

    def start(self, items):
        return items[0]

    def WORD(self, items):
        if items.value.isdigit():
            return float(items.value)

        return self.document[items.value]

    def OPERATOR(self, items):
        return items.value
