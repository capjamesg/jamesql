import json
from contextlib import ExitStack as DoesNotRaise

import pytest
from lark import Lark
from pytest import raises

from jamesql import JameSQL
from jamesql.script_lang import JameSQLScriptTransformer, grammar


@pytest.fixture
def document_to_test():
    with open("tests/fixtures/documents.json") as f:
        documents = json.load(f)

    documents[0]["_score"] = 7.52
    documents[0]["listens"] = 2000

    return documents[0]


@pytest.fixture
def script_score_parser():
    return Lark(grammar)


@pytest.mark.parametrize(
    "query, result, raises_exception",
    [
        (
            "(_score + 1)",
            8.52,
            DoesNotRaise(),
        ),
        (
            "(_score * 2)",
            15.04,
            DoesNotRaise(),
        ),
        (
            "(_score / 2)",
            3.76,
            DoesNotRaise(),
        ),
        (
            "(_score - 2)",
            5.52,
            DoesNotRaise(),
        ),
        (
            "((_score + 1) * 2)",
            17.04,
            DoesNotRaise(),
        ),
        (
            "(((_score + 1) * 2) + 1)",
            18.04,
            DoesNotRaise(),
        ),
        (
            "(_score + _score)",
            15.04,
            DoesNotRaise(),
        ),
        (
            "((_score + _score) + _score)",
            22.56,
            DoesNotRaise(),
        ),
        (
            "(_score * listens)",
            15040,
            DoesNotRaise(),
        ),
        (
            "log (_score * listens)",
            9.618468597503831,
            DoesNotRaise(),
        ),
        (
            "log ((_score * listens) + 1)",
            9.618535084655214,
            DoesNotRaise(),
        ),
        (
            "_score + 1",
            0,
            raises(Exception),  # missing parenthesis
        ),
        (
            "(_score + 1",
            0,
            raises(Exception),  # missing closing parenthesis
        ),
        (
            "(_score + 1))",
            0,
            raises(Exception),  # additional closing parenthesis
        ),
    ],
)
def test_script_score(
    document_to_test, script_score_parser, query, result, raises_exception
):
    with raises_exception:
        tree = script_score_parser.parse(query)

        transformer = JameSQLScriptTransformer(document_to_test)

        assert transformer.transform(tree) == result
