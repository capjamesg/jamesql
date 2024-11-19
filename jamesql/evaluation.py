import math


def dcg_at_k(k, ordered_query_judgements):
    """
    Calculate the Discounted Cumulative Gain at k for a given query.
    """
    scores = [list(i.values())[0] for i in ordered_query_judgements]
    k = min(k, len(scores))
    dcg = sum(
        scores[i] / math.log2(i + 2)  # i+2 to handle zero-based indexing
        for i in range(k)
    )
    return dcg


def ndcg_at_k(dcg, k, ordered_query_judgements):
    """
    Calculate the Normalized Discounted Cumulative Gain at k for a given query.
    """
    scores = [list(i.values())[0] for i in ordered_query_judgements]

    ideal_dcg = sum(
        sorted(scores, reverse=True)[i] / math.log2(i + 2) for i in range(k)
    )
    return dcg / ideal_dcg
