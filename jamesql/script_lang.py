import math

from lark import   Transformer

import datetime

grammar = """
start: query

query: decay | "(" query OPERATOR query ")" | logarithm | FLOAT | WORD
logarithm: LOGARITHM "(" query ")"
OPERATOR: "+" | "-" | "*" | "/"
LOGARITHM: "log"
decay: "decay" WORD

WORD: /[a-zA-Z0-9_]+/
FLOAT: /[0-9]+(\.[0-9]+)?/

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
        # + 0.1 removes the possibility of log(0)
        # which would return a math domain error
        return math.log(items[1] + 0.1)

    def start(self, items):
        return items[0]

    def decay(self, items):
        # decay by half for every 30 days
        # item is datetime.dateime object
        days_since_post = (datetime.datetime.now() - items[0]).days

        return 0.9 ** (days_since_post / 30)

    def WORD(self, items):
        if items.value.isdigit():
            return float(items.value)

        return self.document[items.value]

    def FLOAT(self, items):
        return float(items.value)

    def OPERATOR(self, items):
        return items.value
