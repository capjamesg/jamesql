from __future__ import annotations

from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, model_validator

VALID_QUERY_TYPES = ["contains", "equals", "starts_with"]
VALID_OPERATOR_QUERY_TYPES = ["or", "and"]


class QueryType(str, Enum):
    contains = "contains"
    equals = "equals"
    starts_with = "starts_with"


class AndOperatorQueryType(str, Enum):
    and_ = "and"


class OrOperatorQueryType(str, Enum):
    or_ = "or"


class QueryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contains: Optional[str] = None
    equals: Optional[str] = None
    starts_with: Optional[str] = None

    strict: Optional[bool] = False
    boost: Optional[int] = 1

    # ensure that only one of the query types is used
    @model_validator(mode="after")
    def validate_query_type(cls, v):
        query_types = [v.contains, v.equals, v.starts_with]

        if len([qt for qt in query_types if qt]) > 1:
            raise ValueError("Only one query type can be used")

        return v


class RootQuery(BaseModel):
    query: (
        Dict[AndOperatorQueryType, Dict[str, QueryItem]]
        | Dict[OrOperatorQueryType, Dict[str, QueryItem]]
        | Dict[str, QueryItem]
    )
    limit: Optional[int] = 10
    sort_by: Optional[str] = "score"


query = {
    "query": {
        "or": {
            "post": {"contains": "taylor swift", "strict": False, "boost": 1},
            "title": {"contains": "my desk", "strict": True, "boost": 25},
        }
    },
    "limit": 4,
    "sort_by": "score",
}

# validate query
print(RootQuery(**query))
